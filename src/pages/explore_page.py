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

from gi.repository import Adw
from gi.repository import Gtk
from gi.repository import GLib
from gi.repository import Gio
from gi.repository import Gdk

import tidalapi
from tidalapi.page import PageItem, PageLink
from tidalapi.mix import Mix, MixType
from tidalapi.artist import Artist
from tidalapi.album import Album
from tidalapi.media import Track
from tidalapi.playlist import Playlist

from ..lib import utils

import threading
import requests
import random

from .page import Page

class explorePage(Page):
    __gtype_name__ = 'explorePage'

    """It is used to display the explore page"""

    def _load_page(self):
        explore = self.window.session.explore()

        # print(explore.categories)

        for index, category in enumerate(explore.categories):
            items = []

            if isinstance(category.items[0], PageLink):
                carousel, flow_box_box = self.get_link_carousel(category.title if category.title else "More")

                flow_box = Gtk.FlowBox(homogeneous=True, height_request=100)
                flow_box_box.append(flow_box)
                self.page_content.append(carousel)
            else:
                carousel, cards_box = self.get_carousel(category.title)
                self.page_content.append(carousel)

            buttons_for_page = 0

            for index, item in enumerate(category.items):
                if isinstance(item, PageItem): # Featured
                    button = self.get_page_item_card(item)
                    cards_box.append(button)
                elif isinstance(item, PageLink): # Generes and moods
                    if buttons_for_page == 4:
                        flow_box = Gtk.FlowBox(homogeneous=True, height_request=100)
                        flow_box_box.append(flow_box)
                        buttons_for_page = 0
                    button = self.get_page_link_card(item)
                    flow_box.append(button)
                    buttons_for_page += 1
                elif isinstance(item, Mix): # Mixes and for you
                    button = self.get_mix_card(item)
                    cards_box.append(button)
                elif isinstance(item, Album):
                    album_card = self.get_album_card(item)
                    cards_box.append(album_card)
                elif isinstance(item, Artist):
                    button = self.get_artist_card(item)
                    cards_box.append(button)
                elif isinstance(item, Playlist):
                    button = self.get_playlist_card(item)
                    cards_box.append(button)

        self._page_loaded()
