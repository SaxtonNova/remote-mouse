import sys
import os

# === Handle windowless mode for PyInstaller ===
# Redirect stdout/stderr to a file for debugging, or devnull in production
def setup_output_streams():
    if sys.stdout is None or sys.stderr is None:
        app_data = os.environ.get('LOCALAPPDATA', os.path.expanduser('~'))
        log_dir = os.path.join(app_data, 'RemoteTouchpad')
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, 'debug.log')

        f = open(log_file, 'w', encoding='utf-8')
        if sys.stdout is None:
            sys.stdout = f
        if sys.stderr is None:
            sys.stderr = f

setup_output_streams()

import socket
import qrcode
import threading
import subprocess
import logging

# Setup logging to file when running as exe
if getattr(sys, 'frozen', False):
    app_data = os.environ.get('LOCALAPPDATA', os.path.expanduser('~'))
    log_dir = os.path.join(app_data, 'RemoteTouchpad')
    logging.basicConfig(
        filename=os.path.join(log_dir, 'app.log'),
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

from flask import Flask, send_from_directory
from flask_socketio import SocketIO
from engineio.async_drivers import threading as async_threading  # Required for async_mode='threading'
import pyautogui
import pyperclip
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout,
    QSlider, QComboBox, QPushButton
)
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt

# Disable pyautogui failsafe (prevents error when mouse hits screen corners)
pyautogui.FAILSAFE = False


def get_app_data_path():
    """Get the appropriate AppData folder for storing application files."""
    app_data = os.environ.get('LOCALAPPDATA', os.path.expanduser('~'))
    app_folder = os.path.join(app_data, 'RemoteTouchpad')
    os.makedirs(app_folder, exist_ok=True)
    return app_folder


def get_base_path():
    """Get the base path for resources (works for both dev and PyInstaller exe)."""
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    else:
        return os.path.dirname(os.path.abspath(__file__))


def get_local_ip():
    """Get the local IP address."""
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
webapp_path = os.path.join(get_base_path(), 'webapp')
app = Flask(__name__, static_folder=webapp_path)

# Disable Flask logging
app.logger.disabled = True
log = logging.getLogger('werkzeug')
log.disabled = True

socketio = SocketIO(app, cors_allowed_origins='*', async_mode='threading', logger=False, engineio_logger=False)


@app.route('/')
def index():
    return send_from_directory(webapp_path, 'index.html')


@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(webapp_path, path)


@socketio.on('connect')
def handle_connect():
    pass


@socketio.on('move')
def handle_move(data):
    dx = data.get('dx', 0) * mouse_sensitivity
    dy = data.get('dy', 0) * mouse_sensitivity
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
    dy = data.get('dy', 0) * scroll_sensitivity
    pyautogui.scroll(int(dy * 60))

@socketio.on('rightclick')
def handle_rightclick():
    pyautogui.click(button='right')

@socketio.on('type')
def handle_type(char):
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

        self.setWindowTitle("Remote Touchpad")
        self.setGeometry(200, 200, 350, 600)
        self.setStyleSheet("background-color: #1e1e1e; color: white; font-size: 14px;")

        layout = QVBoxLayout()
        layout.setSpacing(16)

        # QR Code
        ip = get_local_ip()
        self.remote_url = f"http://{ip}:5050"

        # Generate QR code to bytes buffer (no file I/O issues)
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(self.remote_url)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white")

        # Save to AppData
        qr_path = os.path.join(get_app_data_path(), "qr.png")
        qr_img.save(qr_path)

        qr_label = QLabel("Scan this QR on your phone:")
        qr_label.setAlignment(Qt.AlignCenter)
        qr_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(qr_label)

        qr_display = QLabel()
        qr_pixmap = QPixmap(qr_path)
        qr_display.setPixmap(qr_pixmap.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        qr_display.setAlignment(Qt.AlignCenter)
        layout.addWidget(qr_display)

        # URL label
        url_label = QLabel(self.remote_url)
        url_label.setAlignment(Qt.AlignCenter)
        url_label.setStyleSheet("font-size: 12px; color: #888;")
        layout.addWidget(url_label)

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
        size_button = QPushButton("Size Options")
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
            "2. Change 'Scale and layout'"
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
        subprocess.Popen(["cmd", "/c", "start", "ms-settings:display"],
                        creationflags=subprocess.CREATE_NO_WINDOW)


def run_server():
    """Run Flask server in a separate thread."""
    try:
        logging.info("Starting Flask server on 0.0.0.0:5050")
        print("Starting Flask server on 0.0.0.0:5050", flush=True)
        socketio.run(app, host='0.0.0.0', port=5050, use_reloader=False, log_output=False, allow_unsafe_werkzeug=True)
    except Exception as e:
        logging.error(f"Server error: {e}")
        print(f"Server error: {e}", flush=True)
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    # Start Flask server in background thread
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    # Run Qt application on main thread
    qt_app = QApplication(sys.argv)
    window = RemoteMouseUI()
    window.show()
    sys.exit(qt_app.exec_())
