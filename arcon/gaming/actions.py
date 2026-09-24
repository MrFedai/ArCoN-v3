"""`gaming` module (F19): Steam, GameMode, GPU drivers from DETECTED hardware
(v2.5 asked the user). Independent of GNOME/Hyprland (D12)."""

from __future__ import annotations

import os

from arcon.core.action import Action, Change, Context, Reversible, Risk, register
from arcon.core.common import WriteFile
from arcon.core.paths import current_user
from arcon.hardware.linux import Hardware, detect
from arcon.package.actions import request
from arcon.platform.detect import Family

GAMEMODE_INI = "[general]\ndesiredgov=performance\nigpu_desiredgov=performance\n"


def hardware(ctx: Context) -> Hardware:
    if "hardware" not in ctx.facts:
        ctx.facts["hardware"] = detect(ctx.runner)
    return ctx.facts["hardware"]


def gpu_packages(ctx: Context, hw: Hardware) -> tuple[list[str], list[str], list[str]]:
    """(catalog ids, raw package names, notes) for the detected GPUs."""
    ids, names, notes = [], [], []
    forced = ctx.profile.get("gaming", "gpu")
    vendors = [forced] if forced not in ("auto", "none") else ([] if forced == "none" else hw.gpu_vendors)
    arch = ctx.os.family is Family.ARCH
    if "nvidia" in vendors:
        nv = [g for g in hw.gpus if g.vendor == "nvidia"]
        if nv and not any(g.nvidia_open_capable for g in nv):
            notes.append("NVIDIA GPU older than Turing: the open kernel modules do not support it; install the "
                         "legacy driver manually (not automated)")
        elif arch:
            kernels = hw.kernels or ["linux"]
            if kernels == ["linux"]:
                ids.append("nvidia-open")
            else:  # any non-stock kernel needs DKMS + headers for every installed kernel
                ids.append("nvidia-open-dkms")
                names += [f"{k}-headers" for k in kernels]
            ids += ["nvidia-utils", "lib32-nvidia-utils", "nvidia-settings"]
            if hw.is_hybrid:
                names.append("nvidia-prime")
        elif ctx.os.id == "ubuntu":
            notes.append("Ubuntu: NVIDIA driver via `ubuntu-drivers install` (action below)")
        else:
            notes.append(f"{ctx.os.name}: NVIDIA drivers need a non-free repository (Debian non-free / RPM Fusion); "
                         "not enabled automatically — no repository changes without explicit intent")
    if "amd" in vendors:
        ids += ["mesa", "vulkan-radeon"] + (["lib32-mesa", "lib32-vulkan-radeon", "xf86-video-amdgpu"] if arch else [])
    if "intel" in vendors:
        ids += ["mesa", "vulkan-intel"] + (["lib32-mesa", "lib32-vulkan-intel"] if arch else [])
    return ids, names, notes


class UbuntuNvidia(Action):
    id, title, risk, reversible = "gaming.ubuntu-drivers", "Ubuntu: install the recommended NVIDIA driver", Risk.MEDIUM, Reversible.PARTIAL
    reboot = True

    def plan(self, ctx):
        if ctx.os.id != "ubuntu" or "nvidia" not in hardware(ctx).gpu_vendors:
            return []
        return [Change("package", "ubuntu-drivers install", "recommended driver")]

    def apply(self, ctx):
        ctx.runner.run(["ubuntu-drivers", "install"], sudo=True, interactive=True)


class GamemodeGroup(Action):
    id, title, risk, reversible = "gaming.gamemode-group", "Add the user to the gamemode group", Risk.LOW, Reversible.YES
    requires = ("packages.native",)

    def plan(self, ctx):
        group = ctx.runner.run(["getent", "group", "gamemode"], mutating=False, check=False)
        user = current_user()
        if not user or (group.ok and user in group.stdout.strip().split(":")[-1].split(",")):
            return []
        return [Change("setting", f"group gamemode += {user}", "created by the gamemode package")]

    def apply(self, ctx):
        ctx.runner.run(["usermod", "-aG", "gamemode", current_user()], sudo=True)


@register("gaming", "Gaming", order=50)
def build(ctx: Context):
    hw = hardware(ctx)
    ids, names, notes = gpu_packages(ctx, hw)
    request(ctx, ids=["steam", "gamemode", "vulkan-tools", "mangohud", *(["lib32-gamemode", "lib32-mangohud"]
                      if ctx.os.family is Family.ARCH else []), *ids], names=names)
    for note in notes:
        ctx.ui.warn(f"gaming: {note}")
    ini = WriteFile("gaming.gamemode-ini", "GameMode configuration (~/.config/gamemode.ini)",
                    ctx.home / ".config" / "gamemode.ini", lambda c: GAMEMODE_INI)
    # v2.5 wrote ~/.config/gamemode/gamemode.ini, which GameMode never reads (D-08)
    actions = [ini, GamemodeGroup(), UbuntuNvidia()]
    if any(i.startswith("nvidia") for i in ids):
        actions[0].reboot = True
    return actions
