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

from tidalapi.mix import MixV2, Mix

from ..lib import utils

import threading
from .page import Page

from ..lib import utils

from ..disconnectable_iface import IDisconnectable


class HTMixPage(Page):
    __gtype_name__ = "HTMixPage"

    def __init__(self, _id):
        IDisconnectable.__init__(self)
        super().__init__()

        self.id = _id

    def _th_load_page(self):
        self.item = Mix(utils.session, self.id)

        self.set_title(self.item.title)

        builder = Gtk.Builder.new_from_resource(
            "/io/github/nokse22/high-tide/ui/pages_ui/tracks_list_template.ui"
        )

        page_content = builder.get_object("_main")

        auto_load = builder.get_object("_auto_load")
        auto_load.set_scrolled_window(self.scrolled_window)
        auto_load.set_items(self.item.items())

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
            in_my_collection_btn.connect("clicked", self.th_add_to_my_collection),
        ))

        builder.get_object("_share_button").set_visible(False)

        if utils.is_favourited(self.item):
            in_my_collection_btn.set_icon_name("heart-filled-symbolic")

        image = builder.get_object("_image")
        threading.Thread(target=utils.add_image, args=(image, self.item)).start()

        if isinstance(self.item, MixV2):
            self.item = utils.session.mix(self.item.id)

        self.page_content.append(page_content)
        self._page_loaded()

    def th_add_to_my_collection(self, btn):
        utils.on_in_to_my_collection_button_clicked(btn, self.item)
