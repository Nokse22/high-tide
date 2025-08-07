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

from gi.repository import Gtk

from ..lib import utils
from .page import Page

import threading


class HTMixPage(Page):
    """A page to display a mix"""

    __gtype_name__ = "HTMixPage"

    tracks = None

    def _load_async(self):
        self.item = utils.get_mix(self.id)

        self.tracks = self.item.items()

    def _load_finish(self):
        self.set_title(self.item.title)

        builder = Gtk.Builder.new_from_resource(
            "/io/github/nokse22/high-tide/ui/pages_ui/tracks_list_template.ui"
        )

        self.append(builder.get_object("_main"))

        auto_load = builder.get_object("_auto_load")
        auto_load.set_scrolled_window(self.scrolled_window)
        auto_load.set_items(self.tracks)

        builder.get_object("_title_label").set_label(self.item.title)
        builder.get_object("_first_subtitle_label").set_label(self.item.sub_title)

        play_btn = builder.get_object("_play_button")
        self.signals.append((
            play_btn,
            play_btn.connect("clicked", self.on_play_button_clicked),
        ))

        shuffle_btn = builder.get_object("_shuffle_button")
        self.signals.append((
            shuffle_btn,
            shuffle_btn.connect("clicked", self.on_shuffle_button_clicked),
        ))

        in_my_collection_btn = builder.get_object("_in_my_collection_button")
        self.signals.append((
            in_my_collection_btn,
            in_my_collection_btn.connect(
                "clicked", utils.on_in_to_my_collection_button_clicked, self.item
            ),
        ))

        builder.get_object("_share_button").set_visible(False)

        if utils.is_favourited(self.item):
            in_my_collection_btn.set_icon_name("heart-filled-symbolic")

        image = builder.get_object("_image")
        threading.Thread(target=utils.add_image, args=(image, self.item)).start()
