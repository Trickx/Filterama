import sys
from setuptools import setup


def read_requirements(path="requirements.txt"):
    with open(path, "r", encoding="utf-8") as handle:
        lines = [line.strip() for line in handle if line.strip() and not line.strip().startswith("#")]
    return lines


APP = ["src/Filterama.py"]
OPTIONS = {
    "argv_emulation": True,
    "resources": ["Resources", "Filterama.icns"],
    "iconfile": "Filterama.icns",
    "packages": ["numpy", "pandas", "matplotlib", "scipy", "astropy", "PyQt6", "pyckles"],
    "includes": ["matplotlib.backends.backend_qt5agg"],
    "plist": {
        "CFBundleName": "Filterama",
        "CFBundleDisplayName": "Filterama",
        "CFBundleIdentifier": "com.filterama.app",
        "CFBundleVersion": "0.1",
        "CFBundleShortVersionString": "0.1",
        "NSHumanReadableCopyright": "All rights reserved.",
        "CFBundleIconFile": "Filterama",
    },
}

setup_kwargs = {
    "name": "Filterama",
    "app": APP,
    "options": {"py2app": OPTIONS},
}

if "py2app" not in sys.argv:
    setup_kwargs["install_requires"] = read_requirements()

setup(**setup_kwargs)
