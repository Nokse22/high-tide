<div align="center">
  <img height="128" src="data/icons/hicolor/scalable/apps/io.github.nokse22.high-tide.svg" alt="High Tide Logo"/>
  
  # High Tide
  
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
> Not affiliated in any way with TIDAL, this is a third-party unofficial client

<table>
  <tr>
    <th><img src="data/resources/screenshot 1.png"/></th>
    <th><img src="data/resources/screenshot 2.png"/></th>
  </tr>
</table>

## 🚀 Installation
### 🛒 Flathub

<a href='https://flathub.org/apps/io.github.nokse22.high-tide'><img height='80' alt='Download on Flathub' src='https://dl.flathub.org/assets/badges/flathub-badge-en.png'/></a>
</details>

### 📦 From latest build

Go to the [Actions page](https://github.com/Nokse22/high-tide/actions), click on the latest working build and download the Artifact for your architecture.
Extract the .flatpak file from the downloaded .zip file and install it clicking on it or with:

`flatpak install high-tide.flatpak`

Beware: Locales are not available when installing from a `.flatpak` file, since flatpak locales are stored in another runtime for optimisations, and `.flatpak` files only export the app without runtimes.

If you want/need locales, please build from source.

### ⚡ From source (binary)

You need:

- Meson 0.62 or newer, blueprint-compiler, gettext and desktop-file-utils
- Python 3 with PyGObject
- GTK 4 and libadwaita 1.8 or newer (GNOME 49 or later)
- GStreamer with the base and good plugins, plus an AAC decoder (from the bad plugins or libav) for the Low and High qualities
- libsecret, libportal, and a keyring such as GNOME Keyring or KWallet
- The Python packages tidalapi, requests and pypresence 4.5 or newer
- Optional: ffmpeg to keep played songs in the cache, alsa-utils for the ALSA output

On Fedora 43 or newer, for example:

```sh
sudo dnf install meson blueprint-compiler gettext desktop-file-utils python3-gobject python3-requests python3-pip gtk4 libadwaita libsecret libportal gstreamer1-plugins-good gstreamer1-plugins-bad-free
pip install --user tidalapi pypresence
```

Then clone the repository, and build with meson.

```sh
git clone https://github.com/Nokse22/high-tide.git
cd high-tide
meson setup builddir
meson compile -C builddir
sudo meson install -C builddir
```

Or open the project in GNOME Builder and click "Run Project".

## 🎨 Changing the look

High Tide uses libadwaita, which doesn't follow GTK themes. It does follow your system's light or dark style and its accent color.

To change more, you can write your own CSS. With the Flatpak, put it in `~/.var/app/io.github.nokse22.high-tide/config/gtk-4.0/gtk.css`, which only changes High Tide. When built from source, the file is `~/.config/gtk-4.0/gtk.css`, which changes every GTK 4 app. Restart High Tide after editing it. For example, this makes the accent color red:

```css
:root {
  --accent-bg-color: #c01c28;
}
```

The colors you can change are listed in [libadwaita's documentation](https://gnome.pages.gitlab.gnome.org/libadwaita/doc/main/css-variables.html). To find out what to change for a part of the app, start it with GTK's inspector, click the crosshair at its top left, then click that part of High Tide:

```sh
flatpak run --env=GTK_DEBUG=interactive io.github.nokse22.high-tide
```

This isn't an official way to theme the app, so a later version of High Tide or libadwaita may need changes to your CSS.

## 🔧 Troubleshooting

### Accented characters can't be typed (KDE Plasma)

Since GTK 4.20, GTK apps on Wayland only combine dead keys (like `´` then `a` into `á`) when an input method such as IBus or Fcitx5 is running. Running one fixes it for all GTK apps. To fix it for High Tide alone instead, run:

```sh
flatpak override --user --env=GTK_IM_MODULE=simple io.github.nokse22.high-tide
```

This turns off input methods in High Tide, so skip it if you use one to type, for example, Chinese or Japanese.

### My DAC doesn't run at the song's sample rate

High Tide's quality label shows what TIDAL sends, for example 24-bit/96 kHz. Your DAC can still show another rate, because PipeWire by default runs it at one fixed rate (often 48 kHz) and converts everything to that. There are two ways around it:

1. Let PipeWire switch rates. Create `~/.config/pipewire/pipewire.conf.d/10-rates.conf` with:

   ```
   context.properties = {
       default.clock.allowed-rates = [ 44100 48000 88200 96000 176400 192000 ]
   }
   ```

   Then run `systemctl --user restart pipewire`. PipeWire then switches the DAC to the song's rate, as long as nothing else is playing at a different rate at the same time.

2. Skip PipeWire. In Preferences, set *Preferred Audio Sink* to ALSA and pick your DAC under *ALSA Device*. High Tide then sends the song to the DAC directly at its own rate, and other apps can't use the DAC while High Tide plays. For an untouched (bit-perfect) signal, also keep High Tide's volume at 100% and *Normalize volume* off, and set the volume on the DAC or amplifier instead.

## ❌ Uninstallation
We're sorry to see you go! If you want to remove the High Tide flatpak package from your system, here's how to do so:

First, terminate all High Tide processes. Keep in mind that "Run in background" is an option, usually pressing ^Q should be enough to terminate it. Otherwise, you can run `killall high-tide` to make sure that everything is killed.

You can then remove the package using flatpak :
```sh
# When installed system-wide (default)
flatpak uninstall --delete-data io.github.nokse22.high-tide

# When installed for the current user (-u flag at installation)
flatpak uninstall --delete-data -u io.github.nokse22.high-tide
```

The `--delete-data` flag should get rid of all the "junk" directories (i.e. cache, configs, etc.) on your system, and you don't need to do anything else.

## 🤝 Contributing

Read [CONTRIBUTING](CONTRIBUTING.md) for all information about how to contribute to High Tide, you can also contact us on Matrix [#high-tide:matrix.org](https://matrix.to/#/%23high-tide:matrix.org).

## 📄 License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](COPYING) file for details.

## 🌟 Support the Project

If you find High Tide useful, please consider:

- ⭐ Starring this repository
- 🐛 Reporting bugs and issues
- 💡 Suggesting new features
- 🔄 Sharing with others who might find it useful

---

<div align="center">
  <p>Made with ❤️ by the High Tide community</p>
  <p>
    <a href="https://github.com/Nokse22/high-tide">View on GitHub</a> • 
    <a href="https://github.com/Nokse22/high-tide/issues">Report Bug</a> • 
    <a href="https://github.com/Nokse22/high-tide/issues">Request Feature</a>
  </p>
</div>
