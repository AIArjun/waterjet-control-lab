import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtGui import QFont, QRawFont  # noqa: E402
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

from waterjet_lab.core import Mode  # noqa: E402
from waterjet_lab.desktop import Console, configure_application  # noqa: E402


def test_native_qt_panel_uses_real_controller_and_can_render(tmp_path):
    app = QApplication.instance() or QApplication([])
    configure_application(app)
    window = Console()
    font = QRawFont.fromFont(QFont("Segoe UI", 12))
    assert font.isValid() and font.supportsCharacter(ord("A"))
    window.timer.stop()
    window.perform("arm")
    window.perform("run")
    window.sliders["surge"].setValue(50)
    for _ in range(20):
        window.tick()
    assert window.sim.mode == Mode.RUNNING and window.sim.port_output > 0
    window.perform("estop")
    assert window.sim.mode == Mode.E_STOP and window.sim.port_output == 0
    window.load_scenario("heading")
    assert window.sim.command.control == "heading"
    window.show()
    app.processEvents()
    assert all(button.height() >= 30 for button in window.findChildren(QPushButton))
    assert window.grab().save(str(tmp_path / "native-qt.png"))
    window.close()
