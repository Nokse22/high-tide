# single_type_page.py
#
# Copyright 2023 Nokse
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

from gi.repository import GLib, Gtk

from ..disconnectable_iface import IDisconnectable
from ..lib import utils
from ..widgets import HTAutoLoadWidget
from .page import Page

logger = logging.getLogger(__name__)


class HTFromFunctionPage(Page):
    """Used to display lists of albums/artists/mixes/playlists and tracks
    from a request function"""

    __gtype_name__ = "HTFromFunctionPage"

    def __init__(self, _title=""):
        IDisconnectable.__init__(self)
        super().__init__()

        self.set_title(_title)

        self.auto_load = HTAutoLoadWidget(
            margin_start=12, margin_end=12, margin_top=12, margin_bottom=12
        )
        self.auto_load.set_scrolled_window(self.scrolled_window)

        self.append(self.auto_load)

        self.function = None
        self.fixed_items = None

        self.search_bar = None
        self.search_query = ""
        self.search_page_size = 50
        # The whole list, once loaded for a search
        self.all_items = None
        self.loading_all = False
        # What was shown before the search, to show again when it's cleared
        # while the whole list isn't loaded
        self.items_before_search = []
        self.offset_before_search = 0
        # Play or shuffle waiting for the whole list (see enable_play)
        self._play_when_loaded = None

    def enable_play(self, source) -> None:
        """Add Play and Shuffle buttons, as on playlist pages (#237). They play
        the whole list (filtered by the search, if any) from source."""
        self.play_source = source
        box = Gtk.Box(spacing=12, margin_start=12, margin_end=12, margin_top=12)
        self.play_button = Gtk.Button(
            icon_name="media-playback-start-symbolic",
            tooltip_text=_("Play"),
            css_classes=["suggested-action", "pill"],
        )
        self.shuffle_button = Gtk.Button(
            icon_name="media-playlist-shuffle-symbolic",
            tooltip_text=_("Shuffle"),
            css_classes=["flat", "pill"],
        )
        box.append(self.play_button)
        box.append(self.shuffle_button)
        self.content.prepend(box)
        self.signals.extend(
            [
                (
                    self.play_button,
                    self.play_button.connect("clicked", lambda *_: self._play(False)),
                ),
                (
                    self.shuffle_button,
                    self.shuffle_button.connect("clicked", lambda *_: self._play(True)),
                ),
            ]
        )

    def _play(self, shuffle: bool) -> None:
        if self.fixed_items is None and self.all_items is None:
            # The rest of the list loads first
            self._play_when_loaded = shuffle
            self.play_button.set_sensitive(False)
            self.shuffle_button.set_sensitive(False)
            self._load_all_items()
            return
        items = self.fixed_items if self.fixed_items is not None else self.all_items
        if self.search_query:
            items = [i for i in items if utils.matches_search(i, self.search_query)]
        if not items:
            return
        if shuffle:
            utils.player_object.shuffle_this(list(items), source=self.play_source)
        else:
            utils.player_object.play_this(list(items), 0, source=self.play_source)

    def _load_async(self) -> None:
        self.auto_load.th_load_items()

    def _load_finish(self) -> None: ...

    def set_function(self, function) -> None:
        self.function = function
        self.auto_load.set_function(function)

    def set_items(self, items) -> None:
        self.fixed_items = list(items)
        self.auto_load.set_items(items)

    def enable_search(self, placeholder: str, page_size: int = 50) -> None:
        """Add a search button to the header bar, opening a field that filters
        the list. The rest of the list is loaded for it, page_size at a time."""
        self.search_page_size = page_size
        self.search_entry = Gtk.SearchEntry(placeholder_text=placeholder)
        self.search_bar = Gtk.SearchBar(child=self.search_entry)
        self.object.add_top_bar(self.search_bar)

        search_button = Gtk.ToggleButton(
            icon_name="system-search-symbolic",
            tooltip_text=_("Search in This List"),
        )
        self.builder.get_object("_header_bar").pack_end(search_button)

        self.setup_search_bar(self.search_bar, self.search_entry, search_button)
        self.signals.extend(
            [
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

    def enable_sort(self, kind: str) -> None:
        """Add a sort button to the header bar for a Collection list (utils.SORTS);
        the list loads again in the chosen order"""
        menu, actions = utils.sort_menu(kind)
        button = Gtk.MenuButton(
            icon_name="view-sort-descending-symbolic",
            tooltip_text=_("Sort"),
        )
        # On the button: GTK may not see actions added to an ancestor later
        button.insert_action_group("sort", actions)
        self.builder.get_object("_header_bar").pack_end(button)
        button.set_menu_model(menu)

        settings = actions.settings
        for key in (f"sort-{kind}", f"sort-{kind}-reversed"):
            self.signals.append(
                (settings, settings.connect(f"changed::{key}", self._on_sort_changed))
            )

    def _on_sort_changed(self, *args) -> None:
        # The function asks TIDAL for the chosen order: load the list again
        self.all_items = None
        self.items_before_search = []
        self.offset_before_search = 0
        self.auto_load.set_function(self.function)
        self.auto_load.set_items([])
        threading.Thread(target=self.auto_load.th_load_items, daemon=True).start()
        if self.search_query:
            self._load_all_items()

    def _on_search_mode_changed(self, search_bar, _pspec) -> None:
        if not search_bar.get_search_mode():
            self.search_entry.set_text("")

    def _on_search_changed(self, entry) -> None:
        query = entry.get_text().strip().lower()
        if query == self.search_query:
            return
        if query and not self.search_query and self.all_items is None:
            self.items_before_search = list(self.auto_load.items)
            self.offset_before_search = self.auto_load.offset
        self.search_query = query
        if query:
            self._load_all_items()
        self._show_items()

    @staticmethod
    def _slices_of(items):
        return lambda limit=50, offset=0: items[offset : offset + limit]

    def _show_items(self) -> None:
        """Show the list, filtered by the search if any. Long lists show their
        first items and the rest while scrolling, as when the page opened."""
        auto_load = self.auto_load
        if self.fixed_items is not None:
            items = self.fixed_items
        elif self.all_items is not None:
            items = self.all_items
        elif self.search_query:
            items = self.items_before_search
        else:
            # Cleared before the whole list loaded: back to what was shown
            auto_load.set_items(self.items_before_search)
            auto_load.offset = self.offset_before_search
            auto_load.set_function(self.function)
            return

        if self.search_query:
            items = [i for i in items if utils.matches_search(i, self.search_query)]
        auto_load.set_items(items[: auto_load.items_limit])
        auto_load.set_function(self._slices_of(items))
        if self.loading_all:
            auto_load.spinner.set_visible(True)

    def _load_all_items(self) -> None:
        """Fetch the whole list in the background, so a search covers all of it"""
        if self.loading_all or self.all_items is not None or self.function is None:
            return
        if self.fixed_items is not None:
            return
        self.loading_all = True
        function = self.function
        page_size = self.search_page_size

        def fetch():
            items = []
            seen = set()
            try:
                while True:
                    page = function(limit=page_size, offset=len(items))
                    new = [i for i in page or [] if id_of(i) not in seen]
                    if not new:
                        break
                    seen.update(id_of(i) for i in new)
                    items.extend(new)
            except Exception:
                logger.exception("Error while loading the whole list for the search")
                GLib.idle_add(done, None)
                return
            GLib.idle_add(done, utils.filter_ai_items(items))

        def id_of(item):
            return getattr(item, "id", None) or id(item)

        def done(items):
            self.loading_all = False
            self.auto_load.spinner.set_visible(False)
            if items is not None:
                self.all_items = items
            if self.search_query:
                self._show_items()
            if self._play_when_loaded is not None:
                shuffle, self._play_when_loaded = self._play_when_loaded, None
                self.play_button.set_sensitive(True)
                self.shuffle_button.set_sensitive(True)
                if self.all_items is not None:
                    self._play(shuffle)
            return False

        threading.Thread(target=fetch, daemon=True).start()
