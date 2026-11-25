# generic_page.py
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

from gettext import gettext as _

from gi.repository import Gio, Gtk

from tidalapi.media import Track
from tidalapi.page import (
    HorizontalList,
    HorizontalListWithContext,
    ItemList,
    PageLinks,
    ShortcutList,
    TextBlock,
    TrackList,
)

from ..lib import utils
from ..widgets import HTShorcutsWidget, HTShorcutWidget
from .page import Page


class HTGenericPage(Page):
    """A generic page that can display any TIDAL API page content.

    This page dynamically renders content from TIDAL API page objects,
    automatically creating appropriate widgets based on the content type
    (tracks, carousels, shortcuts, etc.). It's used for displaying various
    TIDAL pages like home, explore, genres, and search results.
    """

    __gtype_name__ = "HTGenericPage"

    function = None
    page = None
    # Home: rows can be hidden with Customize Home (setting home-hidden-rows)
    hideable = False

    @classmethod
    def new_from_function(cls, function) -> "HTGenericPage":
        """Create a new generic page instance from a function that returns page data.

        This is useful for dynamic pages such as the home page, explore page,
        genres, or search results. The provided function is called to fetch
        the page content when the page is loaded.

        Args:
            function: A callable that returns a TIDAL API page object when called

        Returns:
            HTGenericPage: A new instance configured with the provided function
        """
        instance = cls()

        instance.function = function

        return instance

    def _load_async(self) -> None:
        self.page = self.function()
        # Blocked items are left out, so wait for the blocked lists after login
        utils.blocked_loaded.wait(10)

    def _load_finish(self) -> None:
        self.set_title(self.page.title or "")

        # (TIDAL's row id, title, widget) of each row shown, for Customize Home
        self.rows = []

        for category in self.page.categories:
            last_widget = self.content.get_last_child()
            self._add_category(category)
            widget = self.content.get_last_child()
            module_id = getattr(category, "module_id", None)
            if widget is not last_widget and module_id:
                self.rows.append((module_id, category.title or "", widget))

        if self.hideable:
            self.apply_hidden_rows()

    def apply_hidden_rows(self) -> None:
        """Hide the rows the user turned off in Customize Home, and add the My
        Tracks button if it's turned on there"""
        settings = Gio.Settings.new("io.github.nokse22.high-tide")
        hidden = settings.get_value("home-hidden-rows").unpack()
        for module_id, _title, widget in self.rows:
            widget.set_visible(module_id not in hidden)
        self._show_my_tracks_shortcut(settings.get_boolean("home-my-tracks"))

    def _show_my_tracks_shortcut(self, wanted: bool) -> None:
        """Put a button to the liked songs first in the grid of shortcuts, or
        on its own at the top when that grid isn't shown"""
        added = getattr(self, "_my_tracks_shortcut", None)
        if added is not None:
            added.get_parent().remove(added)
            added.disconnect_all()
            self._my_tracks_shortcut = None
        if not wanted:
            return

        shortcuts = next(
            (w for m, _t, w in self.rows if m == "SHORTCUT_LIST" and w.get_visible()),
            None,
        )
        if shortcuts is None:
            added = HTShorcutsWidget([utils.MY_TRACKS])
            self.content.prepend(added)
        else:
            flow_box = shortcuts.shorcuts_flow_box
            child = flow_box.get_first_child()
            while child:
                if getattr(child, "item", None) is utils.MY_TRACKS:
                    return  # TIDAL sent it today
                child = child.get_next_sibling()
            added = HTShorcutWidget(utils.MY_TRACKS)
            flow_box.insert(added, 0)
        self._my_tracks_shortcut = added

    def _add_category(self, category) -> None:
        """Add the widget showing one of TIDAL's rows"""
        items = [
            item
            for item in getattr(category, "items", [])
            if item is not None and not utils.is_hidden_by_block(item)
        ]

        if isinstance(category, TrackList) or all(
            isinstance(item, Track) for item in items
        ):
            self.new_track_list_for(category.title, items)

        elif isinstance(category, TextBlock):
            self.append(
                Gtk.Label(
                    justify=0,
                    xalign=0,
                    wrap=True,
                    margin_start=12,
                    margin_top=12,
                    margin_bottom=12,
                    margin_end=12,
                    label=category.text,
                )
            )

        elif isinstance(category, PageLinks):
            self.new_link_carousel_for(category.title or _("More"), items)

        elif isinstance(category, ShortcutList):
            self.append(HTShorcutsWidget(items))

        elif isinstance(
            category, (ItemList, HorizontalList, HorizontalListWithContext)
        ):
            self.new_carousel_for(
                category.title,
                items,
                context=getattr(category, "context_item", None),
            )
