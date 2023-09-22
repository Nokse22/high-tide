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

class trackRadioPage(Page):
    __gtype_name__ = 'trackRadioPage'

    def __init__(self, _window, _item, _name):
        super().__init__(_window, _item, _name)

        self.radio_tracks = []

    def _load_page(self):
        builder = Gtk.Builder.new_from_file("/home/lorenzo/Projects/high-tide/data/ui/pages_ui/tracks_list_template.ui")

        page_content = builder.get_object("_main")
        tracks_list_box = builder.get_object("_list_box")
        tracks_list_box.connect("row-selected", self.on_row_selected)

        builder.get_object("_title_label").set_label(f"Radio of {self.item.name}")
        builder.get_object("_first_subtitle_label").set_label(f"by {self.item.artist.name}")

        builder.get_object("_play_button").connect("clicked", self.on_play_button_clicked)
        builder.get_object("_shuffle_button").connect("clicked", self.on_shuffle_button_clicked)

        image = builder.get_object("_image")
        th = threading.Thread(target=self.add_image, args=(image, self.item.album))
        th.deamon = True
        th.start()

        self.radio_tracks = self.item.get_track_radio()

        for index, track in enumerate(self.radio_tracks):
            listing = self.get_track_listing(track)
            listing.set_name(str(index))
            tracks_list_box.append(listing)

        self.content.remove(self.spinner)
        self.content.append(page_content)

    def on_row_selected(self, list_box, row):
        index = int(row.get_child().get_name())

        self.window.player_object.current_mix_album_list = self.radio_tracks
        track = self.window.player_object.current_mix_album_list[index]
        self.window.player_object.current_mix_album = track.album
        self.window.player_object.play_track(track)
        self.window.player_object.current_song_index = index
