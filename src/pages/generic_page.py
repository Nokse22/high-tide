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

from tidalapi.page import PageItem, TextBlock, ShortcutList, TrackList
from tidalapi.media import Track

from .page import Page
from ..widgets import HTShorcutsWidget

from ..disconnectable_iface import IDisconnectable


class HTGenericPage(Page):
    """A page to display any tidalapi Page from a function to get it"""

    __gtype_name__ = "HTGenericPage"

    function = None
    page = None

    def __init__(self, function):
        IDisconnectable.__init__(self)
        super().__init__()

        self.function = function

    def _load_async(self):
        self.page = self.function()

    def _load_finish(self):
        if self.page.title:
            self.set_title(self.page.title)

        for index, category in enumerate(self.page.categories):
            if isinstance(category, PageItem):
                continue

            if isinstance(category.items[0], Track) or isinstance(category, TrackList):
                self.new_track_list_for(category.title, category.items)
            elif isinstance(category, ShortcutList):
                shortcut_list = HTShorcutsWidget(category.items)
                self.append(shortcut_list)
            elif isinstance(category, TextBlock):
                label = Gtk.Label(
                    justify=0,
                    xalign=0,
                    wrap=True,
                    margin_start=12,
                    margin_top=12,
                    margin_bottom=12,
                    margin_end=12,
                    label=category.text,
                )
                self.append(label)
            else:
                self.new_carousel_for(category.title, category.items)
