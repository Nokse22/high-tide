# cache.py
#
# Copyright 2025 Nokse <nokse@posteo.com>
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

from tidalapi.artist import Artist
from tidalapi.album import Album
from tidalapi.media import Track
from tidalapi.playlist import Playlist
from tidalapi.mix import Mix


class HTCache:
    artists = {}
    albums = {}
    tracks = {}
    playlists = {}
    mixes = {}

    def __init__(self, session):
        self.session = session

    def get_artist(self, artist_id):
        """Get an artist from cache or fetch from TIDAL API if not cached.

        Args:
            artist_id (str): The TIDAL artist ID

        Returns:
            Artist: The artist object from TIDAL API
        """
        if artist_id in self.artists:
            return self.artists[artist_id]
        artist = Artist(self.session, artist_id)
        self.artists[artist_id] = artist
        return artist

    def get_album(self, album_id):
        """Get an album from cache or fetch from TIDAL API if not cached.

        Args:
            album_id (str): The TIDAL album ID

        Returns:
            Album: The album object from TIDAL API
        """
        if album_id in self.albums:
            return self.albums[album_id]
        album = Album(self.session, album_id)
        self.albums[album_id] = album
        return album

    def get_track(self, track_id):
        """Get a track from cache or fetch from TIDAL API if not cached.

        Args:
            track_id (str): The TIDAL track ID

        Returns:
            Track: The track object from TIDAL API
        """
        if track_id in self.tracks:
            return self.tracks[track_id]
        track = Track(self.session, track_id)
        self.tracks[track_id] = track
        return track

    def get_playlist(self, playlist_id):
        """Get a playlist from cache or fetch from TIDAL API if not cached.

        Args:
            playlist_id (str): The TIDAL playlist ID

        Returns:
            Playlist: The playlist object from TIDAL API
        """
        if playlist_id in self.playlists:
            return self.playlists[playlist_id]
        playlist = Playlist(self.session, playlist_id)
        self.playlists[playlist_id] = playlist
        return playlist

    def get_mix(self, mix_id):
        """Get a mix from cache or fetch from TIDAL API if not cached.

        Args:
            mix_id (str): The TIDAL mix ID

        Returns:
            Mix: The mix object from TIDAL API
        """
        if mix_id in self.mixes:
            return self.mixes[mix_id]
        mix = Mix(self.session, mix_id)
        self.mixes[mix_id] = mix
        return mix
