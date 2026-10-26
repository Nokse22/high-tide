# ADR 0001: Faster logged-in launch

- Status: Accepted
- Date: 2026-10-15

## Context

On a launch with an existing login, the home page spinner is slow. Two things
put unnecessary work on the critical path:

1. `HighTideWindow.th_login` calls `utils.get_favourites()` **synchronously**
   before `on_logged_in()` starts the home page. `get_favourites()` is a
   paginated playlist loop over the network, so the home spinner waits for the
   entire favourites fetch — even though the home page does not need
   favourites to render.
2. Every TIDAL API GET request hits the network on every launch, including
   the ~120 per-card/playlist fetches that populate the home feed. Relaunching
   re-downloads all of it even when nothing has changed.

The favourites data is only consumed by `is_favourited()` (hearts) and the
Collection page; it is not needed to paint the home page.

## Decision

**1. De-block the home page from the favourites fetch.**

Reorder `th_login` so `on_logged_in()` is scheduled first and
`get_favourites()` runs in a background thread:

```python
GLib.idle_add(self.on_logged_in)
threading.Thread(target=utils.get_favourites, daemon=True).start()
```

This is safe because `is_favourited()` reads the `favourite_*` lists, which
default to `[]` and return `False` until loaded — hearts simply fill in as the
favourites arrive.

**2. Disk-cache all TIDAL API GET responses with TTL revalidation.**

Add an `_ApiCache` (in `src/lib/utils.py`) that wraps the session's
`requests.Session.request`. For every cacheable request:

- **Cache hit** (file present, age < `max_age` = 1 day): serve the stored
  body + headers as a synthetic `requests.Response`. No network.
- **Cache miss** (file absent or older than `max_age`): issue the network
  request, write the response body + headers to disk, return the live response.

No background revalidation threads. The cache is a transparent TTL layer —
stale means "fetch fresh", never "serve stale in background".

### Cache filter

A request is cached only if **all** of these hold:

- Method is `GET`
- Host is `api.tidal.com`
- URL does **not** contain `playbackinfo` (temporary streaming tokens)

### Storage format

Each cache entry is a JSON file:

```json
{"ts": <unix_epoch>, "body": "<response text>", "headers": {"etag": "...", ...}}
```

Headers are stored because `tidalapi` reads `response.headers["etag"]` during
object construction. Without them, cached responses crash `UserPlaylist` and
other tidalapi classes.

### Cache directory

`$XDG_CACHE_HOME/high-tide/api/<user_id>/` where `<user_id>` is the TIDAL user
id (or `"anon"` before login). Resolved from `XDG_CACHE_HOME` so Flatpak
sandboxes land in the per-app home.

### Keying

File path is derived from the URL path + sorted query params, hashed to keep
filenames short and filesystem-safe.

## Consequences

- The home page no longer waits on the favourites fetch on **every** launch.
- Relaunches serve all previously-fetched API data from disk instantly (no
  spinner for cached content). Only genuinely new or stale (>1 day) endpoints
  hit the network.
- Cache files are disposable and safe to delete at any time.
- A synthetic `requests.Response` served from cache must carry a minimal
  `PreparedRequest` (because tidalapi reads `response.request.url`) and the
  original response headers (because tidalapi reads `response.headers["etag"]`).
- `HTHomePage` is a thin subclass of `HTGenericPage` — no live-swap logic.
- `set_cache_user()` (in `window.py`) keys the cache directory per user.
- **Non-goal / out of scope:** per-card image fetches (already disk-cached by
  the image loader).
