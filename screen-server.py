#!/usr/bin/env python3
"""
Screen manager with clock dashboard - runs as user
States: desktop -> clock -> dimmed
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
import subprocess
import threading
import time
import os
import struct
import signal

BACKLIGHT = "/sys/class/backlight/10-0045/brightness"
TOUCH_DEV = "/dev/input/event4"
IDLE_TO_CLOCK = 300      # 5 min idle -> show clock
IDLE_TO_DIM = 300        # 5 more min -> dim screen  
DIM_LEVEL = 1
BRIGHT_LEVEL = 255
PORT = 8888

state = "desktop"
last_activity = time.time()
state_lock = threading.Lock()
chromium_proc = None

# Reap zombie children automatically
signal.signal(signal.SIGCHLD, lambda s, f: os.waitpid(-1, os.WNOHANG))

def set_brightness(val):
    try:
        with open(BACKLIGHT, "w") as f:
            f.write(str(val))
    except Exception as e:
        print(f"Backlight error: {e}", flush=True)

def kill_chromium():
    global chromium_proc
    # Kill tracked process
    if chromium_proc:
        try:
            chromium_proc.terminate()
            chromium_proc.wait(timeout=2)
        except:
            pass
        chromium_proc = None
    # Also kill any strays
    subprocess.run(["pkill", "-9", "chromium"], capture_output=True)
    time.sleep(0.3)
    # Reap any zombies
    try:
        while True:
            os.waitpid(-1, os.WNOHANG)
    except ChildProcessError:
        pass

def launch_chromium(url):
    global chromium_proc
    kill_chromium()
    env = os.environ.copy()
    env["WAYLAND_DISPLAY"] = "wayland-0"
    env["XDG_RUNTIME_DIR"] = "/run/user/1000"
    chromium_proc = subprocess.Popen([
        "chromium", "--kiosk", "--noerrdialogs", "--disable-infobars",
        "--no-first-run", "--ozone-platform=wayland",
        "--enable-features=UseOzonePlatform", url
    ], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def show_clock():
    global state
    launch_chromium(f"http://localhost:{PORT}/clock")
    set_brightness(BRIGHT_LEVEL)
    state = "clock"
    print(f"STATE: clock", flush=True)

def show_dimmed():
    global state
    launch_chromium(f"http://localhost:{PORT}/black")
    time.sleep(0.5)
    set_brightness(DIM_LEVEL)
    state = "dimmed"
    print(f"STATE: dimmed", flush=True)

def show_desktop():
    global state
    kill_chromium()
    set_brightness(BRIGHT_LEVEL)
    state = "desktop"
    print(f"STATE: desktop", flush=True)

def load_clock_html():
    paths = ["/home/daryxborn/clock.html", os.path.expanduser("~/clock.html")]
    for p in paths:
        if os.path.exists(p):
            return open(p, "rb").read()
    return b"<html><body style='background:#000;color:#fff'><h1>Clock not found</h1></body></html>"

CLOCK_HTML = load_clock_html()

BLACK_HTML = b'''<!DOCTYPE html><html><head>
<style>*{margin:0;padding:0}html,body{background:#000;width:100vw;height:100vh}</style>
</head><body>
<a href="/wake" style="display:block;width:100vw;height:100vh;position:fixed;top:0;left:0"></a>
</body></html>'''

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    
    def safe_write(self, data):
        try:
            self.wfile.write(data)
        except BrokenPipeError:
            pass  # Client closed connection, ignore
    
    def do_GET(self):
        global last_activity
        if self.path == "/clock":
            clock_with_touch = CLOCK_HTML.replace(
                b'</body>',
                b'<a href="/to-desktop" style="display:block;width:100vw;height:100vh;position:fixed;top:0;left:0;z-index:9999"></a></body>'
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.safe_write(clock_with_touch)
        elif self.path == "/black":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.safe_write(BLACK_HTML)
        elif self.path == "/wake":
            last_activity = time.time()
            with state_lock:
                show_clock()
            self.send_response(200)
            self.end_headers()
            self.safe_write(b"clock")
        elif self.path == "/to-desktop":
            last_activity = time.time()
            with state_lock:
                show_desktop()
            self.send_response(200)
            self.end_headers()
            self.safe_write(b"desktop")
        elif self.path == "/status":
            self.send_response(200)
            self.end_headers()
            self.safe_write(state.encode())
        else:
            self.send_response(404)
            self.end_headers()

def idle_monitor():
    global state, last_activity
    while True:
        time.sleep(5)
        idle_time = time.time() - last_activity
        with state_lock:
            if state == "desktop" and idle_time > IDLE_TO_CLOCK:
                show_clock()
                last_activity = time.time()
            elif state == "clock" and idle_time > IDLE_TO_DIM:
                show_dimmed()

def touch_monitor():
    global last_activity
    EVENT_SIZE = struct.calcsize("llHHI")
    while True:
        try:
            with open(TOUCH_DEV, "rb") as f:
                while True:
                    f.read(EVENT_SIZE)
                    last_activity = time.time()
        except Exception as e:
            print(f"Touch monitor error: {e}, retrying...", flush=True)
            time.sleep(1)

if __name__ == "__main__":
    kill_chromium()
    set_brightness(BRIGHT_LEVEL)
    print(f"Screen manager on port {PORT}", flush=True)
    print(f"Desktop -> {IDLE_TO_CLOCK}s -> Clock -> {IDLE_TO_DIM}s -> Dimmed", flush=True)
    threading.Thread(target=idle_monitor, daemon=True).start()
    threading.Thread(target=touch_monitor, daemon=True).start()
    HTTPServer(("", PORT), Handler).serve_forever()
