# artist_page.py
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

import logging
import threading
from gettext import gettext as _
from typing import List

from gi.repository import GLib, Gtk

from tidalapi.album import Album
from tidalapi.artist import Artist
from tidalapi.media import Track
from tidalapi.playlist import Playlist

from ..lib import utils
from .page import Page

logger = logging.getLogger(__name__)


class HTArtistPage(Page):
    """A page to display an artist"""

    __gtype_name__ = "HTArtistPage"

    waits_for_favourites = True

    top_tracks: List[Track] = []
    albums: List[Album] = []
    albums_ep_singles = []
    similar: List[Artist] = []
    bio: str = ""

    def _load_async(self) -> None:
        try:
            self.artist = utils.get_artist(self.id)
        except Exception as e:
            logger.exception(f"Failed to load artist with id {self.id}: {e}")
            self.artist = None
            return  # can't continue if artist is missing

        try:
            self.top_tracks = self.artist.get_top_tracks(limit=5)
        except Exception as e:
            logger.warning(f"Failed to load top tracks for {self.artist}: {e}")
            self.top_tracks = []

        try:
            self.get_albums_ep_singles = utils.AlbumVersionFilter(
                self.artist.get_albums_ep_singles
            )
            self.albums_ep_singles = self.get_albums_ep_singles(limit=10)
        except Exception as e:
            logger.warning(f"Failed to load EPs/singles for {self.artist}: {e}")
            self.albums_ep_singles = []

        self.rows = self._get_page_rows()

        try:
            self.similar = self.artist.get_similar()
        except Exception as e:
            logger.warning(f"Failed to load similar artists for {self.artist}: {e}")
            self.similar = []

        try:
            self.bio = self.artist.get_bio()
        except Exception as e:
            logger.warning(f"Failed to load bio for {self.artist}: {e}")
            self.bio = ""

    def _get_page_rows(self) -> list:
        """The rows of TIDAL's own artist page, after Top Tracks: Albums, EP &
        Singles, Compilations, Live albums, Playlists, Appears On, Influencers...
        (#208). Albums and EP & Singles stay High Tide's own lists, which hide
        other versions of a release; live albums and compilations are left out
        of Albums, as TIDAL has rows for them. Videos, credits, links and Fans
        Also Like (Similar Artists is shown instead) are left out."""
        try:
            categories = self.artist.page().categories
        except Exception as e:
            logger.warning(f"Failed to load the artist page of {self.artist}: {e}")
            categories = []

        rows = []
        in_other_rows = set()
        for category in categories:
            title = getattr(category, "title", None) or ""
            items = [i for i in getattr(category, "items", None) or [] if i is not None]
            key = title.casefold()
            # (the untitled first row is the page's header: the artist again)
            if not items or not title or key == "top tracks":
                continue
            if key in ("featured albums", "albums"):
                rows.append(("albums", None))
            elif key in ("ep & singles", "eps & singles"):
                rows.append(("ep", None))
            elif key == "fans also like":
                rows.append(("similar", None))
            elif all(isinstance(i, (Album, Artist, Playlist)) for i in items):
                full = self._full_row(category, items)
                if key in ("compilations", "live albums"):
                    in_other_rows.update(utils.album_release_key(a) for a in full())
                rows.append((title, (items, full)))
        for name in ("albums", "ep", "similar"):
            if (name, None) not in rows:
                rows.append((name, None))

        self.get_albums = utils.AlbumVersionFilter(
            self.artist.get_albums, exclude=in_other_rows
        )
        try:
            self.albums = self.get_albums(limit=10)
        except Exception as e:
            logger.warning(f"Failed to load albums for {self.artist}: {e}")
            self.albums = []
        return rows

    @staticmethod
    def _full_row(category, items):
        """The whole row for "See all", loaded once when first asked for"""
        cache = []

        def full(limit=None, offset=0):
            if not cache:
                try:
                    more = category.show_more()
                    cache.extend(
                        i
                        for c in more.categories
                        for i in getattr(c, "items", None) or []
                        if i is not None
                    )
                except Exception as e:
                    logger.warning(f"Failed to load the whole row {category.title}: {e}")
                if not cache:
                    cache.extend(items)
            if limit is None:
                return cache[offset:]
            return cache[offset : offset + limit]

        return full

    def _load_finish(self) -> None:
        self.set_title(self.artist.name)

        builder = Gtk.Builder.new_from_resource(
            "/io/github/nokse22/high-tide/ui/pages_ui/artist_page_template.ui"
        )

        self.append(builder.get_object("_main"))

        builder.get_object("_name_label").set_label(self.artist.name)

        play_btn = builder.get_object("_play_button")
        self.signals.append(
            (
                play_btn,
                play_btn.connect("clicked", self.on_play_button_clicked),
            )
        )

        shuffle_btn = builder.get_object("_shuffle_button")
        self.signals.append(
            (
                shuffle_btn,
                shuffle_btn.connect("clicked", self.on_shuffle_button_clicked),
            )
        )

        follow_button = builder.get_object("_follow_button")
        self.signals.append(
            (
                follow_button,
                follow_button.connect(
                    "clicked", utils.on_in_to_my_collection_button_clicked, self.artist
                ),
            )
        )

        share_button = builder.get_object("_share_button")
        self.signals.append(
            (
                share_button,
                share_button.connect(
                    "clicked", lambda *_: utils.share_this(self.artist)
                ),
            )
        )

        utils.set_in_my_collection_button(
            follow_button, utils.is_favourited(self.artist)
        )

        block_button = builder.get_object("_block_button")
        self._update_block_button(block_button, utils.is_blocked(self.artist))
        self.signals.append(
            (
                block_button,
                block_button.connect(
                    "clicked",
                    lambda *_: utils.toggle_blocked(
                        self.artist,
                        lambda blocked: self._update_block_button(
                            block_button, blocked
                        ),
                    ),
                ),
            )
        )

        artist_picture = builder.get_object("_avatar")

        threading.Thread(
            target=utils.add_image_to_avatar, args=(artist_picture, self.artist)
        ).start()

        builder.get_object("_first_subtitle_label").set_label(_("Artist"))

        self.new_track_list_for(
            _("Top Tracks"),
            self.top_tracks,
            self.artist.get_top_tracks,
            source=self.artist,
        )

        for name, row in self.rows:
            if name == "albums":
                self.new_carousel_for(_("Albums"), self.albums, self.get_albums)
            elif name == "ep":
                self.new_carousel_for(
                    _("EP & Singles"),
                    self.albums_ep_singles,
                    self.get_albums_ep_singles,
                )
            elif name == "similar":
                self.new_carousel_for(_("Similar Artists"), self.similar)
            else:
                items, full = row
                self.new_carousel_for(name, items, full)

        builder.get_object("_radio_button").set_action_target_value(
            GLib.Variant("s", str(self.artist.id))
        )

        if self.bio == "":
            return

        bio = utils.replace_links(self.bio)
        label = Gtk.Label(
            wrap=True,
            css_classes=[],
            margin_start=12,
            margin_end=12,
            margin_bottom=24,
        )
        label.set_markup(bio)
        self.append(
            Gtk.Label(
                wrap=True,
                css_classes=["title-3"],
                margin_start=12,
                label=_("Bio"),
                xalign=0,
                margin_top=12,
                margin_bottom=12,
            )
        )
        self.append(label)
        self.signals.append((label, label.connect("activate-link", utils.open_uri)))

    def _update_block_button(self, button, blocked: bool) -> None:
        if blocked:
            button.set_tooltip_text(_("Unblock Artist"))
            button.add_css_class("error")
        else:
            button.set_tooltip_text(_("Block Artist"))
            button.remove_css_class("error")

    def on_play_button_clicked(self, btn) -> None:
        utils.player_object.play_this(self.top_tracks, 0, source=self.artist)

    def on_shuffle_button_clicked(self, btn) -> None:
        utils.player_object.shuffle_this(self.top_tracks, source=self.artist)
