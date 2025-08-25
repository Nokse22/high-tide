{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }: flake-utils.lib.eachDefaultSystem (system:
    let
      pkgs = nixpkgs.legacyPackages.${system};
      native_build_inputs = with pkgs; [ meson ninja pkg-config blueprint-compiler desktop-file-utils ];
      build_inputs = with pkgs; [ glib-networking libadwaita libportal libsecret pipewire ] ++ (with pkgs.gst_all_1; [ gstreamer gst-plugins-base gst-plugins-good ]);
      python_dependencies = with pkgs.python313Packages; [ pygobject3 tidalapi requests mpd2 pypresence ];
    in {
      devShells.default = pkgs.mkShell {
        name = "high-tide-dev-shell";
        packages = native_build_inputs ++ build_inputs ++ python_dependencies;
      };

      packages.high-tide = pkgs.python313Packages.buildPythonApplication {
        name = "high-tide";
        pyproject = false;
        src = ./.;
        
        nativeBuildInputs = with pkgs; [ wrapGAppsHook4 ] ++ native_build_inputs;
        buildInputs = build_inputs;
        dependencies = python_dependencies;

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