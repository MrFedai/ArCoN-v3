#!/usr/bin/env bash
# Characterize ArCoN v2.5 (setup.sh at tag v2.5.0) without touching the system.
#
#   run_v25.sh <scenario> <outdir>
#
# * every external tool with side effects is replaced by a recording mock (mocks/)
# * HOME and USER point into <outdir>; the repo files are copied to <outdir>/work
# * answers are fed from scenarios/<scenario>.answers (one per line)
# * scenarios whose name ends in "-arch" run in a private mount namespace with
#   /etc/os-release bind-mounted to ID=arch (needs root; container only)
#
# Outputs: <outdir>/home (resulting files), commands.log (normalised), capture/
set -u
here="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
scenario="$1"; out="$(mkdir -p "$2" && cd "$2" && pwd)"
answers="$here/scenarios/$scenario.answers"
[[ -f "$answers" ]] || { echo "no scenario $scenario" >&2; exit 2; }

rm -rf "${out:?}/home" "${out:?}/work" "${out:?}/capture" "${out:?}/commands.log"
mkdir -p "$out/home" "$out/work" "$out/capture"
# v2.5 source, unmodified, from the tag (not from the working tree)
git -C "$repo" archive v2.5.0 | tar -x -C "$out/work"

export PATH="$here/mocks:$PATH" HOME="$out/home" USER=arcontest SHELL=/bin/bash TERM=dumb
export ARCON_LOG="$out/commands.raw" ARCON_CAPTURE="$out/capture"
export ARCON_OFFICIAL="$here/scenarios/official-packages.txt"
: > "$ARCON_LOG"

grep -v '^#' "$answers" > "$out/answers.txt"
# shellcheck disable=SC2016  # expanded by the inner bash, $0 = outdir
run='cd "$0/work" && bash ./setup.sh < "$0/answers.txt" > "$0/stdout.txt" 2>&1; echo $? > "$0/exit.txt"'
if [[ "$scenario" == *-arch ]]; then
    printf 'NAME="Arch Linux"\nID=arch\n' > "$out/os-release"
    # shellcheck disable=SC2016
    unshare -m --propagation private bash -c 'mount --bind "$0/os-release" /etc/os-release && '"$run" "$out"
else
    bash -c "$run" "$out"
fi
# normalise volatile paths so the log can be compared with a golden file
sed -e "s|$out|<OUT>|g" "$ARCON_LOG" > "$out/commands.log"
rm -f "$ARCON_LOG"
cat "$out/exit.txt"
