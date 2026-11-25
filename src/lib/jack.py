# jack.py
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Where the JACK output connects to (the "Connect To" preference)."""

import ctypes
import logging
import os
from typing import List

logger = logging.getLogger(__name__)

# Values of the jack-connect setting other than a JACK client's name
SOUND_CARD = ""
NOTHING = "@nothing"

# A Flatpak app may not connect its own JACK ports (PipeWire gives sandboxed
# apps read-only access to other programs), so a patchbay has to do it
IN_FLATPAK = os.path.exists("/.flatpak-info")

_JACK_NO_START_SERVER = 0x01
_JACK_PORT_IS_INPUT = 0x1
_JACK_AUDIO_TYPE = b"32 bit float mono audio"

# Characters with a meaning in the POSIX regular expressions JACK matches
# port names with
_REGEX_SPECIAL = set("\\^.[$()|*+?{")


def port_pattern(client: str) -> str:
    """The pattern matching every port of the given JACK client"""
    escaped = "".join("\\" + c if c in _REGEX_SPECIAL else c for c in client)
    return f"^{escaped}:"


def list_destinations() -> List[str]:
    """The JACK clients with audio inputs, such as sound cards and sinks.

    Returns an empty list when JACK can't be reached."""
    try:
        jack = ctypes.CDLL("libjack.so.0")
    except OSError:
        return []

    jack.jack_client_open.restype = ctypes.c_void_p
    jack.jack_client_open.argtypes = [
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_int),
    ]
    jack.jack_get_ports.restype = ctypes.POINTER(ctypes.c_char_p)
    jack.jack_get_ports.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_ulong,
    ]
    jack.jack_free.argtypes = [ctypes.c_void_p]
    jack.jack_client_close.argtypes = [ctypes.c_void_p]

    status = ctypes.c_int(0)
    client = jack.jack_client_open(
        b"High Tide port list", _JACK_NO_START_SERVER, ctypes.byref(status)
    )
    if not client:
        logger.info("JACK isn't running, no outputs to list")
        return []

    clients: List[str] = []
    try:
        ports = jack.jack_get_ports(
            client, None, _JACK_AUDIO_TYPE, _JACK_PORT_IS_INPUT
        )
        if ports:
            i = 0
            while ports[i]:
                name = ports[i].decode(errors="replace")
                owner = name.rpartition(":")[0]
                if owner and owner not in clients:
                    clients.append(owner)
                i += 1
            jack.jack_free(ports)
    finally:
        jack.jack_client_close(client)
    return clients
