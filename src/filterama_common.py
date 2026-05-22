import csv
import glob
import logging
import os
import sys

import numpy as np
import pandas as pd
from matplotlib.transforms import blended_transform_factory

try:
    from astropy.io import fits
except ImportError:
    fits = None

try:
    import pyckles
except ImportError:
    pyckles = None

logger = logging.getLogger(__name__)

SYSTEM_RESPONSE_COLOR = "#8a5a00"


class ColorFormatter(logging.Formatter):
    RESET = "\033[0m"
    WHITE = "\033[37m"
    RED = "\033[31m"

    def format(self, record):
        message = super().format(record)
        if record.levelno >= logging.WARNING:
            return f"{self.RED}{message}{self.RESET}"
        return f"{self.WHITE}{message}{self.RESET}"


def setup_logging():
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()

    handler = logging.StreamHandler()
    handler.setFormatter(ColorFormatter("%(levelname)s: %(message)s"))
    root_logger.addHandler(handler)


def log_pyckles_install_instructions():
    logger.error("pyckles is not installed. White references from pyckles will be unavailable.")
    logger.info("Install instructions for a new system:")
    logger.info("1) Create/activate a virtual environment")
    logger.info("2) Install package: python -m pip install pyckles")
    logger.info("3) Optional: add pyckles to requirements.txt and run: python -m pip install -r requirements.txt")
    logger.info("4) Restart this application after installation")


def resource_path(relative_path):
    if getattr(sys, "frozen", False):
        if hasattr(sys, "_MEIPASS"):
            return os.path.join(getattr(sys, "_MEIPASS"), relative_path)

        bundle_dir = os.path.dirname(sys.executable)
        resource_dir = os.path.normpath(os.path.join(bundle_dir, "..", "Resources"))
        normalized = relative_path.replace("\\", "/")
        bundled_relative = normalized.split("Resources/", 1)[1] if normalized.startswith("Resources/") else normalized

        direct_candidate = os.path.join(resource_dir, normalized)
        bundled_candidate = os.path.join(resource_dir, bundled_relative)

        if glob.has_magic(normalized):
            direct_base = os.path.dirname(direct_candidate)
            bundled_base = os.path.dirname(bundled_candidate)
            if os.path.isdir(direct_base):
                return direct_candidate
            if os.path.isdir(bundled_base):
                return bundled_candidate
            return bundled_candidate

        if os.path.exists(direct_candidate):
            return direct_candidate
        return bundled_candidate

    src_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.normpath(os.path.join(src_dir, ".."))

    for base_dir in (project_dir, src_dir):
        candidate = os.path.join(base_dir, relative_path)
        if os.path.exists(candidate):
            return candidate

    # Default to project root for glob patterns and missing files.
    return os.path.join(project_dir, relative_path)


def annotate_lines(ax):
    lines = [
        (393.4, "Ca K"),
        (396.8, "Ca H"),
        (486.1, "Hβ"),
        (500.7, "OIII"),
        (517.0, "Mg"),
        (589.3, "Na D"),
        (656.3, "Hα"),
        (672.0, "SII"),
    ]

    transform = blended_transform_factory(ax.transData, ax.transAxes)
    x_offsets = [-2.4, 2.4, -2.0, 2.0, -2.2, 2.2, -2.0, 2.0]

    for idx, (wl, label) in enumerate(lines):
        ax.axvline(wl, ymin=0.06, ymax=0.14, color="black", alpha=0.55, linewidth=1)
        ax.text(
            wl + x_offsets[idx % len(x_offsets)],
            0.012,
            label,
            transform=transform,
            rotation=90,
            fontsize=8,
            ha="center",
            va="bottom",
            color="black",
            alpha=0.85,
        )


