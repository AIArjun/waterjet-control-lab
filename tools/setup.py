"""Local setup without admin access or changes to system security settings."""

import os
import subprocess
import sys
import venv
from pathlib import Path


def main():
    if sys.version_info < (3, 11):  # noqa: UP036 - this bootstrap can run before the project's install
        raise SystemExit("Install Python 3.11 or newer from https://www.python.org/downloads/windows/")
    project = Path(__file__).resolve().parents[1]
    environment = Path(os.environ.get("USERPROFILE", str(Path.home()))) / ".venvs" / "waterjet-lab"
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.is_file():
        venv.create(environment, with_pip=True)
    subprocess.run(
        [str(python), "-m", "pip", "install", "-r", str(project / "requirements-dev.txt")], check=True
    )
    subprocess.run([str(python), "-m", "pip", "install", "-e", f"{project}[desktop,dev]"], check=True)
    print("Ready. Use Start-Web.cmd or Start-Qt.cmd. No hardware or API keys are required.")


if __name__ == "__main__":
    main()
