# Forked from:
# https://github.com/rafaelmardojai/blanket/blob/master/blanket/mpris.py
# Forked from:
# https://gitlab.gnome.org/World/lollypop/-/blob/master/lollypop/mpris.py
#
# Copyright (c) 2014-2020 Cedric Bellegarde <cedric.bellegarde@adishatz.org>
# Copyright (c) 2016 Gaurav Narula
# Copyright (c) 2016 Felipe Borges <felipeborges@gnome.org>
# Copyright (c) 2013 Arnel A. Borja <kyoushuu@yahoo.com>
# Copyright (c) 2013 Vadim Rutkovsky <vrutkovs@redhat.com>
# Copyright (c) 2020 Rafael Mardojai CM
# Copyright (c) 2023 Nokse22
# SPDX-License-Identifier: GPL-3.0-or-later

from random import randint

from gi.repository import Gdk, Gio, GLib

from .lib import utils

import logging

logger = logging.getLogger(__name__)


class Server:
    def __init__(self, con, path):
        method_outargs = {}
        method_inargs = {}
        for interface in Gio.DBusNodeInfo.new_for_xml(self.__doc__ or "").interfaces:
            for method in interface.methods:
                method_outargs[method.name] = (
                    "(" + "".join([arg.signature for arg in method.out_args]) + ")"
                )
                method_inargs[method.name] = tuple(
                    arg.signature for arg in method.in_args
                )

            con.register_object(
                object_path=path,
                interface_info=interface,
                method_call_closure=self.on_method_call,
            )

        self.method_inargs = method_inargs
        self.method_outargs = method_outargs

    def on_method_call(
        self,
        connection,
        sender,
        object_path,
        interface_name,
        method_name,
        parameters,
        invocation,
    ):
        args = list(parameters.unpack())
        for i, sig in enumerate(self.method_inargs[method_name]):
            if sig == "h":
                msg = invocation.get_message()
                fd_list = msg.get_unix_fd_list()
                args[i] = fd_list.get(args[i])

        try:
            result = getattr(self, method_name)(*args)

            # out_args is at least (signature1).
            # We therefore always wrap the result as a tuple.
            # Refer to https://bugzilla.gnome.org/show_bug.cgi?id=765603
            result = (result,)

            out_args = self.method_outargs[method_name]
            if out_args != "()":
                variant = GLib.Variant(out_args, result)
                invocation.return_value(variant)
            else:
                invocation.return_value(None)
        except Exception:
            logger.exception("MPRIS Error")


