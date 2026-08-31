{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = import nixpkgs { inherit system; };
        inherit (pkgs)
          python313Packages
          wrapGAppsHook4
          meson
          ninja
          pkg-config
          blueprint-compiler
          desktop-file-utils
          libadwaita
          glib-networking
          gst_all_1
          libsecret
          libportal
          alsa-utils
          pipewire
          ;

        nativeBuildInputs = [
          wrapGAppsHook4
          meson
          ninja
          pkg-config
          blueprint-compiler
          desktop-file-utils
        ];

        buildInputs = [
          glib-networking
          libadwaita
          libportal
          pipewire # provides a gstreamer plugin for pipewiresink
        ]
        ++ (with gst_all_1; [
          gstreamer
          gst-plugins-base
          gst-plugins-good
          gst-plugins-bad
          libsecret
        ]);

        dependencies = [
          alsa-utils
        ]
        ++ (with python313Packages; [
          pygobject3
          tidalapi
          requests
          python-mpd2
          pypresence
        ]);
      in
      {
        devShells.default = pkgs.mkShell {
          name = "high-tide-dev-shell";
          packages =
            with pkgs;
            [
              ruff
              gettext
              basedpyright
            ]
            ++ (with pkgs.python313Packages; [
              python-lsp-server
              flake8
            ])
            ++ nativeBuildInputs
            ++ buildInputs
            ++ dependencies;
        };

        packages.high-tide = pkgs.python313Packages.buildPythonApplication {
          name = "high-tide";
          pyproject = false;
          src = ./.;
          inherit nativeBuildInputs buildInputs dependencies;

          dontWrapGApps = true;
          makeWrapperArgs = [ "\${gappsWrapperArgs[@]}" ];

          meta = {
            description = "Libadwaita TIDAL client for Linux";
            homepage = "https://github.com/Nokse22/high-tide";
            mainProgram = "high-tide";
          };
        };
        defaultPackage = self.packages.${system}.high-tide;
      }
    );
}
