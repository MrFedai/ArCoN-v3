"""ArCoN profile: the user's choices, stored as TOML (D9).

Read with stdlib `tomllib` semantics, written with `tomlkit` so comments and
key order of a hand-edited profile survive a wizard rewrite (D21).
Unknown sections/keys and invalid values are errors — a typo must never be
silently ignored.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import tomlkit

GROUPS = ("essentials", "media", "cyber", "remote", "privacy", "power")  # base is always installed (D28)


def _bool(v: Any) -> bool:
    return isinstance(v, bool)


def _str(v: Any) -> bool:
    return isinstance(v, str)


def _one_of(*choices: str) -> Callable[[Any], bool]:
    def check(v: Any) -> bool:
        return v in choices
    check.choices = choices  # type: ignore[attr-defined]
    return check


def _str_list(v: Any) -> bool:
    return isinstance(v, list) and all(isinstance(x, str) for x in v)


def _groups(v: Any) -> bool:
    return _str_list(v) and all(x in GROUPS for x in v)


OPTIMIZATIONS = ("fstrim", "bluetooth", "zram", "ananicy")


def _optimizations(v: Any) -> bool:
    return _str_list(v) and all(x in OPTIMIZATIONS for x in v)


def _monitors(v: Any) -> bool:
    if not isinstance(v, list):
        return False
    allowed = {"id", "position", "scale", "primary", "enabled", "transform"}
    return all(isinstance(m, dict) and "id" in m and set(m) <= allowed for m in v)


# section -> key -> (default, validator)
SCHEMA: dict[str, dict[str, tuple[Any, Callable[[Any], bool]]]] = {
    "profile": {"name": ("default", _str)},
    "modules": {m: (d, _bool) for m, d in {
        "system": True, "packages": True, "gnome": True, "hyprland": False, "dotfiles": True, "display": True,
        "terminal": True, "shell": True, "gaming": False, "blackarch": False,
        "security": False, "optimization": True, "cleanup": True,
    }.items()},
    "packages": {
        "groups": (["essentials"], _groups),
        "extra": ([], _str_list),
        "custom_file": ("", _str),
        "flatpak_fallback": (True, _bool),                      # D22
        "aur_helper": ("yay", _one_of("yay", "paru")),
    },
    "system": {
        "upgrade": (True, _bool),          # full system upgrade before installing (no partial upgrades)
        "mirrors": (False, _bool),         # Arch: reflector benchmark, mirrorlist backed up
        "keyring_reset": (False, _bool),   # Arch: v2.5 wiped /etc/pacman.d/gnupg every run — opt-in, HIGH risk
        "speedtest": (False, _bool),       # v2.5 Cloudflare download test (informational)
    },
    "gnome": {"debloat": (False, _bool)},
    "wallpaper": {
        "mode": ("none", _one_of("none", "file")),              # D18: none = solid black
        "file": ("", _str),
        "repo": ("", _str),                                     # D25
    },
    "display": {
        "prefer": ("resolution", _one_of("resolution", "refresh")),  # D13 tie-break
        "monitor": ([], _monitors),
    },
    "terminal": {
        "emulator": ("terminator", _one_of("terminator", "kitty", "alacritty", "gnome-terminal", "none")),
        "theme": ("", _one_of("", "dracula", "nord", "gruvbox_dark", "tokyo_night")),
    },
    "shell": {
        "name": ("none", _one_of("zsh", "fish", "bash", "none")),
        "zsh_theme": ("agnoster", _one_of("agnoster", "robbyrussell", "bira", "powerlevel10k")),
        "starship_preset": ("", _one_of("", "pastel-powerline", "tokyo-night", "pure-preset", "gruvbox-rainbow",
                                         "nerd-font-symbols", "plain-text-symbols")),
    },
    "gaming": {"gpu": ("auto", _one_of("auto", "nvidia", "amd", "intel", "none"))},
    "blackarch": {"install": ("core", _one_of("core", "full", "remove"))},
    "security": {k: (False, _bool) for k in (
        "tools", "scans", "sysctl", "firewall", "ssh_root_login",
        "ssh_disable_password", "opensnitch", "usbguard")},
    "optimization": {"items": (["fstrim", "bluetooth", "zram", "ananicy"], _optimizations)},
    "cleanup": {
        "orphans": (True, _bool),
        "cache": ("trim", _one_of("trim", "none", "purge")),
    },
}


class ProfileError(ValueError):
    pass


def validate(data: dict[str, Any]) -> list[str]:
    errors = []
    for section, values in data.items():
        if section not in SCHEMA:
            errors.append(f"unknown section [{section}]")
            continue
        if not isinstance(values, dict):
            errors.append(f"[{section}] must be a table")
            continue
        for key, value in values.items():
            spec = SCHEMA[section].get(key)
            if spec is None:
                errors.append(f"unknown key {section}.{key}")
            elif not spec[1](value):
                hint = getattr(spec[1], "choices", None)
                errors.append(f"invalid value for {section}.{key}: {value!r}" + (f" (allowed: {', '.join(hint)})" if hint else ""))
    return errors


@dataclass
class Profile:
    doc: tomlkit.TOMLDocument
    path: Path | None = None

    # ---- construction -------------------------------------------------------
    @classmethod
    def load(cls, path: Path) -> "Profile":
        try:
            doc = tomlkit.parse(path.read_text())
        except tomlkit.exceptions.ParseError as exc:
            raise ProfileError(f"{path}: {exc}") from exc
        errors = validate(doc.unwrap())
        if errors:
            raise ProfileError(f"{path}: " + "; ".join(errors))
        return cls(doc, path)

    @classmethod
    def load_or_default(cls, path: Path) -> "Profile":
        return cls.load(path) if path.exists() else cls(tomlkit.document(), path)

    # ---- access -------------------------------------------------------------
    def get(self, section: str, key: str) -> Any:
        default, _ = SCHEMA[section][key]
        table = self.doc.get(section)
        if table is not None and key in table:
            value = table[key]
            return value.unwrap() if hasattr(value, "unwrap") else value
        return list(default) if isinstance(default, list) else default

    def enabled(self, module: str) -> bool:
        return bool(self.get("modules", module))

    def set(self, section: str, key: str, value: Any) -> None:
        spec = SCHEMA.get(section, {}).get(key)
        if spec is None:
            raise ProfileError(f"unknown key {section}.{key}")
        if not spec[1](value):
            raise ProfileError(f"invalid value for {section}.{key}: {value!r}")
        if section not in self.doc:
            self.doc[section] = tomlkit.table()
        self.doc[section][key] = value

    def as_dict(self) -> dict[str, dict[str, Any]]:
        """Effective values: file values over defaults."""
        return {s: {k: self.get(s, k) for k in keys} for s, keys in SCHEMA.items()}

    # ---- persistence --------------------------------------------------------
    def dumps(self) -> str:
        return tomlkit.dumps(self.doc)

    def save(self, path: Path | None = None) -> Path:
        target = path or self.path
        if target is None:
            raise ProfileError("no path to save the profile to")
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(self.dumps())
        tmp.replace(target)
        self.path = target
        return target
