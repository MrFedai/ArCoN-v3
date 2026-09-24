"""Console output and questions (rich). Input is injectable so the wizard and
the confirmation flow are testable without a terminal."""

from __future__ import annotations

import sys
from typing import Callable, Sequence

from rich.console import Console
from rich.table import Table

InputFn = Callable[[str], str]


class UI:
    def __init__(self, console: Console | None = None, input_fn: InputFn | None = None,
                 assume_yes: bool = False, interactive: bool | None = None):
        self.console = console or Console()
        self._input = input_fn or (lambda prompt: self.console.input(prompt))
        self.assume_yes = assume_yes
        self.interactive = sys.stdin.isatty() if interactive is None else interactive

    # ---- output ---------------------------------------------------------------
    def info(self, msg: str) -> None:
        self.console.print(msg)

    def ok(self, msg: str) -> None:
        self.console.print(f"[green]✓[/green] {msg}")

    def warn(self, msg: str) -> None:
        self.console.print(f"[yellow]![/yellow] {msg}")

    def error(self, msg: str) -> None:
        self.console.print(f"[red]✗[/red] {msg}")

    def heading(self, msg: str) -> None:
        self.console.rule(f"[bold]{msg}")

    def table(self, title: str, columns: Sequence[str], rows: Sequence[Sequence[str]]) -> None:
        t = Table(title=title, show_lines=False)
        for c in columns:
            t.add_column(c)
        for r in rows:
            t.add_row(*[str(x) for x in r])
        self.console.print(t)

    # ---- questions ------------------------------------------------------------
    def confirm(self, question: str, default: bool = False) -> bool:
        if self.assume_yes:
            return True
        if not self.interactive:
            return default
        suffix = "[Y/n]" if default else "[y/N]"
        while True:
            answer = self._input(f"{question} {suffix} ").strip().lower()
            if not answer:
                return default
            if answer in ("y", "yes"):
                return True
            if answer in ("n", "no"):
                return False
            self.warn("please answer y or n")

    def choose(self, question: str, choices: Sequence[str], default: str) -> str:
        if self.assume_yes or not self.interactive:
            return default
        self.console.print(question)
        for i, c in enumerate(choices, start=1):
            mark = " (default)" if c == default else ""
            self.console.print(f"  {i}) {c}{mark}")
        while True:
            answer = self._input("> ").strip()
            if not answer:
                return default
            if answer.isdigit() and 1 <= int(answer) <= len(choices):
                return choices[int(answer) - 1]
            if answer in choices:
                return answer
            self.warn(f"choose 1-{len(choices)}")

    def typed_confirm(self, question: str, word: str) -> bool:
        """High-risk confirmation: the user must type `word` (never auto-yes)."""
        if not self.interactive:
            return False
        return self._input(f"{question} Type {word} to confirm: ").strip() == word
