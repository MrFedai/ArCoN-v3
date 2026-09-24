"""`arcon` command line.

    arcon                 wizard → plan → one confirmation → apply  (the v2.5 flow, D14)
    arcon plan            show what would change (dry run)
    arcon apply           apply the saved profile without the wizard
    arcon wizard          only (re)answer the questions and save the profile
    arcon resume          continue the latest unfinished run
    arcon rollback [RUN]  restore files changed by a run (packages are never "rolled back" silently)
    arcon runs            list previous runs
    arcon profile show|path|validate
    arcon doctor          what ArCoN detects on this machine
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from arcon import __version__
from arcon.core.action import Context
from arcon.core.engine import build_plan, collect_actions, execute, report, show_plan
from arcon.core.log import setup_file_logging
from arcon.core.paths import Paths
from arcon.core.profile import Profile, ProfileError
from arcon.core.runner import DryRunRunner, Runner, SystemRunner
from arcon.core.ui import UI
from arcon.core.wizard import run_wizard
from arcon.platform.detect import OSInfo, Tier, detect
from arcon.recovery import snapshot
from arcon.recovery.backup import FileChanger, restore_files
from arcon.recovery.journal import DONE, Journal, list_runs

REPO_ROOT = Path(__file__).resolve().parents[1]
EXIT_OK, EXIT_FAILED, EXIT_USAGE, EXIT_UNSUPPORTED = 0, 1, 2, 3


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="arcon", description="ArCoN — system setup and configuration toolkit")
    p.add_argument("--version", action="version", version=f"arcon {__version__}")
    p.add_argument("--profile", type=Path, help="profile TOML (default: ~/.config/arcon/profile.toml)")
    p.add_argument("-n", "--dry-run", action="store_true", help="show and journal changes without making them")
    p.add_argument("-y", "--yes", action="store_true", help="answer yes to normal confirmations (never to typed ones)")
    p.add_argument("--keep-going", action="store_true", help="continue with other actions after a failure")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command")
    sub.add_parser("plan", help="dry run: show what would change")
    sub.add_parser("apply", help="apply the saved profile")
    sub.add_parser("wizard", help="answer the questions and save the profile")
    sub.add_parser("resume", help="continue the latest unfinished run")
    rb = sub.add_parser("rollback", help="restore files changed by a run")
    rb.add_argument("run_id", nargs="?")
    sub.add_parser("runs", help="list previous runs")
    pr = sub.add_parser("profile", help="show / validate the profile")
    pr.add_argument("what", choices=("show", "path", "validate"))
    sub.add_parser("doctor", help="show detected platform and recovery options")
    return p


class App:
    def __init__(self, args: argparse.Namespace, ui: UI | None = None, runner: Runner | None = None,
                 paths: Paths | None = None, os_info: OSInfo | None = None, repo_root: Path = REPO_ROOT):
        self.args = args
        self.ui = ui or UI(assume_yes=args.yes)
        self.paths = paths or Paths.from_env()
        self.os = os_info or detect()
        self.repo_root = repo_root
        dry = args.dry_run or args.command == "plan"
        self.runner: Runner = runner or (DryRunRunner() if dry else SystemRunner())
        self.profile_path = args.profile or self.paths.profile

    # ---- helpers ----------------------------------------------------------------
    def load_profile(self) -> Profile:
        return Profile.load_or_default(self.profile_path)

    def context(self, profile: Profile, journal: Journal) -> Context:
        return Context(runner=self.runner, profile=profile, os=self.os, journal=journal,
                       files=FileChanger(journal, self.runner), ui=self.ui,
                       repo_root=self.repo_root, home=self.paths.home)

    def guard_platform(self) -> int | None:
        if self.os.tier is Tier.STUB:
            self.ui.error(f"{self.os.name}: ArCoN v3.0 ships interfaces only for this platform — nothing is applied.")
            return EXIT_UNSUPPORTED
        if self.os.tier is Tier.UNSUPPORTED:
            self.ui.error(f"{self.os.name} ({self.os.id or 'unknown'}) is not supported. Supported: Arch, Debian, Ubuntu, Fedora.")
            return EXIT_UNSUPPORTED
        if self.os.tier is Tier.EXPERIMENTAL:
            self.ui.warn(f"{self.os.name} is treated as {self.os.family.value} (experimental, not tested).")
        return None

    # ---- the run ----------------------------------------------------------------
    def run_profile(self, profile: Profile, resume_from: Journal | None = None) -> int:
        blocked = self.guard_platform()
        if blocked is not None:
            return blocked
        done: set[str] = set()
        if resume_from is not None:
            done = {k for k, v in resume_from.action_status().items() if v == DONE}
        journal = Journal.create(self.paths.runs, profile=str(profile.path), dry_run=self.runner.dry_run,
                                 os=self.os.id, resumed_from=resume_from.run_id if resume_from else None)
        setup_file_logging(journal.run_dir / "arcon.log", self.args.verbose)
        ctx = self.context(profile, journal)
        plan = build_plan(ctx, collect_actions(ctx), done)
        show_plan(ctx, plan)
        if not plan.pending:
            journal.write("run_end", summary={"nothing_to_do": True})
            return EXIT_OK
        if not self.runner.dry_run:
            if not self.ui.interactive and not self.args.yes:
                self.ui.error("non-interactive run: pass --yes to apply the plan above")
                journal.write("run_end", summary={"cancelled": "non-interactive without --yes"})
                return EXIT_USAGE
            if not self.ui.confirm("Apply these changes?", default=False):
                self.ui.info("Cancelled — nothing was changed.")
                journal.write("run_end", summary={"cancelled": True})
                return EXIT_OK
            provider = snapshot.detect(self.runner)
            if provider:
                ok = provider.create(self.runner, f"arcon {journal.run_id}")
                journal.write("snapshot", provider=provider.name, ok=ok)
                (self.ui.ok if ok else self.ui.warn)(f"{provider.name} snapshot {'created' if ok else 'FAILED'}")
            else:
                journal.write("snapshot", provider=None)
                self.ui.info("No filesystem snapshot tool configured — changed files are backed up individually.")
        execute(ctx, plan, keep_going=self.args.keep_going)
        return report(ctx, plan)

    # ---- commands ---------------------------------------------------------------
    def cmd_default(self) -> int:
        profile = run_wizard(self.load_profile(), self.ui)
        if not self.runner.dry_run:
            path = profile.save(self.profile_path)
            self.ui.info(f"Profile saved: {path}")
        return self.run_profile(profile)

    def cmd_plan(self) -> int:
        return self.run_profile(self.load_profile())

    cmd_apply = cmd_plan

    def cmd_wizard(self) -> int:
        profile = run_wizard(self.load_profile(), self.ui)
        path = profile.save(self.profile_path)
        self.ui.ok(f"Profile saved: {path}")
        return EXIT_OK

    def cmd_resume(self) -> int:
        try:
            previous = Journal.open(self.paths.runs)
        except FileNotFoundError:
            self.ui.error("No previous run to resume.")
            return EXIT_USAGE
        self.ui.info(f"Resuming run {previous.run_id}")
        return self.run_profile(self.load_profile(), resume_from=previous)

    def cmd_rollback(self) -> int:
        try:
            journal = Journal.open(self.paths.runs, self.args.run_id)
        except FileNotFoundError as exc:
            self.ui.error(str(exc))
            return EXIT_USAGE
        if not self.ui.confirm(f"Restore all files changed by run {journal.run_id}?", default=False):
            return EXIT_OK
        if self.runner.dry_run:
            for ev in journal.events():
                if ev["event"] == "file_backup":
                    self.ui.info(f"would restore {ev['path']}" if ev["existed"] else f"would remove {ev['path']}")
            return EXIT_OK
        for line in restore_files(journal, self.runner):
            self.ui.info(line)
        self.ui.warn("Installed packages and started services are NOT reverted automatically; "
                      f"see {journal.path} for the list.")
        return EXIT_OK

    def cmd_runs(self) -> int:
        rows = []
        for j in list_runs(self.paths.runs):
            status = j.action_status()
            rows.append((j.run_id, "finished" if j.finished() else "interrupted",
                         sum(v == DONE for v in status.values()), sum(v == "failed" for v in status.values())))
        if not rows:
            self.ui.info("No runs yet.")
        else:
            self.ui.table("Runs", ("Run", "State", "Done", "Failed"), rows)
        return EXIT_OK

    def cmd_profile(self) -> int:
        if self.args.what == "path":
            self.ui.console.print(str(self.profile_path), highlight=False, markup=False)
            return EXIT_OK
        profile = self.load_profile()
        if self.args.what == "validate":
            self.ui.ok(f"{self.profile_path}: valid")
            return EXIT_OK
        import tomlkit
        self.ui.console.print(tomlkit.dumps(profile.as_dict()), highlight=False, markup=False)
        return EXIT_OK

    def cmd_doctor(self) -> int:
        provider = snapshot.detect(self.runner) if self.os.is_linux else None
        self.ui.table("ArCoN doctor", ("Item", "Value"), [
            ("ArCoN", __version__),
            ("OS", f"{self.os.name} (id={self.os.id or '-'}, family={self.os.family.value})"),
            ("Support tier", self.os.tier.value),
            ("Profile", str(self.profile_path)),
            ("State dir", str(self.paths.state)),
            ("Snapshot tool", provider.name if provider else "none (per-file backups)"),
        ])
        return EXIT_OK


READ_ONLY_COMMANDS = {"doctor", "profile", "runs"}


def _is_root() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() == 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if _is_root() and os.environ.get("ARCON_ALLOW_ROOT") != "1" and args.command not in READ_ONLY_COMMANDS:
        print("arcon: do not run ArCoN as root — run it as your normal user; it asks for sudo "
              "only for the commands that need it (D15).", file=sys.stderr)
        return EXIT_USAGE
    app = App(args)
    try:
        handler = getattr(app, f"cmd_{args.command or 'default'}")
        return handler()
    except ProfileError as exc:
        app.ui.error(str(exc))
        return EXIT_USAGE
    except KeyboardInterrupt:
        app.ui.warn("Interrupted — continue later with: arcon resume")
        return 130
