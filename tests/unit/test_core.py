"""Phase 3 core: runner, OS detection, profile, journal, backup/rollback, engine, wizard, CLI."""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

import pytest
from rich.console import Console

from arcon.core.action import Action, Change, Context, Reversible, Risk, clear_registry, register
from arcon.core.engine import build_plan, collect_actions, execute, report
from arcon.core.paths import Paths
from arcon.core.profile import Profile, ProfileError, validate
from arcon.core.runner import CommandError, DryRunRunner, FakeRunner, Result, SystemRunner
from arcon.core.ui import UI
from arcon.core.wizard import QUESTIONS, run_wizard
from arcon.package.base import Homebrew, NotSupported, Winget
from arcon.platform.detect import Family, OSInfo, Tier, classify, detect, parse_os_release
from arcon.recovery.backup import FileChanger, restore_files
from arcon.recovery.journal import DONE, FAILED, Journal

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "os"
ARCH = OSInfo(Family.ARCH, Tier.SUPPORTED, "arch", "Arch Linux")


def ui_with(answers=(), yes=False):
    out = io.StringIO()
    feed = iter(answers)
    return UI(Console(file=out, width=200), input_fn=lambda _p: next(feed), assume_yes=yes, interactive=True), out


# ---- runner -------------------------------------------------------------------

def test_system_runner_runs_and_reports():
    r = SystemRunner().run(["sh", "-c", "echo hi; exit 3"], check=False)
    assert r.returncode == 3 and r.stdout == "hi\n" and r.executed


def test_system_runner_missing_command_is_127():
    assert SystemRunner().run(["arcon-no-such-cmd"], check=False).returncode == 127


def test_system_runner_check_raises():
    with pytest.raises(CommandError):
        SystemRunner().run(["false"])


def test_dry_run_records_mutations_but_runs_probes(tmp_path):
    marker = tmp_path / "x"
    r = DryRunRunner()
    res = r.run(["touch", str(marker)])
    assert not res.executed and not marker.exists() and r.planned == [("touch", str(marker))]
    assert r.run(["echo", "probe"], mutating=False).stdout == "probe\n"


def test_sudo_prefix_and_fake_prefix_matching():
    f = FakeRunner().on("pacman", "-Q", result=Result((), 1)).on("pacman", result="ok")
    assert f.run(["pacman", "-Q", "x"], sudo=True, check=False).returncode == 1
    assert f.run(["pacman", "-S", "x"]).stdout == "ok"
    assert f.calls[0][:2] == ("sudo", "--")


# ---- OS detection -----------------------------------------------------------------

@pytest.mark.parametrize("name,family,tier", [
    ("arch", Family.ARCH, Tier.SUPPORTED), ("debian", Family.DEBIAN, Tier.SUPPORTED),
    ("ubuntu", Family.DEBIAN, Tier.SUPPORTED), ("fedora", Family.FEDORA, Tier.SUPPORTED),
    ("cachyos", Family.ARCH, Tier.EXPERIMENTAL), ("endeavouros", Family.ARCH, Tier.EXPERIMENTAL),
    ("linuxmint", Family.DEBIAN, Tier.EXPERIMENTAL), ("nobara", Family.FEDORA, Tier.EXPERIMENTAL),
    ("gentoo", Family.UNKNOWN, Tier.UNSUPPORTED),
])
def test_os_fixtures(name, family, tier):
    info = detect(FIX / f"{name}.os-release", system="Linux")
    assert (info.family, info.tier) == (family, tier)


def test_os_release_is_never_executed(tmp_path):
    info = detect(FIX / "malicious.os-release", system="Linux")
    assert info.tier is Tier.UNSUPPORTED
    assert not Path("/tmp/arcon-pwned").exists() and not Path("/tmp/arcon-pwned2").exists()


def test_windows_and_macos_are_stubs():
    assert detect(system="Windows").tier is Tier.STUB
    assert detect(system="Darwin").family is Family.MACOS
    for pm in (Winget(FakeRunner()), Homebrew(FakeRunner())):
        with pytest.raises(NotSupported):
            pm.install(["x"])


