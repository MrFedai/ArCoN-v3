"""Up-front wizard (D14): every question is asked BEFORE anything changes.
Answers are written to the profile; the next run can reuse them."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from arcon.core.profile import GROUPS, Profile
from arcon.core.ui import UI


@dataclass(frozen=True)
class Question:
    section: str
    key: str
    text: str
    choices: tuple[str, ...] = ()               # empty = yes/no
    when: Callable[[Profile], bool] = lambda p: True


def _mod(name: str) -> Callable[[Profile], bool]:
    return lambda p: p.enabled(name)


QUESTIONS: tuple[Question, ...] = (
    Question("modules", "packages", "Install packages?"),
    Question("modules", "gnome", "Apply GNOME settings (dark theme, keybindings, app folders)?"),
    Question("gnome", "debloat", "Remove GNOME bloatware (Tour, Weather, Maps, Contacts, Music, Web)?", when=_mod("gnome")),
    Question("wallpaper", "mode", "Wallpaper", ("none", "file"), when=_mod("gnome")),
    Question("modules", "display", "Detect monitors and use their best mode?"),
    Question("display", "prefer", "If max resolution and max refresh rate cannot coexist, prefer",
             ("resolution", "refresh"), when=_mod("display")),
    Question("modules", "hyprland", "Install Hyprland with ArCoN's config (optional desktop)?"),
    Question("modules", "dotfiles", "Deploy dotfiles (Terminator config, …)?"),
    Question("modules", "terminal", "Configure a terminal emulator?"),
    Question("terminal", "emulator", "Terminal emulator", ("terminator", "kitty", "alacritty", "gnome-terminal"),
             when=_mod("terminal")),
    Question("modules", "shell", "Configure the shell?"),
    Question("shell", "name", "Shell", ("zsh", "fish", "bash", "none"), when=_mod("shell")),
    Question("modules", "gaming", "Gaming mode (Steam, GameMode, GPU drivers)?"),
    Question("modules", "blackarch", "BlackArch repository (Arch only)?"),
    Question("blackarch", "install", "BlackArch tools", ("none", "core", "full"), when=_mod("blackarch")),
    Question("modules", "security", "Security tools and hardening?"),
    Question("security", "tools", "Install security tools (arch-audit/debsecan, ClamAV, rkhunter, Lynis, Firejail, nethogs)?", when=_mod("security")),
    Question("security", "firewall", "Enable firewall (deny incoming, SSH kept reachable if running)?", when=_mod("security")),
    Question("security", "sysctl", "Apply kernel/network sysctl hardening?", when=_mod("security")),
    Question("security", "ssh_root_login", "Disable SSH root login?", when=_mod("security")),
    Question("security", "ssh_disable_password", "Disable SSH password login (key-only)?", when=_mod("security")),
    Question("security", "scans", "Run security scans at the end (slow)?", when=_mod("security")),
    Question("security", "opensnitch", "Install OpenSnitch application firewall?", when=_mod("security")),
    Question("security", "usbguard", "Enable USBGuard (blocks new USB devices)?", when=_mod("security")),
    Question("modules", "optimization", "Apply recommended optimizations (TRIM, ZRAM, …)?"),
    Question("modules", "cleanup", "Clean up afterwards (orphans, old package cache)?"),
)


def run_wizard(profile: Profile, ui: UI) -> Profile:
    ui.heading("ArCoN setup wizard")
    if profile.path and profile.path.exists():
        if ui.confirm(f"Reuse previous answers from {profile.path}?", default=True):
            return profile
    for q in QUESTIONS:
        if not q.when(profile):
            continue
        current = profile.get(q.section, q.key)
        if q.choices:
            profile.set(q.section, q.key, ui.choose(q.text, q.choices, current))
        else:
            profile.set(q.section, q.key, ui.confirm(q.text, bool(current)))
        if (q.section, q.key) == ("modules", "packages") and profile.enabled("packages"):
            _ask_groups(profile, ui)
    return profile


def _ask_groups(profile: Profile, ui: UI) -> None:
    current = set(profile.get("packages", "groups"))
    chosen = [g for g in GROUPS if ui.confirm(f"  package group '{g}'?", g in current)]
    profile.set("packages", "groups", chosen)
