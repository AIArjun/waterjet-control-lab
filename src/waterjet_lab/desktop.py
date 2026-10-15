"""Native Qt Widgets HMI, using the same controller as the browser adapter."""

from __future__ import annotations

import argparse
import math
import os
import sys
from pathlib import Path

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from .core import Command, Fault, Simulator
from .scenarios import SCENARIOS, advance, scenario

STYLE = """
QMainWindow, QWidget#root { background:#f1f5f6; color:#173546; }
QWidget { font-family:'Segoe UI'; font-size:11px; }
QFrame#rail { background:#102c3d; border:0; }
QFrame#rail QLabel { color:#bed2dc; }
QFrame#rail QPushButton { background:transparent; border:0; color:#bed2dc; text-align:left; padding:13px 8px; }
QFrame#rail QPushButton:hover { background:#254658; }
QFrame#card { background:#ffffff; border:1px solid #dfe7ea; border-radius:7px; }
QLabel#muted { color:#8299a5; font-size:10px; }
QLabel#metric { font-family:Consolas; font-size:28px; color:#254c5c; }
QLabel#title { font-size:26px; font-weight:600; color:#15394b; }
QLabel#section { font-size:13px; font-weight:600; color:#254b5c; }
QLabel#notice { background:#e1eeeb; color:#39786e; border-left:3px solid #409d8e; padding:11px; }
QPushButton { background:white; border:1px solid #cadade; border-radius:4px; padding:9px; color:#486777; }
QPushButton:hover { background:#e7f1f1; }
QPushButton#primary { background:#008d8b; color:white; border:1px solid #008d8b; }
QPushButton#estop { background:#fff0eb; color:#ad493b; border:1px solid #dda89d; font-weight:600; padding:13px; }
QSlider::groove:horizontal {height:5px; background:#dce8eb; border-radius:2px; }
QSlider::handle:horizontal { background:#008d8b; width:13px; margin:-4px 0; border-radius:6px; }
QComboBox { background:#f0f6f6; color:#335c67; border:1px solid #d2e0e3; border-radius:4px; padding:7px; }
QCheckBox { color:#537583; padding:4px; }
"""


def label(text: str, name: str = "") -> QLabel:
    widget = QLabel(text)
    if name:
        widget.setObjectName(name)
    return widget


def card() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 16, 18, 16)
    layout.setSpacing(9)
    return frame, layout


def configure_application(app: QApplication) -> None:
    """Windows' offscreen plugin does not discover installed fonts itself."""
    app.setStyle("Fusion")
    if sys.platform == "win32" and not QFontDatabase.families():
        font_dir = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        for name in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf", "consola.ttf"):
            path = font_dir / name
            if path.is_file():
                QFontDatabase.addApplicationFont(str(path))


