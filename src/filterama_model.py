import glob
import os
import re

import numpy as np
import pandas as pd

from filterama_common import (
    fits,
    logger,
    load_csv_spectra,
    parse_structured_filter_csv,
    pyckles,
)


class FilteramaModel:
    """Model layer: data loading, lookup and numeric helpers."""

    def __init__(self, resource_path, sensor_fits_path):
        self.resource_path = resource_path
        self.sensor_fits_path = sensor_fits_path
        self.pickles_library = None
        self.sensor_fits_curves = None
        self.sensor_fits_sets = None

    def load_filter_spectra(self):
        return sorted(load_csv_spectra(), key=lambda item: item[0].lower())

    def check_resources(self):
        issues = []
        required_dirs = [
            "Resources/Filter",
            "Resources/WhiteReferences",
            "Resources/SensorFilters",
            "Resources/SensorQEs",
        ]

        for relative_dir in required_dirs:
            abs_dir = self.resource_path(relative_dir)
            if not os.path.isdir(abs_dir):
                issues.append(f"Missing directory: {relative_dir}")

        filter_csvs = glob.glob(self.resource_path("Resources/Filter/*.csv"))
        if not filter_csvs:
            issues.append("No filter CSV files found in Resources/Filter")

        sensor_csvs = glob.glob(self.resource_path("Resources/SensorFilters/*.csv"))
        if not sensor_csvs:
            issues.append("No camera sensor CSV files found in Resources/SensorFilters")

        white_ref_csvs = glob.glob(self.resource_path("Resources/WhiteReferences/*.csv"))
        if not white_ref_csvs and pyckles is None:
            issues.append("No local WhiteReference CSV found and pyckles is unavailable")

        sensor_qe_csvs = glob.glob(self.resource_path("Resources/SensorQEs/*.csv"))
        if not sensor_qe_csvs:
            issues.append("No Sensor QE CSV files found in Resources/SensorQEs")

        fits_path = self.resource_path(self.sensor_fits_path)
        if not os.path.isfile(fits_path):
            issues.append("SASP FITS file missing: Resources/FilterFITs/SASP_data.fits")

        return issues

    def get_white_reference_sources(self):
        folder = "Resources/WhiteReferences"
        abs_folder = self.resource_path(folder)
        sources = {}
        logger.info("Scanning white reference sources in %s", abs_folder)

        if os.path.isdir(abs_folder):
            files = sorted(f for f in os.listdir(abs_folder) if f.lower().endswith('.csv'))
            for file_name in files:
                ref_name = os.path.splitext(file_name)[0]
                csv_path = self.resource_path(os.path.join(folder, file_name))
                sources[ref_name] = ("csv", csv_path)
                logger.info("Registered white reference CSV source '%s' from %s", ref_name, csv_path)

        if pyckles is not None:
            try:
                library = self.get_pickles_library()
                if library is not None:
                    added = 0
                    for ref_name in library.available_spectra:
                        ref_name = str(ref_name).strip()
                        if not ref_name or ref_name in sources:
                            continue
                        sources[ref_name] = ("pyckles", ref_name)
                        added += 1
                    logger.info("Registered %d pyckles white reference sources", added)
            except Exception:
                logger.exception("Failed to register pyckles white reference sources")
        else:
            logger.warning("pyckles is not available; only local white reference CSV files can be used.")

        return sources

    def get_pickles_library(self):
        if pyckles is None:
            return None

        try:
            if self.pickles_library is None:
                logger.info("Initializing pyckles spectral library")
                self.pickles_library = pyckles.SpectralLibrary("pickles", return_style="array")
            return self.pickles_library
        except Exception:
            logger.exception("Failed to initialize pyckles spectral library")
            self.pickles_library = None
            return None

    def load_pyckles_white_reference(self, ref_name):
        library = self.get_pickles_library()
        if library is None:
            return None

        try:
            wl, t = library[ref_name]
            wl = pd.to_numeric(pd.Series(wl), errors="coerce")
            t = pd.to_numeric(pd.Series(t), errors="coerce")

            if len(wl) > 0 and wl.max() > 2000:
                wl = wl / 10.0

            df = pd.DataFrame({"wl": wl, "t": t}).dropna().sort_values("wl")
            if len(df) == 0:
                logger.warning("pyckles white reference '%s' returned no valid data", ref_name)
                return None
            return df
        except Exception:
            logger.exception("Failed to load pyckles white reference '%s'", ref_name)
            return None

    def get_sensor_sets(self):
        folder = "Resources/SensorFilters"
        abs_folder = self.resource_path(folder)
        logger.info("Scanning camera sensor CSV sources in %s", abs_folder)

        sensors = {}
        if os.path.isdir(abs_folder):
            files = sorted(f for f in os.listdir(abs_folder) if f.lower().endswith('.csv'))
            pattern = re.compile(r"^(.*?)-(R|G|B)$", re.IGNORECASE)

            for file_name in files:
                stem = os.path.splitext(file_name)[0]
                match = pattern.match(stem)
                if not match:
                    continue

                sensor_name = match.group(1).strip()
                channel = match.group(2).upper()
                file_path = self.resource_path(os.path.join(folder, file_name))
                sensors.setdefault(sensor_name, {})[channel] = file_path
                logger.info("Registered camera sensor '%s' channel '%s' from %s", sensor_name, channel, file_path)

        fits_sets = self.discover_sensor_fits_rgb_sets()
        if fits_sets:
            for sensor_name, channels in fits_sets.items():
                sensors[sensor_name] = channels
                logger.info("Registered camera sensor '%s' from SASP_data.fits", sensor_name)

        return sensors

    def discover_sensor_fits_rgb_sets(self):
        if self.sensor_fits_sets is not None:
            return self.sensor_fits_sets

        fits_sets = {}
        fits_path = self.resource_path(self.sensor_fits_path)
        if fits is None:
            logger.error("SASP_data.fits cannot be loaded because astropy is not available.")
            self.sensor_fits_sets = fits_sets
            return fits_sets

        if not os.path.isfile(fits_path):
            logger.error("SASP_data.fits cannot be loaded. File not found at %s.", fits_path)
            self.sensor_fits_sets = fits_sets
            return fits_sets

        try:
            with fits.open(fits_path, memmap=True) as hdul:
                channel_map = {}
                for hdu in hdul:
                    name = str(getattr(hdu, "name", "")).strip()
                    if not name:
                        continue

                    match = re.match(r"^(.+?)[_\-]([RGB])([_\-].+)?$", name, re.IGNORECASE)
                    if not match:
                        continue

                    base = match.group(1).strip()
                    channel = match.group(2).upper()
                    suffix = (match.group(3) or "").strip("_-").strip()
                    sensor_key = f"{base}-{suffix}" if suffix else base
                    sensor_key = sensor_key.strip()
                    if not sensor_key:
                        continue

                    channel_map.setdefault(sensor_key, {})[channel] = name

                for sensor_name, channels in channel_map.items():
                    if all(ch in channels for ch in ("R", "G", "B")):
                        fits_sets[sensor_name] = {
                            "R": self.sensor_fits_path,
                            "G": self.sensor_fits_path,
                            "B": self.sensor_fits_path,
                            "FITS_RGB": True,
                            "FITS_CHANNEL_HDUS": {
                                "R": channels["R"],
                                "G": channels["G"],
                                "B": channels["B"],
                            },
                        }

        except Exception:
            logger.exception("SASP_data.fits cannot be parsed from %s.", fits_path)
            self.sensor_fits_sets = {}
            return self.sensor_fits_sets

        if not fits_sets:
            logger.warning("No RGB sensor sets were discovered in SASP_data.fits at %s.", fits_path)

        self.sensor_fits_sets = fits_sets
        return fits_sets

    def load_sensor_fits_curves(self):
        if self.sensor_fits_curves is not None:
            return self.sensor_fits_curves

        curves = {}
        fits_path = self.resource_path(self.sensor_fits_path)
        if fits is None:
            logger.error("SASP_data.fits cannot be loaded because astropy is not available.")
            self.sensor_fits_curves = curves
            return curves

        if not os.path.isfile(fits_path):
            logger.error("SASP_data.fits cannot be loaded. File not found at %s.", fits_path)
            self.sensor_fits_curves = curves
            return curves

        try:
            with fits.open(fits_path, memmap=True) as hdul:
                for hdu in hdul:
                    hdu_name = str(getattr(hdu, "name", "")).strip()
                    if not hdu_name:
                        continue

                    data = hdu.data
                    if data is None:
                        continue

                    column_names = set(data.dtype.names or [])
                    if "WAVELENGTH" not in column_names:
                        continue

                    y_column = None
                    for candidate in ("THROUGHPUT", "FLUX", "TRANSMISSION"):
                        if candidate in column_names:
                            y_column = candidate
                            break

                    if y_column is None:
                        continue

                    wl = pd.to_numeric(pd.Series(np.asarray(data["WAVELENGTH"]).astype(np.float64, copy=False)), errors="coerce")
                    t = pd.to_numeric(pd.Series(np.asarray(data[y_column]).astype(np.float64, copy=False)), errors="coerce")
                    df = pd.DataFrame({"wl": wl, "t": t}).dropna().sort_values("wl")
                    if len(df) == 0:
                        continue

                    if df["wl"].max() > 2000:
                        df["wl"] = df["wl"] / 10.0
                    if df["t"].max() <= 1.5:
                        df["t"] = df["t"] * 100.0

                    curves[hdu_name] = df
                    logger.info("Loaded FITS sensor curve '%s' from %s (%d points)", hdu_name, fits_path, len(df))
        except Exception:
            logger.exception("SASP_data.fits cannot be loaded from %s.", fits_path)
            curves = {}

        if not curves:
            logger.error("SASP_data.fits could be read but no valid sensor curves were loaded from %s.", fits_path)

        self.sensor_fits_curves = curves
        return curves

    def get_sensor_fits_channel_df(self, channels, channel):
        curves = self.load_sensor_fits_curves()
        fits_channel_hdus = channels.get("FITS_CHANNEL_HDUS", {})
        hdu_name = fits_channel_hdus.get(channel)
        if not hdu_name:
            return None

        df = curves.get(hdu_name)
        if df is not None and len(df) > 0:
            return df
        return None

    def get_sensor_qes(self):
        folder = "Resources/SensorQEs"
        abs_folder = self.resource_path(folder)
        logger.info("Scanning sensor QE CSV sources in %s", abs_folder)

        if not os.path.isdir(abs_folder):
            return {}

        qes = {}
        files = sorted(f for f in os.listdir(abs_folder) if f.lower().endswith('.csv'))
        for file_name in files:
            qe_name = os.path.splitext(file_name)[0]
            csv_path = self.resource_path(os.path.join(folder, file_name))
            qes[qe_name] = csv_path
            logger.info("Registered sensor QE CSV source '%s' from %s", qe_name, csv_path)

        return qes

    def multiply_curve_with_qe(self, curve_df, qe_df):
        if curve_df is None or len(curve_df) == 0 or qe_df is None or len(qe_df) == 0:
            return curve_df

        plot_df = curve_df.copy()
        qe_factor = np.interp(
            plot_df["wl"].to_numpy(dtype=float),
            qe_df["wl"].to_numpy(dtype=float),
            qe_df["t"].to_numpy(dtype=float) / 100.0,
            left=0.0,
            right=0.0,
        )
        plot_df["t"] = plot_df["t"].to_numpy(dtype=float) * qe_factor
        return plot_df

    def component_factor(self, wl, df):
        if df is None or len(df) == 0:
            return np.ones_like(wl, dtype=float)

        return np.interp(wl, df["wl"].to_numpy(), (df["t"].to_numpy() / 100.0), left=0.0, right=0.0)

    def sensor_channel_factor(self, wl, channel, selected_sensor, sensor_sets, fits_df_getter):
        if not selected_sensor or selected_sensor == "None":
            return np.ones_like(wl, dtype=float)

        channels = sensor_sets.get(selected_sensor, {})
        if "FITS_RGB" in channels:
            df = fits_df_getter(channels, channel)
        else:
            file_path = channels.get(channel)
            if not file_path:
                return np.ones_like(wl, dtype=float)
            _, df = parse_structured_filter_csv(file_path)

        if df is None or len(df) == 0:
            return np.ones_like(wl, dtype=float)

        return np.interp(wl, df["wl"].to_numpy(), (df["t"].to_numpy() / 100.0), left=0.0, right=0.0)

    def sensor_factor(self, wl, selected_sensor, sensor_sets, fits_df_getter):
        channel_factors = []
        for channel in ("R", "G", "B"):
            factor = self.sensor_channel_factor(wl, channel, selected_sensor, sensor_sets, fits_df_getter)
            channel_factors.append(factor)

        if not channel_factors:
            return np.ones_like(wl, dtype=float)

        return np.mean(channel_factors, axis=0)

    def selected_sensor_wavelength_grid(self, selected_sensor, sensor_sets, fits_df_getter):
        if not selected_sensor or selected_sensor == "None":
            return np.array([])

        channels = sensor_sets.get(selected_sensor, {})
        wl_values = []

        if "FITS_RGB" in channels:
            for channel in ("R", "G", "B"):
                df = fits_df_getter(channels, channel)
                if df is None or len(df) == 0:
                    continue
                wl_values.append(df["wl"].to_numpy(dtype=float))
        else:
            for channel in ("R", "G", "B"):
                file_path = channels.get(channel)
                if not file_path:
                    continue
                _, df = parse_structured_filter_csv(file_path)
                if df is None or len(df) == 0:
                    continue
                wl_values.append(df["wl"].to_numpy(dtype=float))

        if not wl_values:
            return np.array([])

        wl = np.unique(np.concatenate(wl_values))
        return wl[np.isfinite(wl)]
