"""`hyprland` module (F22, D12/D24): optional desktop with ArCoN's own config only.
Third-party theme installers are deferred to v3.1 (D24)."""

from __future__ import annotations

from arcon.core.action import Context, register
from arcon.dotfiles.manager import DOTFILES, DeployDotfile
from arcon.package import catalog as cat
from arcon.package.actions import request


@register("hyprland", "Hyprland", order=45)
def build(ctx: Context):
    request(ctx, ids=[e.id for e in cat.group("hyprland")])
    actions = [DeployDotfile(d) for d in DOTFILES if d.module == "hyprland"]
    for a in actions:
        a.requires = ("packages.native",)
    return actions
