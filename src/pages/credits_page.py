# credits_page.py
#
# Copyright 2026 Petru101
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

import html
import logging
from gettext import gettext as _
from typing import List

from gi.repository import Gtk
from tidalapi.album import Album
from tidalapi.media import Track

from ..lib import utils
from .page import Page

logger = logging.getLogger(__name__)


class HTCreditsPage(Page):
    """A page to display the credits of a track, or the info, review and
    credits of an album"""

    __gtype_name__ = "HTCreditsPage"

    item: Track | Album | None = None
    is_album: bool = False
    credits: List[dict] = []
    tracks_credits: List[dict] = []
    review: dict | None = None
    role_size_group: Gtk.SizeGroup | None = None

    @classmethod
    def new_for_track(cls, track_id: str) -> "HTCreditsPage":
        """Create a new page showing the credits of a track.

        Args:
            track_id: The id of the track

        Returns:
            HTCreditsPage: A new instance for the track
        """
        return cls.new_from_id(track_id)

    @classmethod
    def new_for_album(cls, album_id: str) -> "HTCreditsPage":
        """Create a new page showing the info, review and credits of an album.

        Args:
            album_id: The id of the album

        Returns:
            HTCreditsPage: A new instance for the album
        """
        instance = cls.new_from_id(album_id)
        instance.is_album = True
        return instance

    def _load_async(self) -> None:
        request = utils.session.request

        if not self.is_album:
            self.item = utils.get_track(self.id)
            self.credits = request.request(
                "GET",
                f"tracks/{self.item.id}/credits",
                params={"limit": 100, "includeContributors": "true"},
            ).json()
            return

        self.item = utils.get_album(self.id)

        try:
            self.review = request.request("GET", f"albums/{self.item.id}/review").json()
        except Exception:
            # Most albums don't have a review
            self.review = None

        self.tracks_credits = []
        limit = 100
        offset = 0
        while True:
            page = request.request(
                "GET",
                f"albums/{self.item.id}/items/credits",
                params={
                    "limit": limit,
                    "offset": offset,
                    "replace": "true",
                    "includeContributors": "true",
                },
            ).json()
            self.tracks_credits += page["items"]
            offset += limit
            if offset >= page["totalNumberOfItems"]:
                break

    def _load_finish(self) -> None:
        if not self.is_album:
            self.set_title(_("Credits"))
            self._append_heading(self.item.name, "title-1")
            self._append_label(
                ", ".join(artist.name for artist in self.item.artists),
                css_classes=["dim-label"],
                margin_top=0,
            )
            if not self._append_credits(self.credits):
                self._append_label(_("No credits available"), css_classes=["dim-label"])
            return

        self.set_title(_("Album Info"))
        self._append_heading(self.item.name, "title-1")
        self._append_label(
            self.item.artist.name, css_classes=["dim-label"], margin_top=0
        )

        self._append_info()

        if self.review and self.review.get("text"):
            self._append_heading(_("Review"))
            self._append_label(utils.replace_links(self.review["text"]), markup=True)
            if self.review.get("source"):
                self._append_label(
                    _("Review by {}").format(self.review["source"]),
                    css_classes=["dim-label", "caption"],
                    margin_top=0,
                )

        tracks_with_credits = [
            entry for entry in self.tracks_credits if entry.get("credits")
        ]
        if not tracks_with_credits:
            return

        self._append_heading(_("Credits"))
        several_volumes = (self.item.num_volumes or 1) > 1
        for entry in tracks_with_credits:
            track = entry["item"]
            number = str(track.get("trackNumber"))
            if several_volumes:
                number = "{}-{}".format(track.get("volumeNumber"), number)
            self._append_heading("{}. {}".format(number, track.get("title")), "heading")
            self._append_credits(entry["credits"])

    def _append_info(self) -> None:
        album: Album = self.item
        release_date = album.release_date or album.available_release_date

        rows = [
            (
                _("Released"),
                release_date.strftime("%d-%m-%Y") if release_date else None,
            ),
            (
                _("Tracks"),
                _("{} tracks ({})").format(
                    album.num_tracks, utils.pretty_duration(album.duration)
                ),
            ),
            (_("Copyright"), album.copyright),
        ]

        grid = self._new_grid()
        for index, (title, value) in enumerate(row for row in rows if row[1]):
            grid.attach(self._new_role_label(title), 0, index, 1, 1)
            grid.attach(
                Gtk.Label(label=value, xalign=0, wrap=True, selectable=True),
                1,
                index,
                1,
                1,
            )
        self.append(grid)

    def _append_credits(self, credits: List[dict]) -> bool:
        """Append the roles and their contributors.

        Returns:
            bool: False if there were no credits to show
        """
        credits = [credit for credit in credits if credit.get("contributors")]
        if not credits:
            return False

        grid = self._new_grid()
        for index, credit in enumerate(credits):
            grid.attach(self._new_role_label(credit["type"]), 0, index, 1, 1)

            names = Gtk.Label(
                label=self._contributors_markup(credit["contributors"]),
                use_markup=True,
                xalign=0,
                wrap=True,
            )
            self.signals.append((names, names.connect("activate-link", utils.open_uri)))
            grid.attach(names, 1, index, 1, 1)
        self.append(grid)

        return True

    def _contributors_markup(self, contributors: List[dict]) -> str:
        names = []
        for contributor in contributors:
            name = html.escape(contributor["name"])
            if contributor.get("id"):
                names.append(f'<a href="artist:{contributor["id"]}">{name}</a>')
            else:
                names.append(name)
        return ", ".join(names)

    def _new_grid(self) -> Gtk.Grid:
        return Gtk.Grid(
            column_spacing=24,
            row_spacing=6,
            margin_start=12,
            margin_end=12,
            margin_bottom=12,
        )

    def _new_role_label(self, role: str) -> Gtk.Label:
        label = Gtk.Label(label=role, xalign=0, yalign=0, css_classes=["dim-label"])
        # Keep the second column aligned across all the grids of the page
        if self.role_size_group is None:
            self.role_size_group = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL)
        self.role_size_group.add_widget(label)
        return label

    def _append_heading(self, text: str, css_class: str = "title-3") -> None:
        self.append(
            Gtk.Label(
                label=text,
                css_classes=[css_class],
                xalign=0,
                wrap=True,
                margin_start=12,
                margin_end=12,
                margin_top=12,
                margin_bottom=12 if css_class == "title-3" else 6,
            )
        )

    def _append_label(
        self,
        text: str,
        markup: bool = False,
        css_classes: List[str] | None = None,
        margin_top: int = 0,
    ) -> None:
        label = Gtk.Label(
            wrap=True,
            xalign=0,
            css_classes=css_classes or [],
            margin_start=12,
            margin_end=12,
            margin_top=margin_top,
            margin_bottom=12,
        )
        if markup:
            label.set_markup(text)
            self.signals.append((label, label.connect("activate-link", utils.open_uri)))
        else:
            label.set_label(text)
        self.append(label)
