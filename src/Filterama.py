#!/usr/bin/env python3

import glob
import logging
import os
import sys

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QApplication

from filterama_common import resource_path, setup_logging
from filterama_view import FilterPlotWindow


logger = logging.getLogger(__name__)


def log_resource_selftest():
    filter_dir = resource_path("Resources/Filter")
    filter_count = len(glob.glob(os.path.join(filter_dir, "*.csv"))) if os.path.isdir(filter_dir) else 0
    fits_path = resource_path("Resources/FilterFITs/SASP_data.fits")

    logger.info(
        "Resource self-check: filter_dir=%s (exists=%s, csv=%d), fits=%s (exists=%s)",
        filter_dir,
        os.path.isdir(filter_dir),
        filter_count,
        fits_path,
        os.path.isfile(fits_path),
    )


def plot_spectra():
    QCoreApplication.setApplicationName("Filterama")
    app = QApplication(sys.argv)
    if hasattr(app, "setApplicationDisplayName"):
        app.setApplicationDisplayName("Filterama")
    app.setApplicationName("Filterama")

    window = FilterPlotWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    setup_logging()
    log_resource_selftest()
    plot_spectra()
