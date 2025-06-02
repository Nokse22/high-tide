from tidalapi.media import Track
import time
try:
    import discordrpc
except ImportError:
    print("discordrpc not found, skipping")
    discordrpc = None

if discordrpc:
    rpc = discordrpc.RPC(app_id=1379096506065223680)

def set_activity(track: Track = None, offset_ms: int = 0):
    if not discordrpc:
        print("[discordrpc] library not installed, skipping")
        return

    if track is None:
        rpc.set_activity(
            act_type=2,
            details="High Tide",
            state="TIDAL gnome client",
            large_image="hightide_x1024",
            large_text="High Tide",
            buttons=discordrpc.Button(
                    "Get High Tide",
                    "https://github.com/nokse22/high-tide"
                ),
        )
    else:
        rpc.set_activity(
            act_type=2,
            details=track.name,
            state=f"By {track.artist.name}",
            large_image="hightide_x1024",
            large_text="High Tide",
            ts_start=int(time.time() * 1_000 - offset_ms),
            buttons=discordrpc.Button(
                    "Listen to this song",
                    track.share_url,
                    "Get High Tide",
                    "https://github.com/nokse22/high-tide"
                ),
        )