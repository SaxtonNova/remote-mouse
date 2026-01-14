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

import json
import random
import socket
import qrcode
import threading
import subprocess
import logging
from flask import Flask, send_from_directory, request

# Setup logging to file when running as exe
if getattr(sys, 'frozen', False):
    app_data = os.environ.get('LOCALAPPDATA', os.path.expanduser('~'))
    log_dir = os.path.join(app_data, 'RemoteTouchpad')
    logging.basicConfig(
        filename=os.path.join(log_dir, 'app.log'),
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

from flask_socketio import SocketIO, emit
from engineio.async_drivers import threading as async_threading  # Required for async_mode='threading'
import pyautogui
import pyperclip
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout,
    QSlider, QComboBox, QPushButton, QMessageBox
)
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt, pyqtSignal, QObject

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


# === Trusted Devices Management ===
def get_trusted_devices_path():
    return os.path.join(get_app_data_path(), 'trusted_devices.json')


def load_trusted_devices():
    path = get_trusted_devices_path()
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                return set(json.load(f))
        except:
            return set()
    return set()


def save_trusted_devices(devices):
    path = get_trusted_devices_path()
    with open(path, 'w') as f:
        json.dump(list(devices), f)


def generate_pin():
    """Generate a random 4-digit PIN."""
    return str(random.randint(1000, 9999))


# === Globals ===
mouse_sensitivity = 0.8
scroll_sensitivity = 1.0
resolution = (1920, 1080)
trusted_devices = load_trusted_devices()
current_pin = None  # Will be set when "Add Device" is clicked
authenticated_sessions = set()  # Socket IDs that have been authenticated


# === Flask App ===
webapp_path = os.path.join(get_base_path(), 'webapp')
app = Flask(__name__, static_folder=webapp_path)

# Disable Flask logging
app.logger.disabled = True
log = logging.getLogger('werkzeug')
log.disabled = True

socketio = SocketIO(app, cors_allowed_origins='*', async_mode='threading', logger=False, engineio_logger=False)


def get_client_ip():
    """Get the IP address of the connected client."""
    return request.remote_addr


def is_authenticated(sid):
    """Check if a session is authenticated (trusted device or entered PIN)."""
    client_ip = request.remote_addr
    return client_ip in trusted_devices or sid in authenticated_sessions


@app.route('/')
def index():
    return send_from_directory(webapp_path, 'index.html')


@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(webapp_path, path)


@socketio.on('connect')
def handle_connect():
    client_ip = get_client_ip()
    sid = request.sid
    is_trusted = client_ip in trusted_devices
    emit('auth_status', {'trusted': is_trusted})
    logging.info(f"Client connected: {client_ip}, trusted: {is_trusted}")


@socketio.on('check_pin')
def handle_check_pin(pin):
    global current_pin, trusted_devices, authenticated_sessions
    client_ip = get_client_ip()
    sid = request.sid

    if current_pin and pin == current_pin:
        # Add to trusted devices
        trusted_devices.add(client_ip)
        save_trusted_devices(trusted_devices)
        authenticated_sessions.add(sid)
        current_pin = None  # Invalidate PIN after use
        emit('auth_status', {'trusted': True, 'message': 'Device trusted!'})
        logging.info(f"Device authenticated: {client_ip}")
    else:
        emit('auth_status', {'trusted': False, 'message': 'Invalid PIN'})


@socketio.on('move')
def handle_move(data):
    if not is_authenticated(request.sid):
        return
    dx = data.get('dx', 0) * mouse_sensitivity
    dy = data.get('dy', 0) * mouse_sensitivity
    pyautogui.moveRel(dx, dy)


@socketio.on('click')
def handle_click():
    if not is_authenticated(request.sid):
        return
    pyautogui.click()


@socketio.on('mousedown')
def handle_mousedown():
    if not is_authenticated(request.sid):
        return
    pyautogui.mouseDown()


@socketio.on('mouseup')
def handle_mouseup():
    if not is_authenticated(request.sid):
        return
    pyautogui.mouseUp()


@socketio.on('scroll')
def handle_scroll(data):
    if not is_authenticated(request.sid):
        return
    dy = data.get('dy', 0) * scroll_sensitivity
    pyautogui.scroll(int(dy * 60))


@socketio.on('rightclick')
def handle_rightclick():
    if not is_authenticated(request.sid):
        return
    pyautogui.click(button='right')


@socketio.on('type')
def handle_type(char):
    if not is_authenticated(request.sid):
        return
    if char == 'BACKSPACE':
        pyautogui.press('backspace')
    elif char == 'ENTER':
        pyautogui.press('enter')
    else:
        pyperclip.copy(char)
        pyautogui.hotkey("ctrl", "v")


# === Signal for cross-thread communication ===
class SignalEmitter(QObject):
    show_pin_signal = pyqtSignal(str)

signal_emitter = SignalEmitter()


# === UI Code ===
class RemoteMouseUI(QWidget):
    def __init__(self):
        super().__init__()

        # Connect signal for showing PIN from other threads
        signal_emitter.show_pin_signal.connect(self.display_pin_dialog)

        self.setWindowTitle("Remote Touchpad")
        self.setGeometry(200, 200, 350, 650)
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

        # Add Trusted Device button
        self.add_device_btn = QPushButton("Add Trusted Device")
        self.add_device_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                padding: 10px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 8px;
                border: 2px solid #1e7e34;
            }
            QPushButton:hover {
                background-color: #1e7e34;
            }
        """)
        self.add_device_btn.clicked.connect(self.add_trusted_device)
        layout.addWidget(self.add_device_btn)

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
                font-size: 14px;
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

        self.setLayout(layout)

        # Show first-time setup dialog if no trusted devices
        if len(trusted_devices) == 0:
            # Use timer to show after window is displayed
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(500, self.first_time_setup)

    def first_time_setup(self):
        global current_pin
        current_pin = generate_pin()
        QMessageBox.information(
            self,
            "First Time Setup",
            f"Welcome! To connect your phone, enter this PIN on your phone:\n\n"
            f"PIN: {current_pin}\n\n"
            f"This PIN will expire after one use.\n"
            f"Click 'Add Trusted Device' to generate a new PIN anytime."
        )

    def add_trusted_device(self):
        global current_pin
        current_pin = generate_pin()
        QMessageBox.information(
            self,
            "Add Trusted Device",
            f"Enter this PIN on your phone to trust it:\n\n"
            f"PIN: {current_pin}\n\n"
            f"This PIN will expire after one use."
        )

    def display_pin_dialog(self, pin):
        QMessageBox.information(
            self,
            "Add Trusted Device",
            f"Enter this PIN on your phone to trust it:\n\n"
            f"PIN: {pin}\n\n"
            f"This PIN will expire after one use."
        )

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
        logging.info(f"Starting Flask server on 0.0.0.0:5050")
        logging.info(f"webapp_path: {webapp_path}")
        logging.info(f"webapp exists: {os.path.exists(webapp_path)}")
        logging.info(f"index.html exists: {os.path.exists(os.path.join(webapp_path, 'index.html'))}")
        print(f"Starting Flask server on 0.0.0.0:5050", flush=True)
        print(f"webapp_path: {webapp_path}", flush=True)
        print(f"webapp exists: {os.path.exists(webapp_path)}", flush=True)
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