class SeaView(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(400, 260)
        self.sim = Simulator()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        painter.fillRect(self.rect(), QColor("#eaf2f3"))
        s = self.sim
        points = [(p["east_m"], p["north_m"]) for p in s.history]
        radius = max(45, *(max(abs(x), abs(y)) + 12 for x, y in points)) if points else 45
        scale, cx, cy = min(w, h) / (2 * radius), w / 2, h * 0.56
        grid = 20 * max(1, math.ceil(radius / 120))
        painter.setPen(QPen(QColor("#d8e7e9"), 0.7))
        for k in range(-math.ceil(w / scale / grid), math.ceil(w / scale / grid)):
            x = cx + k * grid * scale
            painter.drawLine(QPointF(x, 0), QPointF(x, h))
        for k in range(-math.ceil(h / scale / grid), math.ceil(h / scale / grid)):
            y = cy + k * grid * scale
            painter.drawLine(QPointF(0, y), QPointF(w, y))
        painter.fillRect(0, h - 35, int(w * 0.22), 35, QColor("#cadde1"))
        painter.fillRect(35, h - 85, 14, 85, QColor("#cadde1"))
        painter.fillRect(100, h - 65, 12, 65, QColor("#cadde1"))
        painter.setPen(QColor("#7c9ca9"))
        painter.setFont(QFont("Consolas", 9))
        painter.drawText(15, 23, f"E {s.vessel.east_m:.1f} m  /  N {s.vessel.north_m:.1f} m")
        painter.drawText(w - 27, 24, "N ↑")
        painter.drawText(15, h - 13, "VIRTUAL HARBOR")
        painter.setPen(QPen(QColor("#269d9d"), 2))
        path = QPainterPath()
        for i, (x, y) in enumerate(points):
            point = QPointF(cx + x * scale, cy - y * scale)
            path.moveTo(point) if i == 0 else path.lineTo(point)
        painter.drawPath(path)
        painter.save()
        painter.translate(cx + s.vessel.east_m * scale, cy - s.vessel.north_m * scale)
        painter.rotate(s.vessel.heading_deg)
        hull = QPainterPath(QPointF(0, -29))
        hull.cubicTo(9, -20, 13, -8, 13, 18)
        hull.lineTo(10, 25)
        hull.lineTo(-10, 25)
        hull.lineTo(-13, 18)
        hull.cubicTo(-13, -8, -9, -20, 0, -29)
        painter.setBrush(QColor("white"))
        painter.setPen(QPen(QColor("#245467"), 1.5))
        painter.drawPath(hull)
        painter.fillRect(-7, -5, 14, 15, QColor("#225164"))
        painter.fillRect(-5, -3, 10, 4, QColor("#7ebbc4"))
        for offset, thrust in [(-7, s.vessel.port_feedback), (7, s.vessel.starboard_feedback)]:
            painter.fillRect(offset - 2, 21, 4, 6, QColor("#139d96"))
            if s.mode == "RUNNING":
                painter.setPen(QPen(QColor("#31b1aa"), 3))
                painter.drawLine(QPointF(offset, 29), QPointF(offset, 29 + 30 * abs(thrust)))
        painter.restore()
        painter.end()


class Console(QMainWindow):
    def __init__(self):
        super().__init__()
        self.sim = Simulator()
        self.setWindowTitle("Waterjet Control Lab · Native Qt HMI · Simulation only")
        self.resize(1240, 1040)
        self.setMinimumSize(1050, 760)
        self.setStyleSheet(STYLE)
        root = QWidget()
        root.setObjectName("root")
        root.setMinimumHeight(1000)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(root)
        self.setCentralWidget(scroll)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        rail = QFrame()
        rail.setObjectName("rail")
        rail.setFixedWidth(200)
        side = QVBoxLayout(rail)
        side.setContentsMargins(20, 30, 20, 25)
        title = label("W ~\nWATERJET\nCONTROL LAB")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.DemiBold))
        side.addWidget(title)
        side.addSpacing(25)
        side.addWidget(label("VERIFICATION SCENARIOS", "muted"))
        for index, (key, name) in enumerate(SCENARIOS.items(), 1):
            button = QPushButton(f"{index:02}   {name.split(' · ')[0]}")
            button.clicked.connect(lambda checked=False, key=key: self.load_scenario(key))
            side.addWidget(button)
        side.addStretch()
        side.addWidget(
            label("NATIVE Qt / PySide6\n50 ms fixed scan\n\nSIMULATION ONLY\nNo hardware interface")
        )
        layout.addWidget(rail)
        body = QVBoxLayout()
        body.setContentsMargins(24, 24, 24, 20)
        layout.addLayout(body, 1)
        body.addWidget(label("ENGINEERING LAB   /   TWIN-JET PROPULSION", "muted"))
        body.addWidget(label("Vessel control console.", "title"))
        body.addWidget(label("Control · diagnostics · repeatable verification", "muted"))
        self.notice = label("Neutral → Arm → Run", "notice")
        self.notice.setWordWrap(True)
        body.addWidget(self.notice)
        metrics = QHBoxLayout()
        self.metrics = {}
        for key, heading in [
            ("speed", "VESSEL SPEED / kn"),
            ("heading", "HEADING / °"),
            ("pressure", "PRESSURE / bar"),
            ("temp", "OIL TEMP / °C"),
        ]:
            frame, box = card()
            box.addWidget(label(heading, "muted"))
            self.metrics[key] = label("0.0", "metric")
            box.addWidget(self.metrics[key])
            metrics.addWidget(frame)
        body.addLayout(metrics)
        center = QHBoxLayout()
        map_frame, map_box = card()
        map_box.addWidget(label("Manoeuvring view", "section"))
        self.sea = SeaView()
        map_box.addWidget(self.sea, 1)
        self.feedback = label("PORT 0% / STARBOARD 0%", "muted")
        map_box.addWidget(self.feedback)
        center.addWidget(map_frame, 3)
        controls, form = card()
        controls.setMinimumHeight(510)
        form.addWidget(label("Operator station", "section"))
        self.status = label("DISARMED")
        form.addWidget(self.status)
        self.control = QComboBox()
        self.control.addItems(["Manual", "Heading hold"])
        form.addWidget(self.control)
        self.sliders = {}
        self.slider_labels = {}
        for key, text, low, high in [
            ("surge", "Thrust demand", -100, 100),
            ("turn", "Turn demand", -100, 100),
            ("heading", "Target heading", 0, 359),
        ]:
            self.slider_labels[key] = label(text)
            form.addWidget(self.slider_labels[key])
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(low, high)
            slider.setValue(30 if key == "heading" else 0)
            slider.valueChanged.connect(self.update_labels)
            self.sliders[key] = slider
            form.addWidget(slider)
        buttons = QGridLayout()
        for i, (text, action) in enumerate(
            [("Arm", "arm"), ("Run", "run"), ("Stop", "stop"), ("Reset fault", "reset")]
        ):
            button = QPushButton(text)
            if action == "run":
                button.setObjectName("primary")
            button.clicked.connect(lambda checked=False, action=action: self.perform(action))
            buttons.addWidget(button, i // 2, i % 2)
        form.addLayout(buttons)
        neutral = QPushButton("Neutral controls")
        neutral.clicked.connect(self.neutral)
        form.addWidget(neutral)
        estop = QPushButton("■  EMERGENCY STOP")
        estop.setObjectName("estop")
        estop.clicked.connect(lambda: self.perform("estop"))
        form.addWidget(estop)
        release = QPushButton("Release stop input")
        release.clicked.connect(lambda: self.perform("release_estop"))
        form.addWidget(release)
        center.addWidget(controls, 2)
        body.addLayout(center, 1)
        bottom = QHBoxLayout()
        faults_frame, faults_box = card()
        faults_box.addWidget(label("Fault injection", "section"))
        self.fault_boxes = {}
        for fault in Fault:
            checkbox = QCheckBox(fault.value.replace("_", " ").title())
            checkbox.toggled.connect(lambda enabled, fault=fault: self.sim.inject(fault, enabled))
            faults_box.addWidget(checkbox)
            self.fault_boxes[fault] = checkbox
        bottom.addWidget(faults_frame, 2)
        events_frame, events_box = card()
        events_box.addWidget(label("Event journal", "section"))
        self.journal = label("")
        self.journal.setWordWrap(True)
        self.journal.setMinimumHeight(100)
        events_box.addWidget(self.journal, 1)
        export = QPushButton("Export simulation CSV")
        export.clicked.connect(self.export)
        events_box.addWidget(export)
        bottom.addWidget(events_frame, 3)
        body.addLayout(bottom)
        body.addWidget(
            label(
                "Simplified educational model · virtual sensors · no production or hardware validation",
                "muted",
            )
        )
        self.update_labels()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(50)
        self.refresh()

    def update_labels(self):
        for key, text in [("surge", "Thrust demand"), ("turn", "Turn demand"), ("heading", "Target heading")]:
            self.slider_labels[key].setText(
                f"{text}: {self.sliders[key].value()}{'°' if key == 'heading' else '%'}"
            )

    def get_command(self):
        return Command(
            self.sliders["surge"].value() / 100,
            self.sliders["turn"].value() / 100,
            "manual" if self.control.currentIndex() == 0 else "heading",
            self.sliders["heading"].value(),
        )

    def neutral(self):
        self.sliders["surge"].setValue(0)
        self.sliders["turn"].setValue(0)
        self.sim.receive(self.get_command())

    def perform(self, action):
        if action == "stop":
            self.neutral()
        self.sim.receive(self.get_command())
        self.sim.action(action)
        self.refresh()

    def tick(self):
        self.sim.receive(self.get_command())
        self.sim.step()
        self.refresh()

    def load_scenario(self, name):
        self.sim = scenario(name)
        self.sliders["surge"].setValue(round(self.sim.command.surge * 100))
        self.sliders["turn"].setValue(round(self.sim.command.turn * 100))
        self.sliders["heading"].setValue(round(self.sim.command.heading_deg))
        self.control.setCurrentIndex(0 if self.sim.command.control == "manual" else 1)
        for fault, checkbox in self.fault_boxes.items():
            checkbox.blockSignals(True)
            checkbox.setChecked(fault in self.sim.faults)
            checkbox.blockSignals(False)
        self.refresh()

    def refresh(self):
        s = self.sim.snapshot()
        self.metrics["speed"].setText(f"{math.hypot(s['surge_mps'], s['sway_mps']) * 1.943844:.2f}")
        self.metrics["heading"].setText(f"{s['heading_deg']:05.1f}")
        self.metrics["pressure"].setText(f"{s['pressure_bar']:.0f}")
        self.metrics["temp"].setText(f"{s['temperature_c']:.1f}")
        self.status.setText(f"●  {s['mode']}    /    {s['time_s']:.1f} s")
        self.notice.setText(
            "Latched: " + ", ".join(s["latched"])
            if s["latched"]
            else "Neutral → Arm → Run   |   Inject faults to inspect the controller response"
        )
        self.feedback.setText(
            f"PORT {s['port_feedback']:+.0%}   /   STARBOARD {s['starboard_feedback']:+.0%}    ·    Thrust feedback"
        )
        self.journal.setText("\n".join(f"{e['time_s']:5.1f}s  {e['message']}" for e in s["events"][:5]))
        self.sea.sim = self.sim
        self.sea.update()

    def export(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export simulation", "waterjet-simulation.csv", "CSV (*.csv)"
        )
        if filename:
            Path(filename).write_bytes(self.sim.csv().encode("utf-8"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--screenshot", type=Path, help="Render an offscreen native Qt preview and exit")
    args = parser.parse_args()
    if args.screenshot:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication(sys.argv[:1])
    configure_application(app)
    window = Console()
    if args.screenshot:
        window.timer.stop()
        window.load_scenario("heading")
        advance(window.sim, 7)
        window.refresh()
        window.show()
        app.processEvents()
        args.screenshot.parent.mkdir(parents=True, exist_ok=True)
        if not window.grab().save(str(args.screenshot)):
            raise RuntimeError("Could not save native Qt preview")
        window.close()
        return
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
