import sys
import socket
import qrcode
import threading
import subprocess

from flask import Flask, send_from_directory
from flask_socketio import SocketIO
from engineio.async_drivers import threading as ei_threading
import pyautogui
import pyperclip
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QSlider, QComboBox, QPushButton
)
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtCore import Qt


# === Helpers ===
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


# === Globals ===
mouse_sensitivity = 0.8
scroll_sensitivity = 1.0
resolution = (1920, 1080)


# === Flask App ===
app = Flask(__name__, static_folder="webapp")
socketio = SocketIO(app, cors_allowed_origins='*', async_mode="threading")

@app.route('/')
def index():
    return send_from_directory('webapp', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('webapp', path)

@socketio.on('connect')
def handle_connect():
    print("[CONNECT] Phone connected.")

@socketio.on('move')
def handle_move(data):
    dx = data.get('dx', 0)
    dy = data.get('dy', 0)
    dx *= mouse_sensitivity
    dy *= mouse_sensitivity
    pyautogui.moveRel(dx, dy)

@socketio.on('click')
def handle_click():
    pyautogui.click()

@socketio.on('mousedown')
def handle_mousedown():
    pyautogui.mouseDown()

@socketio.on('mouseup')
def handle_mouseup():
    pyautogui.mouseUp()

@socketio.on('scroll')
def handle_scroll(data):
    dx = data.get('dx', 0)
    dy = data.get('dy', 0)
    dy *= scroll_sensitivity
    pyautogui.scroll(int(dy * 60))

@socketio.on('rightclick')
def handle_rightclick():
    pyautogui.click(button='right')

@socketio.on('type')
def handle_type(char):
    import pyautogui
    print(f"[TYPE] Key received: {char}")
    if char == 'BACKSPACE':
        pyautogui.press('backspace')
    elif char == 'ENTER':
        pyautogui.press('enter')
    else:
        pyperclip.copy(char)
        pyautogui.hotkey("ctrl", "v")




# === UI Code ===
class RemoteMouseUI(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Remote Mouse - Settings Panel")
        self.setGeometry(200, 200, 350, 600)
        self.setStyleSheet("background-color: #1e1e1e; color: white; font-size: 14px;")

        layout = QVBoxLayout()
        layout.setSpacing(16)

        # QR Code
        ip = get_local_ip()
        self.remote_url = f"http://{ip}:5050"
        qr = qrcode.make(self.remote_url)
        qr.save("qr.png")

        qr_image = QImage("qr.png")
        qr_pixmap = QPixmap.fromImage(qr_image)

        qr_label = QLabel("Scan this QR on your phone:")
        qr_label.setAlignment(Qt.AlignCenter)
        qr_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(qr_label)

        qr_display = QLabel()
        qr_display.setPixmap(qr_pixmap.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        qr_display.setAlignment(Qt.AlignCenter)
        layout.addWidget(qr_display)

        # Mouse Sensitivity
        layout.addWidget(QLabel("Mouse Sensitivity"))
        self.mouse_slider = QSlider(Qt.Horizontal)
        self.mouse_slider.setMinimum(1)
        self.mouse_slider.setMaximum(20)
        self.mouse_slider.setValue(8)
        self.mouse_slider.valueChanged.connect(self.update_mouse_sensitivity)
        layout.addWidget(self.mouse_slider)

        # Scroll Sensitivity
        layout.addWidget(QLabel("Scroll Sensitivity"))
        self.scroll_slider = QSlider(Qt.Horizontal)
        self.scroll_slider.setMinimum(1)
        self.scroll_slider.setMaximum(20)
        self.scroll_slider.setValue(5)
        self.scroll_slider.valueChanged.connect(self.update_scroll_sensitivity)
        layout.addWidget(self.scroll_slider)

        # Resolution
        layout.addWidget(QLabel("Monitor Resolution"))
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems([
            "1920x1080", "1600x900", "1366x768", "1280x720", "Custom..."
        ])
        self.resolution_combo.currentIndexChanged.connect(self.update_resolution)
        layout.addWidget(self.resolution_combo)

        # Size Options button
        size_button = QPushButton("🖥️ Size Options")
        size_button.setStyleSheet("""
            QPushButton {
                background-color: #0078D7;
                color: white;
                padding: 10px;
                font-size: 16px;
                font-weight: bold;
                border-radius: 8px;
                border: 2px solid #005A9E;
            }
            QPushButton:hover {
                background-color: #005A9E;
            }
        """)
        size_button.clicked.connect(self.open_display_settings)
        layout.addWidget(size_button)

        # Instruction label
        instruction = QLabel(
            "To change app/icon/text sizes:\n"
            "1. Click 'Size Options'\n"
            "2. Change 'Scale and layout' → "
            "'Change the size of text, apps, and other items'"
        )
        instruction.setAlignment(Qt.AlignCenter)
        instruction.setWordWrap(True)
        layout.addWidget(instruction)

        self.setLayout(layout)

    def update_mouse_sensitivity(self, value):
        global mouse_sensitivity
        mouse_sensitivity = value / 10.0

    def update_scroll_sensitivity(self, value):
        global scroll_sensitivity
        scroll_sensitivity = value / 10.0

    def update_resolution(self):
        global resolution
        text = self.resolution_combo.currentText()
        if "x" in text:
            w, h = map(int, text.split("x"))
            resolution = (w, h)

    def open_display_settings(self):
        subprocess.run(["start", "ms-settings:display"], shell=True)


# === Main Launch ===
if __name__ == '__main__':
    def run_flask():
        socketio.run(app, host='0.0.0.0', port=5050)

    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    qt_app = QApplication(sys.argv)
    window = RemoteMouseUI()
    window.show()
    sys.exit(qt_app.exec_())
