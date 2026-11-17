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
        # The template intentionally carries its own .claude/dw_core so a copied
        # project is self-contained without a pip install. The wheel therefore
        # contains both the installed package and the template copy; a future
        # packaging cleanup can move the template to a single top-level data dir.
        copytree(template, Path(self.build_lib) / "dw_core" / "data" / "template",
                 dirs_exist_ok=True, ignore=ignore_patterns("__pycache__", "*.pyc", "*.bak-*"))


setup(cmdclass={"build_py": BuildPy})
