# ai.py
#
# Copyright 2026 The High Tide Contributors
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

"""Support for TIDAL's AI-generated content labels.

TIDAL marks fully AI-generated tracks (and albums) with an ``ai`` boolean in
its catalog responses. python-tidal 0.8.x does not copy that field onto its
models, so :func:`install` extends the model parsers to keep it. The value is
then available as ``track.ai`` / ``album.ai``.

TIDAL's own "Allow AI content" preference lives in each client's local
storage and is not exposed through the API, so the preference in High Tide is
kept locally too.
"""

import logging
from collections.abc import Iterable
from typing import Any

from tidalapi.album import Album
from tidalapi.media import Media

logger = logging.getLogger(__name__)

_hidden = False
_installed = False


def install() -> None:
    """Teach python-tidal to retain TIDAL's ``ai`` catalog flag.

    Safe to call more than once. If (a future version of) python-tidal already
    exposes the flag, the patches still work and simply set the same value.
    """

    global _installed
    if _installed:
        return

    original_media_parse = Media.parse
    original_album_parse = Album.parse

    def media_parse_with_ai(self: Any, json_obj: Any, album: Any = None) -> None:
        original_media_parse(self, json_obj, album)
        self.ai = bool(json_obj.get("ai", False))

    def album_parse_with_ai(
        self: Any, json_obj: Any, artist: Any = None, artists: Any = None
    ) -> Album:
        parsed = original_album_parse(self, json_obj, artist, artists)
        parsed.ai = bool(json_obj.get("ai", False))
        return parsed

    Media.parse = media_parse_with_ai
    Album.parse = album_parse_with_ai
    _installed = True


def get_hidden() -> bool:
    """Return whether AI-generated content is hidden."""

    return _hidden


def set_hidden(hidden: bool) -> None:
    """Set whether AI-generated content is hidden."""

    global _hidden
    _hidden = bool(hidden)


def is_ai(item: Any) -> bool:
    """Return whether a TIDAL item is labelled AI-generated."""

    return bool(getattr(item, "ai", False))


def is_hidden(item: Any) -> bool:
    """Return whether an item should be left out of lists and playback."""

    return _hidden and is_ai(item)


def filter_items(items: Iterable[Any]) -> list[Any]:
    """Remove hidden AI-generated items from a list."""

    return [item for item in items if not is_hidden(item)]
