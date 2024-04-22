# home_page.py
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
from tidalapi.user import Favorites

from ..lib import utils

import threading
import requests
import random

from .page import Page
from ..widgets import CarouselWidget
from ..widgets import TracksListWidget

from ..lib import variables

class homePage(Page):
    __gtype_name__ = 'homePage'

    def _load_page(self):
        self.set_tag("home")

        self.set_title("Home")

        home = variables.session.home()

        for index, category in enumerate(home.categories):
            items = []
            if isinstance(category.items[0], PageItem) or isinstance(category.items[0], PageLink):
                continue

            if isinstance(category.items[0], Track):
                tracks_list_widget = TracksListWidget(category.title)
                tracks_list_widget.set_tracks_list(category.items)
                self.page_content.append(tracks_list_widget)
            else:
                carousel = CarouselWidget(category.title)
                self.page_content.append(carousel)

                if isinstance(category.items[0], Mix):
                    carousel.set_items(category.items, "mix")
                elif isinstance(category.items[0], Album):
                    carousel.set_items(category.items, "album")
                elif isinstance(category.items[0], Artist):
                    carousel.set_items(category.items, "artist")
                elif isinstance(category.items[0], Playlist):
                    carousel.set_items(category.items, "playlist")

        self._page_loaded()
