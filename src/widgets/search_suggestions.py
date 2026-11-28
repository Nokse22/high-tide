# search_suggestions.py
#
# Copyright 2026 Petru101
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

"""Suggestions under a search field while typing, like TIDAL's: the account's
recent searches and completions to search for, then artists, albums, songs and
playlists to open (a song plays).

The list doesn't take the keyboard, so typing stays in the field; Up and Down
move through it, Enter picks the highlighted one and Escape closes it.
"""

import logging
import threading
from gettext import gettext as _
from typing import Any, Callable

from gi.repository import Adw, Gdk, GLib, Gtk, Pango
from tidalapi.album import Album
from tidalapi.artist import Artist
from tidalapi.media import Track
from tidalapi.playlist import Playlist

from ..lib import utils

logger = logging.getLogger(__name__)

MAX_SEARCHES = 6
MAX_HITS = 6


def fetch_suggestions(query: str) -> tuple:
    """(recent searches, completions, items) TIDAL suggests for query"""
    data = utils.session.request.request(
        "GET",
        "suggestions/",
        base_url="https://api.tidal.com/v2/",
        params={"query": query, "explicit": "true", "hybrid": "true"},
    ).json()
    history = [h["query"] for h in data.get("history", []) if h.get("query")]
    completions = [
        s["query"]
        for s in data.get("suggestions", [])
        if s.get("query") and s["query"] not in history
    ]
    session = utils.session
    parse = {
        "ARTISTS": session.parse_artist,
        "ALBUMS": session.parse_album,
        "TRACKS": session.parse_track,
        "PLAYLISTS": session.parse_playlist,
    }
    items = []
    for hit in data.get("directHits", []):
        parser = parse.get(hit.get("type"))
        value = hit.get("value")
        if parser is None or not isinstance(value, dict):
            continue
        if hit["type"] == "PLAYLISTS":
            # The suggestion answer leaves this out, python-tidal needs it
            value.setdefault("numberOfVideos", value.get("numberOfVideoTracks", 0))
        try:
            items.append(parser(value))
        except Exception as e:
            logger.info(f"Couldn't read a {hit.get('type')} suggestion: {e!r}")
    items = [
        i
        for i in utils.filter_ai_items(items)
        if not utils.is_hidden_by_block(i)
    ]
    return history, completions, items[:MAX_HITS]


