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

from gi.repository import Gdk, GLib, GObject, Graphene, Gtk

from ..lib import utils
from ..widgets.generic_track_widget import HTGenericTrackWidget


@Gtk.Template(resource_path="/io/github/nokse22/high-tide/ui/widgets/queue_widget.ui")
class HTQueueWidget(Gtk.Box):
    """It is used to display the track queue, including played tracks,
    tracks to play and tracks added to the queue"""

    __gtype_name__ = "HTQueueWidget"

    scrolled_window = Gtk.Template.Child()
    played_songs_list = Gtk.Template.Child()
    playing_song_list = Gtk.Template.Child()
    queued_songs_list = Gtk.Template.Child()
    next_songs_list = Gtk.Template.Child()

    played_songs_box = Gtk.Template.Child()
    playing_song_box = Gtk.Template.Child()
    queued_songs_box = Gtk.Template.Child()
    next_songs_box = Gtk.Template.Child()

    clear_queue_button = Gtk.Template.Child()
    clear_next_songs_button = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._dragged_row = None
        # The row showing where the dragged song will land
        self._drop_row = None
        # On desktop a song is dragged by its whole row; on a phone by a handle,
        # as dragging a row with a finger would fight with scrolling the list
        self.drag_whole_rows = False

    @Gtk.Template.Callback("on_played_song_activated")
    def _on_played_song_activated(self, list_box, row) -> None:
        player = utils.player_object
        self._play_row(row, player.played_songs, player.play_from_played_songs)

    @Gtk.Template.Callback("on_queued_song_activated")
    def _on_queued_song_activated(self, list_box, row) -> None:
        player = utils.player_object
        self._play_row(row, player.queue, player.play_from_queue)

    @Gtk.Template.Callback("on_next_song_activated")
    def _on_next_song_activated(self, list_box, row) -> None:
        player = utils.player_object
        self._play_row(row, player.tracks_to_play, player.play_from_next_songs)

    @Gtk.Template.Callback("on_clear_queue_clicked")
    def _on_clear_queue_clicked(self, *args) -> None:
        utils.player_object.clear_queue()

    @Gtk.Template.Callback("on_clear_next_songs_clicked")
    def _on_clear_next_songs_clicked(self, *args) -> None:
        utils.player_object.clear_next_songs()
        self.update_next_songs(utils.player_object)

    def _play_row(self, row, tracks, play) -> None:
        index = self._index_of(row, tracks)
        if index is not None:
            play(index)

    @staticmethod
    def _index_of(row, tracks) -> int | None:
        index = int(row.get_name())
        if index >= len(tracks) or tracks[index] is not row.track:
            # The list changed since it was shown
            index = next((i for i, t in enumerate(tracks) if t is row.track), None)
        return index

    def _remove_queued(self, row) -> None:
        def remove():
            player = utils.player_object
            index = self._index_of(row, player.queue)
            if index is not None:
                player.remove_from_queue(index)
            return False

        # Not while the clicked button is still handling the click: the list
        # is rebuilt
        GLib.idle_add(remove, priority=GLib.PRIORITY_HIGH_IDLE)

    def _remove_next(self, row) -> None:
        def remove():
            player = utils.player_object
            index = self._index_of(row, player.tracks_to_play)
            if index is not None:
                player.remove_from_next_songs(index)
                self.update_next_songs(player)
            return False

        GLib.idle_add(remove, priority=GLib.PRIORITY_HIGH_IDLE)

    def set_drag_whole_rows(self, whole_rows: bool) -> None:
        """Drag songs by their whole row (desktop) or by a handle (phone)"""
        if whole_rows == self.drag_whole_rows:
            return
        self.drag_whole_rows = whole_rows
        if utils.player_object is not None:
            self.update_queue(utils.player_object)
            self.update_next_songs(utils.player_object)

    def _make_draggable(self, row) -> None:
        """Let a queued or next song row be dragged to another place in the same
        list, by the whole row or by its handle"""
        source = Gtk.DragSource(actions=Gdk.DragAction.MOVE)
        source.connect("prepare", self._on_drag_prepare, row)
        source.connect("drag-begin", self._on_drag_begin, row)
        source.connect("drag-end", self._on_drag_end)
        if self.drag_whole_rows:
            row.add_controller(source)
        else:
            row.add_drag_handle().add_controller(source)

        target = Gtk.DropTarget.new(GObject.TYPE_STRING, Gdk.DragAction.MOVE)
        target.connect("motion", self._on_drop_motion, row)
        target.connect("leave", self._on_drop_leave, row)
        target.connect("drop", self._on_drop, row)
        row.add_controller(target)

    def _on_drag_prepare(self, source, x, y, row):
        if self.drag_whole_rows:
            # Not from the row's buttons (remove, menu) or links
            picked = row.pick(x, y, Gtk.PickFlags.DEFAULT)
            while picked is not None and picked is not row:
                if isinstance(picked, Gtk.Button) or (
                    isinstance(picked, Gtk.Label) and picked.get_current_uri()
                ):
                    return None
                picked = picked.get_parent()
        self._dragged_row = row
        return Gdk.ContentProvider.new_for_value(
            GObject.Value(GObject.TYPE_STRING, row.get_name())
        )

    def _on_drag_begin(self, source, drag, row) -> None:
        # A still picture, so it doesn't fade with the row left behind
        icon = Gtk.WidgetPaintable.new(row).get_current_image()
        source.set_icon(icon, 0, row.get_height() // 2)
        row.add_css_class("drag-source")

    def _on_drag_end(self, *args) -> None:
        if self._dragged_row is not None:
            self._dragged_row.remove_css_class("drag-source")
        self._dragged_row = None
        self._show_drop_line(None, False)

    def _same_list(self, row) -> bool:
        dragged = self._dragged_row
        return dragged is not None and dragged.get_parent() is row.get_parent()

    @staticmethod
    def _drops_below(row, y) -> bool:
        return y > row.get_height() / 2

    def _show_drop_line(self, row, below) -> None:
        """Draw a line above or below row, where the dragged song will land"""
        if self._drop_row is not None and self._drop_row is not row:
            self._drop_row.remove_css_class("drop-above")
            self._drop_row.remove_css_class("drop-below")
        self._drop_row = row
        if row is not None:
            row.add_css_class("drop-below" if below else "drop-above")
            row.remove_css_class("drop-above" if below else "drop-below")

    def _on_drop_motion(self, target, x, y, row):
        if not self._same_list(row):
            return 0
        self._show_drop_line(row, self._drops_below(row, y))
        return Gdk.DragAction.MOVE

    def _on_drop_leave(self, target, row) -> None:
        if self._drop_row is row:
            self._show_drop_line(None, False)

    def _on_drop(self, target, value, x, y, row) -> bool:
        dragged = self._dragged_row
        list_box = row.get_parent()
        self._show_drop_line(None, False)
        if not self._same_list(row) or dragged is row:
            return False
        player = utils.player_object
        if list_box is self.queued_songs_list:
            tracks, move = player.queue, player.move_in_queue
        else:
            tracks, move = player.tracks_to_play, player.move_in_next_songs
        index = self._index_of(dragged, tracks)
        target_index = self._index_of(row, tracks)
        if index is None or target_index is None:
            return False
        # Above or below the row it's dropped on, where the line was
        new_index = target_index + (1 if self._drops_below(row, y) else 0)
        if index < new_index:
            new_index -= 1  # counted without the moved track
        if new_index == index:
            return False

        def apply():
            move(index, new_index)
            if list_box is self.next_songs_list:
                self.update_next_songs(player)
            return False

        # Not while the row handles the drop: the list is rebuilt
        GLib.idle_add(apply, priority=GLib.PRIORITY_HIGH_IDLE)
        return True

    def scroll_to_playing(self) -> None:
        """Scroll so the playing song is at the top, below the songs played"""
        clock = self.get_frame_clock()
        if clock is None:
            return
        handler = None

        def after_paint(clock):
            # The rebuilt lists have their size once a frame was drawn
            clock.disconnect(handler)
            if not self.playing_song_box.get_visible():
                return
            ok, point = self.playing_song_box.compute_point(
                self.scrolled_window.get_child().get_child(), Graphene.Point()
            )
            if ok:
                self.scrolled_window.get_vadjustment().set_value(max(0, point.y - 12))

        handler = clock.connect("after-paint", after_paint)
        self.queue_draw()

    def update_all(self, player) -> None:
        """Updates played songs, queue and next songs"""
        self.update_played_songs(player)
        self.update_playing_song(player)
        self.update_queue(player)
        self.update_next_songs(player)

    def update_played_songs(self, player) -> None:
        """Updates played songs"""
        child = self.played_songs_list.get_row_at_index(0)
        while child:
            self.played_songs_list.remove(child)
            del child
            child = self.played_songs_list.get_row_at_index(0)

        if len(player.played_songs) > 0:
            self.played_songs_box.set_visible(True)
            for index, track in enumerate(player.played_songs):
                listing = HTGenericTrackWidget(track)
                listing.hide_queue_button()
                listing.never_mark_playing()
                listing.set_name(str(index))
                self.played_songs_list.append(listing)
        else:
            self.played_songs_box.set_visible(False)

    def update_playing_song(self, player) -> None:
        """Updates the playing song"""
        child = self.playing_song_list.get_row_at_index(0)
        while child:
            child.disconnect_all()
            self.playing_song_list.remove(child)
            child = self.playing_song_list.get_row_at_index(0)

        track = player.playing_track
        self.playing_song_box.set_visible(track is not None)
        if track is not None:
            listing = HTGenericTrackWidget(track)
            listing.hide_queue_button()
            listing.set_activatable(False)
            listing.hide_playing_icon()
            self.playing_song_list.append(listing)

    def update_queue(self, player) -> None:
        """Updates the queue"""
        child = self.queued_songs_list.get_row_at_index(0)
        while child:
            self.queued_songs_list.remove(child)
            del child
            child = self.queued_songs_list.get_row_at_index(0)

        if len(player.queue) > 0:
            self.queued_songs_box.set_visible(True)
            for index, track in enumerate(player.queue):
                listing = HTGenericTrackWidget(track)
                listing.hide_queue_button()
                listing.never_mark_playing()
                listing.set_name(str(index))
                listing.add_remove_button(self._remove_queued)
                self._make_draggable(listing)
                self.queued_songs_list.append(listing)
        else:
            self.queued_songs_box.set_visible(False)

    def update_next_songs(self, player) -> None:
        """Updates next songs"""
        child = self.next_songs_list.get_row_at_index(0)
        while child:
            self.next_songs_list.remove(child)
            del child
            child = self.next_songs_list.get_row_at_index(0)

        if len(player.tracks_to_play) > 0:
            self.next_songs_box.set_visible(True)
            for index, track in enumerate(player.tracks_to_play):
                listing = HTGenericTrackWidget(track)
                listing.hide_queue_button()
                listing.never_mark_playing()
                listing.set_name(str(index))
                listing.add_remove_button(self._remove_next)
                self._make_draggable(listing)
                self.next_songs_list.append(listing)
        else:
            self.next_songs_box.set_visible(False)
