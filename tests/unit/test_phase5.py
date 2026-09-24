"""Phase 5 feature modules (FakeRunner; nothing touches the system)."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from conftest import GOLDEN, REPO
from rich.console import Console

from arcon.core.action import Context
from arcon.core.profile import Profile
from arcon.core.runner import FakeRunner, Result
from arcon.core.ui import UI
from arcon.desktop.gnome import ApplyGnomeSettings, dconf_keys, render_gno
from arcon.dotfiles import manager
from arcon.dotfiles.rules import check
from arcon.gaming.actions import gpu_packages
from arcon.hardware.linux import GPU, Hardware
from arcon.optimization.actions import Cache, _bluetooth
from arcon.platform.detect import Family, OSInfo, Tier
from arcon.core import preflight
from arcon.recovery.backup import FileChanger, dconf_user, restore_files
from arcon.recovery.journal import Journal
from arcon.recovery.reset import CONFIGS, PROTECTED, ResetConfigs, ResetPackages
from arcon.security.actions import SYSCTL, Firewall, SshDropIn
from arcon.system.actions import enable_multilib
from arcon.terminal.actions import PINS, ChangeShell, _zshrc_edit

ARCH = OSInfo(Family.ARCH, Tier.SUPPORTED, "arch", "Arch Linux")
UBUNTU = OSInfo(Family.DEBIAN, Tier.SUPPORTED, "ubuntu", "Ubuntu")
DEBIAN = OSInfo(Family.DEBIAN, Tier.SUPPORTED, "debian", "Debian")


def ctx_for(tmp_path, profile_text="", os_info=ARCH, runner=None, answers=()):
    (tmp_path / "p.toml").write_text(profile_text)
    runner = runner or FakeRunner()
    j = Journal.create(tmp_path / "runs")
    feed = iter(answers)
    ui = UI(Console(file=io.StringIO(), width=200), input_fn=lambda _p: next(feed), interactive=bool(answers))
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return Context(runner, Profile.load(tmp_path / "p.toml"), os_info, j, FileChanger(j, runner), ui, REPO, home)


# ---- GNOME ---------------------------------------------------------------------------

def test_render_gno_equals_v3_golden(tmp_path, monkeypatch):
    monkeypatch.setenv("USER", "arcontest")
    ctx = ctx_for(tmp_path)
    assert render_gno(ctx, (REPO / "configs" / "gno.conf").read_text()) == (GOLDEN / "v3" / "gno.conf").read_text()


def test_render_gno_with_wallpaper_file_obeys_d18(tmp_path, monkeypatch):
    monkeypatch.setenv("USER", "arcontest")
    ctx = ctx_for(tmp_path, '[wallpaper]\nmode = "file"\nfile = "/home/arcontest/Pictures/w.jpg"\n')
    src = (REPO / "configs" / "gno.conf").read_text()
    out = render_gno(ctx, src)
    assert "picture-uri='file:///home/arcontest/Pictures/w.jpg'" in out and "picture-options='zoom'" in out
    assert check("gno", src, out, "arcontest") == []


def test_dconf_keys_parse():
    keys = dconf_keys((GOLDEN / "v3" / "gno.conf").read_text())
    assert keys["/org/gnome/desktop/interface/color-scheme"] == "'prefer-dark'"
    assert keys["/org/gnome/desktop/screensaver/lock-delay"] == "uint32 30"


def test_gnome_plan_lists_only_differences(tmp_path, monkeypatch):
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", "unix:path=/fake")
    keys = dconf_keys(render_gno(ctx_for(tmp_path), (REPO / "configs" / "gno.conf").read_text()))
    current = dict(keys)
    current["/org/gnome/desktop/interface/color-scheme"] = "'default'"
    runner = FakeRunner().on("sh", "-c", result=0).on("dconf", "read", result=lambda cmd, _i: current.get(cmd[2], ""))
    (tmp_path / "second").mkdir()
    ctx = ctx_for(tmp_path / "second", runner=runner)
    changes = ApplyGnomeSettings().plan(ctx)
    assert [c.target for c in changes] == ["/org/gnome/desktop/interface/color-scheme"]


# ---- system ---------------------------------------------------------------------------

PACMAN_CONF = """[options]
HoldPkg = pacman glibc

