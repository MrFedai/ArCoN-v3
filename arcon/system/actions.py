"""`system` module (F12, F13, F16, multilib for F19): keyring, mirrors, full
upgrade. Runs first so later installs never produce a partial upgrade."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

from arcon.core.action import Action, Change, Context, Reversible, Risk, register
from arcon.core.common import WriteFile, read_text
from arcon.platform.detect import Family

PACMAN_CONF = Path("/etc/pacman.conf")
MIRRORLIST = Path("/etc/pacman.d/mirrorlist")


class KeyringReset(Action):
    id, title = "system.keyring-reset", "Arch: reset the pacman keyring (v2.5 behaviour, opt-in)"
    risk, reversible = Risk.HIGH, Reversible.NO

    def plan(self, ctx):
        if ctx.os.family is not Family.ARCH or not ctx.profile.get("system", "keyring_reset"):
            return []
        return [Change("command", "/etc/pacman.d/gnupg", "delete and re-initialise the keyring")]

    def apply(self, ctx):
        ctx.runner.run(["rm", "-rf", "/etc/pacman.d/gnupg"], sudo=True)
        ctx.runner.run(["pacman-key", "--init"], sudo=True)
        ctx.runner.run(["pacman-key", "--populate", "archlinux"], sudo=True)


def enable_multilib(conf: str) -> str:
    """Uncomment the [multilib] section header and its Include line only."""
    lines, out, in_section = conf.splitlines(keepends=True), [], False
    for line in lines:
        if re.match(r"^#\s*\[multilib\]\s*$", line):
            out.append("[multilib]\n")
            in_section = True
            continue
        if in_section and re.match(r"^#\s*Include\s*=", line):
            out.append(line.lstrip("#").lstrip())
            in_section = False
            continue
        if line.strip().startswith("[") and not line.startswith("#"):
            in_section = False
        out.append(line)
    return "".join(out)


def multilib_needed(ctx: Context) -> bool:
    return ctx.os.family is Family.ARCH and ctx.profile.enabled("gaming")


class Multilib(WriteFile):
    reversible = Reversible.YES

    def __init__(self):
        super().__init__("system.multilib", "Arch: enable the multilib repository (32-bit libraries for Steam)",
                         PACMAN_CONF, lambda ctx: enable_multilib(read_text(PACMAN_CONF) or ""), root=True,
                         mode=0o644, risk=Risk.MEDIUM, after=self._sync,
                         verify_fn=lambda ctx: re.search(r"^\[multilib\]", read_text(PACMAN_CONF) or "", re.M) is not None)

    @staticmethod
    def _sync(ctx: Context) -> None:
        # a new repository needs a database sync; -Syu (never -Sy alone) avoids a partial upgrade
        ctx.runner.run(["pacman", "-Syu", "--noconfirm"], sudo=True, interactive=True)

    def plan(self, ctx):
        if not multilib_needed(ctx) or re.search(r"^\[multilib\]", read_text(PACMAN_CONF) or "", re.M):
            return []
        changes = super().plan(ctx)
        return [Change("repo", "multilib", "uncomment [multilib] in /etc/pacman.conf (backup kept)")] if changes else []


class Mirrors(Action):
    id, title = "system.mirrors", "Arch: rank mirrors with reflector (mirrorlist backed up)"
    risk, reversible = Risk.LOW, Reversible.YES

    def plan(self, ctx):
        if ctx.os.family is not Family.ARCH or not ctx.profile.get("system", "mirrors"):
            return []
        return [Change("file", str(MIRRORLIST), "20 latest HTTPS mirrors sorted by rate")]

    def apply(self, ctx):
        if not ctx.runner.run(["sh", "-c", "command -v reflector"], mutating=False, check=False).ok:
            ctx.runner.run(["pacman", "-S", "--needed", "--noconfirm", "reflector"], sudo=True, interactive=True)
        with tempfile.TemporaryDirectory(prefix="arcon-mirrors-") as tmp:
            out = Path(tmp) / "mirrorlist"
            ctx.runner.run(["reflector", "--protocol", "https", "--latest", "20", "--sort", "rate",
                            "--download-timeout", "5", "--save", str(out)], timeout=600)
            if not ctx.dry_run:
                text = out.read_text()
                if "Server" not in text:
                    raise RuntimeError("reflector produced no servers — mirrorlist left unchanged")
                ctx.files.write(MIRRORLIST, text.encode(), root=True, mode=0o644)


class Upgrade(Action):
    id, title = "system.upgrade", "Full system upgrade"
    risk, reversible = Risk.MEDIUM, Reversible.NO
    requires = ("system.multilib",)

    def plan(self, ctx):
        if not ctx.profile.get("system", "upgrade"):
            return []
        return [Change("command", {Family.ARCH: "pacman -Sy archlinux-keyring && pacman -Su",
                                   Family.DEBIAN: "apt-get update && apt-get full-upgrade",
                                   Family.FEDORA: "dnf upgrade --refresh"}[ctx.os.family])]

    def apply(self, ctx):
        r = ctx.runner
        if ctx.os.family is Family.ARCH:
            r.run(["pacman", "-Sy", "--needed", "--noconfirm", "archlinux-keyring"], sudo=True, interactive=True)
            r.run(["pacman", "-Su", "--noconfirm"], sudo=True, interactive=True)
        elif ctx.os.family is Family.DEBIAN:
            env = ["env", "DEBIAN_FRONTEND=noninteractive"]
            r.run([*env, "apt-get", "update"], sudo=True, interactive=True)
            r.run([*env, "apt-get", "full-upgrade", "-y"], sudo=True, interactive=True)
        elif ctx.os.family is Family.FEDORA:
            r.run(["dnf", "upgrade", "--refresh", "-y"], sudo=True, interactive=True)


@register("system", "System", order=10)
def build(ctx: Context):
    return [KeyringReset(), Mirrors(), Multilib(), Upgrade()]
