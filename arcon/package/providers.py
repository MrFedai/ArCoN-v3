"""Linux package managers behind one interface (D4: Debian + Ubuntu share one).

Every query is a single call for all names (v2.5 called pacman once per package).
"""

from __future__ import annotations

from typing import Iterable

from arcon.core.runner import Runner
from arcon.package.base import PackageManager
from arcon.platform.detect import Family, OSInfo


class Pacman(PackageManager):
    name = "pacman"

    def installed(self, names: Iterable[str]) -> set[str]:
        have = set(self.runner.run(["pacman", "-Qq"], mutating=False, check=False, timeout=60).stdout.split())
        return set(names) & have

    def available(self, names: Iterable[str]) -> set[str]:
        repo = set(self.runner.run(["pacman", "-Slq"], mutating=False, check=False, timeout=120).stdout.split())
        return set(names) & repo

    def install(self, names: list[str]) -> None:
        if names:
            self.runner.run(["pacman", "-S", "--needed", "--noconfirm", *names], sudo=True, interactive=True)

    def remove(self, names: list[str]) -> None:
        if names:
            self.runner.run(["pacman", "-Rs", "--noconfirm", *names], sudo=True, interactive=True)


class AurHelper(PackageManager):
    """yay / paru. Runs as the user (never with sudo); it asks for sudo itself."""

    def __init__(self, runner: Runner, helper: str = "yay"):
        super().__init__(runner)
        self.name = helper

    def present(self) -> bool:
        return self.runner.run(["sh", "-c", f"command -v {self.name}"], mutating=False, check=False).ok

    def installed(self, names: Iterable[str]) -> set[str]:
        return Pacman(self.runner).installed(names)

    def available(self, names: Iterable[str]) -> set[str]:
        names = list(names)
        if not names or not self.present():
            return set()
        out = self.runner.run([self.name, "-Si", "--aur", *names], mutating=False, check=False, timeout=120).stdout
        return {line.split(":", 1)[1].strip() for line in out.splitlines()
                if line.startswith("Name") and ":" in line} & set(names)

    def install(self, names: list[str]) -> None:
        if names:
            self.runner.run([self.name, "-S", "--needed", "--noconfirm", "--answerdiff", "None",
                             "--answerclean", "None", *names], interactive=True)

    def remove(self, names: list[str]) -> None:
        Pacman(self.runner).remove(names)


class Apt(PackageManager):
    name = "apt"
    _env = ["env", "DEBIAN_FRONTEND=noninteractive"]

    def installed(self, names: Iterable[str]) -> set[str]:
        out = self.runner.run(["dpkg-query", "-W", "-f=${Package}\t${db:Status-Status}\n"],
                              mutating=False, check=False, timeout=60).stdout
        have = {l.split("\t")[0] for l in out.splitlines() if l.endswith("\tinstalled")}
        return set(names) & have

    def available(self, names: Iterable[str]) -> set[str]:
        repo = set(self.runner.run(["apt-cache", "pkgnames"], mutating=False, check=False, timeout=120).stdout.split())
        return set(names) & repo

    def refresh(self) -> bool:
        """False when some repository could not be refreshed (e.g. a broken third-party
        source); installation continues with the indexes that did update."""
        return self.runner.run([*self._env, "apt-get", "update"], sudo=True, interactive=True, check=False).ok

    def install(self, names: list[str]) -> None:
        if names:
            self.runner.run([*self._env, "apt-get", "install", "-y", *names], sudo=True, interactive=True)

    def remove(self, names: list[str]) -> None:
        if names:
            self.runner.run([*self._env, "apt-get", "remove", "-y", *names], sudo=True, interactive=True)


class Dnf(PackageManager):
    name = "dnf"

    def installed(self, names: Iterable[str]) -> set[str]:
        have = set(self.runner.run(["rpm", "-qa", "--qf", "%{NAME}\n"], mutating=False, check=False,
                                   timeout=60).stdout.split())
        return {n for n in names if n in have}

    def available(self, names: Iterable[str]) -> set[str]:
        names = list(names)
        groups = {n for n in names if n.startswith("@")}
        plain = [n for n in names if not n.startswith("@")]
        out = self.runner.run(["dnf", "-q", "repoquery", "--available", "--qf", "%{name}\n", *plain],
                              mutating=False, check=False, timeout=300).stdout if plain else ""
        return groups | (set(out.split()) & set(plain))

    def install(self, names: list[str]) -> None:
        if names:
            self.runner.run(["dnf", "install", "-y", *names], sudo=True, interactive=True)

    def remove(self, names: list[str]) -> None:
        if names:
            self.runner.run(["dnf", "remove", "-y", *names], sudo=True, interactive=True)


class Flatpak(PackageManager):
    name = "flatpak"
    remote = "flathub"
    remote_url = "https://dl.flathub.org/repo/flathub.flatpakrepo"

    def present(self) -> bool:
        return self.runner.run(["sh", "-c", "command -v flatpak"], mutating=False, check=False).ok

    def has_remote(self) -> bool:
        if not self.present():
            return False
        out = self.runner.run(["flatpak", "remotes", "--columns=name"], mutating=False, check=False).stdout
        return self.remote in out.split()

    def add_remote(self) -> None:
        self.runner.run(["flatpak", "remote-add", "--if-not-exists", self.remote, self.remote_url], sudo=True)

    def installed(self, names: Iterable[str]) -> set[str]:
        if not self.present():
            return set()
        out = self.runner.run(["flatpak", "list", "--app", "--columns=application"], mutating=False,
                              check=False).stdout
        return set(names) & set(out.split())

    def available(self, names: Iterable[str]) -> set[str]:
        return set(names)  # Flathub ids are verified by scripts/verify_catalog.py

    def install(self, names: list[str]) -> None:
        if names:
            self.runner.run(["flatpak", "install", "-y", "--noninteractive", self.remote, *names],
                            sudo=True, interactive=True)

    def remove(self, names: list[str]) -> None:
        if names:
            self.runner.run(["flatpak", "uninstall", "-y", "--noninteractive", *names], sudo=True)


NATIVE: dict[Family, type[PackageManager]] = {Family.ARCH: Pacman, Family.DEBIAN: Apt, Family.FEDORA: Dnf}


def native_for(os: OSInfo, runner: Runner) -> PackageManager:
    try:
        return NATIVE[os.family](runner)
    except KeyError:
        from arcon.package.base import NotSupported
        raise NotSupported(f"no package manager for {os.name}") from None
