from PyQt6.QtCore import Qt


class FilteramaController:
    """Controller layer: event orchestration between view and model."""

    def __init__(self, view):
        self.view = view

    def on_filter_changed(self, item):
        idx = self.view.list_widget.row(item)
        visible = item.checkState() == Qt.CheckState.Checked
        self.view.filter_lines[idx].set_visible(visible)
        self.view.update_system_response_plot()
        self.view._update_dynamic_legend()
        self.view.canvas.draw_idle()

    def on_white_reference_changed(self, _index):
        self.view.update_white_reference_plot()
        self.view.update_system_response_plot()
        self.view._update_dynamic_legend()
        self.view.canvas.draw_idle()

    def on_sensor_changed(self, _index):
        self.view.update_sensor_plot()
        self.view.update_system_response_plot()
        self.view._update_dynamic_legend()
        self.view.canvas.draw_idle()

    def on_sensor_qe_changed(self, _index):
        self.view.update_sensor_plot()
        self.view.update_sensor_qe_plot()
        self.view.update_system_response_plot()
        self.view._update_dynamic_legend()
        self.view.canvas.draw_idle()
