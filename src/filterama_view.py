import os
import sys

import numpy as np
import pandas as pd
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.transforms import blended_transform_factory

from filterama_common import (
    SYSTEM_RESPONSE_COLOR,
    add_spectral_background,
    add_spectral_regions,
    annotate_lines,
    log_pyckles_install_instructions,
    logger,
    parse_structured_filter_csv,
    pyckles,
    resource_path,
)
from filterama_controller import FilteramaController
from filterama_model import FilteramaModel


class FilterPlotWindow(QMainWindow):
    VISIBLE_MIN_NM = 380.0
    VISIBLE_MAX_NM = 750.0
    INTEGRAL_START_NM = 750.0
    SYSTEM_RESPONSE_INTEGRAL_THRESHOLD = 500.0
    SENSOR_FITS_PATH = os.path.join("Resources", "FilterFITs", "SASP_data.fits")

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Filterama")
        self.resize(1320, 700)
        self.project_dir = os.path.dirname(os.path.abspath(__file__))
        self.model = FilteramaModel(resource_path, self.SENSOR_FITS_PATH)
        self.controller = FilteramaController(self)

        self._create_menu_bar()

        if pyckles is None:
            log_pyckles_install_instructions()

        self.resource_issues = self.check_resources()
        for issue in self.resource_issues:
            logger.warning(issue)

        self.spectra = self.model.load_filter_spectra()
        self.filter_names = [name for name, _ in self.spectra]
        self.filter_dfs = [df for _, df in self.spectra]

        central = QWidget()
        self.setCentralWidget(central)
        hbox = QHBoxLayout(central)

        left_vbox = QVBoxLayout()

        filter_group = QGroupBox("Filter")
        filter_vbox = QVBoxLayout()
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        for name in self.filter_names:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.list_widget.addItem(item)
        self.list_widget.setMaximumWidth(220)
        filter_vbox.addWidget(self.list_widget)
        filter_group.setLayout(filter_vbox)
        left_vbox.addWidget(filter_group)

        self.white_ref_sources = self.get_white_reference_sources()
        white_refs = sorted(self.white_ref_sources.keys(), key=str.lower)
        self.white_ref_combo = QComboBox()
        self.white_ref_combo.addItem("None")
        self.white_ref_combo.addItems(white_refs)
        self.white_ref_combo.setCurrentIndex(0)
        white_ref_group = QGroupBox("White Reference")
        white_ref_vbox = QVBoxLayout()
        white_ref_vbox.addWidget(self.white_ref_combo)
        white_ref_group.setLayout(white_ref_vbox)
        left_vbox.addWidget(white_ref_group)

        self.sensor_sets = self.get_sensor_sets()
        self._load_sensor_fits_curves()
        self.sensor_combo = QComboBox()
        self.sensor_combo.addItem("None")
        self.sensor_combo.addItems(sorted(self.sensor_sets.keys()))
        self.sensor_combo.setCurrentIndex(0)
        sensor_group = QGroupBox("Camera Sensor")
        sensor_vbox = QVBoxLayout()
        sensor_vbox.addWidget(self.sensor_combo)
        sensor_group.setLayout(sensor_vbox)
        left_vbox.addWidget(sensor_group)

        self.sensor_qes = self.get_sensor_qes()
        self.sensor_qe_combo = QComboBox()
        self.sensor_qe_combo.addItem("None")
        self.sensor_qe_combo.addItems(sorted(self.sensor_qes.keys()))
        self.sensor_qe_combo.setCurrentIndex(0)
        sensor_qe_group = QGroupBox("Sensor QE")
        sensor_qe_vbox = QVBoxLayout()
        sensor_qe_vbox.addWidget(self.sensor_qe_combo)
        sensor_qe_group.setLayout(sensor_qe_vbox)
        left_vbox.addWidget(sensor_qe_group)

        self.resource_label = QLabel("")
        self.resource_label.setWordWrap(True)
        self.resource_label.setStyleSheet("color: #8a6d1d; font-weight: 600;")
        if self.resource_issues:
            text = self._summarize_resource_issues(self.resource_issues)
            self.resource_label.setText(text)
            self.resource_label.setVisible(True)
        else:
            self.resource_label.setVisible(False)

        self.warning_label = QLabel("")
        self.warning_label.setWordWrap(True)
        self.warning_label.setStyleSheet("color: #b00020; font-weight: 600;")
        self.warning_label.setVisible(False)

        status_group = QGroupBox("Status")
        status_vbox = QVBoxLayout()
        status_vbox.addWidget(self.resource_label)
        status_vbox.addWidget(self.warning_label)
        status_group.setLayout(status_vbox)
        left_vbox.addWidget(status_group)

        left_vbox.addStretch(1)
        left_widget = QWidget()
        left_widget.setLayout(left_vbox)
        left_widget.setMaximumWidth(260)
        hbox.addWidget(left_widget)

        vbox = QVBoxLayout()
        hbox.addLayout(vbox)
        self.canvas = FigureCanvas(Figure(figsize=(9, 6), dpi=120))
        vbox.addWidget(self.canvas)
        self.ax = self.canvas.figure.subplots()
        self.ax_white = self.ax.twinx()
        self.canvas.figure.patch.set_facecolor("white")
        self.ax.set_facecolor("white")
        self.ax_white.set_facecolor("none")
        add_spectral_background(self.ax)

        self.filter_lines = []
        self.system_response_lines = []
        for name, df in zip(self.filter_names, self.filter_dfs):
            line, = self.ax.plot(df["wl"], df["t"], linewidth=1, linestyle="-", label=name, zorder=3)
            line.set_visible(False)
            self.filter_lines.append(line)

            sys_lines = {}
            for channel, linestyle in (("R", "-."), ("G", "--"), ("B", ":")):
                sys_line, = self.ax.plot(
                    [], [], color=SYSTEM_RESPONSE_COLOR, linewidth=1.1, linestyle=linestyle,
                    label=f"System Response {channel}", zorder=6
                )
                sys_line.set_visible(False)
                sys_lines[channel] = sys_line
            self.system_response_lines.append(sys_lines)

        self.system_response_fills = [{"R": None, "G": None, "B": None} for _ in self.system_response_lines]

        self.base_system_response_lines = {}
        for channel, linestyle in (("R", "-."), ("G", "--"), ("B", ":")):
            base_line, = self.ax.plot(
                [], [], color=SYSTEM_RESPONSE_COLOR, linewidth=1.4, linestyle=linestyle,
                label=f"System Response {channel}", zorder=6
            )
            base_line.set_visible(False)
            self.base_system_response_lines[channel] = base_line
        self.base_system_response_fills = {"R": None, "G": None, "B": None}

        integral_transform = blended_transform_factory(self.ax.transData, self.ax.transAxes)
        self.integral_info_text = self.ax.text(
            900.0, 1.06, "", transform=integral_transform, fontsize=9,
            ha="center", va="bottom", color="#8a5a00", fontweight="bold", zorder=8, clip_on=False
        )
        self.integral_info_text.set_visible(False)

        self.white_ref_line, = self.ax.plot(
            [], [], color="#ff8c00", linewidth=1, linestyle="--", label="White Reference", zorder=5
        )
        self.white_ref_flux_line, = self.ax_white.plot(
            [], [], color="#ff8c00", linewidth=1, linestyle="--", label="White Reference Flux", zorder=5
        )
        self.update_white_reference_plot()

        self.sensor_lines = {
            "R": self.ax.plot([], [], color="#ff4d4d", linewidth=1, linestyle=":", zorder=5, label="Camera Sensor R")[0],
            "G": self.ax.plot([], [], color="#44cc66", linewidth=1, linestyle=":", zorder=5, label="Camera Sensor G")[0],
            "B": self.ax.plot([], [], color="#4da3ff", linewidth=1, linestyle=":", zorder=5, label="Camera Sensor B")[0],
        }
        self.update_sensor_plot()

        self.sensor_qe_line, = self.ax.plot(
            [], [], color="#6f42c1", linewidth=1, linestyle="-.", label="Sensor QE", zorder=5
        )
        self.update_sensor_qe_plot()
        self.update_system_response_plot()

        annotate_lines(self.ax)
        add_spectral_regions(self.ax)

        self.ax.set_xlim(300, 1100)
        self.ax.set_ylim(0, 100)
        self.ax.set_xlabel("Wavelength (nm)")
        self.ax.set_ylabel("Transmission (%)")
        self.ax_white.set_ylabel("Flux (erg / (Angstrom s cm2))")
        self.ax_white.tick_params(axis="y", colors="#ff8c00")
        self.ax_white.yaxis.label.set_color("#ff8c00")
        self.ax_white.spines["right"].set_color("#ff8c00")
        self.ax_white.set_visible(False)

        self.ax.grid(True, alpha=0.12)
        self._update_dynamic_legend()

        self.canvas.figure.tight_layout(rect=[0, 0, 0.93, 0.96])
        self.canvas.draw()

        self.list_widget.itemChanged.connect(self.controller.on_filter_changed)
        self.white_ref_combo.currentIndexChanged.connect(self.controller.on_white_reference_changed)
        self.sensor_combo.currentIndexChanged.connect(self.controller.on_sensor_changed)
        self.sensor_qe_combo.currentIndexChanged.connect(self.controller.on_sensor_qe_changed)

    def _update_dynamic_legend(self):
        legend_entries = {}
        for axis in (self.ax, self.ax_white):
            for line in axis.get_lines():
                if not line.get_visible():
                    continue
                label = line.get_label()
                if not label or label.startswith("_"):
                    continue
                if label not in legend_entries:
                    legend_entries[label] = line

        if legend_entries:
            self.ax.legend(
                handles=list(legend_entries.values()), labels=list(legend_entries.keys()),
                loc="upper right", frameon=True, framealpha=0.9, fontsize=8,
            )
        else:
            legend = self.ax.get_legend()
            if legend is not None:
                legend.remove()

    def _create_menu_bar(self):
        menu_bar = self.menuBar()
        if sys.platform == "darwin":
            menu_bar.setNativeMenuBar(False)
        menu_bar.setStyleSheet(
            "QMenuBar { background-color: #f2f2f2; color: #1a1a1a; }"
            "QMenuBar::item { padding: 4px 10px; }"
            "QMenuBar::item:selected { background-color: #d9d9d9; }"
        )

        help_menu = menu_bar.addMenu("Help")
        about_action = QAction("About Filterama", self)
        about_action.triggered.connect(self._show_about_dialog)
        help_menu.addAction(about_action)

    def _show_about_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("About Filterama")
        dialog.setModal(True)

        layout = QVBoxLayout(dialog)
        icon_label = QLabel()
        pixmap = QPixmap(self._resource_path("Resources/Images/Filterama.png"))
        if not pixmap.isNull():
            icon_label.setPixmap(
                pixmap.scaled(128, 128, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            )
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(icon_label)

        title_label = QLabel("<h2>Filterama</h2>")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        text = (
            "<p><b>Version:</b> v0.1</p>"
            "<p>Filterama is a spectral filter visualization and analysis tool.</p>"
            "<p>Credits: Setiastro Suite Pro, PixInsight and Siril.</p>"
        )
        info_label = QLabel(text)
        info_label.setWordWrap(True)
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(info_label)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(dialog.accept)
        layout.addWidget(button_box)

        dialog.exec()

    def _resource_path(self, relative_path):
        return resource_path(relative_path)

    def check_resources(self):
        return self.model.check_resources()

    def _summarize_resource_issues(self, issues):
        short_labels = []
        seen_labels = set()

        for issue in issues:
            if issue.startswith("Missing directory: Resources/"):
                label = issue.split("Resources/", 1)[1]
            elif "Resources/Filter" in issue:
                label = "Filter CSVs"
            elif "Resources/SensorFilters" in issue:
                label = "Sensor CSVs"
            elif "Resources/WhiteReferences" in issue or "WhiteReference" in issue:
                label = "White refs"
            elif "Resources/SensorQEs" in issue or "Sensor QE" in issue:
                label = "Sensor QE"
            elif "SASP FITS" in issue:
                label = "SASP FITS"
            else:
                label = issue

            if label not in seen_labels:
                short_labels.append(label)
                seen_labels.add(label)

        return "Resource check: not found - " + ", ".join(short_labels)

    def _status_ir_warning_text(self):
        return "High near-IR response. Use an IR-cut filter for refractors."

    def get_white_reference_sources(self):
        return self.model.get_white_reference_sources()

    def _get_pickles_library(self):
        return self.model.get_pickles_library()

    def _load_pyckles_white_reference(self, ref_name):
        return self.model.load_pyckles_white_reference(ref_name)

    def _get_selected_white_ref_source(self):
        selected = self.white_ref_combo.currentText().strip()
        if not selected or selected == "None":
            return None, None
        return selected, self.white_ref_sources.get(selected)

    def _get_selected_white_ref_plot_df(self, log_events=True):
        selected, source = self._get_selected_white_ref_source()
        if not source:
            if log_events:
                logger.info("No white reference selected.")
            return None

        source_type, source_value = source
        if log_events:
            logger.info("White reference selected: %s (source=%s)", selected, source_type)

        if source_type == "csv":
            _, df = parse_structured_filter_csv(source_value)
            if log_events:
                if df is None or len(df) == 0:
                    logger.warning("White reference CSV found but could not be loaded: %s", source_value)
                else:
                    logger.info("White reference loaded from CSV: %s (%d points)", source_value, len(df))
            return df

        if source_type == "pyckles":
            df = self._load_pyckles_white_reference(source_value)
            if log_events:
                if df is None or len(df) == 0:
                    logger.warning("White reference pyckles source found but could not be loaded: %s", source_value)
                else:
                    logger.info("White reference loaded from pyckles: %s (%d points)", source_value, len(df))
            return df

        return None

    def _get_selected_white_ref_factor_df(self):
        df = self._get_selected_white_ref_plot_df(log_events=False)
        if df is None or len(df) == 0:
            return None

        _selected, source = self._get_selected_white_ref_source()
        if not source:
            return None

        source_type, _source_value = source
        if source_type != "pyckles":
            return df

        factor_df = df.copy()
        max_value = factor_df["t"].max()
        if pd.isna(max_value) or max_value <= 0:
            return None

        factor_df["t"] = factor_df["t"] / max_value * 100.0
        return factor_df

    def get_sensor_sets(self):
        return self.model.get_sensor_sets()

    def _discover_sensor_fits_rgb_sets(self):
        return self.model.discover_sensor_fits_rgb_sets()

    def _load_sensor_fits_curves(self):
        return self.model.load_sensor_fits_curves()

    def _get_sensor_fits_channel_df(self, channels, channel):
        return self.model.get_sensor_fits_channel_df(channels, channel)

    def get_sensor_qes(self):
        return self.model.get_sensor_qes()

    def update_white_reference_plot(self):
        df = self._get_selected_white_ref_plot_df()
        _selected, source = self._get_selected_white_ref_source()

        if df is None or len(df) == 0:
            self.white_ref_line.set_data([], [])
            self.white_ref_line.set_visible(False)
            self.white_ref_flux_line.set_data([], [])
            self.white_ref_flux_line.set_visible(False)
            self.ax_white.set_visible(False)
            return

        if source and source[0] == "pyckles":
            self.white_ref_line.set_data([], [])
            self.white_ref_line.set_visible(False)
            self.white_ref_flux_line.set_data(df["wl"], df["t"])
            self.white_ref_flux_line.set_visible(True)
            self.ax_white.set_visible(True)
            self.ax_white.relim()
            self.ax_white.autoscale_view()
            return

        self.white_ref_flux_line.set_data([], [])
        self.white_ref_flux_line.set_visible(False)
        self.ax_white.set_visible(False)
        self.white_ref_line.set_data(df["wl"], df["t"])
        self.white_ref_line.set_visible(True)

    def update_sensor_plot(self):
        selected = self.sensor_combo.currentText().strip()
        qe_df = self._get_selected_sensor_qe_df()

        if not selected or selected == "None":
            for line in self.sensor_lines.values():
                line.set_data([], [])
                line.set_visible(False)
            return

        channels = self.sensor_sets.get(selected, {})

        if "FITS_RGB" in channels:
            for channel, line in self.sensor_lines.items():
                df = self._get_sensor_fits_channel_df(channels, channel)
                if df is None or len(df) == 0:
                    line.set_data([], [])
                    line.set_visible(False)
                    continue

                plot_df = self._multiply_curve_with_qe(df, qe_df)
                line.set_data(plot_df["wl"], plot_df["t"])
                line.set_visible(True)
            return

        for channel, line in self.sensor_lines.items():
            file_path = channels.get(channel)
            if not file_path:
                line.set_data([], [])
                line.set_visible(False)
                continue

            _, df = parse_structured_filter_csv(file_path)
            if df is None or len(df) == 0:
                line.set_data([], [])
                line.set_visible(False)
                continue

            plot_df = self._multiply_curve_with_qe(df, qe_df)
            line.set_data(plot_df["wl"], plot_df["t"])
            line.set_visible(True)

    def _multiply_curve_with_qe(self, curve_df, qe_df):
        return self.model.multiply_curve_with_qe(curve_df, qe_df)

    def update_sensor_qe_plot(self):
        selected = self.sensor_qe_combo.currentText().strip()

        if not selected or selected == "None":
            self.sensor_qe_line.set_data([], [])
            self.sensor_qe_line.set_visible(False)
            return

        file_path = self.sensor_qes.get(selected)
        if not file_path:
            self.sensor_qe_line.set_data([], [])
            self.sensor_qe_line.set_visible(False)
            return

        _, df = parse_structured_filter_csv(file_path)
        if df is None or len(df) == 0:
            self.sensor_qe_line.set_data([], [])
            self.sensor_qe_line.set_visible(False)
            return

        self.sensor_qe_line.set_data(df["wl"], df["t"])
        self.sensor_qe_line.set_visible(True)

    def _get_selected_sensor_qe_df(self):
        selected = self.sensor_qe_combo.currentText().strip()
        if not selected or selected == "None":
            return None

        file_path = self.sensor_qes.get(selected)
        if not file_path:
            return None

        _, df = parse_structured_filter_csv(file_path)
        return df

    def _component_factor(self, wl, df):
        return self.model.component_factor(wl, df)

    def _sensor_channel_factor(self, wl, channel):
        selected = self.sensor_combo.currentText().strip()
        return self.model.sensor_channel_factor(wl, channel, selected, self.sensor_sets, self._get_sensor_fits_channel_df)

    def _sensor_factor(self, wl):
        selected = self.sensor_combo.currentText().strip()
        return self.model.sensor_factor(wl, selected, self.sensor_sets, self._get_sensor_fits_channel_df)

    def _get_selected_sensor_wavelength_grid(self):
        selected = self.sensor_combo.currentText().strip()
        return self.model.selected_sensor_wavelength_grid(selected, self.sensor_sets, self._get_sensor_fits_channel_df)

    def update_system_response_plot(self):
        if not hasattr(self, "integral_info_text"):
            integral_transform = blended_transform_factory(self.ax.transData, self.ax.transAxes)
            self.integral_info_text = self.ax.text(
                900.0, 1.06, "", transform=integral_transform, fontsize=9,
                ha="center", va="bottom", color="#8a5a00", fontweight="bold", zorder=8, clip_on=False,
            )
            self.integral_info_text.set_visible(False)

        for base_line in self.base_system_response_lines.values():
            base_line.set_data([], [])
            base_line.set_visible(False)

        for sys_lines in self.system_response_lines:
            for sys_line in sys_lines.values():
                sys_line.set_data([], [])
                sys_line.set_visible(False)

        try:
            for fill_dict in getattr(self, "system_response_fills", []):
                for ch, artist in list(fill_dict.items()):
                    if artist is not None:
                        try:
                            artist.remove()
                        except Exception:
                            pass
                        fill_dict[ch] = None
        except Exception:
            pass

        try:
            for ch, artist in list(getattr(self, "base_system_response_fills", {}).items()):
                if artist is not None:
                    try:
                        artist.remove()
                    except Exception:
                        pass
                    self.base_system_response_fills[ch] = None
        except Exception:
            pass

        white_df = self._get_selected_white_ref_factor_df()
        qe_df = self._get_selected_sensor_qe_df()
        visible_integrals = []

        selected_sensor = self.sensor_combo.currentText().strip()
        has_sensor = bool(selected_sensor and selected_sensor != "None")
        if not has_sensor:
            self.integral_info_text.set_visible(False)
            self.warning_label.setVisible(False)
            self.warning_label.setText("")
            return

        channel_fill_colors = {"R": "#8b0000", "G": "#8b0000", "B": "#8b0000"}

        for idx, (filter_df, filter_line, sys_lines) in enumerate(zip(self.filter_dfs, self.filter_lines, self.system_response_lines)):
            if not filter_line.get_visible():
                for channel, sys_line in sys_lines.items():
                    sys_line.set_data([], [])
                    sys_line.set_visible(False)
                    try:
                        existing = self.system_response_fills[idx].get(channel)
                        if existing is not None:
                            existing.remove()
                            self.system_response_fills[idx][channel] = None
                    except Exception:
                        pass
                continue

            wl = filter_df["wl"].to_numpy(dtype=float)
            filter_factor = filter_df["t"].to_numpy(dtype=float) / 100.0
            white_factor = self._component_factor(wl, white_df)
            qe_factor = self._component_factor(wl, qe_df)

            channel_integrals = []
            for channel, sys_line in sys_lines.items():
                sensor_factor = self._sensor_channel_factor(wl, channel)
                system_t = filter_factor * sensor_factor * white_factor * qe_factor * 100.0

                sys_line.set_data(wl, system_t)
                sys_line.set_visible(True)

                ir_mask = wl >= self.INTEGRAL_START_NM
                try:
                    existing = self.system_response_fills[idx].get(channel)
                    if existing is not None:
                        existing.remove()
                        self.system_response_fills[idx][channel] = None
                except Exception:
                    pass

                if np.count_nonzero(ir_mask) >= 2:
                    integral_value = float(np.trapezoid(system_t[ir_mask], wl[ir_mask]))
                    try:
                        fill = self.ax.fill_between(
                            wl, system_t, where=ir_mask, interpolate=True,
                            color=channel_fill_colors.get(channel, SYSTEM_RESPONSE_COLOR), alpha=0.20, zorder=4,
                        )
                        self.system_response_fills[idx][channel] = fill
                    except Exception:
                        pass
                else:
                    integral_value = 0.0

                channel_integrals.append(integral_value)

            visible_integrals.append((self.filter_names[idx], float(np.mean(channel_integrals))))

        if not visible_integrals:
            has_white = white_df is not None and len(white_df) > 0

            if has_white and has_sensor:
                wl = self._get_selected_sensor_wavelength_grid()
                if wl.size >= 2:
                    white_factor = self._component_factor(wl, white_df)
                    qe_factor = self._component_factor(wl, qe_df)
                    base_channel_integrals = []

                    for channel, base_line in self.base_system_response_lines.items():
                        sensor_factor = self._sensor_channel_factor(wl, channel)
                        system_t = sensor_factor * white_factor * qe_factor * 100.0

                        base_line.set_data(wl, system_t)
                        base_line.set_visible(True)
                        try:
                            existing = self.base_system_response_fills.get(channel)
                            if existing is not None:
                                existing.remove()
                                self.base_system_response_fills[channel] = None
                        except Exception:
                            pass

                        ir_mask = wl >= self.INTEGRAL_START_NM
                        if np.count_nonzero(ir_mask) >= 2:
                            integral_value = float(np.trapezoid(system_t[ir_mask], wl[ir_mask]))
                            try:
                                fill = self.ax.fill_between(
                                    wl, system_t, where=ir_mask, interpolate=True,
                                    color=channel_fill_colors.get(channel, SYSTEM_RESPONSE_COLOR), alpha=0.20, zorder=4,
                                )
                                self.base_system_response_fills[channel] = fill
                            except Exception:
                                pass
                        else:
                            integral_value = 0.0
                        base_channel_integrals.append(integral_value)

                    base_integral = float(np.mean(base_channel_integrals)) if base_channel_integrals else 0.0

                    self.integral_info_text.set_text(
                        f"Integrated System Response >= {self.INTEGRAL_START_NM:.0f} nm (no extra filter): {base_integral:.1f}"
                    )
                    self.integral_info_text.set_visible(True)

                    if base_integral > self.SYSTEM_RESPONSE_INTEGRAL_THRESHOLD:
                        self.warning_label.setText(self._status_ir_warning_text())
                        self.warning_label.setVisible(True)
                    else:
                        self.warning_label.setVisible(False)
                        self.warning_label.setText("")
                    return

            self.integral_info_text.set_visible(False)
            self.warning_label.setVisible(False)
            self.warning_label.setText("")
            return

        total_integral = sum(value for _, value in visible_integrals)
        self.integral_info_text.set_text(f"Integrated System Response >= {self.INTEGRAL_START_NM:.0f} nm: {total_integral:.1f}")
        self.integral_info_text.set_visible(True)

        exceeded = [(name, value) for name, value in visible_integrals if value > self.SYSTEM_RESPONSE_INTEGRAL_THRESHOLD]
        if exceeded:
            self.warning_label.setText(self._status_ir_warning_text())
            self.warning_label.setVisible(True)
        else:
            self.warning_label.setVisible(False)
            self.warning_label.setText("")

    def on_filter_changed(self, item):
        self.controller.on_filter_changed(item)

    def on_white_reference_changed(self, _index):
        self.controller.on_white_reference_changed(_index)

    def on_sensor_changed(self, _index):
        self.controller.on_sensor_changed(_index)

    def on_sensor_qe_changed(self, _index):
        self.controller.on_sensor_qe_changed(_index)
