# album_page.py
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

class albumPage(Page):
    __gtype_name__ = 'albumPage'

    """It is used to display an album"""

    def _load_page(self):
        builder = Gtk.Builder.new_from_resource("/io/github/nokse22/HighTide/ui/pages_ui/tracks_list_template.ui")

        page_content = builder.get_object("_main")
        tracks_list_box = builder.get_object("_list_box")
        tracks_list_box.connect("row-activated", self.on_row_selected)

        builder.get_object("_title_label").set_label(self.item.name)
        builder.get_object("_first_subtitle_label").set_label(self.item.artist.name)
        builder.get_object("_second_subtitle_label").set_label(f"{self.item.num_tracks} tracks ({utils.pretty_duration(self.item.duration)})")

        builder.get_object("_play_button").connect("clicked", self.on_play_button_clicked)
        builder.get_object("_shuffle_button").connect("clicked", self.on_shuffle_button_clicked)
        builder.get_object("_add_to_my_collection_button").connect("clicked", self.on_add_to_my_collection_button_clicked)

        image = builder.get_object("_image")
        th = threading.Thread(target=utils.add_image, args=(image, self.item))
        th.deamon = True
        th.start()

        for index, track in enumerate(self.item.items()):
            listing = self.get_album_track_listing(track)
            listing.set_name(str(index))
            tracks_list_box.append(listing)

        self.content.remove(self.spinner)
        self.content.append(page_content)

    def on_row_selected(self, list_box, row):
        index = int(row.get_name())

        self.window.player_object.play_this(self.item, index)
