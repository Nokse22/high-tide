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
from ..widgets import CarouselWidget
from ..widgets import TracksListWidget

import threading
import requests
import random
import copy
import html
import re

from .page import Page

from ..lib import variables

class artistPage(Page):
    __gtype_name__ = 'artistPage'

    """It is used to display an artist page"""

    # FIXME The bio is not displayed properly, it all bold and the links are not working
    # TODO Add missing features: influences, appears on, credits and so on

    def __init__(self, _artist, _name):
        super().__init__(_artist, _name)

        self.top_tracks = []
        self.artist = _artist

    def _load_page(self):

        print(f"artist: {self.artist.name}, id: {self.artist.id}, {self.artist.picture}")

        builder = Gtk.Builder.new_from_resource("/io/github/nokse22/HighTide/ui/pages_ui/artist_page_template.ui")

        page_content = builder.get_object("_main")
        top_tracks_list_box = builder.get_object("_top_tracks_list_box")
        content_box = builder.get_object("_content_box")

        builder.get_object("_name_label").set_label(self.artist.name)

        play_btn = builder.get_object("_play_button")
        self.signals.append(
            (play_btn, play_btn.connect("clicked", self.on_play_button_clicked))
        )

        shuffle_btn = builder.get_object("_shuffle_button")
        self.signals.append(
            (shuffle_btn, shuffle_btn.connect("clicked", self.on_shuffle_button_clicked))
        )

        follow_button = builder.get_object("_follow_button")
        self.signals.append(
            (follow_button, follow_button.connect("clicked", variables.on_in_to_my_collection_button_clicked, self.artist))
        )

        if (variables.is_favourited(self.artist)):
            follow_button.set_icon_name("heart-filled-symbolic")

        # builder.get_object("_radio_button").connect("clicked", self.on_artist_radio_button_clicked)

        artist_picture = builder.get_object("_avatar")

        threading.Thread(target=utils.add_image_to_avatar, args=(artist_picture, self.artist)).start()

        roles_str = ""
        for role in self.artist.roles:
            roles_str += " " + role.main.value

        builder.get_object("_first_subtitle_label").set_label("Artist")

        tracks_list_widget = TracksListWidget("Top Tracks")
        tracks_list_widget.set_function(self.artist.get_top_tracks)
        content_box.append(tracks_list_widget)

        carousel = CarouselWidget("Albums")
        try:
            albums = self.artist.get_albums(limit=10)
            carousel.set_more_function("album", self.artist.get_albums)
        except:
            pass
        else:
            if len(albums) != 0:
                content_box.append(carousel)
                for album in albums:
                    album_card = self.get_album_card(album)
                    carousel.append_card(album_card)

        carousel = CarouselWidget("EP & Singles")
        try:
            albums = self.artist.get_albums_ep_singles(limit=10)
            carousel.set_more_function("album", self.artist.get_albums_ep_singles)
        except:
            pass
        else:
            if len(albums) != 0:
                content_box.append(carousel)
                for album in albums:
                    album_card = self.get_album_card(album)
                    carousel.append_card(album_card)

        carousel = CarouselWidget("Appears On")
        try:
            albums = self.artist.get_albums_other(limit=10)
            carousel.set_more_function("album", self.artist.get_albums_other)
        except:
            pass
        else:
            if len(albums) != 0:
                content_box.append(carousel)
                for album in albums:
                    album_card = self.get_album_card(album)
                    carousel.append_card(album_card)

        carousel = CarouselWidget("Similar Artists")
        try:
            artists = self.artist.get_similar(limit=10)
            carousel.set_more_function("artist", self.artist.get_similar)
        except:
            pass
        else:
            if len(artists) != 0:
                content_box.append(carousel)
                for artist in artists:
                    artist_card = self.get_artist_card(artist)
                    carousel.append_card(artist_card)

        try:
            bio = self.artist.get_bio()
        except:
            pass
        else:
            bio = utils.replace_links(bio)
            label = Gtk.Label(wrap=True, css_classes=[], margin_start=12, margin_end=12, margin_bottom=24)
            label.set_markup(bio)
            content_box.append(Gtk.Label(wrap=True, css_classes=["title-3"],
                        margin_start=12, label=_("Bio"), xalign=0, margin_top=12,margin_bottom=12))
            content_box.append(label)
            self.signals.append(
                (label, label.connect("activate-link", variables.open_uri))
            )

        self.page_content.append(page_content)
        self._page_loaded()

    def on_row_selected(self, list_box, row):
        index = int(row.get_name())

        variables.player_object.current_mix_album_list = self.top_tracks
        track = variables.player_object.current_mix_album_list[index]
        variables.player_object.current_mix_album = track.album
        variables.player_object.play_track(track)
        variables.player_object.current_song_index = index

    def on_play_button_clicked(self, btn):
        variables.player_object.current_mix_album = self.artist
        variables.player_object.current_mix_album_list = self.top_tracks
        track = variables.player_object.current_mix_album_list[0]
        variables.player_object.play_track(track)
        variables.player_object.current_song_index = 0

    def on_shuffle_button_clicked(self, btn):
        variables.player_object.current_mix_album = None
        variables.player_object.current_mix_album_list = self.top_tracks
        variables.player_object.play_shuffle()

    def on_artist_radio_button_clicked(self, btn):
        from .track_radio_page import trackRadioPage
        page = trackRadioPage(self.artist, f"Radio of {self.artist.name}")
        page.load()
        variables.navigation_view.push(page)

