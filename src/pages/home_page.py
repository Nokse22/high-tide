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

class homePage(Page):
    __gtype_name__ = 'homePage'

    def _load_page(self):
        self.set_tag("home")

        builder = Gtk.Builder.new_from_resource("/io/github/nokse22/high-tide/ui/pages_ui/home_page_template.ui")

        page_content = builder.get_object("_main")
        home_content = builder.get_object("_content")

        self.window.login()

        if not self.window.session.check_login():
            descr = '''To be able to use this app you need to login with your TIDAL account.
Open the hamburger menu on the left and click Login.'''

            status_page = Adw.StatusPage(title="Login first", description=descr, icon_name="face-wink-symbolic")
            status_page.set_vexpand(True)
            status_page.set_hexpand(True)

            self.content.remove(self.spinner)
            self.content.append(status_page)

            return

        th = threading.Thread(target=self.window._set_last_playing_song, args=())
        th.deamon = True
        th.start()

        self.window.add_favourite_playlists()

        home = self.window.session.home()

        for index, category in enumerate(home.categories):
            if index > 8:
                break
            items = []
            if isinstance(category.items[0], PageItem) or isinstance(category.items[0], PageLink):
                continue

            carousel, cards_box = self.get_carousel(category.title)

            if not isinstance(category.items[0], Track):
                home_content.append(carousel)
            else:
                continue

            for item in category.items:
                if isinstance(item, PageItem): # Featured
                    items.append("\t" + item.short_header)
                    items.append("\t" + item.short_sub_header[0:50])
                    button = self.get_page_item_card(item)
                    # cards_box.append(button)
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
