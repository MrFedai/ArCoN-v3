"""Phase 4: hardware + display detection, package catalog, providers, resolution."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from conftest import GOLDEN, REPO
from dotfile_rules import check
from rich.console import Console

from arcon.core.action import Context
from arcon.core.profile import Profile
from arcon.core.runner import FakeRunner, Result
from arcon.core.ui import UI
from arcon.display import hyprland
from arcon.display.gnome import PERSISTENT, VERIFY, DisplayConfigError, GnomeDisplay, parse_state
from arcon.display.model import Mode, Monitor, Placement, placements_from_profile, plan_layout, rank_modes
from arcon.hardware.linux import detect as detect_hw
from arcon.package import catalog as cat
from arcon.package.actions import InstallAur, InstallAurHelper, InstallNative, read_custom_file
from arcon.package.providers import Apt, Dnf, Pacman
from arcon.package.resolve import resolve, wanted_entries
from arcon.platform.detect import Family, OSInfo, Tier
from arcon.recovery.backup import FileChanger
from arcon.recovery.journal import Journal

ARCH = OSInfo(Family.ARCH, Tier.SUPPORTED, "arch", "Arch Linux")
UBUNTU = OSInfo(Family.DEBIAN, Tier.SUPPORTED, "ubuntu", "Ubuntu")
FEDORA = OSInfo(Family.FEDORA, Tier.SUPPORTED, "fedora", "Fedora")


# ---- hardware ---------------------------------------------------------------------

def _pci(root: Path, slot: str, cls: str, vendor: str, device: str, boot_vga: str = "0"):
    d = root / "sys" / "bus" / "pci" / "devices" / slot
    d.mkdir(parents=True)
    for k, v in {"class": cls, "vendor": vendor, "device": device, "boot_vga": boot_vga}.items():
        (d / k).write_text(v + "\n")


def test_hybrid_intel_nvidia_turing(tmp_path):
    _pci(tmp_path, "0000_00_02.0", "0x030000", "0x8086", "0x9a49", "1")
    _pci(tmp_path, "0000_01_00.0", "0x030200", "0x10de", "0x2520")   # RTX 3060 mobile (Ampere)
    _pci(tmp_path, "0000_00_1f.3", "0x040380", "0x8086", "0xa0c8")   # audio: ignored
    (tmp_path / "proc").mkdir()
    (tmp_path / "proc" / "meminfo").write_text("MemTotal:       32653776 kB\n")
    (tmp_path / "proc" / "mounts").write_text("/dev/nvme0n1p2 / ext4 rw 0 0\n")
    blk = tmp_path / "sys" / "class" / "block"
    (blk / "nvme0n1" / "queue").mkdir(parents=True)
    (blk / "nvme0n1" / "queue" / "rotational").write_text("0\n")
    part = blk / "nvme0n1" / "nvme0n1p2"
    part.mkdir()
    (blk / "nvme0n1p2").symlink_to(part)
    for k in ("linux", "linux-lts"):
        m = tmp_path / "usr" / "lib" / "modules" / f"6.x-{k}"
        m.mkdir(parents=True)
        (m / "pkgbase").write_text(k + "\n")
    hw = detect_hw(root=tmp_path)
    assert hw.gpu_vendors == ["intel", "nvidia"] and hw.is_hybrid
    nv = [g for g in hw.gpus if g.vendor == "nvidia"][0]
    assert nv.nvidia_open_capable and nv.slot == "0000:01:00.0"
    assert hw.ram_mb == 31888 and hw.root_is_ssd and hw.kernels == ["linux", "linux-lts"]


def test_old_nvidia_is_not_open_capable(tmp_path):
    _pci(tmp_path, "0000_01_00.0", "0x030000", "0x10de", "0x1b80")   # GTX 1080 (Pascal)
    assert not detect_hw(root=tmp_path).gpus[0].nvidia_open_capable


# ---- display model -----------------------------------------------------------------

HDMI_MODES = (Mode(1920, 1080, 60.0, "a"), Mode(1920, 1080, 180.0, "b"), Mode(1280, 720, 60.0, "c"))
EDP_MODES = (Mode(2560, 1600, 60.0, "d"), Mode(2560, 1600, 165.0, "e", True), Mode(1920, 1200, 240.0, "f"))


def owner_monitors(current_hdmi=HDMI_MODES[0], current_edp=EDP_MODES[0]):
    return [Monitor("HDMI-A-1", "SAM", "Odyssey", "H1", HDMI_MODES, current_hdmi),
            Monitor("eDP-2", "BOE", "0x0bca", "", EDP_MODES, current_edp, builtin=True)]


def test_rank_modes_resolution_vs_refresh():
    assert rank_modes(EDP_MODES, "resolution")[0].label() == "2560x1600@165.00"
    assert rank_modes(EDP_MODES, "refresh")[0].label() == "1920x1200@240.00"


def test_layout_keeps_order_and_recomputes_x():
    # owner's hyprland.conf layout: HDMI at 0,0 ; eDP at 1920,-260
    places = [Placement("SAM Odyssey H1", 0, 0), Placement("BOE 0x0bca", 1920, -260)]
    targets = plan_layout(owner_monitors(), places, "resolution")
    assert [(t.monitor.connector, t.mode.label(), t.placement.x, t.placement.y) for t in targets] == [
        ("HDMI-A-1", "1920x1080@180.00", 0, 0), ("eDP-2", "2560x1600@165.00", 1920, -260)]
    assert [t.placement.primary for t in targets] == [False, True]      # builtin becomes primary if none set


def test_layout_matches_by_identity_not_connector():
    places = placements_from_profile([{"id": "BOE 0x0bca", "position": "0,0", "primary": True},
                                      {"id": "SAM Odyssey H1", "position": "2560,0"}])
    mons = [Monitor("eDP-1", "BOE", "0x0bca", "", EDP_MODES, builtin=True),   # connector renamed by driver
            Monitor("HDMI-A-1", "SAM", "Odyssey", "H1", HDMI_MODES)]
    targets = plan_layout(mons, places, "resolution", keep_positions=True)
    assert [(t.monitor.connector, t.placement.x, t.placement.primary) for t in targets] == [
        ("eDP-1", 0, True), ("HDMI-A-1", 2560, False)]


def test_scaled_monitor_logical_width():
    places = [Placement("BOE 0x0bca", 0, 0, scale=1.25, primary=True), Placement("SAM Odyssey H1", 1, 0)]
    targets = plan_layout(owner_monitors(), places, "resolution")
    assert targets[1].placement.x == 2048                                   # 2560 / 1.25


# ---- GNOME backend with a fake Mutter -----------------------------------------------

def mutter_state(monitors, logical, serial=7):
    raw = []
    for m in monitors:
        modes = [(md.id, md.width, md.height, md.refresh, 1.0, [1.0],
                  {"is-current": ("b", md == m.current), "is-preferred": ("b", md.preferred)}) for md in m.modes]
        raw.append(((m.connector, m.vendor, m.product, m.serial), modes, {"is-builtin": ("b", m.builtin)}))
    lraw = [(l["x"], l["y"], l["scale"], 0, l["primary"], [(c, "", "", "") for c in l["connectors"]], {}) for l in logical]
    return (serial, raw, lraw, {})


class FakeMutter:
    def __init__(self, monitors, logical, broken=()):
        self.monitors, self.logical, self.broken, self.calls = monitors, logical, set(broken), []

    def get_current_state(self):
        return mutter_state(self.monitors, self.logical)

    def apply_monitors_config(self, serial, method, logical, props):
        self.calls.append((method, logical))
        if method == VERIFY:
            return
        new = []
        for m in self.monitors:
            mode_id = next(mid for (_x, _y, _s, _t, _p, mons) in logical for (conn, mid, _) in mons if conn == m.connector)
            mode = next(md for md in m.modes if md.id == mode_id)
            if mode_id in self.broken:               # the cable cannot carry it: Mutter keeps the old mode
                mode = m.current
            new.append(Monitor(m.connector, m.vendor, m.product, m.serial, m.modes, mode, m.builtin))
        self.monitors = new


LOGICAL = [{"x": 0, "y": 0, "scale": 1.0, "primary": False, "connectors": ["HDMI-A-1"]},
           {"x": 1920, "y": -260, "scale": 1.0, "primary": True, "connectors": ["eDP-2"]}]


def test_parse_mutter_state_roundtrip():
    serial, mons, logical = parse_state(mutter_state(owner_monitors(), LOGICAL))
    assert serial == 7 and mons[1].builtin and mons[0].current.refresh == 60.0
    assert logical[1] == {"x": 1920, "y": -260, "scale": 1.0, "transform": 0, "primary": True, "connectors": ["eDP-2"]}


def test_gnome_dry_run_only_verifies():
    bus = FakeMutter(owner_monitors(), LOGICAL)
    display = GnomeDisplay(bus)
    _, mons, logical = display.read()
    targets = plan_layout(mons, [Placement("SAM Odyssey H1", 0, 0), Placement("BOE 0x0bca", 1920, -260, primary=True)], "resolution")
    display.apply(targets, dry_run=True)
    assert [c[0] for c in bus.calls] == [VERIFY] and bus.monitors[0].current.refresh == 60.0


def test_gnome_falls_back_when_mode_does_not_stick():
    bus = FakeMutter(owner_monitors(), LOGICAL, broken={"b"})   # 1080p@180 fails (e.g. HDMI 1.4 cable)
    display = GnomeDisplay(bus)
    _, mons, _ = display.read()
    targets = plan_layout(mons, [Placement("SAM Odyssey H1", 0, 0), Placement("BOE 0x0bca", 1920, -260, primary=True)], "resolution")
    applied = display.apply(targets, dry_run=False)
    assert applied["SAM Odyssey H1"].label() == "1920x1080@60.00"      # next best
    assert applied["BOE 0x0bca"].label() == "2560x1600@165.00"
    assert all(c[0] == PERSISTENT for c in bus.calls)


def test_gnome_gives_up_after_last_candidate():
    bus = FakeMutter([Monitor("DP-1", "X", "Y", "1", (Mode(100, 100, 60.0, "only"), Mode(50, 50, 60.0, "z")),
                              Mode(1, 1, 1.0, "cur"))],
                     [{"x": 0, "y": 0, "scale": 1.0, "primary": True, "connectors": ["DP-1"]}], broken={"only", "z"})
    display = GnomeDisplay(bus)
    _, mons, logical = display.read()
    with pytest.raises(DisplayConfigError):
        display.apply(plan_layout(mons, [Placement("X Y 1", 0, 0, primary=True)], "resolution"), dry_run=False)


# ---- Hyprland block + D18 golden ----------------------------------------------------

HYPRCTL = json.dumps([
    {"name": "HDMI-A-1", "description": "Samsung Electric Company Odyssey G5 H1", "make": "Samsung Electric Company",
     "model": "Odyssey G5", "serial": "H1", "width": 1920, "height": 1080, "refreshRate": 60.0,
     "availableModes": ["1920x1080@180.00Hz", "1920x1080@60.00Hz"]},
    {"name": "eDP-2", "description": "BOE 0x0BCA", "make": "BOE", "model": "0x0BCA", "serial": "",
     "width": 2560, "height": 1600, "refreshRate": 60.0, "availableModes": ["2560x1600@165.00Hz", "2560x1600@60.00Hz"]},
])


def test_hyprland_block_golden_obeys_d18():
    runner = FakeRunner().on("hyprctl", result=HYPRCTL)
    mons = hyprland.read(runner)
    places = [Placement("Samsung Electric Company Odyssey G5 H1", 0, 0), Placement("BOE 0x0BCA", 1920, -260)]
    targets = plan_layout(mons, places, "resolution")
    src = (REPO / "configs" / "hypr" / "hyprland.conf").read_text()
    out = hyprland.replace_monitor_lines(src, hyprland.render_block(hyprland.monitor_lines(targets, "resolution")))
    assert check("hyprland", src, out) == []
    assert out == (GOLDEN / "v3" / "hyprland.conf").read_text()
    assert "monitor=desc:Samsung Electric Company Odyssey G5 H1,1920x1080@180.00,0x0,1" in out
    assert hyprland.replace_monitor_lines(out, hyprland.render_block(hyprland.monitor_lines(targets, "resolution"))) == out


def test_hyprland_block_without_running_hyprland_uses_keywords():
    mons = [Monitor("HDMI-A-1", "", "", "", (Mode(0, 0, 0.0, "auto"),))]
    lines = hyprland.monitor_lines(plan_layout(mons, [Placement("HDMI-A-1", 0, 0)], "refresh", True), "refresh")
    assert lines[0] == "monitor=HDMI-A-1,highrr,0x0,1"
    assert hyprland.read(FakeRunner().on("hyprctl", result=Result((), 1))) is None


# ---- catalog ----------------------------------------------------------------------------

D28 = {"base": 9, "essentials": 11, "media": 14, "cyber": 16, "remote": 4, "privacy": 8, "power": 6}
REMOVED = {"x11vnc", "stacer", "stirling-pdf", "pinokio", "flameshot", "switcheroo"}


def test_catalog_matches_d28():
    catalog = cat.load()
    for group, count in D28.items():
        assert len(cat.group(group, catalog)) == count, group
    assert not REMOVED & set(catalog)
    assert [e.id for e in cat.group("recovery", catalog)] == ["timeshift"]


def test_every_v25_package_is_kept_or_removed():
    v25 = json.loads((GOLDEN / "v25" / "packages.json").read_text())
    names = {n for k in ("PKG_ESSENTIALS", "PKG_MEDIA", "PKG_CYBER", "PKG_REMOTE", "PKG_POWER") for n in v25[k]}
    catalog = cat.load()
    arch_names = {e.arch.removeprefix("aur:") for e in catalog.values()}
    unaccounted = {n for n in names if n not in arch_names and n not in REMOVED}
    assert unaccounted == set()


def test_every_catalog_entry_has_a_source():
    for e in cat.load().values():
        assert e.arch or e.debian or e.fedora or e.flatpak, e.id


# ---- providers & resolution -------------------------------------------------------------

def test_pacman_single_transaction():
    r = FakeRunner()
    Pacman(r).install(["a", "b", "c"])
    assert r.calls == [("sudo", "--", "pacman", "-S", "--needed", "--noconfirm", "a", "b", "c")]


def test_apt_installed_parsing():
    r = FakeRunner().on("dpkg-query", result="vim\tinstalled\nnano\tnot-installed\n")
    assert Apt(r).installed(["vim", "nano", "x"]) == {"vim"}


def test_dnf_groups_are_available():
    r = FakeRunner().on("dnf", result="neovim\n")
    assert Dnf(r).available(["neovim", "@development-tools", "nope"]) == {"neovim", "@development-tools"}


def arch_runner(installed=(), repo=(), aur=()):
    aur_out = "".join(f"Name            : {n}\n" for n in aur)
    return (FakeRunner().on("pacman", "-Qq", result="\n".join(installed)).on("pacman", "-Slq", result="\n".join(repo))
            .on("sh", "-c", result=0).on("yay", "-Si", result=aur_out).on("flatpak", "list", result=""))


def test_resolve_arch_official_aur_and_typo():
    entries = [cat.load()[i] for i in ("neovim", "google-chrome", "planify", "git")]
    res = resolve(ARCH, arch_runner(installed=["git"], repo=["neovim"], aur=["my-aur-pkg"]), entries,
                  extra=["my-aur-pkg", "neovm"])
    assert res.native == ["neovim"] and res.installed == ["git"]
    assert res.aur == ["google-chrome", "planify", "my-aur-pkg"]     # catalog aur:, catalog fallback, verified extra
    assert res.unavailable == ["neovm"]                             # typo: reported, never sent to yay


def test_resolve_ubuntu_flatpak_fallback():
    entries = [cat.load()[i] for i in ("neovim", "discord", "fastfetch", "metasploit")]
    runner = (FakeRunner().on("dpkg-query", result="").on("apt-cache", "pkgnames", result="neovim\n")
              .on("sh", "-c", result=0).on("flatpak", "list", result=""))
    res = resolve(UBUNTU, runner, entries)
    assert res.native == ["neovim"] and res.flatpak == ["com.discordapp.Discord"]
    assert res.unavailable == ["metasploit (not packaged for ubuntu)", "fastfetch (fastfetch not in the repositories)"]
    no_fallback = resolve(UBUNTU, runner, entries, flatpak_fallback=False)
    assert no_fallback.flatpak == [] and len(no_fallback.unavailable) == 3


def test_wanted_entries_always_include_base():
    ids = [e.id for e in wanted_entries(["cyber"])]
    assert ids[:9] == [e.id for e in cat.group("base")] and "nmap" in ids


def test_custom_file_format(tmp_path):
    f = tmp_path / "pacs.txt"
    f.write_text("cmake # build tool\n\n# comment\nhtop  btop\n")
    assert read_custom_file(f) == ["cmake", "htop", "btop"]


def _ctx(tmp_path, runner, os_info=ARCH, profile_text=""):
    (tmp_path / "p.toml").write_text(profile_text)
    j = Journal.create(tmp_path / "runs")
    return Context(runner, Profile.load(tmp_path / "p.toml"), os_info, j, FileChanger(j, runner),
                   UI(Console(file=io.StringIO()), interactive=False), tmp_path, tmp_path)


def test_package_actions_plan_on_fresh_arch(tmp_path):
    runner = arch_runner(repo=["git", "curl", "neovim"]).on("sh", "-c", result=Result((), 1))  # yay missing
    ctx = _ctx(tmp_path, runner, profile_text='[packages]\ngroups = []\nextra = ["neovim"]\n')
    native = InstallNative().plan(ctx)
    assert {c.target for c in native} == {"git", "curl", "neovim"}
    helper = InstallAurHelper().plan(ctx)
    assert helper and helper[-1].target == "yay-bin"                  # AUR work pending, helper missing
    assert {c.target for c in InstallAur().plan(ctx)} >= {"wget"}     # not in the fake repo → AUR fallback
