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


from gi.repository import Gtk
from gi.repository import Gio, GLib
from ..lib import utils
from ..disconnectable_iface import IDisconnectable

from tidalapi import UserPlaylist, Track

import threading

from gettext import gettext as _


@Gtk.Template(
    resource_path="/io/github/nokse22/high-tide/ui/widgets/generic_track_widget.ui"
)
class HTGenericTrackWidget(Gtk.ListBoxRow, IDisconnectable):
    """It is used to display a single track"""

    __gtype_name__ = "HTGenericTrackWidget"

    image = Gtk.Template.Child()
    track_title_label = Gtk.Template.Child()
    track_duration_label = Gtk.Template.Child()
    playlists_submenu = Gtk.Template.Child()
    _grid = Gtk.Template.Child()
    explicit_label = Gtk.Template.Child()

    artist_label = Gtk.Template.Child()
    artist_label_2 = Gtk.Template.Child()
    track_album_label = Gtk.Template.Child()

    menu_button = Gtk.Template.Child()
    track_menu = Gtk.Template.Child()

    def __init__(self, _track=None, is_album=False):
        IDisconnectable.__init__(self)
        super().__init__()
        if not _track:
            return

        self.menu_activated = False

        self.set_track(_track, is_album)

    def set_track(self, track : Track, is_album=False):
        """Set the track for HTGenericTrackWidget

        Args:
            track: the track
            is_album (bool): if this track is in an album view"""
        self.signals.append((
            self.artist_label,
            self.artist_label.connect("activate-link", utils.open_uri),
        ))
        self.signals.append((
            self.artist_label_2,
            self.artist_label_2.connect("activate-link", utils.open_uri),
        ))
        self.signals.append((
            self.track_album_label,
            self.track_album_label.connect("activate-link", utils.open_uri),
        ))

        self.signals.append((
            self.menu_button,
            self.menu_button.connect("notify::active", self._on_menu_activate),
        ))

        self.track = track

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

        threading.Thread(
            target=utils.add_image, args=(self.image, self.track.album)
        ).start()

        self.action_group = Gio.SimpleActionGroup()
        self.insert_action_group("trackwidget", self.action_group)

    def _on_menu_activate(self, *args):
        if self.menu_activated:
            return

        self.menu_activated = True

        self.track_menu.prepend(
            _("Go to track radio"), f"win.push-track-radio-page::{self.track.id}"
        )

        self.track_menu.prepend(
            _("Go to album"), f"win.push-album-page::{self.track.album.id}"
        )

        action_entries = [
            ("play-next", self._play_next),
            ("add-to-queue", self._add_to_queue),
            ("add-to-my-collection", self._th_add_to_my_collection),
            ("copy-share-url", self._copy_share_url),
        ]

        add_to_playlist_action = Gio.SimpleAction.new(
            "add-to-playlist", GLib.VariantType.new("n")
        )
        self.signals.append((
            add_to_playlist_action,
            add_to_playlist_action.connect("activate", self._add_to_playlist),
        ))
        self.action_group.add_action(add_to_playlist_action)

        for index, playlist in enumerate(utils.user_playlists):
            if index > 10:
                break
            item = Gio.MenuItem.new()
            item.set_label(playlist.name)
            item.set_action_and_target_value(
                "trackwidget.add-to-playlist", GLib.Variant.new_int16(index)
            )
            self.playlists_submenu.insert_item(index, item)

        for name, callback in action_entries:
            action = Gio.SimpleAction.new(name, None)
            self.signals.append((action, action.connect("activate", callback)))
            self.action_group.add_action(action)

    def _play_next(self, *args):
        utils.player_object.add_next(self.track)

    def _add_to_queue(self, *args):
        utils.player_object.add_to_queue(self.track)

    def _th_add_to_my_collection(self, *args):
        threading.Thread(target=self.th_add_to_my_collection, args=()).start()

    def th_add_to_my_collection(self):
        utils.session.user.favorites.add_track(self.track.id)

    def _add_to_playlist(self, action, parameter):
        playlist_index = parameter.get_int16()
        selected_playlist = utils.user_playlists[playlist_index]

        if isinstance(selected_playlist, UserPlaylist):
            selected_playlist.add([self.track.id])

            print(f"Added to playlist: {selected_playlist.name}")

    def _copy_share_url(self, *args):
        utils.share_this(self.track)

    def __repr__(self, *args):
        return "<TrackWidget>"
