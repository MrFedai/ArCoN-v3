"""`packages` module: base + selected groups + extra names, one transaction per
source (native repo, AUR, Flatpak). Everything missing is reported up front."""

from __future__ import annotations

import tempfile
from pathlib import Path

from arcon.core.action import Action, Change, Context, Reversible, Risk, register
from arcon.package.providers import Apt, AurHelper, Flatpak, Pacman, native_for
from arcon.package.resolve import Resolution, resolve, wanted_entries
from arcon.platform.detect import Family


def read_custom_file(path: Path) -> list[str]:
    """pacs.txt format: one or more names per line, `#` starts a comment."""
    names = []
    for line in path.read_text().splitlines():
        names += line.split("#", 1)[0].split()
    return names


def resolution(ctx: Context) -> Resolution:
    if "packages" not in ctx.facts:
        p = ctx.profile
        extra = list(p.get("packages", "extra"))
        custom = p.get("packages", "custom_file")
        if custom:
            path = Path(custom) if Path(custom).is_absolute() else ctx.repo_root / custom
            if path.exists():
                extra += read_custom_file(path)
            else:
                ctx.ui.warn(f"custom package file not found: {path}")
        ids = ctx.facts.get("package_ids", [])       # packages requested by other modules
        ctx.facts["packages"] = resolve(ctx.os, ctx.runner, wanted_entries(p.get("packages", "groups"), ids),
                                        extra, p.get("packages", "flatpak_fallback"), p.get("packages", "aur_helper"))
    return ctx.facts["packages"]


class InstallNative(Action):
    id, title, risk, reversible = "packages.native", "Install packages from the distro repositories", Risk.LOW, Reversible.PARTIAL

    def plan(self, ctx):
        return [Change("package", n, "repo") for n in resolution(ctx).native]

    def apply(self, ctx):
        pm = native_for(ctx.os, ctx.runner)
        if isinstance(pm, Apt):
            pm.refresh()
        pm.install(resolution(ctx).native)
        ctx.journal.write("packages_installed", source=pm.name, names=resolution(ctx).native)

    def verify(self, ctx):
        wanted = resolution(ctx).native
        return native_for(ctx.os, ctx.runner).installed(wanted) == set(wanted)


class InstallAurHelper(Action):
    id, title, risk, reversible = "packages.aur-helper", "Build the AUR helper", Risk.MEDIUM, Reversible.YES
    requires = ()

    def _helper(self, ctx):
        return AurHelper(ctx.runner, ctx.profile.get("packages", "aur_helper"))

    def plan(self, ctx):
        if ctx.os.family is not Family.ARCH or not resolution(ctx).aur or self._helper(ctx).present():
            return []
        name = self._helper(ctx).name + "-bin"
        return [Change("package", "git base-devel", "repo (needed to build from the AUR)"),
                Change("package", name, "AUR, built with makepkg")]

    def apply(self, ctx):
        helper = self._helper(ctx).name
        Pacman(ctx.runner).install(["git", "base-devel"])
        with tempfile.TemporaryDirectory(prefix="arcon-aur-") as tmp:
            ctx.runner.run(["git", "clone", "--depth", "1", f"https://aur.archlinux.org/{helper}-bin.git", tmp + "/src"])
            ctx.runner.run(["makepkg", "-si", "--noconfirm"], cwd=tmp + "/src", interactive=True)
        ctx.journal.write("packages_installed", source="aur", names=[f"{helper}-bin"])

    def verify(self, ctx):
        return self._helper(ctx).present()


class InstallAur(Action):
    id, title, risk, reversible = "packages.aur", "Build and install AUR packages", Risk.MEDIUM, Reversible.PARTIAL
    requires = ("packages.aur-helper",)

    def plan(self, ctx):
        return [Change("package", n, "AUR") for n in resolution(ctx).aur] if ctx.os.family is Family.ARCH else []

    def apply(self, ctx):
        AurHelper(ctx.runner, ctx.profile.get("packages", "aur_helper")).install(resolution(ctx).aur)
        ctx.journal.write("packages_installed", source="aur", names=resolution(ctx).aur)

    def verify(self, ctx):
        wanted = resolution(ctx).aur
        return Pacman(ctx.runner).installed(wanted) == set(wanted)


class SetupFlathub(Action):
    id, title, risk, reversible = "packages.flathub", "Enable Flathub (Flatpak fallback, D22)", Risk.LOW, Reversible.YES

    def plan(self, ctx):
        if not resolution(ctx).flatpak:
            return []
        flat = Flatpak(ctx.runner)
        changes = []
        if not flat.present():
            changes.append(Change("package", "flatpak", "repo"))
        if not flat.has_remote():
            changes.append(Change("repo", "flathub", flat.remote_url))
        return changes

    def apply(self, ctx):
        flat = Flatpak(ctx.runner)
        if not flat.present():
            native_for(ctx.os, ctx.runner).install(["flatpak"])
        flat.add_remote()

    def verify(self, ctx):
        return Flatpak(ctx.runner).has_remote()


class InstallFlatpak(Action):
    id, title, risk, reversible = "packages.flatpak", "Install Flatpak applications", Risk.LOW, Reversible.YES
    requires = ("packages.flathub",)

    def plan(self, ctx):
        return [Change("flatpak", f, "Flathub") for f in resolution(ctx).flatpak]

    def apply(self, ctx):
        Flatpak(ctx.runner).install(resolution(ctx).flatpak)
        ctx.journal.write("packages_installed", source="flatpak", names=resolution(ctx).flatpak)

    def verify(self, ctx):
        wanted = resolution(ctx).flatpak
        return Flatpak(ctx.runner).installed(wanted) == set(wanted)


@register("packages", "Packages", order=20)
def build(ctx: Context) -> list[Action]:
    res = resolution(ctx)
    for item in res.unavailable:
        ctx.ui.warn(f"not available, skipped: {item}")
    return [InstallNative(), InstallAurHelper(), InstallAur(), SetupFlathub(), InstallFlatpak()]
