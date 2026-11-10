# activity_page.py
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

import locale
import logging
import threading
from gettext import gettext as _
from gettext import ngettext
from typing import List

from gi.repository import Adw, GLib, Gtk

from ..lib import utils
from .page import Page

logger = logging.getLogger(__name__)


class HTActivityPage(Page):
    """A page to display the user's most played artists of each month"""

    __gtype_name__ = "HTActivityPage"

    timeline: List[dict] = []
    activity: dict = {}

    def _get(self, path: str, **params) -> dict:
        # The month names come from TIDAL in this language
        language = GLib.get_language_names()[0].split(".")[0]
        if language in ("C", "POSIX"):
            language = "en_US"
        params.update({"locale": language, "deviceType": "BROWSER"})
        return utils.session.request.request(
            "GET",
            f"my-activity/{path}",
            params=params,
            base_url=utils.session.config.api_v2_location,
        ).json()

    def _load_async(self) -> None:
        self.timeline = self._get("timeline").get("timeline", [])
        if self.timeline:
            self.activity = self._get_month(self.timeline[0])

    def _get_month(self, month: dict) -> dict:
        return self._get("top-artists", year=month["year"], month=month["month"])

    def _load_finish(self) -> None:
        self.set_title(_("My Activity"))

        if not self.timeline:
            self.append(
                Adw.StatusPage(
                    icon_name="music-artist-symbolic",
                    title=_("No Activity Yet"),
                    description=_("Your most played artists will show up here"),
                    vexpand=True,
                )
            )
            return

        header = Gtk.Box(spacing=12, margin_start=12, margin_end=12, margin_top=12)
        header.append(
            Gtk.Label(
                label=_("Most Played Artists"),
                css_classes=["title-3"],
                xalign=0,
                hexpand=True,
            )
        )

        self.month_dropdown = Gtk.DropDown.new_from_strings(
            [month["title"] for month in self.timeline]
        )
        self.month_dropdown.set_valign(Gtk.Align.CENTER)
        self.signals.append(
            (
                self.month_dropdown,
                self.month_dropdown.connect("notify::selected", self._on_month_changed),
            )
        )
        header.append(self.month_dropdown)
        self.append(header)

        self.total_label = Gtk.Label(
            css_classes=["dim-label"], xalign=0, margin_start=12, margin_end=12
        )
        self.append(self.total_label)

        self.artists_list = Gtk.ListBox(
            css_classes=["boxed-list"],
            selection_mode=Gtk.SelectionMode.NONE,
            margin_start=12,
            margin_end=12,
            margin_top=12,
            margin_bottom=12,
            valign=Gtk.Align.START,
        )
        self.append(self.artists_list)

        self.disclaimer_label = Gtk.Label(
            css_classes=["dim-label", "caption"],
            wrap=True,
            xalign=0,
            margin_start=12,
            margin_end=12,
            margin_bottom=12,
        )
        self.append(self.disclaimer_label)

        self._show_activity()

    def _on_month_changed(self, *args) -> None:
        month = self.timeline[self.month_dropdown.get_selected()]

        def _load():
            try:
                activity = self._get_month(month)
            except Exception:
                logger.exception(f"Failed to load activity for {month}")
                activity = {}
            GLib.idle_add(self._set_activity, activity)

        threading.Thread(target=_load).start()

    def _set_activity(self, activity: dict) -> None:
        self.activity = activity
        self._show_activity()

    def _show_activity(self) -> None:
        self.artists_list.remove_all()

        entries = self.activity.get("artists", [])
        self.artists_list.set_visible(bool(entries))

        total = self.activity.get("totalNrOfStreams")
        if total:
            self.total_label.set_label(
                ngettext("{} play in total", "{} plays in total", total).format(
                    locale.format_string("%d", total, grouping=True)
                )
            )
        elif not entries:
            self.total_label.set_label(_("Nothing played yet"))
        else:
            self.total_label.set_label("")
        self.total_label.set_visible(bool(self.total_label.get_label()))

        for rank, entry in enumerate(entries, 1):
            artist = utils.session.parse_artist(entry["artist"])
            plays = entry.get("nrOfStreams", 0)

            row = Adw.ActionRow(
                title=artist.name,
                subtitle=ngettext("{} play", "{} plays", plays).format(
                    locale.format_string("%d", plays, grouping=True)
                ),
                use_markup=False,
                activatable=True,
            )
            self.signals.append(
                (row, row.connect("activated", self._on_row_activated, artist))
            )

            # Prefixes are added at the start, so the rank goes last
            avatar = Adw.Avatar(size=40, text=artist.name, show_initials=True)
            row.add_prefix(avatar)
            row.add_prefix(
                Gtk.Label(
                    label=str(rank), width_chars=2, css_classes=["dim-label", "numeric"]
                )
            )
            row.add_suffix(Gtk.Image(icon_name="go-next-symbolic"))

            threading.Thread(
                target=utils.add_image_to_avatar, args=(avatar, artist)
            ).start()

            self.artists_list.append(row)

        disclaimers = self.activity.get("disclaimers") or []
        self.disclaimer_label.set_label(
            " ".join(disclaimer.get("text", "") for disclaimer in disclaimers)
        )

    def _on_row_activated(self, row, artist) -> None:
        utils.open_uri("", f"artist:{artist.id}")
