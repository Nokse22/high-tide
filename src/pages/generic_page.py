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

from tidalapi.page import PageItem, TextBlock
from tidalapi.media import Track

from .page import Page

from ..disconnectable_iface import IDisconnectable


class genericPage(Page):
    __gtype_name__ = "genericPage"

    """It is used for explore page categories page"""

    def __init__(self, _page_link):
        IDisconnectable.__init__(self)
        super().__init__()

        self.item = _page_link

        self.content = None

    def _load_async(self):
        self.content = self.item.get()

    def _load_finish(self):
        self.set_title(self.item.title)

        for index, category in enumerate(self.content.categories):
            if isinstance(category, PageItem):
                continue

            if isinstance(category.items[0], Track):
                self.new_track_list_for(category.title, category.items)
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