[core]
Include = /etc/pacman.d/mirrorlist

#[multilib-testing]
#Include = /etc/pacman.d/mirrorlist

#[multilib]
#Include = /etc/pacman.d/mirrorlist
"""


def test_enable_multilib_only_touches_multilib():
    out = enable_multilib(PACMAN_CONF)
    assert "[multilib]\nInclude = /etc/pacman.d/mirrorlist\n" in out
    assert "#[multilib-testing]\n#Include" in out            # testing repo stays disabled
    assert enable_multilib(out) == out                        # idempotent


# ---- gaming ---------------------------------------------------------------------------

def _hw(*gpus, kernels=("linux",)):
    return Hardware(gpus=list(gpus), kernels=list(kernels))


RTX = GPU("nvidia", 0x2520, "0000:01:00.0")
GTX1080 = GPU("nvidia", 0x1B80, "0000:01:00.0")
IGPU = GPU("intel", 0x9A49, "0000:00:02.0", boot_vga=True)


def test_nvidia_open_on_stock_kernel(tmp_path):
    ids, names, notes = gpu_packages(ctx_for(tmp_path), _hw(RTX))
    assert ids[0] == "nvidia-open" and "lib32-nvidia-utils" in ids and names == [] and notes == []


def test_nvidia_dkms_with_extra_kernels_and_prime_on_hybrid(tmp_path):
    ids, names, _ = gpu_packages(ctx_for(tmp_path), _hw(IGPU, RTX, kernels=("linux", "linux-lts")))
    assert "nvidia-open-dkms" in ids and names == ["linux-headers", "linux-lts-headers", "nvidia-prime"]
    assert "vulkan-intel" in ids


def test_old_nvidia_is_not_automated(tmp_path):
    ids, _, notes = gpu_packages(ctx_for(tmp_path), _hw(GTX1080))
    assert not any(i.startswith("nvidia") for i in ids) and "legacy driver" in notes[0]


def test_debian_nvidia_needs_manual_repo(tmp_path):
    _, _, notes = gpu_packages(ctx_for(tmp_path, os_info=DEBIAN), _hw(RTX))
    assert "non-free" in notes[0]


# ---- terminal / shell -----------------------------------------------------------------

def test_zshrc_edit_changes_only_two_lines():
    text = 'export ZSH="$HOME/.oh-my-zsh"\nZSH_THEME="robbyrussell"\nplugins=(git)\nalias ll="ls -l"\n'
    out = _zshrc_edit(text, "agnoster")
    assert out == 'export ZSH="$HOME/.oh-my-zsh"\nZSH_THEME="agnoster"\nplugins=(git zsh-autosuggestions zsh-syntax-highlighting)\nalias ll="ls -l"\n'


def test_all_shell_repos_are_pinned():
    assert all(len(commit) == 40 for _url, commit in PINS.values())


def test_login_shell_path_with_merged_sbin(tmp_path, monkeypatch):
    # Arch / Fedora 42+: /usr/sbin -> bin, root's PATH has sbin first, so `which`
    # answers the sbin path; chsh needs the /etc/shells entry (CI run 36055367756)
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "zsh").write_text("")
    (tmp_path / "sbin").symlink_to("bin")
    shells = f"# /etc/shells\n/bin/sh\n{tmp_path}/bin/zsh\n"
    monkeypatch.setattr("shutil.which", lambda name: f"{tmp_path}/sbin/{name}")
    assert ChangeShell.shell_path("zsh", shells) == f"{tmp_path}/bin/zsh"
    monkeypatch.setattr("shutil.which", lambda name: f"{tmp_path}/bin/{name}")
    assert ChangeShell.shell_path("zsh", shells) == f"{tmp_path}/bin/zsh"   # listed as found
    assert ChangeShell.shell_path("fish", shells) is None                   # not listed at all


# ---- security ---------------------------------------------------------------------------

def test_firewall_inactive_is_not_active(tmp_path):
    runner = FakeRunner().on("ufw", "status", result="Status: inactive\n")
    ctx = ctx_for(tmp_path, "[security]\nfirewall = true\n", runner=runner)
    assert Firewall().plan(ctx)
    runner.on("ufw", "status", result="Status: active\n")
    assert Firewall().plan(ctx) == []


def test_firewall_allows_ssh_before_enabling(tmp_path):
    runner = FakeRunner().on("systemctl", "is-active", "sshd", result="active\n")
    ctx = ctx_for(tmp_path, "[security]\nfirewall = true\n", runner=runner)
    Firewall().apply(ctx)
    cmds = [c[2:] for c in runner.calls if c[:2] == ("sudo", "--")]
    assert cmds.index(("ufw", "allow", "OpenSSH")) < cmds.index(("ufw", "--force", "enable"))


def test_ssh_password_disable_needs_typed_confirmation(tmp_path, monkeypatch):
    ctx = ctx_for(tmp_path, "[security]\nssh_root_login = true\nssh_disable_password = true\n", answers=["no"])
    ctx.facts["ssh_password_confirmed"] = False
    assert "PasswordAuthentication" not in SshDropIn().content(ctx)
    ctx.facts["ssh_password_confirmed"] = True
    assert "PasswordAuthentication no" in SshDropIn().content(ctx)


def test_sysctl_content_matches_v25():
    v25 = (REPO / "legacy" / "v2.5" / "setup.sh").read_text()
    for line in SYSCTL.splitlines():
        if line and not line.startswith("#"):
            assert line in v25


# ---- optimization / cleanup -----------------------------------------------------------------

def test_bluetooth_autoenable_edit():
    assert "AutoEnable=true" in _bluetooth("[Policy]\n#AutoEnable=false\n")
    assert _bluetooth("[Policy]\nAutoEnable=true\n") == "[Policy]\nAutoEnable=true\n"


def test_cache_default_keeps_downgrade_path(tmp_path):
    runner = FakeRunner()
    ctx = ctx_for(tmp_path, runner=runner)
    assert "paccache -rk2" in Cache().plan(ctx)[0].detail
    Cache().apply(ctx)
    assert runner.calls == [("sudo", "--", "paccache", "-rk2")]


# ---- dotfiles --------------------------------------------------------------------------------

def test_terminator_deploy_diff_and_rollback(tmp_path):
    ctx = ctx_for(tmp_path)
    action = manager.DeployDotfile(manager.DOTFILES[0])
    assert action.plan(ctx)
    action.apply(ctx)
    target = ctx.home / ".config" / "terminator" / "config"
    assert target.read_bytes() == (REPO / "configs" / "terminator" / "config").read_bytes()
    assert manager.DeployDotfile(manager.DOTFILES[0]).plan(ctx) == []      # idempotent
    target.write_text(target.read_text() + "# local tweak\n")
    assert "+# local tweak" in manager.diff(ctx, manager.DOTFILES[0])
    restore_files(ctx.journal, FakeRunner())
    assert not target.exists()


def test_hyprland_files_render_d18_valid(tmp_path):
    runner = FakeRunner().on("hyprctl", result=Result((), 1))
    ctx = ctx_for(tmp_path, runner=runner)
    for d in manager.DOTFILES:
        if d.module != "hyprland":
            continue
        src = (REPO / d.source).read_text()
        assert check(d.kind, src, manager.rendered(ctx, d)) == [], d.name


def test_capture_hyprland_restores_original_monitor_lines(tmp_path):
    import shutil
    repo = tmp_path / "repo"
    shutil.copytree(REPO / "configs", repo / "configs")
    ctx = ctx_for(tmp_path, runner=FakeRunner().on("hyprctl", result=Result((), 1)))
    ctx.repo_root = repo
    d = [x for x in manager.DOTFILES if x.name == "hyprland"][0]
    live = manager.rendered(ctx, d).replace("kb_layout = us", "kb_layout = tr")
    (ctx.home / d.target).parent.mkdir(parents=True)
    (ctx.home / d.target).write_text(live)
    assert manager.capture(ctx, d)
    captured = (repo / d.source).read_text()
    assert "kb_layout = tr" in captured and "ArCoN monitors" not in captured
    assert "monitor=HDMI-A-1, 1920x1080@180, 0x0, 1" in captured


# ---- reset -------------------------------------------------------------------------------------

def test_reset_never_touches_protected_or_user_data():
    assert not {".config/nvim", ".config/terminator", ".config/kitty", ".config/google-chrome",
                ".config/Code", ".config/discord"} & set(CONFIGS)
    assert {"neovim", "vim", "git", "terminator", "zsh"} <= PROTECTED


def test_reset_packages_excludes_protected(tmp_path):
    runner = FakeRunner().on("pacman", "-Qq", result="neovim\nvlc\nsteam\ngit\n")
    ctx = ctx_for(tmp_path, runner=runner)
    assert [c.target for c in ResetPackages().plan(ctx)] == ["steam", "vlc"]


def test_reset_configs_backup_and_restore(tmp_path):
    ctx = ctx_for(tmp_path)
    hypr = ctx.home / ".config" / "hypr"
    hypr.mkdir(parents=True)
    (hypr / "hyprland.conf").write_text("x")
    action = ResetConfigs()
    assert [c.target for c in action.plan(ctx)] == [str(hypr)]
    action.apply(ctx)
    assert not hypr.exists()
    restore_files(ctx.journal, FakeRunner())
    assert (hypr / "hyprland.conf").read_text() == "x"


# ---- preflight ------------------------------------------------------------------------------------

def test_live_environment_detection(tmp_path):
    (tmp_path / "proc").mkdir()
    (tmp_path / "proc" / "mounts").write_text("overlay / overlay rw 0 0\n")
    assert preflight.live_environment(tmp_path)
    (tmp_path / "proc" / "mounts").write_text("/dev/nvme0n1p2 / ext4 rw 0 0\n")
    assert not preflight.live_environment(tmp_path)


def test_stale_pacman_lock_is_asked_not_silently_removed(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCON_SKIP_SUDO_CHECK", "1")
    lock = tmp_path / "var" / "lib" / "pacman"
    lock.mkdir(parents=True)
    (lock / "db.lck").write_text("")
    runner = FakeRunner().on("pgrep", result=Result((), 1))
    feed = iter(["n"])
    ui = UI(Console(file=io.StringIO()), input_fn=lambda _p: next(feed), interactive=True)
    assert not preflight.run(ARCH, runner, ui, needs_network=False, dry_run=False, root=tmp_path)
    assert not any("rm" in c for c in runner.calls)


def test_dconf_backup_and_restore_use_the_user_database_only(tmp_path):
    # `dconf dump /` merges system databases (Fedora: locked authselect keys);
    # restoring those failed with "non-writable keys" (CI run 36056633594)
    seen = []

    class Recorder(FakeRunner):
        def run(self, argv, **kw):
            profile = (kw.get("env") or {}).get("DCONF_PROFILE")
            seen.append((tuple(argv), Path(profile).read_text() if profile else None))
            return super().run(argv, **kw)

    runner = Recorder().on("dconf", "dump", result="[org/gnome/desktop/interface]\ncolor-scheme='prefer-dark'\n")
    assert "prefer-dark" in dconf_user(runner, "dump", "/", mutating=False).stdout
    journal = Journal.create(tmp_path / "runs")
    dump = journal.backup_dir / "dconf-full.ini"
    dump.parent.mkdir(parents=True, exist_ok=True)
    dump.write_text("[org/gnome/desktop/interface]\ncolor-scheme='default'\n")
    journal.write("dconf_backup", path=str(dump))
    restore_files(journal, runner)
    dconf_calls = [(argv[1], prof) for argv, prof in seen]
    assert dconf_calls == [("dump", "user-db:user\n"), ("reset", "user-db:user\n"), ("load", "user-db:user\n")]
