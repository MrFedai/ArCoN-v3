#!/usr/bin/env bash
# ArCoN v3 bootstrap (D1/D5): make sure `uv` exists, then hand over to `arcon`.
# No setup logic lives here. Run as your normal user, NOT with sudo.
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
    local id=""
    [[ -r /etc/os-release ]] && id="$(sed -n 's/^ID=//p' /etc/os-release | tr -d '"')"  # parsed, never sourced
    case "$id" in
        arch)   sudo pacman -S --needed --noconfirm uv && return 0 ;;
        fedora) sudo dnf install -y uv && return 0 ;;
    esac
    command -v python3 >/dev/null || { echo "ArCoN needs python3 (>= 3.11)." >&2; exit 1; }
    python3 -m venv "$HOME/.local/share/arcon/bootstrap" 2>/dev/null || {
        echo "python3 venv module missing. Debian/Ubuntu: sudo apt install python3-venv" >&2; exit 1; }
    "$HOME/.local/share/arcon/bootstrap/bin/pip" install --quiet uv
}

uv_bin="$(find_uv || true)"
if [[ -z "$uv_bin" ]]; then
    echo "ArCoN: installing uv (Python environment manager)..."
    install_uv
    uv_bin="$(find_uv)"
fi

exec "$uv_bin" run --quiet --project "$here" arcon "$@"
