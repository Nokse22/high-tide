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
from gettext import gettext as _

from gi.repository import Gdk, GObject, Gtk

from ..disconnectable_iface import IDisconnectable
from ..lib import ai, utils
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

    # The cover is swapped for a play icon while the track plays
    shows_playing_icon = True
    # Whether the row lights up when its song plays; off for the queue panel's
    # history, queue and next songs, where only the Now Playing row is the one
    marks_playing = True
    track_title_label = Gtk.Template.Child()
    track_duration_label = Gtk.Template.Child()
    _grid = Gtk.Template.Child()
    explicit_label = Gtk.Template.Child()
    ai_label = Gtk.Template.Child()

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

        # Set by the list showing the song: returns what that list plays from,
        # so a song queued from it says where it's from
        self.source_of = None
        self.track_menu = TrackMenu(self, self.menu_button, track, self.signals)
        self._add_queue_button()
        # The same menu on a right click or a long press, as on song cards
        right_click = Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY)
        long_press = Gtk.GestureLongPress(touch_only=True)
        for gesture in (right_click, long_press):
            self.add_controller(gesture)
            self.signals.append(
                (gesture, gesture.connect("pressed", self._on_menu_requested))
            )

        self.track_album_label.set_album(self.track.album)
        self.track_title_label.set_label(
            self.track.full_name
            if hasattr(self.track, "full_name")
            else self.track.name
        )
        self.artist_label.set_artists(self.track.artists)

        self.explicit_label.set_visible(self.track.explicit)
        self.ai_label.set_visible(ai.is_ai(self.track))

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

    def _on_menu_requested(self, gesture, *args) -> None:
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        x, y = args[-2], args[-1]
        self.track_menu.popup(x, y)

    def _on_player_song_changed(self, *args):
        self._update_now_playing()

    def _on_playing_changed(self, *args):
        self._update_now_playing()

    def hide_playing_icon(self) -> None:
        """Keep showing the cover while the track plays, where it's clear already
        that it's the playing one"""
        self.shows_playing_icon = False
        self._update_now_playing()

    def never_mark_playing(self) -> None:
        """Don't light up when this song plays: the row is a past or future play
        of it (the queue panel), not the one playing"""
        self.marks_playing = False
        self._update_now_playing()

    def _update_now_playing(self):
        is_now = (
            self.marks_playing
            and utils.player_object.playing_track is not None
            and self.track.id == utils.player_object.playing_track.id
        )
        if is_now and utils.player_object.playing and self.shows_playing_icon:
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

    def _add_queue_button(self) -> None:
        """Add to Queue in one click (#259): a button beside the menu, shown and
        clickable only while the pointer is over the row, so lists stay clean.
        Touch screens keep using the menu."""
        self.queue_button = Gtk.Button(
            icon_name="view-list-ordered-symbolic",
            tooltip_text=_("Add to Queue"),
            valign=Gtk.Align.CENTER,
            opacity=0,
            can_target=False,
        )
        self.queue_button.add_css_class("flat")
        self.menu_button.get_parent().insert_child_after(
            self.queue_button, self.track_duration_label
        )
        hover = Gtk.EventControllerMotion()
        self.add_controller(hover)
        self.signals.extend(
            [
                (
                    self.queue_button,
                    self.queue_button.connect("clicked", self._on_queue_clicked),
                ),
                (hover, hover.connect("enter", lambda *_: self._show_queue_button(True))),
                (hover, hover.connect("leave", lambda *_: self._show_queue_button(False))),
            ]
        )

    def _show_queue_button(self, shown: bool) -> None:
        self.queue_button.set_opacity(1 if shown else 0)
        self.queue_button.set_can_target(shown)

    def _on_queue_clicked(self, *args) -> None:
        source = self.source_of() if self.source_of else None
        utils.player_object.add_to_queue(self.track, source)
        utils.show_queued_toast()

    def hide_queue_button(self) -> None:
        """For rows in the queue itself"""
        self.queue_button.set_visible(False)

    def add_remove_button(self, on_clicked) -> None:
        """Add a button that removes the track from the list it's shown in.

        Args:
            on_clicked: Called with this row when the button is clicked
        """
        button = Gtk.Button(
            icon_name="window-close-symbolic",
            tooltip_text=_("Remove"),
            valign=Gtk.Align.CENTER,
        )
        button.add_css_class("flat")
        self.signals.append(
            (button, button.connect("clicked", lambda *a: on_clicked(self)))
        )
        self.menu_button.get_parent().insert_child_after(
            button, self.track_duration_label
        )

    def add_drag_handle(self) -> Gtk.Widget:
        """Add a handle to drag the row by, at its start, and return it"""
        handle = Gtk.Image(
            icon_name="list-drag-handle-symbolic",
            tooltip_text=_("Drag to move"),
            margin_end=6,
        )
        handle.add_css_class("dim-label")
        handle.set_cursor_from_name("grab")
        self.menu_button.get_parent().prepend(handle)
        return handle
