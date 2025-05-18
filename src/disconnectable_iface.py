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

        for obj, signal_id in self.signals:
            try:
                obj.disconnect(signal_id)
            except Exception:
                pass
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

    # def __del__(self):
    #     print(f"DELETING {self}")
