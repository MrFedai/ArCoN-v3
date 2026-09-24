import os
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
GOLDEN = REPO / "tests" / "golden"
sys.path.insert(0, str(REPO / "tests" / "helpers"))
sys.path.insert(0, str(REPO / "tests" / "characterization"))

TEST_USER = "arcontest"


def pytest_configure(config):
    config.addinivalue_line("markers", "characterization: runs ArCoN v2.5 setup.sh against recording mocks")
    config.addinivalue_line("markers", "dconf: loads files into a real, throw-away dconf database")


@pytest.fixture
def needs_root_namespace():
    if os.geteuid() != 0 or not shutil.which("unshare"):
        pytest.skip("Arch scenarios need root + unshare (container only)")


@pytest.fixture
def dconf_session(tmp_path):
    """Run commands against a private dconf database; returns a callable(cmd:str, stdin_file=None)."""
    import subprocess

    if not (shutil.which("dconf") and shutil.which("dbus-run-session")):
        pytest.skip("dconf / dbus-run-session not installed")
    env = dict(os.environ, HOME=str(tmp_path), XDG_CONFIG_HOME=str(tmp_path / ".config"),
               XDG_RUNTIME_DIR=str(tmp_path))

    def run(script: str) -> str:
        proc = subprocess.run(["dbus-run-session", "--", "sh", "-c", script],
                              env=env, capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0, proc.stderr
        return proc.stdout

    return run
