"""Characterization of ArCoN v2.5 (tag v2.5.0).

These tests pin down what v2.5 ACTUALLY does, bugs included. They are the
reference the Python port is compared against; a failure here means either
the harness or the golden file changed — never "fix" v2.5 to make it pass.
"""

import json

import pytest
from conftest import GOLDEN, REPO, TEST_USER
from snapshot import golden_path, run_scenario
from v25_extract import extract_package_lists, v25_setup_sh

pytestmark = pytest.mark.characterization


def _golden(name):
    return json.loads(golden_path(name).read_text())


def test_package_lists_match_golden():
    assert extract_package_lists(v25_setup_sh()) == json.loads((GOLDEN / "v25" / "packages.json").read_text())


def test_group_package_count():
    lists = extract_package_lists(v25_setup_sh())
    groups = [p for k in ("PKG_ESSENTIALS", "PKG_MEDIA", "PKG_CYBER", "PKG_REMOTE", "PKG_POWER") for p in lists[k]]
    assert len(groups) == 76 and len(set(groups)) == 76


@pytest.mark.parametrize("scenario", ["dotfiles-debian"])
def test_debian_scenario_matches_golden(scenario, tmp_path):
    assert run_scenario(scenario, tmp_path) == _golden(scenario)


@pytest.mark.parametrize("scenario", ["dotfiles-arch", "packages-arch"])
def test_arch_scenario_matches_golden(scenario, tmp_path, needs_root_namespace):
    assert run_scenario(scenario, tmp_path) == _golden(scenario)


def test_v25_gnome_output_is_sed_of_source():
    """v2.5 feeds dconf exactly `sed s/USER_PLACEHOLDER/$USER/ configs/gno.conf`."""
    src = (REPO / "configs" / "gno.conf").read_text().replace("USER_PLACEHOLDER", TEST_USER)
    for name in ("dotfiles-debian", "dotfiles-arch"):
        assert (GOLDEN / "v25" / f"{name}.dconf-load.ini").read_text() == src


def test_v25_deploys_terminator_and_hypr_verbatim():
    sources = dict(line.split()[::-1] for line in (GOLDEN / "sources.sha256").read_text().splitlines())
    arch = _golden("dotfiles-arch")["files"]
    assert arch[".config/terminator/config"] == sources["configs/terminator/config"]
    for f in ("hyprland.conf", "hypridle.conf", "hyprlock.conf"):
        assert arch[f".config/hypr/{f}"] == sources[f"configs/hypr/{f}"]


# ---- known v2.5 bugs, pinned so the port can prove it fixed them ----------

def test_bug_gaming_not_offered_without_gnome():
    cmds = _golden("packages-arch")["commands"]
    assert not any("steam" in c or "gamemode " in c.split("-S")[-1] for c in cmds if c.startswith("sudo pacman -S"))


def test_bug_one_pacman_call_per_package():
    cmds = _golden("packages-arch")["commands"]
    installs = [c for c in cmds if c.startswith("sudo pacman -S --needed --noconfirm --color always")]
    assert len(installs) == 71  # 77 queued = 71 official + 6 AUR, installed one by one


def test_bug_wallpaper_points_to_missing_file():
    files = _golden("dotfiles-debian")["files"]
    assert "Pictures/wallp/default.jpg" not in files
    assert "default.jpg" in (GOLDEN / "v25" / "dotfiles-debian.dconf-load.ini").read_text()


def test_bug_hyprland_official_packages_via_yay():
    cmds = _golden("dotfiles-arch")["commands"]
    assert any(c.startswith("yay -S --noconfirm --needed hyprland") for c in cmds)