def add_spectral_background(ax):
    uv_pastel = (0.90, 0.93, 1.00)
    ir_pastel = (1.00, 0.93, 0.88)

    def wavelength_to_rgb(wl_nm):
        if wl_nm < 380 or wl_nm > 750:
            return (1.0, 1.0, 1.0)

        if wl_nm < 440:
            r = -(wl_nm - 440) / (440 - 380)
            g = 0.0
            b = 1.0
        elif wl_nm < 490:
            r = 0.0
            g = (wl_nm - 440) / (490 - 440)
            b = 1.0
        elif wl_nm < 510:
            r = 0.0
            g = 1.0
            b = -(wl_nm - 510) / (510 - 490)
        elif wl_nm < 580:
            r = (wl_nm - 510) / (580 - 510)
            g = 1.0
            b = 0.0
        elif wl_nm < 645:
            r = 1.0
            g = -(wl_nm - 645) / (645 - 580)
            b = 0.0
        else:
            r = 1.0
            g = 0.0
            b = 0.0

        if wl_nm < 420:
            factor = 0.35 + 0.65 * (wl_nm - 380) / (420 - 380)
        elif wl_nm <= 700:
            factor = 1.0
        else:
            factor = 0.35 + 0.65 * (750 - wl_nm) / (750 - 700)

        gamma = 0.8
        r = (r * factor) ** gamma if r > 0 else 0.0
        g = (g * factor) ** gamma if g > 0 else 0.0
        b = (b * factor) ** gamma if b > 0 else 0.0
        return (r, g, b)

    width = 2200
    x = np.linspace(300, 1100, width)
    gradient = np.ones((2, width, 3))

    for i, wl in enumerate(x):
        if wl < 380:
            gradient[:, i, :] = uv_pastel
        elif wl > 750:
            gradient[:, i, :] = ir_pastel
        else:
            gradient[:, i, :] = wavelength_to_rgb(wl)

    ax.imshow(
        gradient,
        extent=[300, 1100, 0, 100],
        aspect="auto",
        origin="lower",
        alpha=0.20,
        zorder=0,
    )


def add_spectral_regions(ax):
    ax.axvline(380, linestyle="--", color="gray", alpha=0.4)
    ax.axvline(750, linestyle="--", color="gray", alpha=0.4)

    ax.text(330, 102, "UV", color="#b38bff", fontsize=11)
    ax.text(520, 102, "Visible Range", color="#1f4e8c", fontsize=11)
    ax.text(900, 102, "Near IR", color="#ffb347", fontsize=11)


def parse_structured_filter_csv(file_path):
    with open(file_path, newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        rows = [row for row in reader if row]

    if not rows:
        return None, None

    if len(rows[0]) < 2 or rows[0][0].strip().lower() != "type":
        return None, None

    data = {}
    for row in rows:
        if len(row) >= 2:
            data[row[0].strip().lower()] = row[1].strip()

    if "wavelength" not in data or "transmission" not in data:
        return None, None

    wl_vals = [v.strip() for v in data["wavelength"].split(",") if v.strip()]
    t_vals = [v.strip() for v in data["transmission"].split(",") if v.strip()]

    n = min(len(wl_vals), len(t_vals))
    if n == 0:
        return None, None

    wl = pd.to_numeric(pd.Series(wl_vals[:n]), errors="coerce")
    t = pd.to_numeric(pd.Series(t_vals[:n]), errors="coerce")
    df = pd.DataFrame({"wl": wl, "t": t}).dropna().sort_values("wl")

    if len(df) == 0:
        return None, None

    if df["t"].max() <= 1.5:
        df["t"] = df["t"] * 100.0

    name = data.get("name", "").strip().strip('"')
    if not name:
        name = os.path.splitext(os.path.basename(file_path))[0]

    return name, df


def load_csv_spectra():
    files = glob.glob(resource_path("Resources/Filter/*.csv"))
    spectra = []

    if not files:
        logger.warning("No CSV files found in Resources/Filter.")

    print("\n📂 CSV Dateien:")

    for file_path in files:
        print(" -", file_path)
        logger.info("Loading filter CSV: %s", file_path)

        try:
            name, parsed_df = parse_structured_filter_csv(file_path)

            if parsed_df is not None:
                logger.info("Loaded structured filter curve '%s' from %s (%d points)", name, file_path, len(parsed_df))
                spectra.append((name, parsed_df))
                continue

            df = pd.read_csv(file_path, sep=";", decimal=",", header=None, engine="python")
            if df.shape[1] < 2:
                df = pd.read_csv(file_path, sep=None, engine="python", header=None)

            df = df.iloc[:, :2]
            df.columns = ["wl", "t"]
            df["wl"] = pd.to_numeric(df["wl"].astype(str).str.replace(",", "."), errors="coerce")
            df["t"] = pd.to_numeric(df["t"].astype(str).str.replace(",", "."), errors="coerce")
            df = df.dropna().sort_values("wl")

            if len(df) == 0:
                continue

            name = os.path.basename(file_path).replace(".csv", "").replace("_", " ")
            logger.info("Loaded legacy filter curve '%s' from %s (%d points)", name, file_path, len(df))
            spectra.append((name, df))

        except Exception:
            logger.exception("Failed to load filter CSV from %s", file_path)

    if not spectra:
        logger.warning("No valid filter curves could be loaded from CSV files.")

    return spectra
