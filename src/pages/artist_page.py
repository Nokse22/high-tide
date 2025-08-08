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

from gi.repository import Gtk

from .page import Page
from ..lib import utils

import threading

from gettext import gettext as _


class HTArtistPage(Page):
    """A page to display an artist"""

    __gtype_name__ = "HTArtistPage"

    def _load_async(self) -> None:
        self.artist = utils.get_artist(self.id)

        self.top_tracks = self.artist.get_top_tracks(limit=5)
        self.albums = self.artist.get_albums(limit=10)
        self.albums_ep_singles = self.artist.get_albums_ep_singles(limit=10)
        self.albums_other = self.artist.get_albums_other(limit=10)
        self.similar = self.artist.get_similar()
        self.bio = self.artist.get_bio()

    def _load_finish(self) -> None:
        self.set_title(self.artist.name)

        builder = Gtk.Builder.new_from_resource(
            "/io/github/nokse22/high-tide/ui/pages_ui/artist_page_template.ui"
        )

        self.append(builder.get_object("_main"))

        builder.get_object("_name_label").set_label(self.artist.name)

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

        follow_button = builder.get_object("_follow_button")
        self.signals.append((
            follow_button,
            follow_button.connect(
                "clicked", utils.on_in_to_my_collection_button_clicked, self.artist
            ),
        ))

        share_button = builder.get_object("_share_button")
        self.signals.append((
            share_button,
            share_button.connect("clicked", lambda *_: utils.share_this(self.artist)),
        ))

        if utils.is_favourited(self.artist):
            follow_button.set_icon_name("heart-filled-symbolic")

        artist_picture = builder.get_object("_avatar")

        threading.Thread(
            target=utils.add_image_to_avatar, args=(artist_picture, self.artist)
        ).start()

        builder.get_object("_first_subtitle_label").set_label(_("Artist"))

        self.new_track_list_for(
            _("Top Tracks"), self.top_tracks, self.artist.get_top_tracks
        )

        self.new_carousel_for(_("Albums"), self.albums, self.artist.get_albums)

        self.new_carousel_for(
            _("EP & Singles"), self.albums_ep_singles, self.artist.get_albums_ep_singles
        )

        self.new_carousel_for(
            _("Appears On"), self.albums_other, self.artist.get_albums_other
        )

        self.new_carousel_for(_("Similar Artists"), self.similar)

        if self.bio is None:
            return

        bio = utils.replace_links(self.bio)
        label = Gtk.Label(
            wrap=True,
            css_classes=[],
            margin_start=12,
            margin_end=12,
            margin_bottom=24,
        )
        label.set_markup(bio)
        self.append(
            Gtk.Label(
                wrap=True,
                css_classes=["title-3"],
                margin_start=12,
                label=_("Bio"),
                xalign=0,
                margin_top=12,
                margin_bottom=12,
            )
        )
        self.signals.append((label, label.connect("activate-link", utils.open_uri)))

    def on_play_button_clicked(self, btn) -> None:
        utils.player_object.play_this(self.top_tracks, 0)

    def on_shuffle_button_clicked(self, btn) -> None:
        utils.player_object.shuffle_this(self.top_tracks, 0)

    def on_artist_radio_button_clicked(self, btn) -> None:
        from .track_radio_page import HTHrackRadioPage

        page = HTHrackRadioPage.new_from_id(
            self.artist, _("Radio of {}").format(self.artist.name)
        )
        page.load()
        utils.navigation_view.push(page)
