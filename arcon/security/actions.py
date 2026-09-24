"""`security` module (F26, F28–F30) and `blackarch` module (F21). Everything is
opt-in (D23). SSH changes go into a drop-in validated with `sshd -t`; USBGuard
and SSH password-login disable need a typed confirmation."""

from __future__ import annotations

import hashlib
import re
import tempfile
from pathlib import Path

from arcon.core.action import Action, Change, Context, Reversible, Risk, register
from arcon.core.common import EnableService, WriteFile, read_text
from arcon.package.actions import request
from arcon.platform.detect import Family

SYSCTL = """# ArCoN security hardening (v2.5 set, CLAUDE.md D23)
kernel.dmesg_restrict = 1
kernel.kptr_restrict = 2
kernel.sysrq = 0
kernel.unprivileged_bpf_disabled = 1
fs.protected_fifos = 2
fs.protected_regular = 2
net.ipv4.conf.all.log_martians = 1
net.ipv4.conf.all.send_redirects = 0
net.ipv4.conf.default.accept_redirects = 0
net.ipv4.conf.default.accept_source_route = 0
net.ipv6.conf.all.accept_redirects = 0
"""
SSHD_DIR = Path("/etc/ssh/sshd_config.d")
SSHD_DROPIN = SSHD_DIR / "10-arcon.conf"


def _on(ctx: Context, key: str) -> bool:
    return bool(ctx.profile.get("security", key))


class Firewall(Action):
    id, title, risk, reversible = "security.firewall", "Firewall: deny incoming, allow outgoing", Risk.MEDIUM, Reversible.YES
    requires = ("packages.native",)

    def plan(self, ctx):
        if not _on(ctx, "firewall"):
            return []
        if ctx.os.family is Family.FEDORA:
            state = ctx.runner.run(["firewall-cmd", "--state"], sudo=True, mutating=False, check=False)
            return [] if state.ok else [Change("service", "firewalld", "enable --now (Fedora default firewall)")]
        status = ctx.runner.run(["ufw", "status"], sudo=True, mutating=False, check=False).stdout
        # v3.0 lesson: "inactive" contains "active" — match the whole word
        if re.search(r"^Status:\s+active\b", status, re.M):
            return []
        return [Change("service", "ufw", "default deny incoming / allow outgoing; SSH kept if sshd runs")]

    def apply(self, ctx):
        r = ctx.runner
        if ctx.os.family is Family.FEDORA:
            r.run(["systemctl", "enable", "--now", "firewalld"], sudo=True)
            return
        r.run(["ufw", "default", "deny", "incoming"], sudo=True)
        r.run(["ufw", "default", "allow", "outgoing"], sudo=True)
        sshd = r.run(["systemctl", "is-active", "sshd"], mutating=False, check=False).stdout.strip() == "active" or \
            r.run(["systemctl", "is-active", "ssh"], mutating=False, check=False).stdout.strip() == "active"
        if sshd:  # v2.5 enabled ufw without allowing SSH first: remote lock-out (S-06)
            if not r.run(["ufw", "allow", "OpenSSH"], sudo=True, check=False).ok:
                r.run(["ufw", "allow", "22/tcp"], sudo=True)
        r.run(["ufw", "--force", "enable"], sudo=True)
        r.run(["systemctl", "enable", "ufw"], sudo=True)


