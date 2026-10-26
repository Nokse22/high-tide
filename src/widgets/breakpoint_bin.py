# breakpoint_bin.py
#
# Copyright 2026 High Tide contributors
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

from gi.repository import Adw, Gtk


class HTBreakpointBin(Adw.BreakpointBin):
    """An Adw.BreakpointBin that grows to fit its content.

    Adw.BreakpointBin reports a zero minimum size when it has breakpoints, so
    it needs an explicit height-request. That fixed height only fits the font
    size it was designed for: with larger text the content overflows and gets
    clipped.

    Report the child's minimum height instead, while leaving the minimum width
    at zero so width-based breakpoints can still shrink the bin.
    """

    __gtype_name__ = "HTBreakpointBin"

    def do_get_request_mode(self):
        return Gtk.SizeRequestMode.HEIGHT_FOR_WIDTH

    def do_measure(self, orientation, for_size):
        child = self.get_child()

        if child is None:
            return 0, 0, -1, -1

        minimum, natural, _min_baseline, _nat_baseline = child.measure(
            orientation, for_size
        )

        if orientation == Gtk.Orientation.VERTICAL:
            return minimum, natural, -1, -1

        # Keep the minimum width at zero, like Adw.BreakpointBin does, so that
        # the bin can still reach width-based breakpoints.
        return 0, natural, -1, -1
