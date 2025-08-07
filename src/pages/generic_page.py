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

from gi.repository import Gtk

from tidalapi.page import PageItem, TextBlock, ShortcutList, TrackList, PageLinks
from tidalapi.page import HorizontalList, HorizontalListWithContext
from tidalapi.page import FeaturedItems, ItemList, LinkList
from tidalapi.media import Track

from .page import Page
from ..widgets import HTShorcutsWidget

from gettext import gettext as _


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

    @classmethod
    def new_from_function(cls, function):
        """Create a new generic page instance from a function that returns page data.

        Args:
            function: A callable that returns a TIDAL API page object when called

        Returns:
            HTGenericPage: A new instance configured with the provided function
        """
        instance = cls()

        instance.function = function

        return instance

    def _load_async(self):
        self.page = self.function()

    def _load_finish(self):
        if self.page.title:
            self.set_title(self.page.title)
        else:
            self.set_title("")

        for index, category in enumerate(self.page.categories):
            if isinstance(category.items[0], Track) or isinstance(category, TrackList):
                self.new_track_list_for(category.title, category.items)
            elif isinstance(category, ShortcutList):
                self.append(HTShorcutsWidget(category.items))
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
            elif (
                isinstance(category, HorizontalList)
                or isinstance(category, HorizontalListWithContext)
                or isinstance(category, ItemList)
            ):
                self.new_carousel_for(category.title, category.items)
            elif isinstance(category, PageLinks):
                self.new_link_carousel_for(
                    category.title if category.title else _("More"), category.items
                )
