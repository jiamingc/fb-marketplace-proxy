{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
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
    {
      self,
      nixpkgs,
      pyproject-nix,
      uv2nix,
      pyproject-build-systems,
      ...
    }:
    let
      pkgs = import nixpkgs {
        system = "x86_64-linux";
      };
      workspace = uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ./.; };
      pythonSet =
        (pkgs.callPackage pyproject-nix.build.packages {
          python = pkgs.python314;
        }).overrideScope
          (
            nixpkgs.lib.composeManyExtensions [
              pyproject-build-systems.overlays.wheel
              (workspace.mkPyprojectOverlay { sourcePreference = "wheel"; })
            ]
          );
    in
    {
      devShells.x86_64-linux.default =
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
      packages.x86_64-linux.default = pythonSet.mkVirtualEnv "venv" workspace.deps.default;
      nixosModules.default =
        {
          config,
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

          config = lib.mkMerge [
            (lib.mkIf cfg.enable {
              systemd.services.fb-marketplace-proxy = {
                after = [
                  "network-online.target"
                ];
                wantedBy = [ "multi-user.target" ];
                serviceConfig = {
                  Type = "notify";
                  RuntimeDirectory = "/run/fb-marketplace-proxy";
                  ExecStart = "${lib.getExe' self.packages.x86_64-linux.default "gunicorn"} --bind unix:/run/fb-marketplace-proxy/gunicorn.sock";
                };
              };
            })
          ];
        };
    };
}
