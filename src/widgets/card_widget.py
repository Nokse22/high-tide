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
from gettext import ngettext
from typing import Union

from gi.repository import Adw, Gdk, GLib, Gtk

from tidalapi.album import Album
from tidalapi.artist import Artist
from tidalapi.mix import Mix, MixV2
from tidalapi.playlist import Folder, Playlist
from tidalapi.media import Track
from tidalapi.page import PageItem

from ..disconnectable_iface import IDisconnectable
from ..lib import ai, utils
from .track_menu import TrackMenu

import logging

logger = logging.getLogger(__name__)


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
    motion_controller = Gtk.Template.Child()
    play_revealer = Gtk.Template.Child()
    play_button = Gtk.Template.Child()
    title_label = Gtk.Template.Child()
    ai_label = Gtk.Template.Child()
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

        self.signals.append(
            (
                self.motion_controller,
                self.motion_controller.connect("enter", self._on_enter),
            )
        )

        self.signals.append(
            (
                self.motion_controller,
                self.motion_controller.connect("leave", self._on_leave),
            )
        )

        self.signals.append(
            (
                self.play_button,
                self.play_button.connect("clicked", self._on_play_clicked),
            )
        )

        self.item: Union[Track, Album, Artist, Playlist, Mix, MixV2] = item

        self.action: str | None = None
        self.loading = False

        self._populate()

    def _populate(self):
        self.ai_label.set_visible(ai.is_ai(self.item))

        if isinstance(self.item, MixV2) or isinstance(self.item, Mix):
            self._make_mix_card()
            self.action = "win.push-mix-page"
        elif isinstance(self.item, Album):
            self._make_album_card()
            self.action = "win.push-album-page"
        elif isinstance(self.item, Playlist):
            self._make_playlist_card()
            self.action = "win.push-playlist-page"
        elif isinstance(self.item, Folder):
            self._make_folder_card()
            self.action = "win.push-folder-page"
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

        self._add_track_menu()

        threading.Thread(
            target=utils.add_image, args=(self.image, self.item.album)
        ).start()

    def _add_track_menu(self) -> None:
        """Open the track menu on a right click or a long press."""
        self.track_menu = TrackMenu(self, None, self.item, self.signals)

        right_click = Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY)
        long_press = Gtk.GestureLongPress(touch_only=True)
        for gesture in (right_click, long_press):
            self.add_controller(gesture)
            self.signals.append(
                (
                    gesture,
                    gesture.connect(
                        "pressed", lambda g, *a: self._on_menu_requested(g, *a)
                    ),
                )
            )

    def _on_menu_requested(self, gesture, *args) -> None:
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        x, y = args[-2], args[-1]
        self.track_menu.popup(x, y)

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

    def _make_folder_card(self) -> None:
        """Configure the card to display a playlist folder"""
        self.title_label.set_label(self.item.name or "")
        self.title_label.set_tooltip_text(self.item.name or "")
        self.track_artist_label.set_visible(False)
        count = self.item.total_number_of_items or 0
        self.detail_label.set_label(
            ngettext("{} playlist", "{} playlists", count).format(count)
        )
        # Like TIDAL's: the folder icon in the accent colour on a tinted tile
        self.image.set_from_icon_name("folder-symbolic")
        self.image.set_pixel_size(64)
        self.image.set_size_request(155, 155)
        self.image.add_css_class("folder-cover")

        # Rename, delete, a new playlist in it: on a right click or a long press
        menu, actions = utils.folder_menu(self.item)
        self.insert_action_group("folder", actions)
        self._folder_menu = menu
        # Shown on hover where other cards have their play button, like TIDAL's
        menu_button = Gtk.MenuButton(
            icon_name="view-more-symbolic",
            tooltip_text=_("Folder Options"),
            menu_model=menu,
            css_classes=["circular", "card-play-button"],
        )
        self.play_revealer.set_child(menu_button)
        right_click = Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY)
        long_press = Gtk.GestureLongPress(touch_only=True)
        for gesture in (right_click, long_press):
            self.add_controller(gesture)
            self.signals.append(
                (gesture, gesture.connect("pressed", self._on_folder_menu_requested))
            )

    def _on_folder_menu_requested(self, gesture, *args) -> None:
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        popover = Gtk.PopoverMenu.new_from_model(self._folder_menu)
        popover.set_has_arrow(False)
        popover.set_parent(self)
        x, y = args[-2], args[-1]
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        popover.set_pointing_to(rect)
        popover.connect(
            "closed", lambda p: GLib.idle_add(lambda: (p.unparent(), False)[1])
        )
        popover.popup()

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

    def _on_enter(self, *args) -> None:
        self.play_revealer.set_reveal_child(True)

    def _on_leave(self, *args) -> None:
        self.play_revealer.set_reveal_child(False)

    def _on_play_clicked(self, *args) -> None:
        """Start playback of the card's item without opening its page."""
        if self.loading:
            return

        self.loading = True
        self.play_button.set_child(Adw.Spinner())

        def th_get_tracks():
            item = self.item
            tracks = None
            try:
                if isinstance(item, PageItem):
                    item = item.get()
                elif isinstance(item, MixV2):
                    item = utils.get_mix(item.id)
                tracks = utils.player_object.get_track_list(item)
            except Exception:
                logger.exception("Could not get the tracks of %s", item)

            GLib.idle_add(_on_tracks_loaded, item, tracks)

        def _on_tracks_loaded(item, tracks):
            self.loading = False
            self.play_button.set_icon_name("media-playback-start-symbolic")
            if tracks:
                utils.player_object.play_this(item, 0, tracks)

        threading.Thread(target=th_get_tracks).start()

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
                GLib.idle_add(utils.player_object.play_this, self.item.get())

            threading.Thread(target=_get).start()
