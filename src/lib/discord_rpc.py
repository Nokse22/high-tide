import logging
import queue
import threading
import time
from enum import Enum

from tidalapi.media import Track

from pypresence.presence import Presence
from pypresence.types import ActivityType

logger = logging.getLogger(__name__)

try:
    import pypresence

    has_pypresence = True
except ImportError:
    logger.warning("pypresence not found, skipping")
    has_pypresence = False


class State(Enum):
    DISCONNECTED = 0
    IDLE = 1
    PLAYING = 2


state: State = State.DISCONNECTED
disconnect_thread: threading.Thread | None = None

# Discord IPC calls can block for a long time (e.g. ~30s before Discord
# rejects an invalid client ID), so they run on a single daemon worker thread
# to keep the GTK main loop responsive while preserving call order.
_tasks: queue.SimpleQueue = queue.SimpleQueue()

# Set when Discord rejects the client ID; retrying would only block again.
_client_rejected = False


def th_run_tasks() -> None:
    """Run queued Discord IPC calls one at a time, in order."""
    while True:
        func, args = _tasks.get()
        try:
            func(*args)
        except Exception:
            logger.exception("Error while running a Discord IPC task")


def _submit(func, *args) -> None:
    _tasks.put((func, args))


def _connect() -> bool:
    """Connect to Discord Rich Presence IPC.

    Attempts to establish a connection to Discord's IPC server for
    Rich Presence functionality.

    Returns:
        bool: True if connection successful, False otherwise
    """
    global state
    global _client_rejected

    if not has_pypresence or _client_rejected:
        return False

    try:
        rpc.connect()
    except pypresence.exceptions.InvalidID:
        logger.warning("Discord rejected the client ID, disabling Rich Presence")
        _client_rejected = True
        state = State.DISCONNECTED
        return False
    except Exception:
        logger.debug(
            "Can't connect to discord IPC; usually means that the RPC server is closed."
        )
        state = State.DISCONNECTED
        return False
    else:
        logger.info("Connected to discord IPC")
        state = State.IDLE
        return True


def _disconnect() -> bool:
    """Disconnect from Discord Rich Presence IPC.

    Closes the connection to Discord's IPC server and updates the state.

    Returns:
        bool: True if disconnection successful, False otherwise
    """
    global state

    if not has_pypresence:
        return False

    try:
        rpc.close()
    except Exception:
        logger.debug("Can't disconnect from discord IPC")
        return False
    else:
        logger.info("Disconnected from discord IPC")
        state = State.DISCONNECTED
        return True


def _set_activity(track: Track | None = None, offset_ms: int = 0) -> None:
    """Set the Discord Rich Presence activity status.

    Updates Discord with the current playing track information and playback position.

    Args:
        track: The currently playing Track object, or None to clear activity
        offset_ms: Current playback position in milliseconds (default: 0)
    """
    global state
    global disconnect_thread

    if not has_pypresence:
        return

    if track is None:
        if state != State.DISCONNECTED:
            try:
                rpc.clear()
                state = State.IDLE
            except Exception:
                state = State.DISCONNECTED
        return

    if state == State.DISCONNECTED:
        if not _connect():
            return

    try:
        if track is not None:
            artists = (
                [artist.name for artist in track.artists if artist.name is not None]
                if track.artists
                else None
            )
            if artists is not None and len(artists) == 0:
                artists = None

            rpc.update(
                activity_type=ActivityType.LISTENING,
                details=track.name,
                state=", ".join(artists)
                if artists
                else "Unknown Artist",
                large_image=track.album.image()
                if track.album
                else "hightide_x1024",
                small_text="High Tide"
                if track.album
                else None,
                start=int(time.time() - offset_ms),
                end=int(
                    time.time() - offset_ms + track.duration
                ),
            )
            state = State.PLAYING
    except (pypresence.exceptions.PipeClosed, AssertionError) as e:
        if _connect():
            _set_activity(track, offset_ms)
        else:
            state = State.DISCONNECTED
            logger.debug(f"Connection with discord IPC lost: {e}")
    except Exception:
        state = State.DISCONNECTED
        logger.exception("Unknown error with discord IPC")


def connect() -> None:
    """Connect to Discord Rich Presence IPC in the background."""
    _submit(_connect)


def disconnect() -> None:
    """Disconnect from Discord Rich Presence IPC in the background."""
    _submit(_disconnect)


def set_activity(track: Track | None = None, offset_ms: int = 0) -> None:
    """Set the Discord Rich Presence activity status in the background.

    See _set_activity for details; this never blocks the caller.
    """
    _submit(_set_activity, track, offset_ms)


if has_pypresence:
    rpc: Presence = Presence(client_id=1379096506065223680)
    threading.Thread(target=th_run_tasks, name="discord-rpc", daemon=True).start()
    connect()
