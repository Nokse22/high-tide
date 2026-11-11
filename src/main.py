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
import threading
from gettext import gettext as _
from typing import Any, Callable, List

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from .lib import utils
from .lib.player_object import AudioSink
from .window import HighTideWindow


class HighTideApplication(Adw.Application):
    """The main application singleton class.

    This class handles the main application lifecycle, manages global actions,
    preferences, and provides the entry point for the High Tide TIDAL music player.
    """

    def __init__(self) -> None:
        super().__init__(
            application_id="io.github.nokse22.high-tide",
            flags=Gio.ApplicationFlags.HANDLES_OPEN,
        )
        self.create_action("quit", lambda *_: self.quit(), ["<primary>q", "<primary>w"])
        self.create_action("about", self.on_about_action)
        self.create_action(
            "preferences", self.on_preferences_action, ["<primary>comma"]
        )
        self.create_action("log-in", self.on_login_action)
        self.create_action("log-out", self.on_logout_action)

        utils.init()
        utils.setup_logging()

        self.settings: Gio.Settings = Gio.Settings.new("io.github.nokse22.high-tide")

        self.preferences: Gtk.Window | None = None

        self.alsa_devices = utils.get_alsa_devices()

        self.connect("shutdown", self.on_shutdown)

    def on_shutdown(self, *args) -> None:
        """Report the play in progress before the app closes"""
        win = self.props.active_window
        if win and getattr(win, "play_reporter", None):
            win.play_reporter.flush()

    def do_open(self, files: List[Gio.File], n_files: int, hint: str) -> None:
        self.win: HighTideWindow | None = self.props.active_window
        if not self.win:
            self.do_activate()

        uri: str = files[0].get_uri()
        if uri:
            if self.win.is_logged_in:
                utils.open_tidal_uri(uri)
            else:
                self.win.queued_uri = uri

    def on_login_action(self, *args) -> None:
        """Handle the login action by initiating a new login process."""
        self.win.new_login()

    def on_logout_action(self, *args) -> None:
        """Handle the logout action by logging out the current user."""
        self.win.logout()

    def do_activate(self) -> None:
        """Activate the application by creating and presenting the main window."""
        self.win: HighTideWindow | None = self.props.active_window
        if not self.win:
            # The custom symbolic icons are bundled in high-tide.gresource
            # rather than installed into the user's icon theme. The display is
            # guaranteed to exist by the time the application is activated.
            icon_theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
            icon_theme.add_resource_path(
                "/io/github/nokse22/high-tide/icons",
            )
            self.win = HighTideWindow(application=self)

        self.win.present()

    def on_about_action(self, widget: Any, *args) -> None:
        """Display the about dialog with application information"""
        about = Adw.AboutDialog(
            application_name="High Tide",
            application_icon="io.github.nokse22.high-tide",
            developer_name="The High Tide Contributors",
            version="1.6.0",
            developers=[
                "Nokse https://github.com/Nokse22",
                "Nila The Dragon https://github.com/nilathedragon",
                "Dråfølin https://github.com/drafolin",
                "Plamper https://github.com/Plamper",
                "Petru Mare https://github.com/Petru101",
            ],
            copyright="© 2023-2025 Nokse",
            license_type="GTK_LICENSE_GPL_3_0",
            issue_url="https://github.com/Nokse22/high-tide/issues",
            website="https://github.com/Nokse22/high-tide",
        )

        about.set_support_url("https://matrix.to/#/%23high-tide:matrix.org")

        about.present(self.props.active_window)

    def on_preferences_action(self, *args) -> None:
        """Display the preferences window and bind settings to UI controls"""

        if not self.preferences:
            builder: Gtk.Builder = Gtk.Builder.new_from_resource(
                "/io/github/nokse22/high-tide/ui/preferences.ui"
            )

            builder.get_object("_quality_row").set_selected(
                self.settings.get_int("quality")
            )
            builder.get_object("_quality_row").connect(
                "notify::selected", self.on_quality_changed
            )

            builder.get_object("_sink_row").set_selected(
                self.settings.get_int("preferred-sink")
            )
            builder.get_object("_sink_row").connect(
                "notify::selected", self.on_sink_changed
            )

            bg_row: Gtk.Widget = builder.get_object("_background_row")
            bg_row.set_active(self.settings.get_boolean("run-background"))
            self.settings.bind(
                "run-background", bg_row, "active", Gio.SettingsBindFlags.DEFAULT
            )

            builder.get_object("_normalize_row").set_active(
                self.settings.get_boolean("normalize")
            )
            builder.get_object("_normalize_row").connect(
                "notify::active", self.on_normalize_changed
            )

            builder.get_object("_quadratic_volume_row").set_active(
                self.settings.get_boolean("quadratic-volume")
            )
            builder.get_object("_quadratic_volume_row").connect(
                "notify::active", self.on_quadratic_volume_changed
            )

            builder.get_object("_video_cover_row").set_active(
                self.settings.get_boolean("video-covers")
            )
            builder.get_object("_video_cover_row").connect(
                "notify::active", self.on_video_covers_changed
            )

            builder.get_object("_discord_rpc_row").set_active(
                self.settings.get_boolean("discord-rpc")
            )
            builder.get_object("_discord_rpc_row").connect(
                "notify::active", self.on_discord_rpc_changed
            )

            self.settings.bind(
                "prefer-clean-versions",
                builder.get_object("_prefer_clean_row"),
                "active",
                Gio.SettingsBindFlags.DEFAULT,
            )

            self.lastfm_status_row = builder.get_object("_lastfm_status_row")
            self.lastfm_connect_button = builder.get_object(
                "_lastfm_connect_button"
            )
            self.lastfm_disconnect_button = builder.get_object(
                "_lastfm_disconnect_button"
            )
            self.lastfm_connect_button.connect(
                "clicked", self.on_lastfm_connect_clicked
            )
            self.lastfm_disconnect_button.connect(
                "clicked", self.on_lastfm_disconnect_clicked
            )
            self.lastfm_auth_pending = False
            self.update_lastfm_preferences()

            self.alsa_row = builder.get_object("_alsa_device_row")

            # Create a new label factory to just set max_width
            # Idk how to add the tickmark back
            factory = Gtk.SignalListItemFactory()

            def setup(factory, list_item):
                label = Gtk.Label(xalign=0)
                label.set_width_chars(1)
                list_item.set_child(label)

            def bind(factory, list_item):
                label = list_item.get_child()
                string_obj = list_item.get_item()
                label.set_text(string_obj.get_string())

            factory.connect("setup", setup)
            factory.connect("bind", bind)

            self.alsa_row.set_factory(factory)

            names = Gtk.StringList.new([d["name"] for d in self.alsa_devices])
            self.alsa_row.set_model(names)

            last_used_device = self.settings.get_string("alsa-device")

            selected_index = next(
                (
                    i
                    for i, d in enumerate(self.alsa_devices)
                    if d["hw_device"] == last_used_device
                ),
                0,
            )
            self.alsa_row.set_selected(selected_index)
            builder.get_object("_alsa_device_row").set_selected(selected_index)
            self.alsa_row.connect("notify::selected", self.on_alsa_device_changed)

            alsa_used = AudioSink.ALSA == self.settings.get_int("preferred-sink")
            self.alsa_row.set_sensitive(alsa_used)
            if not alsa_used:
                self.alsa_row.set_selected(0)

            builder.get_object("_sink_row").connect(
                "notify::selected-item", self.deactive_alsa_device_row
            )

            self.blocked_groups = [
                (builder.get_object("_blocked_artists_group"), "artists"),
                (builder.get_object("_blocked_tracks_group"), "tracks"),
                (builder.get_object("_blocked_videos_group"), "videos"),
            ]
            self.blocked_rows = []

            self.preferences = builder.get_object("_preference_window")

        self.update_blocked_rows()
        self.preferences.present(self.win)

    def update_blocked_rows(self) -> None:
        """Fill the Blocked preferences page with the blocked items"""

        for group, row in self.blocked_rows:
            group.remove(row)
        self.blocked_rows = []

        for group, name in self.blocked_groups:
            items = getattr(utils, f"blocked_{name}")
            group.set_visible(len(items) > 0)

            for item in items:
                row = Adw.ActionRow(title=item.name, use_markup=False)

                artists = getattr(item, "artists", None)
                if artists:
                    row.set_subtitle(", ".join(artist.name for artist in artists))

                button = Gtk.Button(
                    label=_("Unblock"), valign=Gtk.Align.CENTER, css_classes=["flat"]
                )
                button.connect(
                    "clicked",
                    lambda _btn, item=item: utils.toggle_blocked(
                        item, lambda *_: self.update_blocked_rows()
                    ),
                )
                row.add_suffix(button)

                group.add(row)
                self.blocked_rows.append((group, row))

    def on_quality_changed(self, widget: Any, *args) -> None:
        self.win.select_quality(widget.get_selected())

    def on_sink_changed(self, widget: Any, *args) -> None:
        self.win.change_audio_sink(widget.get_selected())

    def on_alsa_device_changed(self, widget: Any, *args) -> None:
        index = widget.get_selected()
        device_string = self.alsa_devices[index]["hw_device"]
        self.win.change_alsa_device(device_string)

    def on_normalize_changed(self, widget: Any, *args) -> None:
        self.win.change_normalization(widget.get_active())

    def on_quadratic_volume_changed(self, widget: Any, *args) -> None:
        self.win.change_quadratic_volume(widget.get_active())

    def on_video_covers_changed(self, widget: Any, *args) -> None:
        self.win.change_video_covers_enabled(widget.get_active())

    def on_discord_rpc_changed(self, widget: Any, *args) -> None:
        self.win.change_discord_rpc_enabled(widget.get_active())

    def update_lastfm_preferences(self, error: str | None = None) -> None:
        client = self.win.lastfm_client
        self.lastfm_connect_button.set_sensitive(True)
        self.lastfm_disconnect_button.set_visible(client.authenticated)
        self.lastfm_connect_button.set_visible(not client.authenticated)

        if error:
            self.lastfm_status_row.set_title(_("Connection failed"))
            self.lastfm_status_row.set_subtitle(error)
        elif client.authenticated:
            self.lastfm_status_row.set_title(
                _("Connected as {username}").format(username=client.username)
            )
            self.lastfm_status_row.set_subtitle(
                _("Now playing and completed listens will be sent to Last.fm.")
            )
        elif self.lastfm_auth_pending:
            self.lastfm_status_row.set_title(_("Waiting for authorization"))
            self.lastfm_status_row.set_subtitle(
                _("Authorize High Tide in your browser, then click Finish.")
            )
            self.lastfm_connect_button.set_label(_("Finish"))
        else:
            self.lastfm_status_row.set_title(_("Not connected"))
            self.lastfm_status_row.set_subtitle("")
            self.lastfm_connect_button.set_label(_("Connect"))

    def on_lastfm_connect_clicked(self, *_args) -> None:
        self.lastfm_connect_button.set_sensitive(False)
        if self.lastfm_auth_pending:
            target = self.th_finish_lastfm_authentication
            args = ()
        else:
            target = self.th_begin_lastfm_authentication
            args = ()
        threading.Thread(target=target, args=args, daemon=True).start()

    def th_begin_lastfm_authentication(self) -> None:
        try:
            auth_url = self.win.lastfm_client.begin_authentication()
        except Exception as exc:
            GLib.idle_add(self.on_lastfm_authentication_failed, str(exc))
            return
        GLib.idle_add(self.on_lastfm_authorization_ready, auth_url)

    def on_lastfm_authorization_ready(self, auth_url: str) -> None:
        self.lastfm_auth_pending = True
        self.update_lastfm_preferences()
        Gio.AppInfo.launch_default_for_uri(auth_url, None)

    def th_finish_lastfm_authentication(self) -> None:
        try:
            self.win.lastfm_client.finish_authentication()
        except Exception as exc:
            GLib.idle_add(self.on_lastfm_authentication_failed, str(exc))
            return
        GLib.idle_add(self.on_lastfm_authentication_finished)

    def on_lastfm_authentication_finished(self) -> None:
        self.lastfm_auth_pending = False
        self.win.lastfm_scrobbler.credentials_changed()
        self.update_lastfm_preferences()

    def on_lastfm_authentication_failed(self, message: str) -> None:
        self.update_lastfm_preferences(message)

    def on_lastfm_disconnect_clicked(self, *_args) -> None:
        self.win.lastfm_client.disconnect()
        self.lastfm_auth_pending = False
        self.win.lastfm_scrobbler.credentials_changed()
        self.update_lastfm_preferences()

    def deactive_alsa_device_row(self, widget: Any, *args) -> None:
        alsa_used = widget.get_selected() == AudioSink.ALSA
        self.alsa_row.set_sensitive(alsa_used)
        if not alsa_used:
            self.alsa_row.set_selected(0)

    def create_action(
        self, name: str, callback: Callable, shortcuts: List[str] | None = None
    ) -> None:
        """Create a new application action with optional keyboard shortcuts.

        Args:
            name: The action name
            callback: The callback function to execute when action is triggered
            shortcuts: Optional list of keyboard shortcut strings
        """
        action: Gio.SimpleAction = Gio.SimpleAction.new(name, None)
        action.connect("activate", callback)
        self.add_action(action)
        if shortcuts:
            self.set_accels_for_action(f"app.{name}", shortcuts)


def main(version: str) -> int:
    """The application's entry point."""
    app: HighTideApplication = HighTideApplication()
    app.set_version(version)
    return app.run(sys.argv)
