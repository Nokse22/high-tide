# collection_page.py
#
# Copyright 2024 Nokse22
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

from tidalapi.page import PageItem, PageLink
from tidalapi.artist import Artist
from tidalapi.mix import Mix
from tidalapi.album import Album
from tidalapi.media import Track
from tidalapi.playlist import Playlist

from .page import Page
from ..widgets import HTCarouselWidget
from ..widgets import HTTracksListWidget

from ..lib import variables


class collectionPage(Page):
    __gtype_name__ = 'collectionPage'

    """It is used for the collection"""

    def _th_load_page(self):
        self.set_tag("collection")
        self.set_title("Collection")

        self.new_carousel_for(
            "My Mixes and Radios", variables.favourite_mixes)
        self.new_carousel_for(
            "Playlists", variables.playlist_and_favorite_playlists)
        self.new_carousel_for(
            "Albums", variables.favourite_albums)
        self.new_carousel_for(
            "Tracks", variables.favourite_tracks)
        self.new_carousel_for(
            "Artists", variables.favourite_artists)

        self._page_loaded()

    def new_carousel_for(self, carousel_title, carousel_content):
        print(carousel_title, len(carousel_content))
        if len(carousel_content) == 0:
            return

        carousel = self.get_carousel(carousel_title)
        self.page_content.append(carousel)

        if isinstance(carousel_content[0], Mix):
            carousel.set_items(carousel_content, "mix")
        elif isinstance(carousel_content[0], Album):
            carousel.set_items(carousel_content, "album")
        elif isinstance(carousel_content, Artist):
            carousel.set_items(carousel_content, "artist")
        elif isinstance(carousel_content[0], Playlist):
            carousel.set_items(carousel_content, "playlist")
        elif isinstance(carousel_content[0], Track):
            carousel.set_items(carousel_content, "track")

    # @Gtk.Template.Callback("on_playlists_sidebar_row_activated")
    # def on_playlists_sidebar_row_activated_func(self, list_box, row):
    #     """Handles the click on an user playlist on the sidebar"""

    #     if row is None:
    #         return
    #     index = row.get_child().get_name()

    #     playlist = self.my_playlists[int(index)]

    #     page = playlistPage(playlist, playlist.name)
    #     page.load()
    #     self.navigation_view.push(page)

    # @Gtk.Template.Callback("on_new_playlist_button_clicked")
    # def on_new_playlist_button_clicked_func(self, btn):
    #     new_playlist_win = NewPlaylistWindow()
    #     new_playlist_win.connect(
    #         "create-playlist", self.on_create_new_playlist_requested)
    #     new_playlist_win.present(self)

    # @Gtk.Template.Callback("on_track_radio_button_clicked")
    # def on_track_radio_button_clicked_func(self, widget):
    #     track = self.player_object.playing_track
    #     page = trackRadioPage(track, f"{track.name} Radio")
    #     page.load()
    #     self.navigation_view.push(page)

    def update_my_playlists(self):
        child = self.sidebar_playlists.get_first_child()
        while child is not None:
            self.sidebar_playlists.remove(child)
            del child
            child = self.sidebar_playlists.get_first_child()

        playlists = self.session.user.playlists()

        for index, playlist in enumerate(playlists):
            if playlist.creator:
                if playlist.creator.name != "me":
                    playlists.remove(playlist)
                    continue
            label = Gtk.Label(xalign=0, label=playlist.name, name=index)
            self.sidebar_playlists.append(label)

        self.my_playlists = playlists

    def on_create_new_playlist_requested(self, window, p_title, p_description):
        self.session.user.create_playlist(p_title, p_description)
        window.close()
