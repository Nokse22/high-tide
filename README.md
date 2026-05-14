<div align="center">
  <img height="128" src="data/icons/hicolor/scalable/apps/io.github.nokse22.high-tide.svg" alt="High Tide Logo"/>

  # High Tide (AI fork)

  <p align="center">
    <strong>Linux client for TIDAL streaming service</strong>
  </p>

  <p align="center">
    <a href="https://www.gnu.org/licenses/gpl-3.0">
      <img src="https://img.shields.io/badge/License-GPLv3-blue.svg" alt="License: GPL v3"/>
    </a>
    <a href="https://www.python.org/">
      <img src="https://img.shields.io/badge/Made%20with-Python-ff7b3f.svg" alt="Made with Python"/>
    </a>
  </p>
</div>

> [!IMPORTANT]
> Not affiliated in any way with TIDAL, this is a third-party unofficial client.

> [!NOTE]
> This is a personal fork of [Nokse22/high-tide](https://github.com/Nokse22/high-tide) with an added AI Radio feature. Upstream changes are merged periodically from the `master` branch.

## Installation

This fork is only available by building from source.

### Dependencies

- Python 3.10+
- GTK 4
- libadwaita 1.4+
- GStreamer
- `blueprint-compiler`
- Meson 0.62+

### Build

```sh
git clone https://github.com/hcuadrado/high-tide.git
cd high-tide
meson builddir
meson compile -C builddir
meson install -C builddir
```

The installed binary is named `high-tide-ai`.

## AI Radio

AI Radio generates a personalized TIDAL radio station from a plain-language description. It uses an AI provider of your choice to translate your prompt into search queries, resolves seeds on TIDAL, and builds a radio mix from them.

### Supported providers

| Provider | Requires |
|---|---|
| OpenAI | API key |
| Anthropic | API key |
| Google Gemini | API key |
| Ollama | Local instance running at a configurable URL |

### Setup

1. Open **Preferences** (hamburger menu or `Ctrl+,`)
2. Scroll to the **AI Radio** section
3. Select your **Provider**
4. Paste your **API key** (not required for Ollama)
5. Optionally set a specific **Model** — leave blank to use the provider default
6. For Ollama, set the **Ollama URL** (default: `http://localhost:11434`)

### Using AI Radio

1. Click the **AI Radio** button in the bottom navigation bar
2. Describe the music you want — e.g. *"chill electronic music for working after lunch"*
3. Optionally enable **Use my playlists as context** to send your playlist names to the AI as hints
4. Click **Generate**

Once the radio loads you can:

- **Refine** the result by typing a follow-up in the bottom bar — e.g. *"make it more upbeat"* — the AI remembers the conversation context across up to 8 turns
- **Use suggestion chips** that appear below the header for one-click refinements
- **Save as playlist** to keep the generated tracklist in your TIDAL library
- **Play / Shuffle** directly from the page header

### Preferences reference

| Setting | Description |
|---|---|
| **Provider** | AI backend: OpenAI, Anthropic, Google Gemini, or Ollama |
| **API key** | Secret key for the selected provider (stored in the system keyring) |
| **Model** | Model identifier (e.g. `gpt-4o`, `claude-sonnet-4-6`). Leave blank for the provider default |
| **Ollama URL** | Base URL of your local Ollama instance. Only used when provider is Ollama |
| **Use critic filter** | Runs a second AI pass to score and filter the track list for relevance. Doubles API usage; recommended for short or very specific prompts |

## License

This project is licensed under the GNU General Public License v3.0 — see the [LICENSE](COPYING) file for details.
