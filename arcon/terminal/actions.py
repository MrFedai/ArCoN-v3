"""`terminal` (F24) and `shell` (F25) modules.

No `curl | sh` (S-03, D24): Oh-My-Zsh and plugins are cloned from pinned commits,
Starship comes from the distro package, Kitty themes via kitty's own `themes`
kitten, Alacritty themes are imported (alacritty.toml is never overwritten)."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path

from arcon.core.action import Action, Change, Context, Reversible, Risk, register
from arcon.core.common import WriteFile, read_text
from arcon.core.paths import current_user
from arcon.package.actions import request

# pinned 2026-09-24 (git ls-remote HEAD); update deliberately
PINS = {
    "ohmyzsh": ("https://github.com/ohmyzsh/ohmyzsh.git", "74965c96098134b192f00084f966b4b02438a739"),
    "zsh-autosuggestions": ("https://github.com/zsh-users/zsh-autosuggestions.git", "85919cd1ffa7d2d5412f6d3fe437ebdbeeec4fc5"),
    "zsh-syntax-highlighting": ("https://github.com/zsh-users/zsh-syntax-highlighting.git", "0bfcb582e71d3abe604ce67bc0fe5a21f377507e"),
    "powerlevel10k": ("https://github.com/romkatv/powerlevel10k.git", "d05a1b00f9a61f9578bf9dc19b8451942dde8734"),
}
ALACRITTY_THEME_URL = "https://raw.githubusercontent.com/alacritty/alacritty-theme/master/themes/{}.toml"
KITTY_THEMES = {"dracula": "Dracula", "nord": "Nord", "gruvbox_dark": "Gruvbox Dark", "tokyo_night": "Tokyo Night"}


def pinned_clone(ctx: Context, name: str, dest: Path) -> None:
    url, commit = PINS[name]
    r = ctx.runner
    if not ctx.dry_run:
        dest.parent.mkdir(parents=True, exist_ok=True)
    r.run(["git", "init", "-q", str(dest)])
    r.run(["git", "-C", str(dest), "fetch", "-q", "--depth", "1", url, commit], timeout=300)
    r.run(["git", "-C", str(dest), "checkout", "-q", "FETCH_HEAD"])
    ctx.journal.write("git_clone", repo=url, commit=commit, path=str(dest))


# ---- terminal -----------------------------------------------------------------------

class KittyTheme(Action):
    id, title, risk, reversible = "terminal.kitty-theme", "Kitty theme (kitty +kitten themes)", Risk.LOW, Reversible.YES
    requires = ("packages.native",)

    def plan(self, ctx):
        theme = ctx.profile.get("terminal", "theme")
        if ctx.profile.get("terminal", "emulator") != "kitty" or not theme:
            return []
        current = read_text(ctx.home / ".config" / "kitty" / "current-theme.conf") or ""
        if KITTY_THEMES[theme] in current:
            return []
        return [Change("file", "~/.config/kitty/current-theme.conf", KITTY_THEMES[theme])]

    def apply(self, ctx):
        base = ctx.home / ".config" / "kitty"
        for f in ("kitty.conf", "current-theme.conf"):   # the kitten edits these: back them up first
            ctx.files.backup_only(base / f)
        ctx.runner.run(["kitty", "+kitten", "themes", "--reload-in=none", KITTY_THEMES[ctx.profile.get("terminal", "theme")]])


class AlacrittyTheme(Action):
    id, title, risk, reversible = "terminal.alacritty-theme", "Alacritty theme (imported, config kept)", Risk.LOW, Reversible.YES

    def _paths(self, ctx):
        base = ctx.home / ".config" / "alacritty"
        return base / "alacritty.toml", base / "themes" / f"{ctx.profile.get('terminal', 'theme')}.toml"

    def plan(self, ctx):
        theme = ctx.profile.get("terminal", "theme")
        if ctx.profile.get("terminal", "emulator") != "alacritty" or not theme:
            return []
        conf, theme_file = self._paths(ctx)
        changes = []
        if not theme_file.exists():
            changes.append(Change("file", str(theme_file), ALACRITTY_THEME_URL.format(theme)))
        if str(theme_file) not in (read_text(conf) or "") and f"themes/{theme}.toml" not in (read_text(conf) or ""):
            changes.append(Change("file", str(conf), "add general.import (backup kept)"))
        return changes

    def apply(self, ctx):
        conf, theme_file = self._paths(ctx)
        url = ALACRITTY_THEME_URL.format(ctx.profile.get("terminal", "theme"))
        body = ctx.runner.run(["curl", "-fsSL", "--max-time", "30", url], mutating=False).stdout  # -f: no 404 page as config
        ctx.files.write(theme_file, body.encode())
        text = read_text(conf) or ""
        line = f'import = ["{theme_file}"]\n'
        if "[general]" in text:
            new = re.sub(r"^\[general\]\s*$", "[general]\n" + line.rstrip(), text, count=1, flags=re.M)
        else:
            new = "[general]\n" + line + "\n" + text
        ctx.files.write(conf, new.encode())


# ---- shell ----------------------------------------------------------------------------

def _zshrc_edit(text: str, theme: str) -> str:
    theme_line = f'ZSH_THEME="{theme}"'
    plugins_line = "plugins=(git zsh-autosuggestions zsh-syntax-highlighting)"
    text = re.sub(r"^ZSH_THEME=.*$", theme_line, text, flags=re.M) if re.search(r"^ZSH_THEME=", text, re.M) \
        else theme_line + "\n" + text
    text = re.sub(r"^plugins=\(.*?\)$", plugins_line, text, flags=re.M | re.S) if re.search(r"^plugins=\(", text, re.M) \
        else text + plugins_line + "\n"
    return text


class OhMyZsh(Action):
    id, title, risk, reversible = "shell.ohmyzsh", "Oh-My-Zsh + plugins (pinned git commits)", Risk.LOW, Reversible.YES
    requires = ("packages.native",)

    def _targets(self, ctx):
        omz = ctx.home / ".oh-my-zsh"
        custom = omz / "custom"
        t = {"ohmyzsh": omz, "zsh-autosuggestions": custom / "plugins" / "zsh-autosuggestions",
             "zsh-syntax-highlighting": custom / "plugins" / "zsh-syntax-highlighting"}
        if ctx.profile.get("shell", "zsh_theme") == "powerlevel10k":
            t["powerlevel10k"] = custom / "themes" / "powerlevel10k"
        return t

    def plan(self, ctx):
        return [Change("command", f"git clone {PINS[n][0]}@{PINS[n][1][:10]}", str(p))
                for n, p in self._targets(ctx).items() if not p.exists()]

    def apply(self, ctx):
        for name, path in self._targets(ctx).items():
            if not path.exists():
                pinned_clone(ctx, name, path)


class Zshrc(WriteFile):
    reversible = Reversible.YES

    def __init__(self):
        super().__init__("shell.zshrc", "~/.zshrc: theme + plugins (only these two lines are edited)",
                         Path("~/.zshrc"), self._render)

    @staticmethod
    def _render(ctx):
        theme = ctx.profile.get("shell", "zsh_theme")
        theme = "powerlevel10k/powerlevel10k" if theme == "powerlevel10k" else theme
        current = read_text(ctx.home / ".zshrc")
        if current is None:
            template = read_text(ctx.home / ".oh-my-zsh" / "templates" / "zshrc.zsh-template")
            current = template or 'export ZSH="$HOME/.oh-my-zsh"\nsource $ZSH/oh-my-zsh.sh\n'
        return _zshrc_edit(current, theme)

    def plan(self, ctx):
        self.path = ctx.home / ".zshrc"
        return super().plan(ctx)


class ShellInitLine(WriteFile):
    """Append `starship init` to ~/.bashrc or fish config (idempotent)."""

    def __init__(self, shell: str):
        rel = ".config/fish/config.fish" if shell == "fish" else ".bashrc"
        line = "starship init fish | source" if shell == "fish" else 'eval "$(starship init bash)"'
        self.rel, self.line = rel, line
        super().__init__(f"shell.{shell}-starship", f"Starship prompt in ~/{rel}", Path("~") / rel, self._render)

    def _render(self, ctx):
        text = read_text(ctx.home / self.rel) or ""
        if self.line in text:
            return text
        return text + ("" if text.endswith("\n") or not text else "\n") + self.line + "\n"

    def plan(self, ctx):
        self.path = ctx.home / self.rel
        return super().plan(ctx)


class StarshipPreset(Action):
    id, title, risk, reversible = "shell.starship-preset", "Starship preset (~/.config/starship.toml)", Risk.LOW, Reversible.YES
    requires = ("packages.native",)

    def plan(self, ctx):
        preset = ctx.profile.get("shell", "starship_preset")
        if not preset or ctx.profile.get("shell", "name") not in ("fish", "bash"):
            return []
        return [Change("file", "~/.config/starship.toml", f"preset {preset} (backup kept)")]

    def apply(self, ctx):
        preset = ctx.profile.get("shell", "starship_preset")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "starship.toml"
            ctx.runner.run(["starship", "preset", preset, "-o", str(out)], mutating=False)
            ctx.files.write(ctx.home / ".config" / "starship.toml", out.read_bytes())


class ChangeShell(Action):
    id, risk, reversible = "shell.chsh", Risk.LOW, Reversible.PARTIAL   # previous shell journaled; `chsh` to revert
    requires = ("packages.native",)

    @property
    def title(self):
        return "Make it the login shell (chsh)"

    @staticmethod
    def login_shell(ctx) -> str:
        entry = ctx.runner.run(["getent", "passwd", current_user()], mutating=False, check=False).stdout.strip()
        return entry.split(":")[-1] if entry else os.environ.get("SHELL", "")

    def plan(self, ctx):
        name = ctx.profile.get("shell", "name")
        if name == "none" or os.path.basename(self.login_shell(ctx)) == name:
            return []
        return [Change("setting", f"login shell -> {name}", "chsh")]

    def apply(self, ctx):
        name = ctx.profile.get("shell", "name")
        path = shutil.which(name) or f"/usr/bin/{name}"
        shells = read_text(Path("/etc/shells")) or ""
        if path not in shells.split() and not ctx.dry_run:
            raise RuntimeError(f"{path} is not listed in /etc/shells")
        ctx.journal.write("login_shell", user=current_user(), previous=self.login_shell(ctx), new=path)
        ctx.runner.run(["chsh", "-s", path, current_user()], sudo=True)


@register("terminal", "Terminal", order=70)
def build_terminal(ctx: Context):
    emulator = ctx.profile.get("terminal", "emulator")
    if emulator != "none":
        request(ctx, ids=[emulator])
    return [KittyTheme(), AlacrittyTheme()]


@register("shell", "Shell", order=75)
def build_shell(ctx: Context):
    name = ctx.profile.get("shell", "name")
    if name == "none":
        return []
    request(ctx, ids=["font-jetbrains-nerd", name] + (["starship"] if name in ("fish", "bash") else []))
    if name == "zsh":
        return [OhMyZsh(), Zshrc(), ChangeShell()]
    return [ShellInitLine(name), StarshipPreset(), ChangeShell()]
