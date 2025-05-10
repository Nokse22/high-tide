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

from gi.repository import Gtk
from ..lib import utils
from .page import Page
from ..lib import variables
import threading


class albumPage(Page):
    __gtype_name__ = 'albumPage'

    """It is used to display an album"""

    def _th_load_page(self):
        builder = Gtk.Builder.new_from_resource(
            "/io/github/nokse22/HighTide/ui/pages_ui/tracks_list_template.ui")

        page_content = builder.get_object("_main")
        tracks_list_box = builder.get_object("_list_box")
        self.signals.append((
            tracks_list_box,
            tracks_list_box.connect("row-activated", self.on_row_selected)))

        builder.get_object("_title_label").set_label(self.item.name)
        builder.get_object("_first_subtitle_label").set_label(
            "{} - {}".format(
                self.item.artist.name,
                self.item.release_date.strftime('%d-%m-%Y') if self.item.release_date else "Unknown"))
        builder.get_object("_second_subtitle_label").set_label(
            "{} tracks ({})".format(
                self.item.num_tracks,
                utils.pretty_duration(self.item.duration)))

        play_btn = builder.get_object("_play_button")
        self.signals.append((
            play_btn,
            play_btn.connect("clicked", self.on_play_button_clicked)))

        shuffle_btn = builder.get_object("_shuffle_button")
        self.signals.append((
            shuffle_btn,
            shuffle_btn.connect("clicked", self.on_shuffle_button_clicked)))

        in_my_collection_btn = builder.get_object("_in_my_collection_button")
        self.signals.append((
            in_my_collection_btn,
            in_my_collection_btn.connect(
                "clicked",
                variables.on_in_to_my_collection_button_clicked, self.item)))

        share_button = builder.get_object("_share_button")
        self.signals.append((
            share_button,
            share_button.connect(
                "clicked",
                lambda *_: variables.share_this(self.item))))

        if (variables.is_favourited(self.item)):
            in_my_collection_btn.set_icon_name("heart-filled-symbolic")

        image = builder.get_object("_image")
        threading.Thread(
            target=utils.add_image,
            args=(image, self.item)).start()

        for index, track in enumerate(self.item.items()):
            listing = self.get_album_track_listing(track)
            listing.set_name(str(index))
            tracks_list_box.append(listing)

        self.page_content.append(page_content)
        self._page_loaded()

    def on_row_selected(self, list_box, row):
        index = int(row.get_name())

        variables.player_object.play_this(self.item, index)
