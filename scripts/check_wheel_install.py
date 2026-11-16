"""Exercise the wheel from outside the source tree in an isolated venv."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path


def main() -> None:
    wheel = Path(sys.argv[1]).resolve()
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONUTF8"] = "1"
    with tempfile.TemporaryDirectory(prefix="dw-wheel-") as directory:
        project = Path(directory)
        venv.create(project / "venv", with_pip=True)
        bin_dir = project / "venv" / ("Scripts" if os.name == "nt" else "bin")
        suffix = ".exe" if os.name == "nt" else ""
        python = str(bin_dir / ("python" + suffix))
        dw = str(bin_dir / ("dw" + suffix))

        def run(*args):
            subprocess.run(args, cwd=project, env=env, check=True, timeout=120)

        run(python, "-m", "pip", "install", "--no-deps", str(wheel))
        run(dw, "init", "--target", ".", "--python", python, "--mcp")
        run(dw, "doctor", "--mode", "template")
        run(dw, "mcp", "--selftest")


if __name__ == "__main__":
    main()
