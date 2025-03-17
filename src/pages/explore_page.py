# explore_page.py
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

from tidalapi.page import PageItem, PageLink
from tidalapi.artist import Artist
from tidalapi.album import Album
from tidalapi.mix import Mix
from tidalapi.playlist import Playlist

from .page import Page
from .search_page import searchPage

from ..lib import variables


class explorePage(Page):
    __gtype_name__ = 'explorePage'

    """It is used to display the explore page"""

    def _th_load_page(self):
        self.set_tag("explore")
        self.set_title("Explore")

        explore = variables.session.explore()

        builder = Gtk.Builder.new_from_resource(
            "/io/github/nokse22/HighTide/ui/search_entry.ui")
        search_entry = builder.get_object("search_entry")
        self.signals.append((
            search_entry,
            search_entry.connect("activate", self.on_search_activated)))

        self.page_content.append(search_entry)

        for index, category in enumerate(explore.categories):
            if isinstance(category.items[0], PageLink):
                carousel, flow_box_box = self.get_link_carousel(
                    category.title if category.title else "More")

                flow_box = Gtk.FlowBox(homogeneous=True, height_request=100)
                flow_box_box.append(flow_box)
                self.page_content.append(carousel)
            else:
                carousel, cards_box = self.get_link_carousel(category.title)
                self.page_content.append(carousel)

            buttons_for_page = 0

            for index, item in enumerate(category.items):
                if isinstance(item, PageItem):  # Featured
                    cards_box.append(self.get_card(item.get()))
                elif isinstance(item, PageLink):  # Generes and moods
                    if buttons_for_page == 4:
                        flow_box = Gtk.FlowBox(
                            homogeneous=True,
                            height_request=100)
                        flow_box_box.append(flow_box)
                        buttons_for_page = 0
                    button = self.get_page_link_card(item)
                    flow_box.append(button)
                    buttons_for_page += 1
                elif isinstance(item, Mix):  # Mixes and for you
                    cards_box.append(self.get_card(item))
                elif isinstance(item, Album):
                    cards_box.append(self.get_card(item))
                elif isinstance(item, Artist):
                    cards_box.append(self.get_card(item))
                elif isinstance(item, Playlist):
                    cards_box.append(self.get_card(item))

        self._page_loaded()

    def on_search_activated(self, entry):
        query = entry.get_text()
        page = searchPage(query, "Search")
        page.load()
        variables.navigation_view.push(page)
