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
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('Gst', '1.0')

from gi.repository import Gtk, Gio, Adw, Gdk
from .window import TidalWindow

from tidalapi.media import Quality

import threading

class TidalApplication(Adw.Application):
    """The main application singleton class."""

    def __init__(self):
        super().__init__(application_id='io.github.nokse22.high-tide',
                         flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.create_action('quit', lambda *_: self.quit(), ['<primary>q'])
        self.create_action('about', self.on_about_action)
        self.create_action('preferences', self.on_preferences_action)
        self.create_action('log-in', self.on_login_action)
        self.create_action('download', self.on_download, ['<primary>d'])

        css = '''
        .card-image{
            border-radius:10px;
            transition: opacity 0.1s ease-in-out;
        }

        .card-image:hover{
            opacity: 0.8;
        }

        .small-image{
            border-radius:4px;
        }

        .card-bg{
            transition: opacity 0.1s ease-in-out;
	        border-radius:14px;
        }

        .card-bg:hover{
            transition: background-color 0.1s ease-in-out;
            background-color:@card_shade_color;
	        border-radius:14px;
        }

        .link-text{
            color: #888;
            text-decoration: underline;
            transition: color 0.3s ease-in-out;
            background-color: transparent;
            font-weight: normal;
        }

        .link-text:hover{
            color: #444;
        }

        .card-label{
            padding:6px;
        }

        .card-button{
            padding:0px;
            border-radius:10px;
            background-color:black;
        }

        .artist-button{
            padding:0px;
        }

        .play-btn{
            padding-left:18px;
            padding-right:18px;
            padding-top:8px;
            padding-bottom:8px;
        }

        .artist-picture{
            border-radius:100px;
        }

        .lyrics{
            font-weight:bold;
            font-size:16pt;
            color:@theme_text_color;
        }
        '''
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(css, -1)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def on_download(self, *args):
        th = threading.Thread(target=self.win.download_song)
        th.deamon = True
        th.start()

    def on_login_action(self, *args):
        self.win.new_login()

    def do_activate(self):
        """Called when the application is activated.

        We raise the application's main window, creating it if
        necessary.
        """
        self.win = self.props.active_window
        if not self.win:
            self.win = TidalWindow(application=self)
        self.win.present()

    def on_about_action(self, widget, _):
        """Callback for the app.about action."""
        about = Adw.AboutWindow(transient_for=self.props.active_window,
                                application_name='High Tide',
                                application_icon='io.github.nokse22.high-tide',
                                developer_name='Nokse',
                                version='0.1.0',
                                developers=['Nokse'],
                                copyright='© 2023 Nokse')
        about.present()

    def on_preferences_action(self, widget, _):
        """Callback for the app.preferences action."""
        print('app.preferences action activated')

        builder = Gtk.Builder.new_from_resource("/io/github/nokse22/high-tide/preferences.ui")

        builder.get_object("_quality_row").connect("notify::selected", self.on_quality_changed)
        builder.get_object("_quality_row").set_selected(self.win.settings.get_int("quality"))

        builder.get_object("_preference_window").present()

    def on_quality_changed(self, widget, *args):
        self.win.select_quality(widget.get_selected())

    def create_action(self, name, callback, shortcuts=None):
        """Add an application action.

        Args:
            name: the name of the action
            callback: the function to be called when the action is
              activated
            shortcuts: an optional list of accelerators
        """
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", callback)
        self.add_action(action)
        if shortcuts:
            self.set_accels_for_action(f"app.{name}", shortcuts)

    def do_shutdown(self):
        track = self.win.player_object.playing_track
        list_ = self.win.player_object.current_mix_album
        if track and list_:
            track_id = track.id
            list_id = list_.id
            self.win.settings.set_int("last-playing-song-id", track_id)
            self.win.settings.set_int("last-playing-list-id", list_id)

def main(version):
    """The application's entry point."""
    app = TidalApplication()
    return app.run(sys.argv)
