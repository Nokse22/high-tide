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

from ..lib import utils
from ..widgets import HTCarouselWidget
from ..widgets import HTTracksListWidget

import threading

from .page import Page

from tidalapi.artist import Artist

from ..lib import utils
from ..disconnectable_iface import IDisconnectable

from gettext import gettext as _


class HTArtistPage(Page):
    __gtype_name__ = 'HTArtistPage'

    """It is used to display an artist page"""

    # TODO Add missing features: influences, appears on, credits and so on

    def __init__(self, _id):
        IDisconnectable.__init__(self)
        super().__init__()

        self.top_tracks = []
        self.id = _id
        self.artist = None

    def _th_load_page(self):
        self.artist = Artist(utils.session, self.id)

        self.set_title(self.artist.name)

        builder = Gtk.Builder.new_from_resource(
            "/io/github/nokse22/HighTide/ui/pages_ui/artist_page_template.ui")

        page_content = builder.get_object("_main")
        # top_tracks_list_box = builder.get_object("_top_tracks_list_box")
        self.content_box = builder.get_object("_content_box")

        builder.get_object("_name_label").set_label(self.artist.name)

        play_btn = builder.get_object("_play_button")
        self.signals.append((
            play_btn,
            play_btn.connect("clicked", self.on_play_button_clicked)))

        shuffle_btn = builder.get_object("_shuffle_button")
        self.signals.append((
            shuffle_btn,
            shuffle_btn.connect("clicked", self.on_shuffle_button_clicked)))

        follow_button = builder.get_object("_follow_button")
        self.signals.append((
            follow_button,
            follow_button.connect(
                "clicked",
                utils.on_in_to_my_collection_button_clicked,
                self.artist)))

        share_button = builder.get_object("_share_button")
        self.signals.append((
            share_button,
            share_button.connect(
                "clicked",
                lambda *_: utils.share_this(self.artist))))

        if (utils.is_favourited(self.artist)):
            follow_button.set_icon_name("heart-filled-symbolic")

        artist_picture = builder.get_object("_avatar")

        threading.Thread(
            target=utils.add_image_to_avatar,
            args=(artist_picture, self.artist)).start()

        builder.get_object("_first_subtitle_label").set_label("Artist")

        self.top_tracks = self.artist.get_top_tracks()

        tracks_list_widget = HTTracksListWidget("Top Tracks")
        self.disconnectables.append(tracks_list_widget)
        tracks_list_widget.set_function(self.artist.get_top_tracks)
        self.content_box.append(tracks_list_widget)

        self.make_content()
        self.make_bio()

        self.page_content.append(page_content)
        self._page_loaded()

    def make_content(self):
        carousel = self.get_carousel("Albums")
        try:
            albums = self.artist.get_albums(limit=10)
            carousel.set_more_function("album", self.artist.get_albums)
        except Exception as e:
            print(e)
        else:
            if len(albums) != 0:
                self.content_box.append(carousel)
                carousel.set_items(albums, "album")

        carousel = self.get_carousel("EP & Singles")
        try:
            albums = self.artist.get_albums_ep_singles(limit=10)
            carousel.set_more_function(
                "album", self.artist.get_albums_ep_singles)
        except Exception as e:
            print(e)
        else:
            if len(albums) != 0:
                self.content_box.append(carousel)
                carousel.set_items(albums, "album")

        carousel = self.get_carousel("Appears On")
        try:
            albums = self.artist.get_albums_other(limit=10)
            carousel.set_more_function("album", self.artist.get_albums_other)
        except Exception as e:
            print(e)
        else:
            if len(albums) != 0:
                self.content_box.append(carousel)
                carousel.set_items(albums, "album")

        carousel = self.get_carousel("Similar Artists")
        try:
            artists = self.artist.get_similar()
        except Exception as e:
            print("could not find similar artists", e)
        else:
            if len(artists) != 0:
                self.content_box.append(carousel)
                carousel.set_items(artists, "artist")

    def make_bio(self):
        try:
            bio = self.artist.get_bio()
        except Exception as e:
            print(e)
        else:
            bio = utils.replace_links(bio)
            label = Gtk.Label(
                wrap=True,
                css_classes=[],
                margin_start=12,
                margin_end=12,
                margin_bottom=24)
            label.set_markup(bio)
            self.content_box.append(
                Gtk.Label(
                    wrap=True,
                    css_classes=["title-3"],
                    margin_start=12,
                    label=_("Bio"),
                    xalign=0,
                    margin_top=12,
                    margin_bottom=12))
            self.content_box.append(label)
            self.signals.append(
                (label, label.connect("activate-link", utils.open_uri))
            )

    def on_row_selected(self, list_box, row):
        index = int(row.get_name())
        utils.player_object.play_this(self.item, index)

    def on_play_button_clicked(self, btn):
        utils.player_object.play_this(self.top_tracks, 0)

    def on_shuffle_button_clicked(self, btn):
        utils.player_object.shuffle_this(self.top_tracks, 0)

    def on_artist_radio_button_clicked(self, btn):
        from .track_radio_page import HTHrackRadioPage
        page = HTHrackRadioPage(self.artist, f"Radio of {self.artist.name}")
        page.load()
        utils.navigation_view.push(page)
