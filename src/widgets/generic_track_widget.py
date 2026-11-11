# generic_track_widget.py
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

from gi.repository import GObject, Gtk

from ..disconnectable_iface import IDisconnectable
from ..lib import utils
from .track_menu import TrackMenu

import logging

logger = logging.getLogger(__name__)


@Gtk.Template(
    resource_path="/io/github/nokse22/high-tide/ui/widgets/generic_track_widget.ui"
)
class HTGenericTrackWidget(Gtk.ListBoxRow, IDisconnectable):
    """A widget for displaying a single track with playback and menu options.

    This widget shows track information including title, artist, album, duration,
    and cover art. It provides context menu actions for playing, adding to queue,
    adding to playlists, and other track-related operations.
    """

    __gtype_name__ = "HTGenericTrackWidget"

    image = Gtk.Template.Child()
    now_playing_indicator = Gtk.Template.Child()
    album_stack = Gtk.Template.Child()
    track_title_label = Gtk.Template.Child()
    track_duration_label = Gtk.Template.Child()
    _grid = Gtk.Template.Child()
    explicit_label = Gtk.Template.Child()

    artist_label = Gtk.Template.Child()
    artist_label_2 = Gtk.Template.Child()
    track_album_label = Gtk.Template.Child()

    menu_button = Gtk.Template.Child()

    index = GObject.Property(type=int, default=0)

    def __init__(self, track):
        IDisconnectable.__init__(self)
        super().__init__()

        self.track = track

        self.signals.append(
            (
                self.artist_label,
                self.artist_label.connect("activate-link", utils.open_uri),
            )
        )
        self.signals.append(
            (
                self.artist_label_2,
                self.artist_label_2.connect("activate-link", utils.open_uri),
            )
        )
        self.signals.append(
            (
                self.track_album_label,
                self.track_album_label.connect("activate-link", utils.open_uri),
            )
        )

        self.track_menu = TrackMenu(self, self.menu_button, track, self.signals)

        self.track_album_label.set_album(self.track.album)
        self.track_title_label.set_label(
            self.track.full_name
            if hasattr(self.track, "full_name")
            else self.track.name
        )
        self.artist_label.set_artists(self.track.artists)

        self.explicit_label.set_visible(self.track.explicit)

        self.track_duration_label.set_label(utils.pretty_duration(self.track.duration))

        if not self.track.available:
            self.set_activatable(False)
            self.set_sensitive(False)

        self._update_now_playing()
        self.signals.append((
            utils.player_object,
            utils.player_object.connect("song-changed", self._on_player_song_changed),
        ))
        self.signals.append((
            utils.player_object,
            utils.player_object.connect(
                "notify::playing", self._on_playing_changed
            ),
        ))

        threading.Thread(
            target=utils.add_image, args=(self.image, self.track.album)
        ).start()

    def _on_player_song_changed(self, *args):
        self._update_now_playing()

    def _on_playing_changed(self, *args):
        self._update_now_playing()

    def _update_now_playing(self):
        is_now = (
            utils.player_object.playing_track is not None
            and self.track.id == utils.player_object.playing_track.id
        )
        if is_now and utils.player_object.playing:
            self.album_stack.set_visible_child(self.now_playing_indicator)
        else:
            self.album_stack.set_visible_child(self.image)

        if is_now:
            self.add_css_class("now-playing")
        else:
            self.remove_css_class("now-playing")

    def set_playlist(self, playlist, on_removed=None):
        """Show a "Remove from this playlist" option for one of the user's
        playlists.

        Args:
            playlist: The playlist the track is shown in
            on_removed: Called after the track is removed from the playlist
        """
        self.track_menu.set_playlist(playlist, on_removed)
