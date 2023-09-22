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

class singleTypePage(Page):
    __gtype_name__ = 'singleTypePage'

    def _load_page(self):
        builder = Gtk.Builder.new_from_file("/home/lorenzo/Projects/high-tide/data/ui/pages_ui/home_page_template.ui")

        page_content = builder.get_object("_main")
        content = builder.get_object("_content")

        if self.item == "track":
            self.add_tracks(content)
        elif self.item == "mix":
            self.add_mixes(content)
        elif self.item == "album":
            self.add_albums(content)
        elif self.item == "artist":
            self.add_artists(content)
        elif self.item == "playlist":
            self.add_playlists(content)

        self.content.remove(self.spinner)
        self.content.append(page_content)

    def add_tracks(self, content):
        tracks_list_box = Gtk.ListBox(css_classes=["navigation-sidebar"])
        content.append(tracks_list_box)

        favourite_tracks = Favorites(self.window.session, self.window.session.user.id).tracks(50)
        tracks_list_box.connect("row-selected", self.on_tracks_row_selected, favourite_tracks)

        for index, track in enumerate(favourite_tracks):
            listing = self.get_track_listing(track)
            listing.set_name(str(index))
            tracks_list_box.append(listing)

    def add_mixes(self, content):
        flow_box = Gtk.FlowBox(selection_mode=0)
        content.append(flow_box)

        favourites = Favorites(self.window.session, self.window.session.user.id).mix()

        for index, mix in enumerate(favourites):
            card = self.get_mix_card(mix)
            flow_box.append(card)

    def add_artists(self, content):
        flow_box = Gtk.FlowBox(selection_mode=0)
        content.append(flow_box)

        favourites = Favorites(self.window.session, self.window.session.user.id).artists()

        for index, artist in enumerate(favourites):
            card = self.get_artist_card(artist)
            flow_box.append(card)

    def add_playlists(self, content):
        flow_box = Gtk.FlowBox(selection_mode=0)
        content.append(flow_box)

        favourites = Favorites(self.window.session, self.window.session.user.id).playlists()

        for index, playlist in enumerate(favourites):
            card = self.get_playlist_card(playlist)
            flow_box.append(card)

    def add_albums(self, content):
        flow_box = Gtk.FlowBox(selection_mode=0)
        content.append(flow_box)

        favourites = Favorites(self.window.session, self.window.session.user.id).albums()

        for index, album in enumerate(favourites):
            card = self.get_album_card(album)
            flow_box.append(card)

    def on_tracks_row_selected(self, list_box, row, favourite_tracks):
        index = int(row.get_child().get_name())

        self.window.player_object.current_mix_album_list = favourite_tracks
        track = favourite_tracks[index]
        print(track)
        self.window.player_object.song_album = track.album
        self.window.player_object.play_track(track)
        self.window.player_object.current_song_index = index