class MPRIS(Server):
    """
    <!DOCTYPE node PUBLIC
    "-//freedesktop//DTD D-BUS Object Introspection 1.0//EN"
    "http://www.freedesktop.org/standards/dbus/1.0/introspect.dtd">
    <node>
        <interface name="org.freedesktop.DBus.Introspectable">
            <method name="Introspect">
                <arg name="data" direction="out" type="s"/>
            </method>
        </interface>
        <interface name="org.freedesktop.DBus.Properties">
            <method name="Get">
                <arg name="interface" direction="in" type="s"/>
                <arg name="property" direction="in" type="s"/>
                <arg name="value" direction="out" type="v"/>
            </method>
            <method name="Set">
                <arg name="interface_name" direction="in" type="s"/>
                <arg name="property_name" direction="in" type="s"/>
                <arg name="value" direction="in" type="v"/>
            </method>
            <method name="GetAll">
                <arg name="interface" direction="in" type="s"/>
                <arg name="properties" direction="out" type="a{sv}"/>
            </method>
        </interface>
        <interface name="org.mpris.MediaPlayer2">
            <method name="Raise">
            </method>
            <method name="Quit">
            </method>
            <property name="CanQuit" type="b" access="read" />
            <property name="CanRaise" type="b" access="read" />
            <property name="Identity" type="s" access="read"/>
            <property name="DesktopEntry" type="s" access="read"/>
        </interface>
        <interface name="org.mpris.MediaPlayer2.Player">
            <method name="Next"/>
            <method name="Previous"/>
            <method name="PlayPause"/>
            <method name="Play"/>
            <method name="Pause"/>
            <method name="Stop"/>
            <method name="Seek">
                <arg name="Offset" direction="in" type="x"/>
            </method>
            <method name="SetPosition">
                <arg name="TrackId" direction="in" type="o"/>
                <arg name="Position" direction="in" type="x"/>
            </method>
            <property name="PlaybackStatus" type="s" access="read"/>
            <property name="Metadata" type="a{sv}" access="read">
            </property>
            <property name="Position" type="x" access="read"/>
            <property name="Volume" type="d" access="readwrite"/>
            <property name="CanGoNext" type="b" access="read"/>
            <property name="CanGoPrevious" type="b" access="read"/>
            <property name="CanPlay" type="b" access="read"/>
            <property name="CanPause" type="b" access="read"/>
            <property name="CanSeek" type="b" access="read"/>
            <property name="CanControl" type="b" access="read"/>
        </interface>
    </node>
    """

    __MPRIS_IFACE = "org.mpris.MediaPlayer2"
    __MPRIS_PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"
    __MPRIS_HIGH_TIDE = "org.mpris.MediaPlayer2.io.github.nokse22.high-tide"
    __MPRIS_PATH = "/org/mpris/MediaPlayer2"

    def __init__(self, player):
        self.player = player

        self.__metadata = {}

        track_id = 0 + randint(10000000, 90000000)
        self.__metadata["mpris:trackid"] = GLib.Variant("o", f"/Track/{track_id}")

        track = self.player.playing_track

        if track:
            self.__metadata["xesam:title"] = GLib.Variant("s", track.name)
            self.__metadata["xesam:album"] = GLib.Variant("s", track.album)
            self.__metadata["xesam:artist"] = GLib.Variant("as", [track.artist])
            self.__metadata["mpris:length"] = GLib.Variant(
                "x", self.player.query_duration() / 1000
            )

        self.__bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        Gio.bus_own_name_on_connection(
            self.__bus, self.__MPRIS_HIGH_TIDE, Gio.BusNameOwnerFlags.NONE, None, None
        )
        Server.__init__(self, self.__bus, self.__MPRIS_PATH)

        self.player.connect("song-changed", self._on_preset_changed)
        self.player.connect("duration-changed", self._on_preset_changed)
        self.player.connect("notify::playing", self._on_playing_changed)
        self.player.connect("volume-changed", self._on_volume_changed)

        self.start_position_updates()

    def start_position_updates(self):
        """Start a repeating timer to update the MPRIS Position property."""
        GLib.timeout_add(500, self._update_position)  # update every 500ms

    def _update_position(self):
        if self.player.playing_track:
            duration = self.player.query_duration() / 1000

            if (
                duration > 0
                and self.__metadata.get(
                    "mpris:length", GLib.Variant("x", 0)
                ).get_int64()
                != duration
            ):
                self.__metadata["mpris:length"] = GLib.Variant("x", int(duration))
                self.PropertiesChanged(
                    self.__MPRIS_PLAYER_IFACE,
                    {
                        "Metadata": GLib.Variant("a{sv}", self.__metadata),
                    },
                    [],
                )

            self.PropertiesChanged(
                self.__MPRIS_PLAYER_IFACE,
                {
                    "Position": GLib.Variant(
                        "x", int(self.player.query_position() / 1000)
                    )
                },
                [],
            )
        return True

    def Raise(self):
        """Bring the High Tide application window to the foreground"""
        utils.window.present_with_time(Gdk.CURRENT_TIME)

    def Quit(self):
        """Quit the High Tide application"""
        utils.window.quit()

    def Next(self):
        """Skip to the next track in the playlist or queue"""
        self.player.play_next()

    def Previous(self):
        """Skip to the previous track or restart the current track"""
        self.player.play_previous()

    def PlayPause(self):
        """Toggle between play and pause states"""
        self.player.play_pause()

    def Play(self):
        """Start or resume playback"""
        self.player.play()

    def Pause(self):
        """Pause the current playback"""
        self.player.pause()

    def Stop(self):
        """Stop playback (implemented as pause for TIDAL streams)"""
        self.player.pause()
        self._on_playing_changed()

    def Seek(self, offset):
        """Seek forward or backward by the given offset (offset in microseconds)"""
        current_pos_us = self.player.query_position() / 1000
        duration_us = self.player.query_duration() / 1000

        new_pos_us = current_pos_us + offset

        new_pos_us = max(0, min(new_pos_us, duration_us))

        seek_fraction = new_pos_us / duration_us if duration_us > 0 else 0

        self.player.seek(seek_fraction)

        self.PropertiesChanged(
            self.__MPRIS_PLAYER_IFACE,
            {"Position": GLib.Variant("x", int(new_pos_us))},
            [],
        )

    def SetPosition(self, track_id, position):
        """Set the playback position to a specific point (position in microseconds)"""
        duration_us = self.player.query_duration() / 1000

        position = max(0, min(position, duration_us))

        seek_fraction = position / duration_us if duration_us > 0 else 0

        self.player.seek(seek_fraction)

        self.PropertiesChanged(
            self.__MPRIS_PLAYER_IFACE,
            {"Position": GLib.Variant("x", int(position))},
            [],
        )

    def Get(self, interface, property_name):
        """Get the value of a specific MPRIS property.

        Args:
            interface (str): The D-Bus interface name
            property_name (str): The property name to retrieve

        Returns:
            GLib.Variant: The property value wrapped in a GVariant
        """
        if property_name in [
            "CanQuit",
            "CanRaise",
            "CanControl",
            "CanPlay",
            "CanPause",
        ]:
            return GLib.Variant("b", True)
        elif property_name == "CanGoNext":
            return GLib.Variant("b", self.player.can_go_next)
        elif property_name == "CanGoPrevious":
            return GLib.Variant("b", self.player.can_go_prev)
        elif property_name == "CanSeek":
            return GLib.Variant("b", True)
        elif property_name == "Identity":
            return GLib.Variant("s", "High Tide")
        elif property_name == "DesktopEntry":
            return GLib.Variant("s", "io.github.nokse22.high-tide")
        elif property_name == "PlaybackStatus":
            return GLib.Variant("s", self._get_status())
        elif property_name == "Metadata":
            return GLib.Variant("a{sv}", self.__metadata)
        elif property_name == "Position":
            return GLib.Variant("x", self.player.query_position() / 1000)
        elif property_name == "Volume":
            return GLib.Variant("d", self.player.query_volume())
        else:
            return GLib.Variant("b", False)

    def GetAll(self, interface):
        """Get all properties for a specific MPRIS interface.

        Args:
            interface (str): The D-Bus interface name

        Returns:
            dict: Dictionary containing all properties and their values
        """
        ret = {}
        if interface == self.__MPRIS_IFACE:
            for property_name in ["CanQuit", "CanRaise", "Identity", "DesktopEntry"]:
                ret[property_name] = self.Get(interface, property_name)
        elif interface == self.__MPRIS_PLAYER_IFACE:
            for property_name in [
                "PlaybackStatus",
                "Metadata",
                "Position",
                "Volume",
                "CanGoNext",
                "CanGoPrevious",
                "CanPlay",
                "CanPause",
                "CanControl",
                "CanSeek",
            ]:
                ret[property_name] = self.Get(interface, property_name)
        return ret

    def Set(self, interface, property_name, new_value):
        """Set the value of a specific MPRIS property.

        Args:
            interface (str): The D-Bus interface name
            property_name (str): The property name to set
            new_value: The new value for the property
        """
        if property_name == "Volume":
            self.player.change_volume(new_value)

    def PropertiesChanged(
        self, interface_name, changed_properties, invalidated_properties
    ):
        """Emit a PropertiesChanged signal on D-Bus.

        Notifies other applications that MPRIS properties have changed.

        Args:
            interface_name (str): The interface that had properties changed
            changed_properties (dict): Properties that changed with new values
            invalidated_properties (list): Properties that were invalidated
        """
        self.__bus.emit_signal(
            None,
            self.__MPRIS_PATH,
            "org.freedesktop.DBus.Properties",
            "PropertiesChanged",
            GLib.Variant.new_tuple(
                GLib.Variant("s", interface_name),
                GLib.Variant("a{sv}", changed_properties),  # type: ignore
                GLib.Variant("as", invalidated_properties),
            ),
        )

    def Introspect(self):
        """Return the D-Bus introspection XML for this interface.

        Returns:
            str: The XML introspection data describing available methods and properties
        """
        return self.__doc__

    def _get_status(self):
        playing = self.player.playing
        if playing:
            return "Playing"
        else:
            return "Paused"

    def _on_preset_changed(self, *args):
        if self.player.playing_track is None:
            return

        self.__metadata["xesam:title"] = GLib.Variant(
            "s", self.player.playing_track.name
        )
        self.__metadata["xesam:album"] = GLib.Variant(
            "s", self.player.playing_track.album.name
        )
        self.__metadata["xesam:artist"] = GLib.Variant(
            "as", [self.player.playing_track.artist.name]
        )
        self.__metadata["mpris:length"] = GLib.Variant(
            "x", self.player.query_duration() / 1000
        )

        # 320 px should always be fetched for example by queue logic
        url = f"file://{utils.IMG_DIR}/{self.player.playing_track.album.id}_320.jpg"

        self.__metadata["mpris:artUrl"] = GLib.Variant("s", url)

        changed_properties = {
            "Metadata": GLib.Variant("a{sv}", self.__metadata),
            "Position": GLib.Variant("x", self.player.query_position() / 1000),
            "CanGoNext": GLib.Variant("b", self.player.can_go_next),
            "CanGoPrevious": GLib.Variant("b", self.player.can_go_prev),
        }
        self.PropertiesChanged(self.__MPRIS_PLAYER_IFACE, changed_properties, [])

    def _on_volume_changed(self, _player, volume):
        self.PropertiesChanged(
            self.__MPRIS_PLAYER_IFACE, {"Volume": GLib.Variant("d", volume)}, []
        )

    def _on_playing_changed(self, *args):
        properties = {"PlaybackStatus": GLib.Variant("s", self._get_status())}
        self.PropertiesChanged(self.__MPRIS_PLAYER_IFACE, properties, [])
