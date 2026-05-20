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

import logging
import threading
from gettext import gettext as _
from typing import List
from functools import partial

from gi.repository import GLib, Gtk

from tidalapi.album import Album
from tidalapi.artist import Artist
from tidalapi.media import Track

from ..lib import utils
from .page import Page

logger = logging.getLogger(__name__)


class HTArtistPage(Page):
    """A page to display an artist"""

    __gtype_name__ = "HTArtistPage"

    top_tracks: List[Track] = []
    albums: List[Album] = []
    albums_ep_singles = []
    albums_other = []
    similar: List[Artist] = []
    bio: str = ""

    def _load_async(self) -> None:
        try:
            self.artist = utils.get_artist(self.id)
        except Exception as e:
            logger.exception(f"Failed to load artist with id {self.id}: {e}")
            self.artist = None
            return  # can't continue if artist is missing

        try:
            self.top_tracks = self.artist.get_top_tracks(limit=5)
        except Exception as e:
            logger.warning(f"Failed to load top tracks for {self.artist}: {e}")
            self.top_tracks = []

        try:
            self.albums = utils.get_albums(self.artist, post_limit=10)
        except Exception as e:
            logger.warning(f"Failed to load albums for {self.artist}: {e}")
            self.albums = []

        try:
            self.albums_ep_singles = utils.get_albums_ep_singles(
                self.artist, post_limit=10
            )
        except Exception as e:
            logger.warning(f"Failed to load EPs/singles for {self.artist}: {e}")
            self.albums_ep_singles = []

        try:
            self.albums_other = utils.get_albums_other(self.artist, post_limit=10)
        except Exception as e:
            logger.warning(f"Failed to load other albums for {self.artist}: {e}")
            self.albums_other = []

        try:
            self.similar = self.artist.get_similar()
        except Exception as e:
            logger.warning(f"Failed to load similar artists for {self.artist}: {e}")
            self.similar = []

        try:
            self.bio = self.artist.get_bio()
        except Exception as e:
            logger.warning(f"Failed to load bio for {self.artist}: {e}")
            self.bio = ""

    def _load_finish(self) -> None:
        self.set_title(self.artist.name)

        builder = Gtk.Builder.new_from_resource(
            "/io/github/nokse22/high-tide/ui/pages_ui/artist_page_template.ui"
        )

        self.append(builder.get_object("_main"))

        builder.get_object("_name_label").set_label(self.artist.name)

        play_btn = builder.get_object("_play_button")
        self.signals.append(
            (
                play_btn,
                play_btn.connect("clicked", self.on_play_button_clicked),
            )
        )

        shuffle_btn = builder.get_object("_shuffle_button")
        self.signals.append(
            (
                shuffle_btn,
                shuffle_btn.connect("clicked", self.on_shuffle_button_clicked),
            )
        )

        follow_button = builder.get_object("_follow_button")
        self.signals.append(
            (
                follow_button,
                follow_button.connect(
                    "clicked", utils.on_in_to_my_collection_button_clicked, self.artist
                ),
            )
        )

        share_button = builder.get_object("_share_button")
        self.signals.append(
            (
                share_button,
                share_button.connect(
                    "clicked", lambda *_: utils.share_this(self.artist)
                ),
            )
        )

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

        self.new_carousel_for(
            _("Albums"),
            self.albums,
            partial(
                utils.get_albums,
                self.artist,
            ),
        )

        self.new_carousel_for(
            _("EP & Singles"),
            self.albums_ep_singles,
            partial(
                utils.get_albums_ep_singles,
                self.artist,
            ),
        )

        self.new_carousel_for(
            _("Appears On"),
            self.albums_other,
            partial(
                utils.get_albums_other,
                self.artist,
            ),
        )

        self.new_carousel_for(_("Similar Artists"), self.similar)

        builder.get_object("_radio_button").set_action_target_value(
            GLib.Variant("s", str(self.artist.id))
        )

        if self.bio == "":
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
        self.append(label)
        self.signals.append((label, label.connect("activate-link", utils.open_uri)))

    def on_play_button_clicked(self, btn) -> None:
        utils.player_object.play_this(self.top_tracks, 0)

    def on_shuffle_button_clicked(self, btn) -> None:
        utils.player_object.shuffle_this(self.top_tracks, 0)
