# main.py
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

import sys

from gi.repository import Gtk, Gio, Adw
from .window import HighTideWindow
# from gi.events import GLibEventLoopPolicy

from .lib import variables

import threading
# import asyncio

# asyncio.set_event_loop_policy(GLibEventLoopPolicy())


class TidalApplication(Adw.Application):
    """The main application singleton class."""

    def __init__(self):
        super().__init__(application_id='io.github.nokse22.HighTide',
                         flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.create_action(
            'quit', lambda *_: self.quit(), ['<primary>q', '<primary>w'])
        self.create_action('about', self.on_about_action)
        self.create_action('preferences', self.on_preferences_action)
        self.create_action('log-in', self.on_login_action)
        self.create_action('log-out', self.on_logout_action)
        self.create_action('download', self.on_download, ['<primary>d'])

        variables.init()

        self.settings = Gio.Settings.new('io.github.nokse22.HighTide')

        self.preferences = None

    def on_download(self, *args):
        th = threading.Thread(target=self.win.th_download_song)
        th.deamon = True
        th.start()

    def on_login_action(self, *args):
        self.win.new_login()

    def on_logout_action(self, *args):
        self.win.logout()

    def do_activate(self):
        self.win = self.props.active_window
        if not self.win:
            self.win = HighTideWindow(application=self)
            self.win.connect(
                "close-request", self.on_close_request)
            self.win.set_hide_on_close(
                self.settings.get_boolean("run-background"))

        self.win.present()

    def on_about_action(self, widget, _):
        about = Adw.AboutDialog(
            application_name='High Tide',
            application_icon='io.github.nokse22.HighTide',
            developer_name='Nokse',
            version='0.1.3',
            developers=['Nokse'],
            copyright='© 2023-2025 Nokse',
            license_type="GTK_LICENSE_GPL_3_0",
            issue_url='https://github.com/Nokse22/high-tide/issues',
            website='https://github.com/Nokse22/high-tide')
        about.present(self.props.active_window)

    def on_preferences_action(self, widget, _):
        """Callback for the app.preferences action."""

        if not self.preferences:
            builder = Gtk.Builder.new_from_resource(
                "/io/github/nokse22/HighTide/ui/preferences.ui")

            builder.get_object("_quality_row").set_selected(
                self.settings.get_int("quality"))
            builder.get_object("_quality_row").connect(
                "notify::selected", self.on_quality_changed)

            builder.get_object("_sink_row").set_selected(
                self.settings.get_int("preferred-sink"))
            builder.get_object("_sink_row").connect(
                "notify::selected", self.on_sink_changed)

            builder.get_object("_background_row").set_active(
                self.settings.get_boolean("run-background"))
            builder.get_object("_background_row").connect(
                "notify::active", self.on_background_changed)

            builder.get_object("_normalize_row").set_active(
                self.settings.get_boolean("normalize"))
            builder.get_object("_normalize_row").connect(
                "notify::active", self.on_normalize_changed)

            self.preferences = builder.get_object("_preference_window")

        self.preferences.present(self.win)

    def on_quality_changed(self, widget, *args):
        self.win.select_quality(widget.get_selected())

    def on_sink_changed(self, widget, *args):
        self.win.change_audio_sink(widget.get_selected())

    def on_background_changed(self, widget, *args):
        self.settings.set_boolean("run-background", widget.get_active())
        self.win.set_hide_on_close(widget.get_active())

    def on_normalize_changed(self, widget, *args):
        self.win.change_normalization(widget.get_active())

    def create_action(self, name, callback, shortcuts=None):
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", callback)
        self.add_action(action)
        if shortcuts:
            self.set_accels_for_action(f"app.{name}", shortcuts)

    def on_close_request(self, *args):
        track = self.win.player_object.playing_track
        mix_album_playlist = self.win.player_object.current_mix_album_playlist

        print("close request")

        if (mix_album_playlist is not None and
                not isinstance(mix_album_playlist, list)):
            self.settings.set_string(
                "last-playing-list-id",
                str(mix_album_playlist.id))
            self.settings.set_string(
                "last-playing-list-type",
                variables.get_type(mix_album_playlist))
        if track is not None:
            self.settings.set_string(
                "last-playing-song-id",
                str(track.id))


def main(version):
    """The application's entry point."""
    app = TidalApplication()
    return app.run(sys.argv)
