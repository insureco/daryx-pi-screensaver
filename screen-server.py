#!/usr/bin/env python3
"""
Screen manager with clock dashboard - runs as user
States: desktop -> clock -> dimmed
BULLETPROOF VERSION - never blocks, auto-recovers
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

# Cached stats (updated by background thread)
cached_stats = {
    "cpu_temp_f": None,
    "mem_percent": None,
    "uptime": None,
    "queries_total": None,
    "blocked_total": None,
    "weather_f": None,
    "weather_desc": None,
    "sunrise": None,
    "sunset": None
}
stats_lock = threading.Lock()

def reap_children(sig, frame):
    try:
        while True:
            os.waitpid(-1, os.WNOHANG)
    except:
        pass

signal.signal(signal.SIGCHLD, reap_children)

def set_brightness(val):
    try:
        with open(BACKLIGHT, "w") as f:
            f.write(str(val))
    except:
        pass

def kill_chromium():
    global chromium_proc
    if chromium_proc:
        try:
            chromium_proc.terminate()
            chromium_proc.wait(timeout=2)
        except:
            pass
        chromium_proc = None
    try:
        subprocess.run(["pkill", "-9", "chromium"], capture_output=True, timeout=5)
    except:
        pass
    time.sleep(0.3)

def launch_chromium(url):
    global chromium_proc
    kill_chromium()
    try:
        env = os.environ.copy()
        env["WAYLAND_DISPLAY"] = "wayland-0"
        env["XDG_RUNTIME_DIR"] = "/run/user/1000"
        chromium_proc = subprocess.Popen([
            "chromium", "--kiosk", "--noerrdialogs", "--disable-infobars",
            "--no-first-run", "--ozone-platform=wayland",
            "--enable-features=UseOzonePlatform", url
        ], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"Chromium launch error: {e}", flush=True)

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

def get_system_stats():
    """Get local system stats (fast, no network)"""
    stats = {}
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            stats["cpu_temp_f"] = round(int(f.read().strip()) / 1000 * 9/5 + 32)
    except:
        pass
    try:
        with open("/proc/meminfo") as f:
            lines = f.readlines()
            total = int([l for l in lines if "MemTotal" in l][0].split()[1])
            avail = int([l for l in lines if "MemAvailable" in l][0].split()[1])
            stats["mem_percent"] = round((total - avail) / total * 100)
    except:
        pass
    try:
        with open("/proc/uptime") as f:
            secs = int(float(f.read().split()[0]))
            days, rem = divmod(secs, 86400)
            hours, rem = divmod(rem, 3600)
            stats["uptime"] = f"{days}d {hours}h"
    except:
        pass
    return stats

def get_blocky_stats():
    """Get Blocky DNS stats (local network, fast)"""
    try:
        req = urllib.request.urlopen("http://localhost:4000/metrics", timeout=2)
        metrics = req.read().decode()
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
    """Get weather (external API, can be slow)"""
    try:
        req = urllib.request.Request(
            "https://wttr.in/San+Diego?format=j1",
            headers={"User-Agent": "curl/7.68.0"}
        )
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.load(resp)
        current = data["current_condition"][0]
        astro = data["weather"][0]["astronomy"][0]
        return {
            "weather_f": current["temp_F"],
            "weather_desc": current["weatherDesc"][0]["value"],
            "sunrise": astro["sunrise"].lstrip("0").replace(" ", ""),
            "sunset": astro["sunset"].lstrip("0").replace(" ", "")
        }
    except:
        return None

def background_stats_updater():
    """Background thread that updates all stats periodically"""
    global cached_stats
    weather_last_update = 0
    
    while True:
        try:
            new_stats = {}
            
            # System stats (always update)
            new_stats.update(get_system_stats())
            
            # Blocky stats (local, fast)
            total, blocked = get_blocky_stats()
            new_stats["queries_total"] = total
            new_stats["blocked_total"] = blocked
            
            # Weather (external, update every 10 min)
            now = time.time()
            if now - weather_last_update > 600:
                weather = get_weather()
                if weather:
                    new_stats.update(weather)
                    weather_last_update = now
            
            # Update cache atomically
            with stats_lock:
                for k, v in new_stats.items():
                    if v is not None:
                        cached_stats[k] = v
        except Exception as e:
            print(f"Stats updater error: {e}", flush=True)
        
        time.sleep(10)

def chromium_watchdog():
    """Restart Chromium if it dies while in clock/dimmed state"""
    global chromium_proc, state
    while True:
        time.sleep(5)
        try:
            with state_lock:
                if state in ("clock", "dimmed") and chromium_proc:
                    poll = chromium_proc.poll()
                    if poll is not None:  # Process died
                        print(f"Chromium died (exit {poll}), restarting...", flush=True)
                        if state == "clock":
                            show_clock()
                        else:
                            show_dimmed()
        except Exception as e:
            print(f"Watchdog error: {e}", flush=True)

def load_clock_html():
    paths = ["/home/daryxborn/clock.html", os.path.expanduser("~/clock.html")]
    for p in paths:
        try:
            if os.path.exists(p):
                return open(p, "rb").read()
        except:
            pass
    return b"<html><body style='background:#000;color:#fff'><h1>Clock</h1></body></html>"

BLACK_HTML = b'''<!DOCTYPE html><html><head>
<style>*{margin:0;padding:0}html,body{background:#000;width:100vw;height:100vh}</style>
</head><body>
<a href="/wake" style="display:block;width:100vw;height:100vh;position:fixed;top:0;left:0"></a>
</body></html>'''

class Handler(BaseHTTPRequestHandler):
    timeout = 5  # Socket timeout
    
    def log_message(self, *args): pass
    
    def safe_write(self, data):
        try:
            self.wfile.write(data)
        except:
            pass
    
    def do_GET(self):
        global last_activity
        try:
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
                with stats_lock:
                    stats_copy = dict(cached_stats)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.safe_write(json.dumps(stats_copy).encode())
            else:
                self.send_response(404)
                self.end_headers()
        except Exception as e:
            print(f"Handler error: {e}", flush=True)

def idle_monitor():
    global state, last_activity
    while True:
        time.sleep(5)
        try:
            idle_time = time.time() - last_activity
            with state_lock:
                if state == "desktop" and idle_time > IDLE_TO_CLOCK:
                    show_clock()
                    last_activity = time.time()
                elif state == "clock" and idle_time > IDLE_TO_DIM:
                    show_dimmed()
        except Exception as e:
            print(f"Idle monitor error: {e}", flush=True)

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
    print(f"Screen manager on port {PORT} (bulletproof)", flush=True)
    print(f"Desktop -> {IDLE_TO_CLOCK}s -> Clock -> {IDLE_TO_DIM}s -> Dimmed", flush=True)
    
    # Start all background threads
    threading.Thread(target=idle_monitor, daemon=True).start()
    threading.Thread(target=touch_monitor, daemon=True).start()
    threading.Thread(target=background_stats_updater, daemon=True).start()
    threading.Thread(target=chromium_watchdog, daemon=True).start()
    
    # Run HTTP server (never blocks on stats now)
    HTTPServer(("", PORT), Handler).serve_forever()
