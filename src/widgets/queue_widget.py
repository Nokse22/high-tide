# queue_widget.py
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

from ..widgets import HTGenericTrackWidget


@Gtk.Template(resource_path="/io/github/nokse22/high-tide/ui/widgets/queue_widget.ui")
class HTQueueWidget(Gtk.Box):
    """It is used to display the track queue, including played tracks,
    tracks to play and tracks added to the queue"""

    __gtype_name__ = "HTQueueWidget"

    played_songs_list = Gtk.Template.Child()
    queued_songs_list = Gtk.Template.Child()
    next_songs_list = Gtk.Template.Child()

    played_songs_box = Gtk.Template.Child()
    queued_songs_box = Gtk.Template.Child()
    next_songs_box = Gtk.Template.Child()

    def __init__(self):
        super().__init__()

    def update_all(self, player):
        """Updates played songs, queue and next songs"""
        self.update_played_songs(player)
        self.update_queue(player)
        self.update_next_songs(player)

    def update_played_songs(self, player):
        """Updates played songs"""
        child = self.played_songs_list.get_row_at_index(0)
        while child:
            self.played_songs_list.remove(child)
            del child
            child = self.played_songs_list.get_row_at_index(0)

        if len(player.played_songs) > 0:
            self.played_songs_box.set_visible(True)
            for index, track in enumerate(player.played_songs):
                listing = HTGenericTrackWidget(track, False)
                listing.set_name(str(index))
                self.played_songs_list.append(listing)
        else:
            self.played_songs_box.set_visible(False)

    def update_queue(self, player):
        """Updates the queue"""
        child = self.queued_songs_list.get_row_at_index(0)
        while child:
            self.queued_songs_list.remove(child)
            del child
            child = self.queued_songs_list.get_row_at_index(0)

        if len(player.queue) > 0:
            self.queued_songs_box.set_visible(True)
            for index, track in enumerate(player.queue):
                listing = HTGenericTrackWidget(track, False)
                listing.set_name(str(index))
                self.queued_songs_list.append(listing)
        else:
            self.queued_songs_box.set_visible(False)

    def update_next_songs(self, player):
        """Updates next songs"""
        child = self.next_songs_list.get_row_at_index(0)
        while child:
            self.next_songs_list.remove(child)
            del child
            child = self.next_songs_list.get_row_at_index(0)

        if len(player.tracks_to_play) > 0:
            self.next_songs_box.set_visible(True)
            for index, track in enumerate(player.tracks_to_play):
                listing = HTGenericTrackWidget(track, False)
                listing.set_name(str(index))
                self.next_songs_list.append(listing)
        else:
            self.next_songs_box.set_visible(False)
