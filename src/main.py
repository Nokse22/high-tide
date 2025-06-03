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

from .lib import utils, discord_rpc

import threading

from gettext import gettext as _


class TidalApplication(Adw.Application):
    """The main application singleton class."""

    def __init__(self):
        super().__init__(application_id='io.github.nokse22.HighTide',
                         flags=Gio.ApplicationFlags.HANDLES_OPEN)
        self.create_action(
            'quit', lambda *_: self.quit(), ['<primary>q', '<primary>w'])
        self.create_action('about', self.on_about_action)
        self.create_action('preferences', self.on_preferences_action)
        self.create_action('log-in', self.on_login_action)
        self.create_action('log-out', self.on_logout_action)
        self.create_action('download', self.on_download, ['<primary>d'])

        utils.init()
        # discord_rpc.init()

        self.settings = Gio.Settings.new('io.github.nokse22.HighTide')

        self.preferences = None

    def do_open(self, files, n_files, hint):
        self.win = self.props.active_window
        if not self.win:
            self.do_activate()

        uri = files[0].get_uri()
        if uri:
            utils.open_tidal_uri(uri)

    def on_download(self, *args):
        threading.Thread(target=self.win.th_download_song).start()

    def on_login_action(self, *args):
        self.win.new_login()

    def on_logout_action(self, *args):
        self.win.logout()

    def do_activate(self):
        self.win = self.props.active_window
        if not self.win:
            self.win = HighTideWindow(application=self)

        self.win.present()

    def on_about_action(self, widget, *args):
        about = Adw.AboutDialog(
            application_name='High Tide',
            application_icon='io.github.nokse22.HighTide',
            developer_name='Nokse',
            version='0.1.6',
            developers=['Nokse', 'Nila The Dragon', 'Dråfølin'],
            copyright='© 2023-2025 Nokse',
            license_type="GTK_LICENSE_GPL_3_0",
            issue_url='https://github.com/Nokse22/high-tide/issues',
            website='https://github.com/Nokse22/high-tide')

        about.add_link(
            _("Donate with Ko-Fi"), "https://ko-fi.com/nokse22")
        about.add_link(
            _("Donate with Github"), "https://github.com/sponsors/Nokse22")

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

            bg_row = builder.get_object("_background_row")
            bg_row.set_active(self.settings.get_boolean("run-background"))
            self.settings.bind(
                "run-background", bg_row,
                "active", Gio.SettingsBindFlags.DEFAULT)

            builder.get_object("_normalize_row").set_active(
                self.settings.get_boolean("normalize"))
            builder.get_object("_normalize_row").connect(
                "notify::active", self.on_normalize_changed)

            builder.get_object("_quadratic_volume_row").set_active(
                self.settings.get_boolean("quadratic-volume"))
            builder.get_object("_quadratic_volume_row").connect(
                "notify::active", self.on_quadratic_volume_changed)

            self.preferences = builder.get_object("_preference_window")

        self.preferences.present(self.win)

    def on_quality_changed(self, widget, *args):
        self.win.select_quality(widget.get_selected())

    def on_sink_changed(self, widget, *args):
        self.win.change_audio_sink(widget.get_selected())

    def on_normalize_changed(self, widget, *args):
        self.win.change_normalization(widget.get_active())

    def on_quadratic_volume_changed(self, widget, *args):
        self.win.change_quadratic_volume(widget.get_active())

    def create_action(self, name, callback, shortcuts=None):
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", callback)
        self.add_action(action)
        if shortcuts:
            self.set_accels_for_action(f"app.{name}", shortcuts)


def main(version):
    """The application's entry point."""
    app = TidalApplication()
    return app.run(sys.argv)
