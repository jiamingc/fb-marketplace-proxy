{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    flake-parts.url = "github:hercules-ci/flake-parts";
    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.uv2nix.follows = "uv2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    inputs@{ flake-parts, ... }:
    flake-parts.lib.mkFlake { inherit inputs; } (
      { inputs, getSystem, ... }:
      {
        flake = {
          nixosModules.default =
            {
              config,
              pkgs,
              lib,
              ...
            }:
            let
              cfg = config.services.fb-marketplace-proxy;
            in
            {
              options.services.fb-marketplace-proxy = {
                enable = lib.mkEnableOption "Enable FB Marketplace Proxy webserver";
              };

              config = (
                lib.mkIf cfg.enable {
                  systemd.services.fb-marketplace-proxy = {
                    after = [
                      "network-online.target"
                    ];
                    wantedBy = [ "multi-user.target" ];
                    serviceConfig = {
                      Type = "notify";
                      RuntimeDirectory = "/run/fb-marketplace-proxy";
                      ExecStart = "${lib.getExe' (getSystem pkgs.system).packages.default "gunicorn"} --bind unix:/run/fb-marketplace-proxy/gunicorn.sock";
                    };
                  };
                }
              );
            };
        };

        systems = [
          "x86_64-linux"
          "aarch64-linux"
        ];

        perSystem =
          { pkgs, ... }:
          let
            workspace = inputs.uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ./.; };
            pythonSet =
              (pkgs.callPackage inputs.pyproject-nix.build.packages {
                python = pkgs.python314;
              }).overrideScope
                (
                  pkgs.lib.composeManyExtensions [
                    inputs.pyproject-build-systems.overlays.wheel
                    (workspace.mkPyprojectOverlay { sourcePreference = "wheel"; })
                  ]
                );
          in
          {
            packages.default = pythonSet.mkVirtualEnv "venv" workspace.deps.default;
            devShells.default =
              let
                pythonSetEditable = pythonSet.overrideScope (
                  workspace.mkEditablePyprojectOverlay { root = "$REPO_ROOT"; }
                );
              in
              pkgs.mkShell {
                packages = with pkgs; [
                  (pythonSetEditable.mkVirtualEnv "venv" workspace.deps.all)
                  uv
                  just
                ];
                env = {
                  UV_NO_SYNC = "1";
                  UV_PYTHON = pythonSet.python.interpreter;
                  UV_PYTHON_DOWNLOADS = "never";
                };
                shellHook = ''
                  unset PYTHONPATH
                  export REPO_ROOT=$(jj root)
                '';
              };
          };
      }
    );
}