def test_parse_os_release_quotes():
    assert parse_os_release('ID="arch"\nPRETTY_NAME="Arch Linux"\n# c\n')["PRETTY_NAME"] == "Arch Linux"
    assert classify({"ID": "Ubuntu"}).family is Family.DEBIAN


# ---- profile ------------------------------------------------------------------------

def test_owner_profile_is_valid():
    p = Profile.load(Path(__file__).resolve().parents[2] / "profiles" / "mrfedai.toml")
    assert p.get("shell", "name") == "zsh"
    assert p.get("packages", "groups") == ["essentials", "media", "cyber"]
    assert p.get("wallpaper", "mode") == "none" and not p.enabled("gaming")


def test_profile_rejects_typos_and_bad_values(tmp_path):
    f = tmp_path / "p.toml"
    f.write_text("[modules]\ngnom = true\n[shell]\nname = 'tcsh'\n[packages]\ngroups=['base']\n")
    with pytest.raises(ProfileError) as exc:
        Profile.load(f)
    msg = str(exc.value)
    assert "modules.gnom" in msg and "shell.name" in msg and "packages.groups" in msg
    assert validate({"nope": {}}) == ["unknown section [nope]"]


def test_profile_save_keeps_comments(tmp_path):
    f = tmp_path / "p.toml"
    f.write_text("# my notes\n[shell]\nname = \"bash\"  # keep this comment\n")
    p = Profile.load(f)
    p.set("shell", "name", "zsh")
    p.set("modules", "gaming", True)
    p.save()
    text = f.read_text()
    assert "# my notes" in text and "# keep this comment" in text and 'name = "zsh"' in text
    assert Profile.load(f).enabled("gaming")


def test_profile_defaults():
    p = Profile.load_or_default(Path("/nonexistent/p.toml"))
    assert p.get("wallpaper", "mode") == "none" and p.get("display", "prefer") == "resolution"
    assert p.as_dict()["packages"]["flatpak_fallback"] is True


# ---- journal, backup, rollback ------------------------------------------------------

def test_journal_roundtrip_and_torn_line(tmp_path):
    j = Journal.create(tmp_path, run_id="r1")
    j.write("action", id="a", status=DONE)
    with j.path.open("a") as fh:
        fh.write('{"event": "action", "id": "b"')  # crash mid-write
    assert Journal.open(tmp_path).action_status() == {"a": DONE}


def test_file_changer_backup_and_rollback(tmp_path):
    j = Journal.create(tmp_path / "runs", run_id="r1")
    fc = FileChanger(j, FakeRunner())
    existing, new = tmp_path / "home" / "a.conf", tmp_path / "home" / "new.conf"
    existing.parent.mkdir()
    existing.write_text("old\n")
    existing.chmod(0o600)
    assert fc.write(existing, b"new\n") and fc.write(new, b"x\n")
    assert not fc.write(existing, b"new\n")                    # idempotent
    assert existing.read_text() == "new\n" and oct(existing.stat().st_mode & 0o777) == "0o600"
    report = restore_files(j, FakeRunner())
    assert existing.read_text() == "old\n" and not new.exists() and len(report) == 2


def test_file_changer_dry_run_changes_nothing(tmp_path):
    j = Journal.create(tmp_path / "runs", run_id="r1")
    target = tmp_path / "f"
    assert FileChanger(j, FakeRunner(dry_run=True)).write(target, b"x")
    assert not target.exists()
    assert [e["event"] for e in j.events()] == ["run_start", "file_planned"]


def test_root_file_goes_through_sudo(tmp_path):
    j = Journal.create(tmp_path / "runs", run_id="r1")
    runner = FakeRunner()
    FileChanger(j, runner).write(tmp_path / "etc" / "x.conf", b"k=v\n", root=True, mode=0o644)
    assert ("sudo", "--", "tee", str(tmp_path / "etc" / "x.conf")) in runner.calls
    assert runner.inputs[runner.calls.index(("sudo", "--", "tee", str(tmp_path / "etc" / "x.conf")))] == "k=v\n"


# ---- engine -------------------------------------------------------------------------

