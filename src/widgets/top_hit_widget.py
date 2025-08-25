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

from gi.repository import Gtk, GLib

from tidalapi.mix import Mix
from tidalapi.artist import Artist
from tidalapi.album import Album
from tidalapi.media import Track
from tidalapi.playlist import Playlist

from ..lib import utils
from ..disconnectable_iface import IDisconnectable
import threading

from gettext import gettext as _


@Gtk.Template(resource_path="/io/github/nokse22/high-tide/ui/widgets/top_hit_widget.ui")
class HTTopHitWidget(Gtk.Box, IDisconnectable):
    """A widget to display the top hit when searching"""

    __gtype_name__ = "HTTopHitWidget"

    image = Gtk.Template.Child()
    primary_label = Gtk.Template.Child()
    secondary_label = Gtk.Template.Child()
    play_button = Gtk.Template.Child()
    shuffle_button = Gtk.Template.Child()
    artist_label = Gtk.Template.Child()
    click_gesture = Gtk.Template.Child()

    def __init__(self, _item):
        IDisconnectable.__init__(self)
        super().__init__()

        self.signals.append((
            self.artist_label,
            self.artist_label.connect("activate-link", utils.open_uri),
        ))

        self.item = _item

        self.action = None

        if isinstance(_item, Mix):
            self._make_mix()
            self.action = "win.push-mix-page"
        elif isinstance(_item, Album):
            self._make_album()
            self.action = "win.push-album-page"
        elif isinstance(_item, Playlist):
            self._make_playlist()
            self.action = "win.push-playlist-page"
        if isinstance(_item, Artist):
            self._make_artist()
            self.action = "win.push-artist-page"
        elif isinstance(_item, Track):
            self._make_track()

        self.signals.append((
            self.click_gesture,
            self.click_gesture.connect("released", self._on_click),
        ))

    def _on_click(self, *args) -> None:
        if self.action:
            self.activate_action(self.action, GLib.Variant("s", str(self.item.id)))

    def _make_track(self) -> None:
        self.primary_label.set_label(self.item.name)
        self.secondary_label.set_label(_("Track"))

        self.artist_label.set_visible(True)
        self.artist_label.set_artists(self.item.artists)

        self.shuffle_button.set_visible(False)

        self.signals.append((
            self.play_button,
            self.play_button.connect(
                "clicked", lambda *args: utils.player_object.play_track(self.item)
            ),
        ))

        threading.Thread(
            target=utils.add_image, args=(self.image, self.item.album)
        ).start()

    def _make_mix(self) -> None:
        self.primary_label.set_label(self.item.title)
        self.secondary_label.set_label(_("Mix"))

        self.artist_label.set_visible(True)
        self.artist_label.set_label(self.item.sub_title)

        self.signals.append((
            self.play_button,
            self.play_button.connect(
                "clicked", lambda *_: utils.player_object.play_this(self.item)
            ),
        ))

        self.signals.append((
            self.play_button,
            self.play_button.connect(
                "clicked", lambda *_: utils.player_object.shuffle_this(self.item)
            ),
        ))

        threading.Thread(target=utils.add_image, args=(self.image, self.item)).start()

    def _make_album(self) -> None:
        self.primary_label.set_label(self.item.name)
        self.secondary_label.set_label(_("Album"))

        self.artist_label.set_visible(True)
        self.artist_label.set_artists([self.item.artist])

        self.signals.append((
            self.play_button,
            self.play_button.connect(
                "clicked", lambda *_: utils.player_object.play_this(self.item)
            ),
        ))

        self.signals.append((
            self.play_button,
            self.play_button.connect(
                "clicked", lambda *_: utils.player_object.shuffle_this(self.item)
            ),
        ))

        threading.Thread(target=utils.add_image, args=(self.image, self.item)).start()

    def _make_playlist(self) -> None:
        self.primary_label.set_label(self.item.name)

        creator_name = "TIDAL"
        if self.item.creator is not None and self.item.creator.name is not None:
            creator_name = self.item.creator.name
        self.secondary_label.set_label(_("By {}").format(creator_name))

        self.signals.append((
            self.play_button,
            self.play_button.connect(
                "clicked", lambda *_: utils.player_object.play_this(self.item)
            ),
        ))

        self.signals.append((
            self.play_button,
            self.play_button.connect(
                "clicked", lambda *_: utils.player_object.shuffle_this(self.item)
            ),
        ))

        threading.Thread(target=utils.add_image, args=(self.image, self.item)).start()

    def _make_artist(self) -> None:
        self.primary_label.set_label(self.item.name)
        self.secondary_label.set_label(_("Artist"))

        self.play_button.set_visible(False)
        self.shuffle_button.set_visible(False)

        threading.Thread(target=utils.add_image, args=(self.image, self.item)).start()