class SshDropIn(Action):
    id, title, risk, reversible = "security.ssh", "SSH hardening (drop-in, validated with sshd -t)", Risk.HIGH, Reversible.YES

    def content(self, ctx) -> str:
        lines = ["# ArCoN SSH hardening (CLAUDE.md D23)"]
        if _on(ctx, "ssh_root_login"):
            lines.append("PermitRootLogin no")
        if _on(ctx, "ssh_disable_password") and ctx.facts.get("ssh_password_confirmed"):
            lines.append("PasswordAuthentication no")
            lines.append("KbdInteractiveAuthentication no")
        return "\n".join(lines) + "\n"

    def plan(self, ctx):
        if not (_on(ctx, "ssh_root_login") or _on(ctx, "ssh_disable_password")):
            return []
        if not Path("/etc/ssh/sshd_config").exists():
            ctx.ui.warn("security: OpenSSH server not installed — SSH hardening skipped")
            return []
        main = read_text(Path("/etc/ssh/sshd_config")) or ""
        if not re.search(r"^\s*Include\s+/etc/ssh/sshd_config\.d/\*\.conf", main, re.M):
            ctx.ui.warn("security: sshd_config has no `Include /etc/ssh/sshd_config.d/*.conf` — "
                        "ArCoN does not edit sshd_config itself; SSH hardening skipped")
            return []
        if _on(ctx, "ssh_disable_password") and "ssh_password_confirmed" not in ctx.facts:
            ctx.facts["ssh_password_confirmed"] = ctx.ui.typed_confirm(
                "Disable SSH password login? Make sure your public key is in ~/.ssh/authorized_keys on this machine.",
                "KEYONLY")
        if read_text(SSHD_DROPIN) == self.content(ctx):
            return []
        return [Change("file", str(SSHD_DROPIN), self.content(ctx).strip().replace("\n", "; "))]

    def apply(self, ctx):
        ctx.files.write(SSHD_DROPIN, self.content(ctx).encode(), root=True, mode=0o644)
        if ctx.dry_run:
            return
        test = ctx.runner.run(["sshd", "-t"], sudo=True, check=False)
        if not test.ok:  # invalid config: take the drop-in out again before anything reloads sshd
            ctx.runner.run(["rm", "-f", str(SSHD_DROPIN)], sudo=True)
            raise RuntimeError(f"sshd -t rejected the configuration: {test.stderr.strip()}")
        for unit in ("sshd", "ssh"):
            if ctx.runner.run(["systemctl", "is-active", unit], mutating=False, check=False).stdout.strip() == "active":
                ctx.runner.run(["systemctl", "reload", unit], sudo=True)


class UsbGuard(Action):
    id, title, risk, reversible = "security.usbguard", "USBGuard: allow current devices, block new ones", Risk.HIGH, Reversible.YES
    requires = ("packages.native",)

    def plan(self, ctx):
        if not _on(ctx, "usbguard"):
            return []
        active = ctx.runner.run(["systemctl", "is-active", "usbguard"], mutating=False, check=False).stdout.strip()
        if active == "active":
            return []
        if "usbguard_confirmed" not in ctx.facts:
            ctx.facts["usbguard_confirmed"] = ctx.ui.typed_confirm(
                "USBGuard blocks every USB device plugged in later (keyboards too) until you allow it.", "USBGUARD")
        if not ctx.facts["usbguard_confirmed"]:
            ctx.ui.warn("security: USBGuard not confirmed — skipped")
            return []
        return [Change("file", "/etc/usbguard/rules.conf", "policy from currently connected devices"),
                Change("service", "usbguard", "enable --now")]

    def apply(self, ctx):
        policy = ctx.runner.run(["usbguard", "generate-policy"], sudo=True, mutating=False).stdout
        if not policy.strip():
            raise RuntimeError("usbguard generate-policy returned nothing — refusing to enable an empty policy")
        ctx.files.write(Path("/etc/usbguard/rules.conf"), policy.encode(), root=True, mode=0o600)
        ctx.runner.run(["systemctl", "enable", "--now", "usbguard"], sudo=True)


class Scans(Action):
    id, title, risk, reversible = "security.scans", "Security scans (reports in the run directory)", Risk.LOW, Reversible.YES
    requires = ("packages.native",)

    def plan(self, ctx):
        return [Change("command", "scan", "arch-audit/debsecan, Lynis, rkhunter, ClamAV (home)")] if _on(ctx, "scans") else []

    def apply(self, ctx):
        out = ctx.journal.run_dir / "scans"
        out.mkdir(exist_ok=True)
        home = str(ctx.home)
        jobs = {"lynis.txt": (["lynis", "audit", "system", "--quick"], True),
                "rkhunter.txt": (["rkhunter", "--check", "--sk", "--rwo"], True),
                "clamav.txt": (["clamscan", "-r", "-i", home], False)}
        jobs["vulns.txt"] = (["arch-audit"], False) if ctx.os.family is Family.ARCH else (["debsecan"], False)
        for name, (argv, sudo) in jobs.items():
            res = ctx.runner.run(argv, sudo=sudo, check=False, timeout=7200)
            if res.executed:
                (out / name).write_text(res.stdout + res.stderr)
        ctx.ui.info(f"scan reports: {out}")


def _sysctl(ctx):
    ctx.runner.run(["sysctl", "--system"], sudo=True)


