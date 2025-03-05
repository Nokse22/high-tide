# card_widget.py
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

import threading

from ..lib import utils

from tidalapi.page import PageItem
from tidalapi.mix import MixV2, Mix
from tidalapi.artist import Artist
from tidalapi.album import Album
from tidalapi.media import Track
from tidalapi.playlist import Playlist

from ..lib import variables

from ..disconnectable_iface import IDisconnectable


@Gtk.Template(
    resource_path='/io/github/nokse22/HighTide/ui/widgets/card_widget.ui')
class HTCardWidget(Adw.BreakpointBin, IDisconnectable):
    __gtype_name__ = 'HTCardWidget'

    """It is card that adapts to the content it needs to display,
    it is used when listing artists, albums, mixes and so on"""

    image = Gtk.Template.Child()
    click_gesture = Gtk.Template.Child()
    title_label = Gtk.Template.Child()
    detail_label = Gtk.Template.Child()

    track_artist_label = Gtk.Template.Child()

    def __init__(self, _item):
        IDisconnectable.__init__(self)
        super().__init__()

        self.signals.append((
            self.track_artist_label,
            self.track_artist_label.connect(
                "activate-link", variables.open_uri)))

        self.signals.append((
            self.click_gesture,
            self.click_gesture.connect("released", self.on_click)))

        self.item = _item

        if isinstance(_item, MixV2) or isinstance(_item, Mix):
            self.make_mix_card()
        elif isinstance(_item, Album):
            self.make_album_card()
        elif isinstance(_item, Playlist):
            self.make_playlist_card()
        elif isinstance(_item, Artist):
            self.make_artist_card()
        elif isinstance(_item, PageItem):
            self.make_page_item_card()
        elif isinstance(_item, Track):
            self.make_track_card()

    def make_track_card(self):
        self.title_label.set_label(self.item.name)
        self.title_label.set_tooltip_text(self.item.name)
        self.track_artist_label.set_artists(self.item.artists)
        self.track_artist_label.set_label(
            "Track by {}".format(self.track_artist_label.get_label()))
        self.detail_label.set_visible(False)

        self.item = self.item.album

        threading.Thread(
            target=utils.add_image,
            args=(self.image, self.item)).start()

    def make_mix_card(self):
        self.title_label.set_label(self.item.title)
        self.title_label.set_tooltip_text(self.item.title)
        self.detail_label.set_label(self.item.sub_title)
        self.track_artist_label.set_visible(False)

        threading.Thread(
            target=utils.add_image,
            args=(self.image, self.item)).start()

    def make_album_card(self):
        self.title_label.set_label(self.item.name)
        self.title_label.set_tooltip_text(self.item.name)
        self.track_artist_label.set_artists(self.item.artists)
        self.detail_label.set_visible(False)

        threading.Thread(
            target=utils.add_image,
            args=(self.image, self.item)).start()

    def make_playlist_card(self):
        self.title_label.set_label(self.item.name)
        self.title_label.set_tooltip_text(self.item.name)
        self.track_artist_label.set_visible(False)

        creator = self.item.creator
        if creator:
            creator = creator.name
        else:
            creator = "TIDAL"
        self.detail_label.set_label(f"by {creator.title()}")

        threading.Thread(
            target=utils.add_image,
            args=(self.image, self.item)).start()

    def make_artist_card(self):
        self.title_label.set_label(self.item.name)
        self.title_label.set_tooltip_text(self.item.name)
        self.detail_label.set_label("Artist")
        self.track_artist_label.set_visible(False)

        threading.Thread(
            target=utils.add_image,
            args=(self.image, self.item)).start()

    def make_page_item_card(self):
        self.title_label.set_label(self.item.short_header)
        self.title_label.set_tooltip_text(self.item.short_header)
        self.detail_label.set_label(self.item.short_sub_header)
        self.track_artist_label.set_visible(False)

        threading.Thread(
            target=utils.add_image,
            args=(self.image, self.item)).start()

    def on_click(self, *args):
        if isinstance(self.item, Mix) or isinstance(self.item, MixV2):
            from ..pages import mixPage
            page = mixPage(self.item, f"{self.item.title}")
            page.load()
            variables.navigation_view.push(page)

        elif isinstance(self.item, Album):
            from ..pages import albumPage
            page = albumPage(self.item, f"{self.item.name}")
            page.load()
            variables.navigation_view.push(page)

        elif isinstance(self.item, Playlist):
            from ..pages import playlistPage
            page = playlistPage(self.item, f"{self.item.name}")
            page.load()
            variables.navigation_view.push(page)

        elif isinstance(self.item, Artist):
            from ..pages import artistPage
            page = artistPage(self.item, f"{self.item.name}")
            page.load()
            variables.navigation_view.push(page)

    def __repr__(self, *args):
        return "<CardWidget>"
