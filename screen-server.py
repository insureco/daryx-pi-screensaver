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
import json
import urllib.request
import re

BACKLIGHT = "/sys/class/backlight/10-0045/brightness"
TOUCH_DEV = "/dev/input/event4"
IDLE_TO_CLOCK = 300
IDLE_TO_DIM = 300
DIM_LEVEL = 1
BRIGHT_LEVEL = 255
PORT = 8888

state = "desktop"
last_activity = time.time()
state_lock = threading.Lock()
chromium_proc = None

# Cache weather data (refresh every 10 min)
weather_cache = {"data": None, "time": 0}

def reap_children(sig, frame):
    try:
        while True:
            os.waitpid(-1, os.WNOHANG)
    except ChildProcessError:
        pass

signal.signal(signal.SIGCHLD, reap_children)

def set_brightness(val):
    try:
        with open(BACKLIGHT, "w") as f:
            f.write(str(val))
    except Exception as e:
        print(f"Backlight error: {e}", flush=True)

def kill_chromium():
    global chromium_proc
    if chromium_proc:
        try:
            chromium_proc.terminate()
            chromium_proc.wait(timeout=2)
        except:
            pass
        chromium_proc = None
    subprocess.run(["pkill", "-9", "chromium"], capture_output=True)
    time.sleep(0.3)
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

def get_blocky_stats():
    """Parse Prometheus metrics from Blocky"""
    try:
        req = urllib.request.urlopen("http://localhost:4000/metrics", timeout=2)
        metrics = req.read().decode()
        
        # Count blocked and total responses
        blocked = 0
        total = 0
        for line in metrics.split('\n'):
            if line.startswith('blocky_response_total{'):
                match = re.search(r'}\s+(\d+)', line)
                if match:
                    count = int(match.group(1))
                    total += count
                    if 'BLOCKED' in line:
                        blocked += count
        return total, blocked
    except:
        return None, None

def get_weather():
    """Get weather from wttr.in with caching"""
    global weather_cache
    now = time.time()
    
    # Return cached if fresh (10 min)
    if weather_cache["data"] and (now - weather_cache["time"]) < 600:
        return weather_cache["data"]
    
    try:
        req = urllib.request.Request(
            "https://wttr.in/San+Diego?format=j1",
            headers={"User-Agent": "curl/7.68.0"}
        )
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.load(resp)
        
        current = data["current_condition"][0]
        astro = data["weather"][0]["astronomy"][0]
        
        result = {
            "temp_f": current["temp_F"],
            "desc": current["weatherDesc"][0]["value"],
            "humidity": current["humidity"],
            "sunrise": astro["sunrise"].lstrip("0").replace(" ", ""),
            "sunset": astro["sunset"].lstrip("0").replace(" ", "")
        }
        weather_cache = {"data": result, "time": now}
        return result
    except Exception as e:
        print(f"Weather error: {e}", flush=True)
        return weather_cache.get("data")  # Return stale cache if available

def get_stats():
    stats = {}
    
    # CPU temp
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            stats["cpu_temp_f"] = round(int(f.read().strip()) / 1000 * 9/5 + 32)
    except:
        stats["cpu_temp_f"] = None
    
    # Memory
    try:
        with open("/proc/meminfo") as f:
            lines = f.readlines()
            total = int([l for l in lines if "MemTotal" in l][0].split()[1])
            avail = int([l for l in lines if "MemAvailable" in l][0].split()[1])
            stats["mem_percent"] = round((total - avail) / total * 100)
    except:
        stats["mem_percent"] = None
    
    # Uptime
    try:
        with open("/proc/uptime") as f:
            secs = int(float(f.read().split()[0]))
            days, rem = divmod(secs, 86400)
            hours, rem = divmod(rem, 3600)
            stats["uptime"] = f"{days}d {hours}h"
    except:
        stats["uptime"] = None
    
    # Blocky stats
    total, blocked = get_blocky_stats()
    stats["queries_total"] = total
    stats["blocked_total"] = blocked
    
    # Weather
    weather = get_weather()
    if weather:
        stats["weather_f"] = weather["temp_f"]
        stats["weather_desc"] = weather["desc"]
        stats["sunrise"] = weather["sunrise"]
        stats["sunset"] = weather["sunset"]
    else:
        stats["weather_f"] = None
        stats["weather_desc"] = None
        stats["sunrise"] = None
        stats["sunset"] = None
    
    return stats

def load_clock_html():
    paths = ["/home/daryxborn/clock.html", os.path.expanduser("~/clock.html")]
    for p in paths:
        if os.path.exists(p):
            return open(p, "rb").read()
    return b"<html><body style='background:#000;color:#fff'><h1>Clock not found</h1></body></html>"

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
            pass
    
    def do_GET(self):
        global last_activity
        if self.path == "/clock":
            clock_html = load_clock_html()
            clock_with_touch = clock_html.replace(
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
        elif self.path == "/stats":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.safe_write(json.dumps(get_stats()).encode())
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
