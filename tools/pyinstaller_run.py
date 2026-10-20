"""Run PyInstaller with the same tempfile workaround used for pip."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import uuid


def _mkdtemp(suffix=None, prefix=None, dir=None):
    base = dir or tempfile.gettempdir()
    name = (prefix or "") + "pytmp" + uuid.uuid4().hex[:12] + (suffix or "")
    path = os.path.join(base, name)
    os.makedirs(path, exist_ok=True)
    return path


tempfile.mkdtemp = _mkdtemp  # type: ignore[assignment]
tempfile.TemporaryDirectory.cleanup = lambda self: shutil.rmtree(self.name, ignore_errors=True)  # type: ignore[assignment]

from PyInstaller.__main__ import run  # noqa: E402

if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
