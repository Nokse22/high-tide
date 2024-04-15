# artist_page.py
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
from ..widgets.carousel_widget import CarouselWidget

import threading
import requests
import random
import copy

from .page import Page

class artistPage(Page):
    __gtype_name__ = 'artistPage'

    """It is used to display an artist page"""

    # FIXME The bio is not displayed properly, it all bold and the links are not working
    # TODO Add missing features: influences, appears on, credits and so on

    def __init__(self, _window, _artist, _name):
        super().__init__(_window, _artist, _name)

        self.top_tracks = []
        self.artist = _artist

    def _load_page(self):

        print(f"artist: {self.artist.name}, id: {self.artist.id}, {self.artist.picture}")

        builder = Gtk.Builder.new_from_resource("/io/github/nokse22/HighTide/ui/pages_ui/artist_page_template.ui")

        page_content = builder.get_object("_main")
        top_tracks_list_box = builder.get_object("_top_tracks_list_box")
        carousel_box = builder.get_object("_carousel_box")
        top_tracks_list_box.connect("row-activated", self.on_row_selected)

        builder.get_object("_name_label").set_label(self.artist.name)

        builder.get_object("_play_button").connect("clicked", self.on_play_button_clicked)
        builder.get_object("_shuffle_button").connect("clicked", self.on_shuffle_button_clicked)

        # builder.get_object("_follow_button").connect("clicked", self.on_add_to_my_collection_button_clicked)
        # builder.get_object("_radio_button").connect("clicked", self.on_artist_radio_button_clicked)

        artist_picture = builder.get_object("_avatar")

        th = threading.Thread(target=utils.add_image_to_avatar, args=(artist_picture, self.artist))
        th.deamon = True
        th.start()

        roles_str = ""
        for role in self.artist.roles:
            print(role)
            roles_str += " " + role.main.value

        builder.get_object("_first_subtitle_label").set_label(roles_str)

        try:
            self.top_tracks = self.artist.get_top_tracks(10)
        except:
            pass
        else:
            for index, track in enumerate(self.top_tracks):
                listing = self.get_track_listing(track)
                listing.set_name(str(index))
                top_tracks_list_box.append(listing)

        carousel = CarouselWidget("Albums", self.window)
        try:
            albums = self.artist.get_albums(limit=10)
            carousel.set_more_action("album", self.artist.get_albums)
        except:
            pass
        else:
            if len(albums) != 0:
                carousel_box.append(carousel)
                for album in albums:
                    album_card = self.get_album_card(album)
                    carousel.append_card(album_card)

        carousel = CarouselWidget("EP & Singles", self.window)
        try:
            albums = self.artist.get_albums_ep_singles(limit=10)
            carousel.set_more_action("album", self.artist.get_albums_ep_singles)
        except:
            pass
        else:
            if len(albums) != 0:
                carousel_box.append(carousel)
                for album in albums:
                    album_card = self.get_album_card(album)
                    carousel.append_card(album_card)

        carousel = CarouselWidget("Appears On", self.window)
        try:
            albums = self.artist.get_albums_other(limit=10)
            carousel.set_more_action("album", self.artist.get_albums_other)
        except:
            pass
        else:
            if len(albums) != 0:
                carousel_box.append(carousel)
                for album in albums:
                    album_card = self.get_album_card(album)
                    carousel.append_card(album_card)

        carousel = CarouselWidget("Similar Artists", self.window)
        try:
            artists = self.artist.get_similar(limit=10)
            carousel.set_more_action("artist", self.artist.get_similar)
        except:
            pass
        else:
            if len(artists) != 0:
                carousel_box.append(carousel)
                for artist in artists:
                    artist_card = self.get_artist_card(artist)
                    carousel.append_card(artist_card)

        try:
            bio = self.artist.get_bio()
        except:
            pass
        else:
            expander = Gtk.Expander(label="Bio", css_classes=["title-3"], margin_bottom=50)
            label = Gtk.Label(label=bio, wrap=True, css_classes=[])
            expander.set_child(label)
            carousel_box.append(expander)

        self.page_content.append(page_content)
        self._page_loaded()

    def on_row_selected(self, list_box, row):
        index = int(row.get_name())

        self.window.player_object.current_mix_album_list = self.top_tracks
        track = self.window.player_object.current_mix_album_list[index]
        self.window.player_object.current_mix_album = track.album
        self.window.player_object.play_track(track)
        self.window.player_object.current_song_index = index

    def on_play_button_clicked(self, btn):
        self.window.player_object.current_mix_album = self.artist
        self.window.player_object.current_mix_album_list = self.top_tracks
        track = self.window.player_object.current_mix_album_list[0]
        self.window.player_object.play_track(track)
        self.window.player_object.current_song_index = 0

    def on_shuffle_button_clicked(self, btn):
        self.window.player_object.current_mix_album = None
        self.window.player_object.current_mix_album_list = self.top_tracks
        self.window.player_object.play_shuffle()

    def on_artist_radio_button_clicked(self, btn):
        from .track_radio_page import trackRadioPage
        page = trackRadioPage(self.window, self.artist, f"Radio of {self.artist.name}")
        page.load()
        self.window.navigation_view.push(page)
