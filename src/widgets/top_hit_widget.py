# top_hit_widget.py
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

from tidalapi.page import PageItem
from tidalapi.mix import Mix
from tidalapi.artist import Artist
from tidalapi.album import Album
from tidalapi.media import Track
from tidalapi.playlist import Playlist

from ..lib import utils
from ..lib import variables
from ..disconnectable_iface import IDisconnectable
import threading


@Gtk.Template(
    resource_path='/io/github/nokse22/HighTide/ui/widgets/top_hit_widget.ui')
class HTTopHitWidget(Gtk.Box, IDisconnectable):
    __gtype_name__ = 'HTTopHitWidget'

    """It is used to display the top hit when searching regardless
    of the type"""

    artist_avatar = Gtk.Template.Child()
    artist_label = Gtk.Template.Child()
    play_button = Gtk.Template.Child()
    shuffle_button = Gtk.Template.Child()
    # track_artist_label = Gtk.Template.Child()
    # track_artist_button = Gtk.Template.Child()

    def __init__(self, _item):
        IDisconnectable.__init__(self)
        super().__init__()

        self.signals.append((
            self,
            self.connect("unrealize", self.__on_unrealized)))

        self.item = _item

        # if isinstance(_item, Mix):
        #     self.make_mix_card()
        # elif isinstance(_item, Album):
        #     self.make_album_card()
        # elif isinstance(_item, Playlist):
        #     self.make_playlist_card()
        if isinstance(_item, Artist):
            self.make_artist()
        # elif isinstance(_item, Track):
        #     self.make_track()
        elif isinstance(_item, PageItem):
            self.make_page_item_card()

    def make_track(self):
        self.artist_label.set_text(self.item.name)

        threading.Thread(
            target=utils.add_image_to_avatar,
            args=(self.artist_avatar, self.item.album.artist)).start()

    def make_mix_card(self):
        self.title_label.set_text(self.item.title)
        self.detail_label.set_text(self.item.sub_title)
        self.track_artist_label.set_visible(False)

        # self.signals.append(
        #     (self.play_button, self.play_button.connect("clicked", self.on_))
        # )
        # self.signals.append(
        #     (self.shuffle_button, self.shuffle_button.connect("clicked", self.on_))
        # )

        threading.Thread(
            target=utils.add_image,
            args=(self.image, self.item)).start()

    def make_album_card(self):
        self.title_label.set_text(self.item.name)
        self.track_artist_label.set_text(self.item.artist.name)
        self.detail_label.set_visible(False)

        threading.Thread(
            target=utils.add_image,
            args=(self.image, self.item)).start()

    def make_playlist_card(self):
        self.title_label.set_text(self.item.name)
        self.track_artist_label.set_visible(False)

        creator = self.item.creator
        if creator:
            creator = creator.name
        else:
            creator = "TIDAL"
        self.detail_label.set_text(f"by {creator}")

        threading.Thread(
            target=utils.add_image,
            args=(self.image, self.item)).start()

    def make_artist(self):
        self.artist_label.set_text(self.item.name)

        threading.Thread(
            target=utils.add_image_to_avatar,
            args=(self.artist_avatar, self.item)).start()

    def make_page_item_card(self):
        self.title_label.set_text(self.item.short_header)
        self.detail_label.set_text(self.item.short_sub_header)
        self.track_artist_label.set_visible(False)

        threading.Thread(
            target=utils.add_image,
            args=(self.image, self.item)).start()

    def _on_artist_button_clicked(self, *args):
        from ..pages.artist_page import artistPage
        page = artistPage(self.item.artist, f"{self.item.artist.name}")
        page.load()
        variables.navigation_view.push(page)

    def _on_image_button_clicked(self, *args):
        if isinstance(self.item, Mix):
            from ..pages.mix_page import mixPage
            page = mixPage(self.item, f"{self.item.title}")
            page.load()
            variables.navigation_view.push(page)

        elif isinstance(self.item, Album):
            from ..pages.album_page import albumPage
            page = albumPage(self.item, f"{self.item.name}")
            page.load()
            variables.navigation_view.push(page)

        elif isinstance(self.item, Playlist):
            from ..pages.playlist_page import playlistPage
            page = playlistPage(self.item, f"{self.item.name}")
            page.load()
            variables.navigation_view.push(page)

        elif isinstance(self.item, Artist):
            from ..pages.artist_page import artistPage
            page = artistPage(self.item, f"{self.item.name}")
            page.load()
            variables.navigation_view.push(page)

        elif isinstance(self.item, Track):
            from ..pages.artist_page import albumPage
            page = artistPage(self.item.album, f"{self.item.album.name}")
            page.load()
            variables.navigation_view.push(page)

    def __repr__(self, *args):
        return "<HTCardWidget>"
