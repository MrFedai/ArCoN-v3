"""Smart Factory Reset (F10, D19): explicit lists, protected packages enforced
for configs too, verified backups first, typed confirmation. User data (browser
profiles, editor settings, chat logins) is never touched — v2.5 deleted
~/.config/google-chrome, ~/.config/Code and ~/.config/discord."""

from __future__ import annotations

import shutil

from arcon.core.action import Action, Change, Context, Reversible, Risk
from arcon.package import catalog as cat
from arcon.package.providers import native_for
from arcon.recovery.backup import backup_dir, dconf_user

# v2.5 PROTECTED_PKGS (tests/golden/v25/packages.json) — never removed
PROTECTED = {"base", "base-devel", "linux", "linux-firmware", "sudo", "pacman", "yay", "systemd", "systemd-libs",
             "glibc", "networkmanager", "network-manager-applet", "wpa_supplicant", "wget", "curl", "git",
             "openssh", "vim", "nano", "neovim", "bluez", "bluez-utils", "kitty", "alacritty", "terminator",
             "gnome-terminal", "konsole", "xfce4-terminal", "bash", "zsh", "fish"}
# config paths ArCoN itself writes or that belong to packages it installs (relative to $HOME)
# (configs of PROTECTED packages — kitty, alacritty, terminator, nvim, vim, git — are kept: D19)
CONFIGS = (".config/hypr", ".config/waybar", ".config/wofi", ".config/fastfetch", ".config/btop",
           ".config/gamemode.ini", ".config/starship.toml", ".oh-my-zsh")
GROUPS = ("essentials", "media", "cyber", "remote", "privacy", "power", "hyprland", "gaming", "security")


class ResetConfigs(Action):
    id, title, risk, reversible = "reset.configs", "Remove ArCoN-managed config files (backup first)", Risk.HIGH, Reversible.YES

    def plan(self, ctx):
        self._paths = [ctx.home / p for p in CONFIGS if (ctx.home / p).exists()]
        return [Change("file-remove", str(p), "backed up") for p in self._paths]

    def apply(self, ctx):
        for path in self._paths:
            if ctx.dry_run:
                continue
            if backup_dir(ctx.journal, path) is None:
                continue
            shutil.rmtree(path) if path.is_dir() and not path.is_symlink() else path.unlink()


class ResetPackages(Action):
    id, title, risk, reversible = "reset.packages", "Uninstall packages ArCoN installs (protected list kept)", Risk.HIGH, Reversible.PARTIAL

    def plan(self, ctx):
        names = {e.native(ctx.os).removeprefix("aur:") for g in GROUPS for e in cat.group(g)} - {""} - PROTECTED
        self._names = sorted(native_for(ctx.os, ctx.runner).installed(names))
        return [Change("package-remove", n) for n in self._names]

    def apply(self, ctx):
        ctx.journal.write("packages_removed", names=self._names)
        native_for(ctx.os, ctx.runner).remove(self._names)


class ResetGnome(Action):
    id, title, risk, reversible = "reset.gnome", "Reset all GNOME settings (full dconf backup first)", Risk.HIGH, Reversible.YES

    def plan(self, ctx):
        return [Change("setting", "dconf /", "reset to defaults")]

    def apply(self, ctx):
        dump = dconf_user(ctx.runner, "dump", "/", mutating=False).stdout  # user db only
        path = ctx.journal.backup_dir / "dconf-full.ini"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dump)
        ctx.journal.write("dconf_backup", path=str(path))
        ctx.runner.run(["dconf", "reset", "-f", "/"])


def reset_actions(uninstall: bool, gnome: bool) -> list[Action]:
    actions: list[Action] = [ResetConfigs()]
    if uninstall:
        actions.append(ResetPackages())
    if gnome:
        actions.append(ResetGnome())
    return actions