@register("security", "Security", order=80)
def build(ctx: Context):
    ids = []
    if _on(ctx, "tools") or _on(ctx, "scans"):
        ids += ["clamav", "rkhunter", "lynis", "firejail", "nethogs",
                "arch-audit" if ctx.os.family is Family.ARCH else "debsecan"]
        if ctx.os.family is not Family.ARCH:
            ids.append("clamav-freshclam")
    if _on(ctx, "firewall") and ctx.os.family is not Family.FEDORA:
        ids.append("ufw")
    if _on(ctx, "opensnitch"):
        ids += ["opensnitch"] + (["python3-opensnitch-ui"] if ctx.os.family is Family.DEBIAN else [])
    if _on(ctx, "usbguard"):
        ids.append("usbguard")
    request(ctx, ids=ids)
    actions = []
    if _on(ctx, "tools"):
        actions.append(EnableService("security.freshclam", "clamav-freshclam", "ClamAV signature updates"))
    if _on(ctx, "sysctl"):
        actions.append(WriteFile("security.sysctl", "Kernel/network hardening (sysctl)",
                                 Path("/etc/sysctl.d/99-arcon-security.conf"), lambda c: SYSCTL, root=True,
                                 mode=0o644, risk=Risk.MEDIUM, after=_sysctl))
    actions += [Firewall(), SshDropIn(), UsbGuard()]
    if _on(ctx, "opensnitch"):
        actions.append(EnableService("security.opensnitch", "opensnitchd", "OpenSnitch application firewall"))
    actions.append(Scans())
    return actions


# ---- BlackArch (Arch only) --------------------------------------------------------------

STRAP_URL = "https://blackarch.org/strap.sh"
CORE_GROUPS = ["blackarch-webapp", "blackarch-networking", "blackarch-wireless"]


def blackarch_enabled() -> bool:
    return re.search(r"^\[blackarch\]", read_text(Path("/etc/pacman.conf")) or "", re.M) is not None


class BlackArchRepo(Action):
    id, title, risk, reversible = "blackarch.repo", "BlackArch repository (strap.sh, third-party)", Risk.HIGH, Reversible.ONE_WAY

    def plan(self, ctx):
        if ctx.profile.get("blackarch", "install") == "remove" or blackarch_enabled():
            return []
        return [Change("repo", "blackarch", f"runs {STRAP_URL} as root after showing its SHA-256")]

    def apply(self, ctx):
        with tempfile.TemporaryDirectory(prefix="arcon-blackarch-") as tmp:
            script = Path(tmp) / "strap.sh"
            body = ctx.runner.run(["curl", "-fsSL", "--max-time", "60", STRAP_URL], mutating=False).stdout
            script.write_text(body)
            digest = hashlib.sha256(body.encode()).hexdigest()
            ctx.journal.write("third_party_script", url=STRAP_URL, sha256=digest)
            if not ctx.ui.typed_confirm(f"strap.sh SHA-256 {digest}. Compare it with blackarch.org/downloads "
                                        "before continuing.", "BLACKARCH"):
                raise RuntimeError("BlackArch strap.sh not confirmed")
            ctx.runner.run(["sh", str(script)], sudo=True, interactive=True)


class BlackArchTools(Action):
    id, risk, reversible = "blackarch.tools", Risk.MEDIUM, Reversible.PARTIAL
    requires = ("blackarch.repo",)
    title = "BlackArch tools"

    def plan(self, ctx):
        mode = ctx.profile.get("blackarch", "install")
        if mode == "remove":
            return []
        groups = ["blackarch"] if mode == "full" else CORE_GROUPS
        return [Change("package", g, "BlackArch group (no --overwrite)") for g in groups]

    def apply(self, ctx):
        groups = ["blackarch"] if ctx.profile.get("blackarch", "install") == "full" else CORE_GROUPS
        # v2.5 used --overwrite '*' (could replace files of other packages, S-05): not any more
        ctx.runner.run(["pacman", "-S", "--needed", "--noconfirm", *groups], sudo=True, interactive=True)


class BlackArchRemove(Action):
    id, title, risk, reversible = "blackarch.remove", "Remove the BlackArch repository", Risk.MEDIUM, Reversible.YES

    def plan(self, ctx):
        if ctx.profile.get("blackarch", "install") != "remove" or not blackarch_enabled():
            return []
        return [Change("repo", "blackarch", "remove from /etc/pacman.conf (backup kept); installed tools stay")]

    def apply(self, ctx):
        conf = read_text(Path("/etc/pacman.conf")) or ""
        new = re.sub(r"^\[blackarch\]\n(?:(?!\[).*\n)*", "", conf, flags=re.M)
        ctx.files.write(Path("/etc/pacman.conf"), new.encode(), root=True, mode=0o644)
        ctx.runner.run(["pacman", "-Syu", "--noconfirm"], sudo=True, interactive=True)


@register("blackarch", "BlackArch", order=85)
def build_blackarch(ctx: Context):
    if ctx.os.family is not Family.ARCH:
        ctx.ui.warn("blackarch: Arch only — use the `cyber` package group on this distro")
        return []
    return [BlackArchRepo(), BlackArchTools(), BlackArchRemove()]
