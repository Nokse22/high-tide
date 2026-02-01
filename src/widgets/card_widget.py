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

import threading
from gettext import gettext as _
from typing import Union

from gi.repository import Adw, GLib, Gtk

from tidalapi.album import Album
from tidalapi.artist import Artist
from tidalapi.mix import Mix, MixV2
from tidalapi.playlist import Playlist
from tidalapi.media import Track
from tidalapi.page import PageItem

from ..disconnectable_iface import IDisconnectable
from ..lib import utils


@Gtk.Template(resource_path="/io/github/nokse22/high-tide/ui/widgets/card_widget.ui")
class HTCardWidget(Adw.BreakpointBin, IDisconnectable):
    """A card widget that adapts to display different types of TIDAL content.

    This widget automatically configures itself based on the type of TIDAL item
    it receives (Track, Album, Artist, Playlist, Mix) and displays appropriate
    information and imagery. It handles click events to navigate to detail pages
    or start playback for tracks.
    """

    __gtype_name__ = "HTCardWidget"

    image = Gtk.Template.Child()
    click_gesture = Gtk.Template.Child()
    title_label = Gtk.Template.Child()
    detail_label = Gtk.Template.Child()

    track_artist_label = Gtk.Template.Child()

    def __init__(self, item: Union[Track, Album, Artist, Playlist, Mix, MixV2]) -> None:
        """Initialize the card widget with a TIDAL item.

        Args:
            item: A TIDAL object (Track, Album, Artist, Playlist, or Mix) to display
        """
        IDisconnectable.__init__(self)
        super().__init__()

        self.signals.append(
            (
                self.track_artist_label,
                self.track_artist_label.connect("activate-link", utils.open_uri),
            )
        )

        self.signals.append(
            (
                self.click_gesture,
                self.click_gesture.connect("released", self._on_click),
            )
        )

        self.item: Union[Track, Album, Artist, Playlist, Mix, MixV2] = item

        self.action: str | None = None

        self._populate()

    def _populate(self):
        if isinstance(self.item, MixV2) or isinstance(self.item, Mix):
            self._make_mix_card()
            self.action = "win.push-mix-page"
        elif isinstance(self.item, Album):
            self._make_album_card()
            self.action = "win.push-album-page"
        elif isinstance(self.item, Playlist):
            self._make_playlist_card()
            self.action = "win.push-playlist-page"
        elif isinstance(self.item, Artist):
            self._make_artist_card()
            self.action = "win.push-artist-page"
        elif isinstance(self.item, Track):
            self._make_track_card()
        elif isinstance(self.item, PageItem):
            self._make_page_item_card()

    def _make_track_card(self) -> None:
        """Configure the card to display a Track item"""
        self.title_label.set_label(self.item.name)
        self.title_label.set_tooltip_text(self.item.name)
        self.track_artist_label.set_artists(self.item.artists)
        self.track_artist_label.set_label(
            _("Track by {}").format(self.track_artist_label.get_label())
        )
        self.detail_label.set_visible(False)

        threading.Thread(
            target=utils.add_image, args=(self.image, self.item.album)
        ).start()

    def _make_mix_card(self) -> None:
        """Configure the card to display a Mix item"""
        self.title_label.set_label(self.item.title)
        self.title_label.set_tooltip_text(self.item.title)
        self.detail_label.set_label(self.item.sub_title)
        self.track_artist_label.set_visible(False)

        threading.Thread(target=utils.add_image, args=(self.image, self.item)).start()

    def _make_album_card(self) -> None:
        """Configure the card to display an Album item"""
        self.title_label.set_label(self.item.name)
        self.title_label.set_tooltip_text(self.item.name)
        self.track_artist_label.set_artists(self.item.artists)
        self.detail_label.set_visible(False)

        threading.Thread(target=utils.add_image, args=(self.image, self.item)).start()

    def _make_playlist_card(self) -> None:
        """Configure the card to display a Playlist item"""
        self.title_label.set_label(self.item.name)
        self.title_label.set_tooltip_text(self.item.name)
        self.track_artist_label.set_visible(False)

        creator_name = "TIDAL"
        if self.item.creator is not None and self.item.creator.name is not None:
            creator_name = self.item.creator.name
        self.detail_label.set_label(_("By {}").format(creator_name))

        threading.Thread(target=utils.add_image, args=(self.image, self.item)).start()

    def _make_artist_card(self) -> None:
        """Configure the card to display an Artist item"""
        self.title_label.set_label(self.item.name)
        self.title_label.set_tooltip_text(self.item.name)
        self.detail_label.set_label(_("Artist"))
        self.track_artist_label.set_visible(False)

        threading.Thread(target=utils.add_image, args=(self.image, self.item)).start()

    def _make_page_item_card(self) -> None:
        """Configure the card to display a PageItem"""

        def _get_item():
            if self.item.type == "PLAYLIST":
                self.item = utils.get_playlist(self.item.artifact_id)
            elif self.item.type == "TRACK":
                self.item = utils.get_track(self.item.artifact_id)
            elif self.item.type == "ARTIST":
                self.item = utils.get_artist(self.item.artifact_id)
            elif self.item.type == "ALBUM":
                self.item = utils.get_album(self.item.artifact_id)

            GLib.idle_add(self._populate)

        threading.Thread(target=_get_item).start()

    def _on_click(self, *args) -> None:
        """Handle click events on the card.

        For non-track items, activates the appropriate navigation action to show
        the detail page. For track items, starts playback immediately.
        """
        if self.action:
            self.activate_action(self.action, GLib.Variant("s", str(self.item.id)))
        elif isinstance(self.item, Track):
            utils.player_object.play_this(self.item)
        elif isinstance(self.item, PageItem) and self.item.type == "TRACK":

            def _get():
                utils.player_object.play_this(self.item.get())

            threading.Thread(target=_get).start()
