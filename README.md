<img height="128" src="data/icons/hicolor/scalable/apps/io.github.nokse22.HighTide.svg" align="left"/>

# High Tide
  [![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
  [![made-with-python](https://img.shields.io/badge/Made%20with-Python-ff7b3f.svg)](https://www.python.org/)
  
  <p>
    Linux client for TIDAL streaming service.
	</p>

> [!IMPORTANT] 
> Not affiliated in any way with TIDAL, this is a third-party unofficial client

<table>
  <tr>
    <th><img src="data/resources/screenshot 1.png"/></th>
    <th><img src="data/resources/screenshot 2.png"/></th>
  </tr>
</table>

## Contributing

### Coding
There are some TODOs and FIXMEs in the code, you can start there. I'm trying to comment the code, but if needed you can contact me on Matrix (@nokse22:matrix.org) or on Github.

The application is made with GNOME Builder so it should just work if you clone the project and open it with Builder.

If you have contributed you can open a pull request.


## Installation
<details><summary>Stores (Still not avalaible)</summary>
### High Tide is available on

<a href='https://flathub.org/apps/io.github.nokse22.high-tide'><img height='80' alt='Download on Flathub' src='https://dl.flathub.org/assets/badges/flathub-badge-en.png'/></a>
<h>&emsp;</h> <a href="https://snapcraft.io/high-tide"><img height='80' alt="Get it from the Snap Store" src="https://snapcraft.io/static/images/badges/en/snap-store-black.svg"/></a>
</details>

### From latest build

Go to the [Actions page](https://github.com/Nokse22/high-tide/actions), click on the latest working build and download the Artifact for your architecture.
Extract the .flatpak file from the downloaded .zip file and install it clicking on it or with:

`flatpak install HighTide.flatpak`

Beware: Locales are not available when installing from a `.flatpak` file, since flatpak locales are stored in another runtime for optimisations, and `.flatpak` files only export the app without runtimes.

If you want/need locales, please build from source.

### From source (binary)

You just need to clone the repository, and build with mason.

```sh
git clone https://github.com/Nokse22/high-tide.git
mason builddir
mason compile -C builddir
mason install -C builddir
```

### From source (flatpak)

You just need to clone the repository, prepare the repository location and build with mason.

```sh
git clone https://github.com/Nokse22/high-tide.git
mkdir -p $HOME/.local/share/flatpak
flatpak-builder builddir build-aux/io.github.nokse22.HighTide.json --force-clean --repo="$HOME/.local/share/flatpak/high-tide-local" --user --install
```