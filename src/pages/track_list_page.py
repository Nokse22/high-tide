# track_list_page.py
#
# Copyright 2023 p0ryae
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

import threading
from gettext import gettext as _
from ..lib import utils
from .page import Page


class TrackListPage(Page):
    """Base class for pages displaying a list of tracks with sorting and autoload"""

    __gtype_name__ = "TrackListPage"

    original_tracks = []
    current_sort = 0
    auto_load = None

    def _setup_ui(
        self, builder, title, subtitle, tracks, reload_function=None, hide_share=False
    ):
        self.append(builder.get_object("_main"))

        self.auto_load = builder.get_object("_auto_load")
        self.auto_load.set_scrolled_window(self.scrolled_window)
        self.auto_load.set_items(tracks)
        if reload_function:
            self.auto_load.set_function(reload_function)

        builder.get_object("_title_label").set_label(title)
        builder.get_object("_first_subtitle_label").set_label(subtitle)
        builder.get_object("_second_subtitle_label").set_label(
            _("{} tracks ({})").format(
                len(tracks),
                utils.pretty_duration(sum((t.duration or 0) for t in tracks)),
            )
        )

        play_btn = builder.get_object("_play_button")
        shuffle_btn = builder.get_object("_shuffle_button")
        in_my_collection_btn = builder.get_object("_in_my_collection_button")
        share_button = builder.get_object("_share_button")

        self.signals.extend(
            [
                (play_btn, play_btn.connect("clicked", self.on_play_button_clicked)),
                (
                    shuffle_btn,
                    shuffle_btn.connect("clicked", self.on_shuffle_button_clicked),
                ),
                (
                    in_my_collection_btn,
                    in_my_collection_btn.connect(
                        "clicked",
                        utils.on_in_to_my_collection_button_clicked,
                        getattr(self, "item", None),
                    ),
                ),
            ]
        )

        if hide_share:
            share_button.set_visible(False)
        else:
            self.signals.append(
                (
                    share_button,
                    share_button.connect(
                        "clicked",
                        lambda *_: utils.share_this(getattr(self, "item", None)),
                    ),
                )
            )

        if getattr(self, "item", None) and utils.is_favourited(self.item):
            in_my_collection_btn.set_icon_name("heart-filled-symbolic")

        image = builder.get_object("_image")
        if getattr(self, "item", None):
            threading.Thread(target=utils.add_image, args=(image, self.item)).start()

        sort_dropdown = builder.get_object("_sort_by_dropdown")
        sort_dropdown.connect("notify::selected", self.on_sort_changed)

    def on_sort_changed(self, dropdown, _pspec):
        selected = dropdown.get_selected()
        if selected == self.current_sort:
            return
        self.current_sort = selected

        valid_tracks = [t for t in self.original_tracks if t is not None]

        sort_map = {
            0: lambda tracks: tracks.copy(),
            1: lambda tracks: sorted(
                tracks, key=lambda t: t.name.lower() if t.name else ""
            ),
            2: lambda tracks: sorted(
                tracks,
                key=lambda t: (
                    t.artist.name.lower() if t.artist and t.artist.name else ""
                ),
            ),
            3: lambda tracks: sorted(
                tracks,
                key=lambda t: t.album.name.lower() if t.album and t.album.name else "",
            ),
            4: lambda tracks: sorted(tracks, key=lambda t: t.duration or 0),
        }

        sorted_tracks = sort_map.get(selected, lambda t: t.copy())(valid_tracks)

        if selected == 0 and hasattr(self.item, "tracks"):
            self.auto_load.set_function(getattr(self.item, "tracks", None))
        else:
            self.auto_load.set_function(None)

        self.auto_load.set_items(sorted_tracks)
