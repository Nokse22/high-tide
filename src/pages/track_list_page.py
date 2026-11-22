# track_list_page.py
#
# Copyright 2023 p0ryae
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import threading
from gettext import gettext as _

from gi.repository import GLib, GObject, Gtk

from ..lib import utils
from .page import Page

logger = logging.getLogger(__name__)


class TrackListPage(Page):
    """Base class for pages displaying a list of tracks with sorting and autoload"""

    __gtype_name__ = "TrackListPage"

    waits_for_favourites = True

    original_tracks = []
    current_sort = 0
    auto_load = None

    def _setup_ui(
        self, builder, title, subtitle, tracks, reload_function=None, hide_share=False
    ):
        self.append(builder.get_object("_main"))

        self.auto_load = builder.get_object("_auto_load")
        self.auto_load.source = getattr(self, "item", None)
        self.auto_load.set_scrolled_window(self.scrolled_window)
        self.auto_load.set_items(tracks)
        if reload_function:
            self.auto_load.set_function(reload_function)

        self.set_title(title)
        builder.get_object("_title_label").set_label(title)
        builder.get_object("_first_subtitle_label").set_label(subtitle)
        item = getattr(self, "item", None)
        num_tracks = getattr(item, "num_tracks", None) or len(tracks)
        total_duration = getattr(item, "duration", None) or sum(
            (t.duration or 0) for t in tracks
        )
        builder.get_object("_second_subtitle_label").set_label(
            _("{} tracks ({})").format(
                num_tracks,
                utils.pretty_duration(total_duration),
            )
        )

        play_btn = builder.get_object("_play_button")
        shuffle_btn = builder.get_object("_shuffle_button")
        in_my_collection_btn = builder.get_object("_in_my_collection_button")
        share_button = builder.get_object("_share_button")

        self.signals.extend(
            [
                (play_btn, play_btn.connect("clicked", self.on_play_button_clicked)),
                (
                    shuffle_btn,
                    shuffle_btn.connect("clicked", self.on_shuffle_button_clicked),
                ),
                (
                    in_my_collection_btn,
                    in_my_collection_btn.connect(
                        "clicked",
                        utils.on_in_to_my_collection_button_clicked,
                        getattr(self, "item", None),
                    ),
                ),
            ]
        )

        if hide_share:
            share_button.set_visible(False)
        else:
            self.signals.append(
                (
                    share_button,
                    share_button.connect(
                        "clicked",
                        lambda *_: utils.share_this(getattr(self, "item", None)),
                    ),
                )
            )

        utils.set_in_my_collection_button(
            in_my_collection_btn,
            bool(getattr(self, "item", None)) and utils.is_favourited(self.item),
        )

        image = builder.get_object("_image")
        if getattr(self, "item", None):
            threading.Thread(target=utils.add_image, args=(image, self.item)).start()

        sort_dropdown = builder.get_object("_sort_by_dropdown")
        sort_dropdown.connect("notify::selected", self.on_sort_changed)
        self.sort_dropdown = sort_dropdown

        self._setup_search(builder)

    def _setup_search(self, builder) -> None:
        """A search field above the list, hidden until the search button, Ctrl+F or
        typing on the page opens it; it filters the list by title, artist or album"""
        self.search_query = ""
        self.loading_all = False
        self.search_bar = builder.get_object("_search_bar")
        self.search_entry = builder.get_object("_search_entry")
        search_button = builder.get_object("_search_button")

        self.search_bar.connect_entry(self.search_entry)
        self.bindings.append(
            search_button.bind_property(
                "active",
                self.search_bar,
                "search-mode-enabled",
                GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE,
            )
        )

        def open_search(*_args):
            if utils.navigation_view.get_visible_page() is not self:
                return False  # another page's search
            self.search_bar.set_search_mode(True)
            self.search_entry.grab_focus()
            return True

        # Window-wide, so it works wherever the keyboard focus is
        shortcuts = Gtk.ShortcutController(scope=Gtk.ShortcutScope.GLOBAL)
        shortcuts.add_shortcut(
            Gtk.Shortcut.new(
                Gtk.ShortcutTrigger.parse_string("<Control>f"),
                Gtk.CallbackAction.new(open_search),
            )
        )
        self.add_controller(shortcuts)

        # Typing anywhere in the window opens the search of the page shown
        def capture(*_args):
            self.search_bar.set_key_capture_widget(self.get_root())

        def release(*_args):
            self.search_bar.set_key_capture_widget(None)

        if utils.navigation_view.get_visible_page() is self:
            capture()

        self.signals.extend(
            [
                (self, self.connect("shown", capture)),
                (self, self.connect("hiding", release)),
                (
                    self.search_entry,
                    self.search_entry.connect("search-changed", self._on_search_changed),
                ),
                (
                    self.search_bar,
                    self.search_bar.connect(
                        "notify::search-mode-enabled", self._on_search_mode_changed
                    ),
                ),
            ]
        )

    def _on_search_mode_changed(self, search_bar, _pspec) -> None:
        if search_bar.get_search_mode():
            # The field is at the top of the list
            self.scrolled_window.get_vadjustment().set_value(0)
        else:
            self.search_entry.set_text("")

    def _on_search_changed(self, entry) -> None:
        query = entry.get_text().strip().lower()
        if query == self.search_query:
            return
        self.search_query = query
        if query:
            self._load_all_tracks()
        self._show_tracks()

    def _load_all_tracks(self) -> None:
        """Fetch the songs not loaded yet (pages load 50 at first), so a search
        covers the whole album or playlist"""
        item = getattr(self, "item", None)
        total = getattr(item, "num_tracks", None) or 0
        if self.loading_all or not hasattr(item, "tracks"):
            return
        if len(self.original_tracks) >= total:
            return
        self.loading_all = True

        def fetch():
            tracks = list(self.original_tracks)
            try:
                while len(tracks) < total:
                    page = item.tracks(limit=100, offset=len(tracks))
                    if not page:
                        break
                    tracks.extend(page)
            except Exception:
                logger.exception("Error while loading all songs for the search")
            GLib.idle_add(done, tracks)

        def done(tracks):
            self.loading_all = False
            self.original_tracks = tracks
            if self.search_query:
                self._show_tracks()
            return False

        threading.Thread(target=fetch, daemon=True).start()

    def _matches(self, track) -> bool:
        query = self.search_query
        names = [getattr(track, "full_name", None) or track.name or ""]
        names += [a.name or "" for a in (track.artists or []) if a]
        if track.album:
            names.append(track.album.name or "")
        return any(query in name.lower() for name in names)

    def _show_tracks(self) -> None:
        """Show the list in the chosen order, filtered by the search if any"""
        if not self.search_query:
            self.current_sort = None  # shows the list again as sorted
            self.on_sort_changed(self.sort_dropdown, None)
            return
        valid_tracks = [t for t in self.original_tracks if t is not None]
        if self.current_sort == 5:
            ordered = list(reversed(valid_tracks))
        else:
            ordered = self._sorted(self.current_sort, valid_tracks)
        self.auto_load.set_function(None)
        self.auto_load.set_items([t for t in ordered if self._matches(t)])

    def on_sort_changed(self, dropdown, _pspec):
        selected = dropdown.get_selected()
        if selected == self.current_sort:
            return
        self.current_sort = selected
        if getattr(self, "search_query", ""):
            self._show_tracks()
            return

        valid_tracks = [t for t in self.original_tracks if t is not None]
        sorted_tracks = self._sorted(selected, valid_tracks)

        if selected == 0 and hasattr(self.item, "tracks"):
            # After a search loaded all songs: show the first ones again and load the
            # rest while scrolling, as when the page opened
            sorted_tracks = sorted_tracks[: self.auto_load.items_limit]
            self.auto_load.set_function(getattr(self.item, "tracks", None))
        elif selected == 5 and hasattr(self.item, "tracks"):
            self.auto_load.set_function(self.load_new_recently_added)
        else:
            self.auto_load.set_function(None)

        self.auto_load.set_items(sorted_tracks)

    def _sorted(self, selected, tracks):
        sort_map = {
            0: lambda tracks: tracks.copy(),
            1: lambda tracks: sorted(
                tracks, key=lambda t: t.name.lower() if t.name else ""
            ),
            2: lambda tracks: sorted(
                tracks,
                key=lambda t: (
                    t.artist.name.lower() if t.artist and t.artist.name else ""
                ),
            ),
            3: lambda tracks: sorted(
                tracks,
                key=lambda t: t.album.name.lower() if t.album and t.album.name else "",
            ),
            4: lambda tracks: sorted(tracks, key=lambda t: t.duration or 0),
            5: lambda tracks: self._recently_added(tracks),
        }
        return sort_map.get(selected, lambda t: t.copy())(tracks)

    def _recently_added(self, tracks):
        if not(hasattr(self.item, "num_tracks") and hasattr(self.item, "tracks")):
            return tracks.copy()

        num_tracks = self.item.num_tracks or len(tracks)
        offset = num_tracks - 50
        return reversed(self.item.tracks(limit=50, offset=offset))

    def load_new_recently_added(self, limit, offset):
        if not(hasattr(self.item, "num_tracks") and hasattr(self.item, "tracks")):
            return []

        num_tracks = self.item.num_tracks
        reversed_offset = max(0, num_tracks - offset - limit)
        reversed_limit = min(limit, num_tracks - offset)
        if reversed_limit <= 0:
            return []
        return list(reversed(self.item.tracks(limit=limit, offset=reversed_offset)))




