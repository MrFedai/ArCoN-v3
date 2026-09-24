"""Turn wanted packages into an install plan: native repo / AUR / Flatpak /
unavailable. Nothing is installed by guess (fixes v2.5 #15: unknown names were
sent to yay)."""

from __future__ import annotations

from dataclasses import dataclass, field

from arcon.core.runner import Runner
from arcon.package import catalog as cat
from arcon.package.providers import AurHelper, Flatpak, native_for
from arcon.platform.detect import Family, OSInfo


@dataclass
class Resolution:
    native: list[str] = field(default_factory=list)       # to install from the distro repos
    aur: list[str] = field(default_factory=list)          # to build from the AUR
    flatpak: list[str] = field(default_factory=list)      # Flathub ids (D22 fallback)
    installed: list[str] = field(default_factory=list)    # already present (idempotency)
    unavailable: list[str] = field(default_factory=list)  # reported, never guessed

    @property
    def empty(self) -> bool:
        return not (self.native or self.aur or self.flatpak)


def wanted_entries(groups: list[str], ids: list[str] = ()) -> list[cat.Entry]:
    catalog = cat.load()
    seen, out = set(), []
    for g in ["base", *groups]:
        for e in cat.group(g, catalog):
            if e.id not in seen:
                seen.add(e.id)
                out.append(e)
    for pid in ids:
        if pid in catalog and pid not in seen:
            seen.add(pid)
            out.append(catalog[pid])
    return out


def resolve(os: OSInfo, runner: Runner, entries: list[cat.Entry], extra: list[str] = (),
            flatpak_fallback: bool = True, aur_helper: str = "yay") -> Resolution:
    res = Resolution()
    pm = native_for(os, runner)
    flat = Flatpak(runner)
    native_names: dict[str, cat.Entry | None] = {}
    aur_names: list[str] = []
    for e in entries:
        name = e.native(os)
        if name.startswith("aur:"):
            aur_names.append(name[4:])
        elif name:
            native_names[name] = e
        elif flatpak_fallback and e.flatpak:
            res.flatpak.append(e.flatpak)
        else:
            res.unavailable.append(f"{e.id} (not packaged for {os.id})")
    for name in extra:  # user packages (profile `extra`, custom file): must exist somewhere
        native_names.setdefault(name, None)

    present = pm.installed(list(native_names) + aur_names)
    res.installed += sorted(present)
    todo = [n for n in native_names if n not in present]
    in_repo = pm.available(todo)
    missing = [n for n in todo if n not in in_repo]
    res.native = [n for n in todo if n in in_repo]

    if os.family is Family.ARCH:
        # v2.5 behaviour kept for catalog names: official repo first, then AUR
        aur_candidates = [n for n in missing if native_names[n] is not None]
        unknown_extra = [n for n in missing if native_names[n] is None]
        helper = AurHelper(runner, aur_helper)
        found_extra = helper.available(unknown_extra) if unknown_extra else set()
        res.aur = [n for n in aur_names if n not in present] + aur_candidates + sorted(found_extra)
        missing = [n for n in unknown_extra if n not in found_extra]

    for n in missing:
        e = native_names.get(n)
        if e is not None and flatpak_fallback and e.flatpak:
            res.flatpak.append(e.flatpak)
        else:
            res.unavailable.append(n if e is None else f"{e.id} ({n} not in the repositories)")

    if res.flatpak:
        have = flat.installed(res.flatpak)
        res.installed += sorted(have)
        res.flatpak = [f for f in dict.fromkeys(res.flatpak) if f not in have]
    return res
