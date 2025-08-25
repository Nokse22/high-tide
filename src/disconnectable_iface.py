# disconnectable_iface.py
#
# Copyright 2024 Nokse22
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


from typing import Any, List, Tuple


class IDisconnectable:
    """
    A class that provides automatic resource cleanup for GTK widgets and other objects.

    This class manages three types of resources that need cleanup:
    - GTK signals (stored in self.signals)
    - Data bindings (stored in self.bindings)
    - Child disconnectable widgets (stored in self.disconnectables)

    Usage:
    ------
    1. Inherit from IDisconnectable alongside your main class:

    >>> class MyWidget(Gtk.Box, IDisconnectable):
    ...     def __init__(self):
    ...         Gtk.Box.__init__(self)
    ...         IDisconnectable.__init__(self)

    2. When connecting signals, store them in self.signals as a tuple of the object
        and the handler id:

    >>> self.signals.append((some_object, some_object.connect("signal-name", callback)))

    3. When creating bindings, store them in self.bindings:

    >>> self.bindings.append(some_binding_object.bind_property(...))

    4. When creating child widgets that are also IDisconnectable, store them:

    >>> child_widget = SomeDisconnectableWidget()
    ... self.disconnectables.append(child_widget)

    5. Call disconnect_all() when the widget is being destroyed:
    """

    def __init__(self) -> None:
        self.signals: List[Tuple[Any, int]] = []
        self.bindings: List[Any] = []
        self.disconnectables: List["IDisconnectable"] = []

    def connect_signal(
        self, g_object: Any, signal_name: str, callback_func: Any, *args
    ) -> None:
        """Connect a signal and track it for later disconnection.

        Args:
            g_object: The GObject to connect the signal to
            signal_name (str): Name of the signal to connect
            callback_func: The callback function to execute when signal is emitted
            *args: Additional arguments to pass to the callback function
        """
        self.signals.append((
            g_object,
            g_object.connect(signal_name, callback_func, *args),
        ))

    def disconnect_all(self, *_args) -> None:
        """Disconnect all tracked signals and child disconnectable objects.

        This method should be called when the widget is being removed to ensure
        proper cleanup. It disconnects all tracked signal connections and
        recursively calls disconnect_all on child disconnectable objects.
        """

        for obj, signal_id in self.signals:
            if obj.handler_is_connected(signal_id):
                obj.disconnect(signal_id)
        del self.signals

        for binding in self.bindings:
            try:
                binding.unbind()
            except Exception:
                pass
        del self.bindings

        for widget in self.disconnectables:
            try:
                widget.disconnect_all()
            except Exception:
                pass
        del self.disconnectables

        self.signals = []
        self.bindings = []
        self.disconnectables = []

    def __repr__(self, *args) -> str | None:
        return self.__gtype_name__ if self.__gtype_name__ else None

    # def __del__(self):
    #     print(f"DELETING {self}")
