"""Owner-config protection (CLAUDE.md D8/D18).

* repo dotfiles may only change deliberately (hash manifest)
* owner settings are present in the sources
* v3 golden files obey the D18 substitution rules and load into real dconf
* the D18 checker itself rejects forbidden changes
"""

import hashlib
import json
import re

import pytest
from conftest import GOLDEN, REPO, TEST_USER
from dotfile_rules import ARCON_SOURCE, MONITOR_BEGIN, MONITOR_END, check

OWNER = json.loads((GOLDEN / "owner_settings.json").read_text())


def _read(rel):
    return (REPO / rel).read_text()


# ---- sources ------------------------------------------------------------------

@pytest.mark.parametrize("line", (GOLDEN / "sources.sha256").read_text().splitlines())
def test_source_dotfile_unchanged(line):
    digest, rel = line.split()
    actual = hashlib.sha256((REPO / rel).read_bytes()).hexdigest()
    assert actual == digest, f"{rel} changed — update tests/golden/sources.sha256 only if the owner approved it"


@pytest.mark.parametrize("path,value", sorted(OWNER["dconf"].items()))
def test_owner_dconf_setting_in_source(path, value):
    section, key = path.lstrip("/").rsplit("/", 1)
    text = _read("configs/gno.conf")
    block = text.split(f"[{section}]\n", 1)[1].split("\n[", 1)[0]
    lines = {l.split("=", 1)[0]: l.split("=", 1)[1] for l in block.splitlines() if "=" in l and not l.startswith("#")}
    # dconf normalises the literal; compare after removing insignificant spaces
    assert re.sub(r"\s", "", lines[key]) == re.sub(r"\s", "", value)


@pytest.mark.parametrize("key,value", sorted(OWNER["terminator_default_profile"].items()))
def test_owner_terminator_setting_in_source(key, value):
    profile = _read("configs/terminator/config").split("[[default]]", 1)[1].split("[layouts]", 1)[0]
    assert f"    {key} = {value}\n" in profile


# ---- v3 golden files obey D18 -------------------------------------------------

def test_v3_gno_golden_obeys_d18():
    assert check("gno", _read("configs/gno.conf"), (GOLDEN / "v3" / "gno.conf").read_text(), TEST_USER) == []


def test_v3_hyprlock_golden_obeys_d18():
    assert check("hyprlock", _read("configs/hypr/hyprlock.conf"), (GOLDEN / "v3" / "hyprlock.conf").read_text()) == []
    assert (GOLDEN / "v3" / "hyprlock.conf").read_text().splitlines()[0] == ARCON_SOURCE


@pytest.mark.dconf
def test_v3_gno_golden_loads_into_dconf_with_owner_settings(dconf_session):
    golden = GOLDEN / "v3" / "gno.conf"
    expected = {**OWNER["dconf"], **OWNER["dconf_v3_wallpaper_default"]}
    script = f"dconf load / < '{golden}' && " + " && ".join(f"dconf read '{p}'" for p in expected)
    got = dconf_session(script).splitlines()
    assert dict(zip(expected, got)) == expected


@pytest.mark.dconf
def test_v25_source_loads_into_dconf(dconf_session):
    src = (REPO / "configs" / "gno.conf").read_text().replace("USER_PLACEHOLDER", TEST_USER)
    out = dconf_session(f"cat <<'EOF' | dconf load /\n{src}EOF\ndconf dump / | grep -c '^\\['")
    assert int(out.strip()) == 27


# ---- the checker rejects what D8 forbids --------------------------------------

def test_checker_rejects_theme_change():
    src = _read("configs/gno.conf")
    bad = src.replace("USER_PLACEHOLDER", TEST_USER).replace("'prefer-dark'", "'default'")
    assert check("gno", src, bad, TEST_USER)


def test_checker_rejects_extra_line():
    src = _read("configs/terminator/config")
    assert check("verbatim", src, src + "\n")


def test_checker_hyprland_block_rules():
    src = _read("configs/hypr/hyprland.conf")
    lines = src.splitlines(keepends=True)
    kept = [l for l in lines if not l.lstrip().lstrip("#").lstrip().startswith("monitor")]
    first = next(i for i, l in enumerate(lines) if "monitor=" in l)
    block = [MONITOR_BEGIN + "\n", "monitor=desc:Example Vendor 1,1920x1080@180,0x0,1\n", MONITOR_END + "\n"]
    good = "".join(kept[:first] + block + kept[first:])
    assert check("hyprland", src, good) == []
    assert check("hyprland", src, src)                         # no block
    assert check("hyprland", src, good + "monitor=,preferred,auto,1\n")  # stray monitor line
    assert check("hyprland", src, good.replace("kb_layout = us", "kb_layout = tr"))
