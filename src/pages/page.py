# mix_page.py
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
import os

from ..widgets import HTGenericTrackWidget
from ..widgets import HTCardWidget

from ..lib import variables

class Page(Adw.NavigationPage):
    __gtype_name__ = 'Page'

    """It's the base class for all types of pages, it contains all the shared functions"""

    def __init__(self, _item=None, _name=None):
        super().__init__()

        self.signals = []

        self.signals.append(
            (self, self.connect("unrealize", self.__on_unrealized))
        )

        if _name:
            self.set_title(_name)

        self.page_content = Gtk.Box(vexpand=True, hexpand=True, orientation=1)

        self.builder = Gtk.Builder.new_from_resource('/io/github/nokse22/HighTide/ui/pages_ui/page_template.ui')
        self.item = _item

        self.content = self.builder.get_object("_content")
        self.content_stack = self.builder.get_object("_content_stack")
        self.object = self.builder.get_object("_main")
        self.scrolled_window = self.builder.get_object("_scrolled_window")

        self.set_child(self.object)

    def load(self):

        """Called when the page is created, it just starts a thread running the actual function to load the page UI"""

        th = threading.Thread(target=self._th_load_page)
        th.deamon = True
        th.start()

    def _th_load_page(self):

        """Overwritten by each different page"""

        return

    def _page_loaded(self):
        def _add_content_to_page():
            self.content_stack.set_visible_child_name("content")
            self.content.append(self.page_content)

        GLib.idle_add(_add_content_to_page)

    def get_album_card(self, item):
        card = HTCardWidget(item)
        return card

    def get_track_listing(self, track):
        track_listing = HTGenericTrackWidget(track, False)
        return track_listing

    def get_mix_card(self, item):
        card = HTCardWidget(item)
        return card

    def get_album_track_listing(self, track):
        track_listing = HTGenericTrackWidget(track, True)
        return track_listing

    def get_playlist_card(self, playlist):
        card = HTCardWidget(playlist)
        return card

    def on_mix_button_clicked(self, btn, mix):
        variables.sidebar_list.select_row(None)

        from .mix_page import mixPage

        page = mixPage(mix, mix.title)
        page.load()
        variables.navigation_view.push(page)

    def on_play_button_clicked(self, btn):
        variables.player_object.play_this(self.item)

    def on_shuffle_button_clicked(self, btn):
        variables.player_object.shuffle_this(self.item)

    def on_artist_button_clicked(self, btn, artist):
        print(artist)
        variables.sidebar_list.select_row(None)

        from .artist_page import artistPage

        page = artistPage(artist, artist.name)
        page.load()
        variables.navigation_view.push(page)

    def get_link_carousel(self, title):

        """Similar to the last function but used to display links to other pages
        like in the explore page to display genres..."""

        cards_box = Gtk.Box()
        box = Gtk.Box(orientation=1, margin_bottom=12, margin_start=12, margin_end=12, overflow=Gtk.Overflow.HIDDEN)
        title_box = Gtk.Box(margin_top=12, margin_bottom=6)
        title_box.append(Gtk.Label(label=title, xalign=0, css_classes=["title-3"], ellipsize=3))
        prev_button = Gtk.Button(icon_name="go-next-symbolic", margin_start=6, halign=Gtk.Align.END, css_classes=["circular"])
        next_button = Gtk.Button(icon_name="go-previous-symbolic", hexpand=True, halign=Gtk.Align.END, css_classes=["circular"])
        title_box.append(next_button)
        title_box.append(prev_button)

        box.append(title_box)
        cards_box = Adw.Carousel(halign=Gtk.Align.FILL, allow_scroll_wheel=False, allow_long_swipes=True)
        cards_box.set_overflow(Gtk.Overflow.VISIBLE)
        box.append(cards_box)

        self.signals.append(
            (prev_button, prev_button.connect("clicked", self.carousel_go_prev, cards_box, 1))
        )

        self.signals.append(
            (next_button, next_button.connect("clicked", self.carousel_go_next, cards_box, 1))
        )

        return box, cards_box

    def carousel_go_prev(self, btn, carousel, jump=2):
        pos = carousel.get_position()
        if pos + 2 >= carousel.get_n_pages():
            if pos + 1 == carousel.get_n_pages():
                return
            else:
                next_page = carousel.get_nth_page(pos + 1)
        else:
            next_page = carousel.get_nth_page(pos + jump)
        if next_page != None:
            carousel.scroll_to(next_page, True)

    def carousel_go_next(self, btn, carousel, jump=2):
        pos = carousel.get_position()
        if pos - 2 < 0:
            if pos - 1 < 0:
                return
            else:
                next_page = carousel.get_nth_page(0)
        else:
            next_page = carousel.get_nth_page(pos - jump)

        carousel.scroll_to(next_page, True)

    def on_playlist_button_clicked(self, btn, playlist):
        variables.sidebar_list.select_row(None)

        from .playlist_page import playlistPage

        page = playlistPage(playlist, playlist.name)
        page.load()
        variables.navigation_view.push(page)

    def on_album_button_clicked(self, btn, album):
        variables.sidebar_list.select_row(None)
        variables.player_object.current_mix_album = album

        from .album_page import albumPage

        page = albumPage(album, album.name)
        page.load()
        variables.navigation_view.push(page)

    def get_artist_page(self, artist):
        from .artist_page import artistPage

        page = artistPage(artist, artist.name)
        page.load()
        variables.navigation_view.push(page)

    def get_artist_card(self, item):
        card = HTCardWidget(item)
        return card

    def get_page_item_card(self, page_item):
        card = HTCardWidget(page_item)
        return card

    def get_page_link_card(self, page_link):
        button = Gtk.Button(label=page_link.title, margin_start=12, margin_end=12,
                hexpand=True, width_request=200, vexpand=True)
        self.signals.append(
            (button, button.connect("clicked", self.on_page_link_clicked, page_link))
        )

        return button

    def on_page_link_clicked(self, btn, page_link):
        from .generic_page import genericPage

        page = genericPage(page_link, page_link.title)
        page.load()
        variables.navigation_view.push(page)

    def delete_signals(self):
        disconnected_signals = 0
        for obj, signal_id in self.signals:
            disconnected_signals += 1
            obj.disconnect(signal_id)

            self.signals = []
        print(f"disconnected {disconnected_signals} signals from {self}")

    def __on_unrealized(self, *args):
        self.delete_signals()

    def __del__(self, *args):
        print(f"DELETING {self}")