class Touch(Action):
    def __init__(self, id, path, fail=False, requires=(), reversible=Reversible.YES):
        self.id, self.title, self.path, self.fail = id, f"touch {path.name}", path, fail
        self.requires, self.reversible = requires, reversible

    def plan(self, ctx):
        return [] if self.path.exists() else [Change("file", str(self.path))]

    def apply(self, ctx):
        if self.fail:
            raise RuntimeError("boom")
        ctx.files.write(self.path, b"x")

    def verify(self, ctx):
        return self.path.exists()


@pytest.fixture
def ctx_factory(tmp_path):
    def make(runner=None, answers=(), yes=True, profile=None):
        runner = runner or FakeRunner()
        j = Journal.create(tmp_path / "runs")
        ui, out = ui_with(answers, yes)
        ctx = Context(runner=runner, profile=profile or Profile.load_or_default(tmp_path / "p.toml"),
                      os=ARCH, journal=j, files=FileChanger(j, runner), ui=ui,
                      repo_root=tmp_path, home=tmp_path)
        ctx._out = out
        return ctx
    return make


def test_engine_apply_skip_and_idempotent(tmp_path, ctx_factory):
    a, b = Touch("a", tmp_path / "a"), Touch("b", tmp_path / "b")
    (tmp_path / "b").write_text("already")
    ctx = ctx_factory()
    plan = execute(ctx, build_plan(ctx, [a, b]))
    assert [p.status for p in plan.items] == ["done", "skipped"] and report(ctx, plan) == 0
    ctx2 = ctx_factory()
    assert build_plan(ctx2, [a, b]).pending == []            # second run: nothing to do


def test_engine_failure_stops_then_resume(tmp_path, ctx_factory):
    a, bad, c = Touch("a", tmp_path / "a"), Touch("bad", tmp_path / "bad", fail=True), Touch("c", tmp_path / "c")
    ctx = ctx_factory()
    plan = execute(ctx, build_plan(ctx, [a, bad, c]))
    assert [p.status for p in plan.items] == ["done", "failed", "not-run"] and report(ctx, plan) == 1
    status = ctx.journal.action_status()
    assert status == {"a": DONE, "bad": FAILED}
    bad.fail = False
    ctx2 = ctx_factory()
    plan2 = execute(ctx2, build_plan(ctx2, [a, bad, c], done={k for k, v in status.items() if v == DONE}))
    assert [p.status for p in plan2.items] == ["done", "done", "done"]


def test_engine_keep_going_and_requires(tmp_path, ctx_factory):
    bad = Touch("bad", tmp_path / "bad", fail=True)
    dep = Touch("dep", tmp_path / "dep", requires=("bad",))
    other = Touch("other", tmp_path / "other")
    ctx = ctx_factory()
    plan = execute(ctx, build_plan(ctx, [bad, dep, other]), keep_going=True)
    assert [p.status for p in plan.items] == ["failed", "not-run", "done"]


def test_engine_dry_run_changes_nothing(tmp_path, ctx_factory):
    ctx = ctx_factory(runner=FakeRunner(dry_run=True))
    plan = execute(ctx, build_plan(ctx, [Touch("a", tmp_path / "a")]))
    assert plan.items[0].status == "done" and not (tmp_path / "a").exists()


def test_registry_respects_profile_modules(tmp_path, ctx_factory):
    clear_registry()
    try:
        register("gaming", "Gaming")(lambda ctx: [Touch("g", tmp_path / "g")])
        register("gnome", "GNOME")(lambda ctx: [Touch("n", tmp_path / "n")])
        ids = [a.id for a in collect_actions(ctx_factory())]   # defaults: gnome on, gaming off
        assert ids == ["n"]
    finally:
        clear_registry()


# ---- wizard ----------------------------------------------------------------------------

def test_wizard_asks_everything_up_front_and_saves(tmp_path):
    profile = Profile.load_or_default(tmp_path / "p.toml")
    answers = []
    for q in QUESTIONS:  # enable everything, pick defaults for choices
        answers.append("y" if not q.choices else "")
        if (q.section, q.key) == ("modules", "packages"):
            answers += ["y", "n", "y", "n", "n", "n"]  # essentials + cyber
    ui, _ = ui_with(answers)
    run_wizard(profile, ui)
    assert profile.get("packages", "groups") == ["essentials", "cyber"]
    assert profile.enabled("gaming") and profile.get("security", "usbguard") is True
    profile.save()
    ui2, _ = ui_with(["y"])                                      # reuse previous answers
    reused = run_wizard(Profile.load(tmp_path / "p.toml"), ui2)
    assert reused.get("packages", "groups") == ["essentials", "cyber"]


