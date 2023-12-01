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

class genericPage(Page):
    __gtype_name__ = 'genericPage'

    """It is not used much, possibly not needed anymore"""

    def _load_page(self):
        builder = Gtk.Builder.new_from_resource("/io/github/nokse22/high-tide/ui/pages_ui/home_page_template.ui")

        page_content = builder.get_object("_main")
        generic_page_content = builder.get_object("_content")

        generic_content = self.item.get()

        for index, category in enumerate(generic_content.categories):
            items = []

            carousel, cards_box = self.get_carousel(category.title)

            if not isinstance(category.items[0], Track):
                generic_page_content.append(carousel)
            else:
                continue

            for item in category.items:
                if isinstance(item, PageItem): # Featured
                    button = self.get_page_item_card(item)
                    cards_box.append(button)
                elif isinstance(item, PageLink): # Generes and moods
                    items.append("\t" + item.title)
                    button = self.get_page_link_card(item)
                    cards_box.append(button)
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

        self.content.remove(self.spinner)
        self.content.append(page_content)
