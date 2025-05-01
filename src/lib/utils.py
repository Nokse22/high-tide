# utils.py
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

from gi.repository import GLib
from gi.repository import Gio
from gi.repository import Gdk

import requests
import uuid
import re
import html

from pathlib import Path
from . import variables


def pretty_duration(secs):
    if not secs:
        return "00:00"

    hours = secs // 3600
    minutes = (secs % 3600) // 60
    seconds = secs % 60

    if hours > 0:
        return f"{int(hours):02}:{int(minutes):02}:{int(seconds):02}"
    else:
        return f"{int(minutes):02}:{int(seconds):02}"

    return "00:00"


def get_image_url(item):
    if hasattr(item, "id"):
        file_path = Path(f"{variables.IMG_DIR}/{item.id}.jpg")
    else:
        file_path = Path(f"{variables.IMG_DIR}/{uuid.uuid4()}.jpg")

    if file_path.is_file():
        return str(file_path)

    try:
        picture_url = item.image()
        response = requests.get(picture_url)
    except Exception as e:
        print(e)
        return None
    if response.status_code == 200:
        picture_data = response.content

        with open(file_path, "wb") as file:
            file.write(picture_data)

    return str(file_path)


def add_picture(widget, item, cancellable=Gio.Cancellable.new()):
    """Retrieves and adds an picture"""

    if cancellable is None:
        cancellable = Gio.Cancellable.new()

    def _add_picture(widget, file_path, cancellable):
        if not cancellable.is_cancelled():
            widget.set_filename(file_path)

    GLib.idle_add(
        _add_picture, widget, get_image_url(item), cancellable)


def add_image(widget, item, cancellable=Gio.Cancellable.new()):
    """Retrieves and adds an image"""

    def _add_image(widget, file_path, cancellable):
        if not cancellable.is_cancelled():
            widget.set_from_file(file_path)

    GLib.idle_add(
        _add_image, widget, get_image_url(item), cancellable)


def add_image_to_avatar(widget, item, cancellable=Gio.Cancellable.new()):
    """Same ad the previous function, but for Adwaita's avatar widgets"""

    def _add_image_to_avatar(avatar_widget, file_path, cancellable):
        if not cancellable.is_cancelled():
            file = Gio.File.new_for_path(file_path)
            image = Gdk.Texture.new_from_file(file)
            widget.set_custom_image(image)

    GLib.idle_add(
        _add_image_to_avatar, widget, get_image_url(item), cancellable)


def replace_links(text):
    # Define regular expression pattern to match escaped [wimpLink ...]...[/wimpLink] tags
    pattern = r'\[wimpLink (artistId|albumId)=&quot;(\d+)&quot;\]([^[]+)\[\/wimpLink\]'

    # Escape HTML in the entire text
    escaped_text = html.escape(text)

    # Define a function to replace the matched pattern with the desired format
    def replace(match):
        link_type = match.group(1)
        id_value = match.group(2)
        label = match.group(3)

        if link_type == "artistId":
            return f'<a href="artist:{id_value}">{label}</a>'
        elif link_type == "albumId":
            return f'<a href="album:{id_value}">{label}</a>'
        else:
            return label

    # Replace <br/> with two periods
    escaped_text = escaped_text.replace('&lt;br/&gt;', '\n')

    # Use re.sub() to perform the replacement
    replaced_text = re.sub(pattern, replace, escaped_text)

    return replaced_text
