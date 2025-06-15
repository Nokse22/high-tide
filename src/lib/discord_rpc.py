import logging
from tidalapi.media import Track
import time
try:
    import pypresence
    rpc: pypresence.Presence | None = None
except ImportError:
    print("pypresence not found, skipping")
    pypresence = None

connected: bool = False
logger = logging.getLogger(__name__)


def connect():
    global connected

    if pypresence is None:
        return False

    try:
        rpc.connect()
    except Exception:
        logger.debug("Can't connect to discord IPC; usually means that the RPC server is closed.")
        connected = False
        return False
    else:
        logger.info("Connected to discord IPC")
        connected = True
        return True


def set_activity(track: Track | None = None, offset_ms: int = 0):
    global connected

    if pypresence is None:
        return

    if not connected:
        if not connect():
            return

    try:
        if track is None:
            rpc.update(
                activity_type=pypresence.ActivityType.LISTENING,
                details="High Tide",
                state="TIDAL gnome client",
                large_image="hightide_x1024",
                large_text="High Tide",
                buttons=[
                    {
                        "label": "Get High Tide",
                        "url": "https://github.com/nokse22/high-tide"
                    }
                ]
            )
        else:
            rpc.update(
                activity_type=pypresence.ActivityType.LISTENING,
                details=track.name,
                state=f"By {track.artist.name}",
                large_image=track.album.image() if track.album else "hightide_x1024",
                large_text=track.name if track.album else "High Tide",
                small_image="hightide_x1024" if track.album else None,
                small_text="High Tide" if track.album else None,
                start=int(time.time() * 1_000 - offset_ms),
                buttons=[
                    {
                        "label": "Listen to this song",
                        "url": f"{track.share_url}?u"
                    },
                    {
                        "label": "Get High Tide",
                        "url": "https://github.com/nokse22/high-tide"
                    }
                ],
            )
    except pypresence.exceptions.PipeClosed:
        if connect():
            set_activity(track, offset_ms)
        else:
            connected = False
            logger.error("Connection with discord IPC lost.")


if pypresence:
    rpc = pypresence.Presence(client_id=1379096506065223680)
    connect()
else:
    logger.info("[pypresence] library not installed, rpc disabled")
