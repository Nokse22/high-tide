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

from ..widgets.generic_track_widget import GenericTrackWidget
from ..widgets.card_widget import CardWidget

class Page(Adw.NavigationPage):
    __gtype_name__ = 'Page'

    def __init__(self, _window, _item, _name):
        super().__init__()

        # self.builder = None

        self.window = _window
        self.set_title(_name)

        self.builder = Gtk.Builder.new_from_resource('/io/github/nokse22/high-tide/ui/pages_ui/page_template.ui')
        self.item = _item

        self.content = self.builder.get_object("_content")
        self.object = self.builder.get_object("_main")
        self.spinner = self.builder.get_object("_spinner")

        self.set_child(self.object)

    def load(self):
        th = threading.Thread(target=self._load_page)
        th.deamon = True
        th.start()

    def _load_page(self):
        return

    def get_album_card(self, item):
        card = CardWidget(item, self.window)
        return card

    def get_track_listing(self, track):
        track_listing = GenericTrackWidget(track, self.window, False)
        return track_listing

    def get_mix_card(self, item):
        card = CardWidget(item, self.window)
        return card

    def on_mix_button_clicked(self, btn, mix):
        self.window.sidebar_list.select_row(None)

        from .mix_page import mixPage

        page = mixPage(self.window, mix, mix.title)
        page.load()
        self.window.navigation_view.push(page)

    def get_album_track_listing(self, track):
        track_listing = GenericTrackWidget(track, self.window, True)
        return track_listing

    def on_play_button_clicked(self, btn):
        self.window.player_object.current_mix_album = self.item
        self.window.player_object.tracks_from_list_to_play = self.item.items()
        track = self.window.player_object.tracks_from_list_to_play[0]
        self.window.player_object.play_track(track)
        self.play()
        self.window.player_object.current_song_index = 0

    def on_shuffle_button_clicked(self, btn):
        self.window.player_object.current_mix_album = self.item
        self.window.player_object.tracks_from_list_to_play = self.item.items()
        self.window.player_object.play_shuffle()

    def on_artist_button_clicked(self, btn, artist):
        print(artist)
        self.window.sidebar_list.select_row(None)

        from .artist_page import artistPage

        page = artistPage(self.window, artist, artist.name)
        page.load()
        self.window.navigation_view.push(page)

    def add_image(self, image_widget, item):
        try:
            image_url = item.image()
            response = requests.get(image_url)
        except Exception as e:
            print(str(e))
            return
        if response.status_code == 200:
            image_data = response.content
            file_path = f"tmp_img/{item.id}.jpg"
            with open(file_path, "wb") as file:
                file.write(image_data)

            GLib.idle_add(self._add_image, image_widget, file_path)

    def _add_image(self, image_widget, file_path):
        image_widget.set_from_file(file_path)

    def add_image_to_avatar(self, avatar_widget, image_url):
        try:
            response = requests.get(image_url)
        except:
            return

        if response.status_code == 200:
            image_data = response.content
            file_path = f"{random.randint(0, 100)}.jpg"
            with open(file_path, "wb") as file:
                file.write(image_data)

            GLib.idle_add(self._add_image_to_avatar, avatar_widget, file_path)

    def _add_image_to_avatar(self, avatar_widget, file_path):
        file = Gio.File.new_for_path(file_path)
        image = Gdk.Texture.new_from_file(file)
        avatar_widget.set_custom_image(image)

    def on_row_selected(self, list_box, row):
        index = int(row.get_name())

        self.window.player_object.current_mix_album = self.item
        self.window.player_object.tracks_from_list_to_play = self.item.items()
        track = self.window.player_object.tracks_from_list_to_play[index]
        self.window.player_object.play_track(track)
        self.window.player_object.play()
        self.window.player_object.current_song_index = index

    def get_carousel(self, title):
        cards_box = Gtk.Box()
        box = Gtk.Box(orientation=1, margin_bottom=12, margin_start=12, margin_end=12, overflow=Gtk.Overflow.HIDDEN)
        title_box = Gtk.Box(margin_top=12, margin_bottom=6)
        title_box.append(Gtk.Label(label=title, xalign=0, css_classes=["title-3"], ellipsize=3))
        prev_button = Gtk.Button(icon_name="go-next-symbolic", margin_start=6, halign=Gtk.Align.END, css_classes=["circular"])
        next_button = Gtk.Button(icon_name="go-previous-symbolic", hexpand=True, halign=Gtk.Align.END, css_classes=["circular"])
        title_box.append(next_button)
        title_box.append(prev_button)

        box.append(title_box)
        cards_box = Adw.Carousel(halign=Gtk.Align.START, allow_scroll_wheel=False, allow_long_swipes=True)
        cards_box.set_overflow(Gtk.Overflow.VISIBLE)
        box.append(cards_box)

        prev_button.connect("clicked", self.carousel_go_prev, cards_box)
        next_button.connect("clicked", self.carousel_go_next, cards_box)

        return box, cards_box

    def carousel_go_prev(self, btn, carousel):
        pos = carousel.get_position()
        if pos + 2 >= carousel.get_n_pages():
            if pos + 1 == carousel.get_n_pages():
                return
            else:
                next_page = carousel.get_nth_page(pos + 1)
        else:
            next_page = carousel.get_nth_page(pos + 2)
        if next_page != None:
            carousel.scroll_to(next_page, True)

    def carousel_go_next(self, btn, carousel):
        pos = carousel.get_position()
        if pos - 2 < 0:
            if pos - 1 < 0:
                return
            else:
                next_page = carousel.get_nth_page(0)
        else:
            next_page = carousel.get_nth_page(pos - 2)

        carousel.scroll_to(next_page, True)

    def get_playlist_card(self, playlist):
        card = CardWidget(playlist, self.window)
        return card

    def on_playlist_button_clicked(self, btn, playlist):
        self.window.sidebar_list.select_row(None)

        from .playlist_page import playlistPage

        page = playlistPage(self.window, playlist, playlist.name)
        page.load()
        self.window.navigation_view.push(page)

    def on_album_button_clicked(self, btn, album):
        self.window.sidebar_list.select_row(None)
        self.window.player_object.current_mix_album = album

        from .album_page import albumPage

        page = albumPage(self.window, album, album.name)
        page.load()
        self.window.navigation_view.push(page)

    def get_artist_page(self, artist):
        from .artist_page import artistPage

        page = artistPage(self.window, artist, artist.name)
        page.load()
        self.window.navigation_view.push(page)

    def get_artist_card(self, item):
        card = CardWidget(item, self.window)
        return card

    def get_page_item_card(self, page_item):
        card = CardWidget(page_item, self.window)
        return card

    def get_page_link_card(self, page_link):
        button = Gtk.Button(label=page_link.title, margin_start=12, margin_end=12,
                hexpand=True, width_request=200, vexpand=True)
        button.connect("clicked", self.on_page_link_clicked, page_link)
        return button

    def on_page_link_clicked(self, btn, page_link):
        from .generic_page import genericPage

        page = genericPage(self.window, page_link, page_link.title)
        page.load()
        self.window.navigation_view.push(page)
