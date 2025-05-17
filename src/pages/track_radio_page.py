# track_radio.py
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

from gi.repository import Gtk
from tidalapi.media import Track
from ..lib import utils
from ..lib import utils
from .page import Page
import threading


class HTHrackRadioPage(Page):
    __gtype_name__ = 'HTHrackRadioPage'

    """It is used to display a radio from a track"""

    # FIXME Fix the favourite hearth (Probably impossible because tidalapi doesn't store a radio as a mix, but maybe possible with some ID)

    def __init__(self, _id):
        super().__init__()

        self.id = _id
        self.radio_tracks = []

    def _th_load_page(self):
        self.item = Track(utils.session, self.id)

        builder = Gtk.Builder.new_from_resource(
            "/io/github/nokse22/HighTide/ui/pages_ui/tracks_list_template.ui")

        page_content = builder.get_object("_main")
        tracks_list_box = builder.get_object("_list_box")
        self.signals.append((
                tracks_list_box,
                tracks_list_box.connect(
                    "row-activated", self.on_row_selected)))

        page_title = "Radio of {}".format(self.item.name)

        builder.get_object("_title_label").set_label(page_title)
        self.set_title(page_title)

        if isinstance(self.item, Track):
            builder.get_object("_first_subtitle_label").set_label(
                "by {}".format(self.item.artist.name))

        play_btn = builder.get_object("_play_button")
        self.signals.append((
                play_btn,
                play_btn.connect("clicked", self.on_play_button_clicked)))

        shuffle_btn = builder.get_object("_shuffle_button")
        self.signals.append((
                shuffle_btn,
                shuffle_btn.connect(
                    "clicked", self.on_shuffle_button_clicked)))

        builder.get_object("_in_my_collection_button").set_visible(False)
        builder.get_object("_share_button").set_visible(False)

        image = builder.get_object("_image")
        if isinstance(self.item, Track):
            threading.Thread(
                target=utils.add_image,
                args=(image, self.item.album)).start()
        else:
            threading.Thread(
                target=utils.add_image,
                args=(image, self.item)).start()

        if isinstance(self.item, Track):
            self.radio_tracks = self.item.get_track_radio()
        else:
            self.radio_tracks = self.item.get_radio()

        for index, track in enumerate(self.radio_tracks):
            listing = self.get_track_listing(track)
            listing.set_name(str(index))
            tracks_list_box.append(listing)

        self.page_content.append(page_content)
        self._page_loaded()

    def on_row_selected(self, list_box, row):
        index = int(row.get_name())

        utils.player_object.play_this(self.radio_tracks, index)

    def on_play_button_clicked(self, btn):
        # overwritten to pass a list and not the Track or Artist (that is the self.item for the radio page)
        utils.player_object.play_this(self.radio_tracks)

    def on_shuffle_button_clicked(self, btn):
        # overwritten to pass a list and not the Track or Artist (that is the self.item for the radio page)
        utils.player_object.shuffle_this(self.radio_tracks)
