"""Include the generated standalone installer files in the wheel."""
from pathlib import Path
from shutil import copytree, ignore_patterns

from setuptools import setup
from setuptools.command.build_py import build_py


class BuildPy(build_py):
    def run(self):
        super().run()
        template = Path(__file__).resolve().parent / "template"
        if not (template / ".claude" / "settings.json").is_file():
            raise RuntimeError("generated template missing; run python scripts/build.py")
        copytree(template, Path(self.build_lib) / "dw_core" / "data" / "template",
                 dirs_exist_ok=True, ignore=ignore_patterns("__pycache__", "*.pyc", "*.bak-*"))


setup(cmdclass={"build_py": BuildPy})
