#!/usr/bin/env bash
# ArCoN v3 bootstrap (D1/D5): make sure `uv` exists, then hand over to `arcon`.
# No setup logic lives here. Run as your normal user, NOT with sudo.
#
#   git clone https://github.com/MrFedai/ArCoN-v3.git ~/ArCoN-v3 && ~/ArCoN-v3/setup.sh
#
#   ./setup.sh              wizard -> plan -> one confirmation -> apply
#   ./setup.sh plan         dry run
#   ./setup.sh --help       all commands
#
# The v2.5 script is kept unchanged in legacy/v2.5/setup.sh.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ ${EUID:-$(id -u)} -eq 0 && "${ARCON_ALLOW_ROOT:-}" != 1 ]]; then
    echo "ArCoN: run ./setup.sh as your normal user; it asks for sudo only when needed." >&2
    exit 2
fi

find_uv() {
    command -v uv 2>/dev/null && return 0
    [[ -x "$HOME/.local/share/arcon/bootstrap/bin/uv" ]] && echo "$HOME/.local/share/arcon/bootstrap/bin/uv" && return 0
    return 1
}

install_uv() {
    # 1) distro package where one exists, 2) PyPI wheel into a private venv.
    # Never `curl | sh` (CLAUDE.md D16).
    local id="" like="" venv="$HOME/.local/share/arcon/bootstrap"
    if [[ -r /etc/os-release ]]; then  # parsed, never sourced
        id="$(sed -n 's/^ID=//p' /etc/os-release | tr -d '"')"
        like="$(sed -n 's/^ID_LIKE=//p' /etc/os-release | tr -d '"')"
    fi
    case "$id" in
        arch)   sudo pacman -S --needed --noconfirm uv && return 0 ;;
        fedora) sudo dnf install -y uv && return 0 ;;
    esac
    # Debian/Ubuntu ship python3 without the venv module: install it once (fresh-install one-liner)
    if ! command -v python3 >/dev/null || ! python3 -m venv --clear "$venv" 2>/dev/null; then
        if [[ " $id $like " == *" debian "* || " $id $like " == *" ubuntu "* ]]; then
            echo "ArCoN: installing python3-venv (needed once to set up uv)..."
            sudo apt-get install -y python3 python3-venv
            python3 -m venv --clear "$venv"
        else
            echo "ArCoN needs python3 (>= 3.11) with the venv module." >&2; exit 1
        fi
    fi
    "$venv/bin/pip" install --quiet uv
}

uv_bin="$(find_uv || true)"
if [[ -z "$uv_bin" ]]; then
    echo "ArCoN: installing uv (Python environment manager)..."
    install_uv
    uv_bin="$(find_uv)"
fi

exec "$uv_bin" run --quiet --project "$here" arcon "$@"