def test_typed_confirmation_never_auto_yes():
    ui, _ = ui_with([], yes=True)
    ui.interactive = False
    assert ui.confirm("x") is True and ui.typed_confirm("x", "CLEAN") is False


# ---- CLI --------------------------------------------------------------------------------

def _app(tmp_path, command, os_info=ARCH, answers=(), yes=False, dry=False):
    from arcon.cli import App
    args = argparse.Namespace(command=command, profile=None, dry_run=dry, yes=yes, keep_going=False,
                              verbose=False, run_id=None, what="show")
    ui, out = ui_with(answers, yes)
    env = {"HOME": str(tmp_path), "XDG_CONFIG_HOME": str(tmp_path / "cfg"), "XDG_STATE_HOME": str(tmp_path / "st")}
    app = App(args, ui=ui, runner=FakeRunner(dry_run=dry), paths=Paths.from_env(env), os_info=os_info,
              repo_root=tmp_path)
    return app, out


def test_cli_refuses_stub_and_unsupported(tmp_path):
    app, out = _app(tmp_path, "apply", OSInfo(Family.WINDOWS, Tier.STUB, "windows", "Windows"))
    assert app.cmd_apply() == 3 and "interfaces only" in out.getvalue()
    app, _ = _app(tmp_path, "apply", OSInfo(Family.UNKNOWN, Tier.UNSUPPORTED, "gentoo", "Gentoo"))
    assert app.cmd_apply() == 3


def test_cli_full_flow_confirm_apply_rollback(tmp_path):
    clear_registry()
    target = tmp_path / "home.conf"
    target.write_text("original\n")

    class Edit(Touch):
        def plan(self, ctx):
            return [] if target.read_text() == "arcon\n" else [Change("file", str(target))]

        def apply(self, ctx):
            ctx.files.write(target, b"arcon\n")

    try:
        register("dotfiles", "Dotfiles")(lambda ctx: [Edit("edit", target)])
        app, out = _app(tmp_path, "apply", answers=["y"])
        assert app.cmd_apply() == 0 and target.read_text() == "arcon\n"
        assert "ArCoN plan" in out.getvalue()
        app, _ = _app(tmp_path, "runs")
        assert app.cmd_runs() == 0
        app, _ = _app(tmp_path, "rollback", answers=["y"])
        assert app.cmd_rollback() == 0 and target.read_text() == "original\n"
        app, out = _app(tmp_path, "apply", answers=["n"])          # declining changes nothing
        assert app.cmd_apply() == 0 and target.read_text() == "original\n"
        assert "Cancelled" in out.getvalue()
    finally:
        clear_registry()


def test_cli_root_guard(monkeypatch, capsys):
    import arcon.cli as cli
    monkeypatch.setattr(cli, "_is_root", lambda: True)
    monkeypatch.delenv("ARCON_ALLOW_ROOT", raising=False)
    assert cli.main(["apply"]) == 2
    assert "normal user" in capsys.readouterr().err


def test_profile_template_is_valid_and_complete():
    import tomllib
    from arcon.core.profile import SCHEMA
    path = Path(__file__).resolve().parents[2] / "arcon" / "data" / "profile.template.toml"
    data = tomllib.loads(path.read_text())
    Profile.load(path)
    for section, keys in SCHEMA.items():
        for key, (default, _v) in keys.items():
            if (section, key) == ("display", "monitor"):
                continue
            assert data[section][key] == default, f"{section}.{key}"


def test_global_options_after_the_command():
    from arcon.cli import _parser
    args = _parser().parse_args(["plan", "--profile", "x.toml", "-v"])
    assert args.command == "plan" and str(args.profile) == "x.toml" and args.verbose
    args = _parser().parse_args(["--profile", "y.toml", "apply"])
    assert str(args.profile) == "y.toml" and args.dry_run is False
