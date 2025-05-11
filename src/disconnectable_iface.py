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

class IDisconnectable:
    def __init__(self):
        self.signals = []
        self.bindings = []
        self.disconnectables = []

    def disconnect_all(self, *_args):
        """Disconnects all signals so that the class can be deleted"""

        try:
            for obj, signal_id in self.signals:
                obj.disconnect(signal_id)
            del self.signals
        except Exception:
            pass

        try:
            for binding in self.bindings:
                binding.unbind()
            del self.bindings
        except Exception:
            pass

        try:
            for widget in self.disconnectables:
                widget.disconnect_all()
            del self.disconnectables
        except Exception:
            pass