class SearchSuggestions:
    """The suggestion list of a search entry. search(query) is called for a
    search to run (a completion or recent search picked, or Enter)."""

    def __init__(self, entry: Gtk.SearchEntry, search: Callable[[str], None]) -> None:
        self.entry = entry
        self.search = search
        self.generation = 0
        self.signals = []
        # The text set by picking a search: it doesn't ask for suggestions again
        self.picked = None

        self.list_box = Gtk.ListBox(
            selection_mode=Gtk.SelectionMode.SINGLE,
            css_classes=["navigation-sidebar", "search-suggestions"],
            can_focus=False,
        )
        self.list_box.set_header_func(self._header)
        self.list_box.connect("row-activated", self._on_row_activated)
        self.popover = Gtk.Popover(
            child=self.list_box,
            has_arrow=False,
            autohide=False,
            can_focus=False,
            position=Gtk.PositionType.BOTTOM,
            halign=Gtk.Align.START,
        )
        self.popover.add_css_class("menu")
        self.popover.set_parent(entry)

        self.signals.append(
            (entry, entry.connect("search-changed", self._on_search_changed))
        )
        self.signals.append((entry, entry.connect("activate", self._on_activate)))
        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._on_key_pressed)
        entry.add_controller(keys)
        focus = Gtk.EventControllerFocus()
        focus.connect("leave", lambda *_: GLib.timeout_add(150, self._hide_unless_focused))
        entry.add_controller(focus)

    def disconnect_all(self) -> None:
        self.hide()
        for obj, handler in self.signals:
            if obj.handler_is_connected(handler):
                obj.disconnect(handler)
        self.signals = []
        self.popover.unparent()

    # Showing

    def hide(self) -> None:
        self.generation += 1
        self.popover.popdown()

    def _hide_unless_focused(self) -> bool:
        root = self.entry.get_root()
        focus = root.get_focus() if root else None
        if not (focus and focus.is_ancestor(self.entry)):
            self.hide()
        return False

    def _on_search_changed(self, entry) -> None:
        query = entry.get_text().strip()
        self.generation += 1
        if not query:
            # Also the moment setting a picked search's text clears the field
            self.popover.popdown()
            return
        if entry.get_text() == self.picked:
            return
        self.picked = None
        generation = self.generation

        def fetch():
            try:
                found = fetch_suggestions(query)
            except Exception as e:
                logger.info(f"No search suggestions: {e!r}")
                found = None
            GLib.idle_add(self._show, generation, found)

        threading.Thread(target=fetch, daemon=True).start()

    def _show(self, generation, found) -> bool:
        if generation != self.generation or found is None:
            return False
        if not self.entry.get_mapped():
            return False  # the page went away meanwhile
        history, completions, items = found
        while row := self.list_box.get_row_at_index(0):
            self.list_box.remove(row)
        searches = [(q, True) for q in history] + [(q, False) for q in completions]
        for query, recent in searches[:MAX_SEARCHES]:
            self.list_box.append(self._search_row(query, recent))
        for item in items:
            row = self._item_row(item)
            if row is not None:
                self.list_box.append(row)
        if self.list_box.get_row_at_index(0) is None:
            self.popover.popdown()
            return False
        self.list_box.unselect_all()
        width = max(self.entry.get_width(), 320)
        self.list_box.set_size_request(width, -1)
        self.popover.popup()
        return False

    def _search_row(self, query: str, recent: bool) -> Gtk.ListBoxRow:
        box = Gtk.Box(spacing=12, margin_top=3, margin_bottom=3)
        box.append(
            Gtk.Image(
                icon_name="document-open-recent-symbolic" if recent else "system-search-symbolic",
                tooltip_text=_("Recent search") if recent else None,
            )
        )
        box.append(Gtk.Label(label=query, xalign=0, ellipsize=Pango.EllipsizeMode.END))
        row = Gtk.ListBoxRow(child=box, can_focus=False)
        row.query = query
        row.group = "search"
        return row

    def _item_row(self, item: Any) -> Gtk.ListBoxRow | None:
        if isinstance(item, Artist):
            kind = _("Artist")
            title = item.name
            picture_of = item
        elif isinstance(item, Album):
            kind = _("Album · {}").format(item.artist.name if item.artist else "")
            title = item.name
            picture_of = item
        elif isinstance(item, Track):
            artists = ", ".join(a.name for a in utils.get_track_artists(item))
            kind = _("Song · {}").format(artists)
            title = item.name
            picture_of = item.album
        elif isinstance(item, Playlist):
            kind = _("Playlist")
            title = item.name
            picture_of = item
        else:
            return None
        if isinstance(item, Artist):
            # Round, as artists are everywhere else
            image = Adw.Avatar(size=36, text=item.name or "")
            add = utils.add_image_to_avatar
        else:
            image = Gtk.Image(pixel_size=36, icon_name="audio-x-generic-symbolic")
            add = utils.add_image
        if picture_of is not None:
            threading.Thread(target=add, args=(image, picture_of), daemon=True).start()
        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
        labels.append(Gtk.Label(label=title or "", xalign=0, ellipsize=Pango.EllipsizeMode.END))
        labels.append(
            Gtk.Label(
                label=kind,
                xalign=0,
                ellipsize=Pango.EllipsizeMode.END,
                css_classes=["caption", "dim-label"],
            )
        )
        box = Gtk.Box(spacing=12, margin_top=3, margin_bottom=3)
        box.append(image)
        box.append(labels)
        row = Gtk.ListBoxRow(child=box, can_focus=False)
        row.item = item
        row.group = "items"
        return row

    def _header(self, row, before) -> None:
        # A line between the searches and the things to open
        if before is not None and row.group != before.group:
            row.set_header(Gtk.Separator(margin_top=3, margin_bottom=3))
        else:
            row.set_header(None)

    # Picking

    def _on_row_activated(self, _list_box, row) -> None:
        self.hide()
        query = getattr(row, "query", None)
        if query is not None:
            self.picked = query
            self.entry.set_text(query)
            self.entry.set_position(-1)
            self.search(query)
            return
        item = row.item
        if isinstance(item, Track):
            utils.player_object.play_this([item], 0)
            return
        action, target = {
            Artist: ("win.push-artist-page", str(item.id)),
            Album: ("win.push-album-page", str(item.id)),
            Playlist: ("win.push-playlist-page", str(item.id)),
        }[type(item) if type(item) in (Artist, Album) else Playlist]
        self.entry.activate_action(action, GLib.Variant("s", target))

    def _on_activate(self, _entry) -> None:
        # Enter with nothing highlighted runs the search as typed (the page's
        # own handler); the list goes away
        self.hide()

    def _on_key_pressed(self, _controller, keyval, _keycode, state) -> bool:
        if not self.popover.get_visible():
            return False
        if keyval in (Gdk.KEY_Down, Gdk.KEY_Up):
            rows = []
            row = self.list_box.get_row_at_index(0)
            while row is not None:
                rows.append(row)
                row = self.list_box.get_row_at_index(len(rows))
            selected = self.list_box.get_selected_row()
            index = rows.index(selected) if selected in rows else -1
            index += 1 if keyval == Gdk.KEY_Down else -1
            if index < 0:
                self.list_box.unselect_all()
            else:
                self.list_box.select_row(rows[min(index, len(rows) - 1)])
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            selected = self.list_box.get_selected_row()
            if selected is not None:
                self._on_row_activated(self.list_box, selected)
                return True
            return False
        if keyval == Gdk.KEY_Escape:
            self.hide()
            return True
        return False
