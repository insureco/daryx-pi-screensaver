# daryx-pi-screensaver

Touch-to-wake screensaver with clock dashboard for Raspberry Pi touchscreen running Wayland/labwc.

## Features

- **Clock Dashboard** - Large time display with Exo 2 font
- **Weather & Sun Times** - Current temp, conditions, sunrise/sunset from wttr.in
- **Sunset Countdown** - Live countdown to sunset
- **System Stats** - CPU temp, memory, uptime
- **Blocky DNS Stats** - Blocked queries count from Prometheus metrics
- **Three States** - Desktop → Clock → Dimmed with touch navigation
- **Bulletproof** - Auto-recovers from crashes, never blocks

## Screenshot

```
         10:41:23
    Wednesday, January 28

   58° Partly cloudy  🌅 6:46AM  🌇 5:18PM
   
        ☀️ 5h 32m until sunset

  🌡️ 114°  🛡️ 701  💾 22%  ⏱️ 0d 10h
```

## The Problem This Solves

On Raspberry Pi with DSI touchscreen running Wayland:
- Setting `brightness=0` completely disables the touch controller
- No way to wake the screen without a keyboard
- Traditional screensavers don't work on Wayland

## The Solution

- Keep brightness at minimum (1) instead of 0
- Display fullscreen black page via Chromium kiosk
- Touch triggers HTTP endpoint to wake
- Watchdog auto-restarts Chromium if it crashes

## How It Works

```
Desktop ──(5 min idle)──► Clock ──(5 min idle)──► Dimmed
   ▲                        │                        │
   └────────(touch)─────────┘                        │
                            ▲                        │
                            └───────(touch)──────────┘
```

## Installation

### 1. Install emoji font (optional but recommended)

```bash
sudo apt install -y fonts-noto-color-emoji
```

### 2. Set up backlight permissions

```bash
sudo cp 99-backlight.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
```

### 3. Copy files

```bash
cp screen-server.py ~/screen-server.py
cp clock.html ~/clock.html
chmod +x ~/screen-server.py
```

### 4. Configure autostart

```bash
mkdir -p ~/.config/labwc
cp labwc-autostart ~/.config/labwc/autostart
```

### 5. Reboot or start manually

```bash
python3 ~/screen-server.py &
```

## Configuration

Edit `screen-server.py`:

```python
IDLE_TO_CLOCK = 300   # seconds until clock shows (default: 5 min)
IDLE_TO_DIM = 300     # seconds until dim (default: 5 min)  
DIM_LEVEL = 1         # minimum brightness (0 disables touch!)
BRIGHT_LEVEL = 255    # full brightness
PORT = 8888           # HTTP server port
```

Weather location is hardcoded to San Diego - edit the `get_weather()` function to change.

## API Endpoints

| Endpoint | Action |
|----------|--------|
| `/clock` | Serves clock HTML |
| `/black` | Serves black overlay |
| `/wake` | Transition: dimmed → clock |
| `/to-desktop` | Transition: clock → desktop |
| `/status` | Returns current state |
| `/stats` | Returns JSON stats (cached, instant) |

## Architecture

The server runs 4 background threads:

1. **Idle Monitor** - Tracks inactivity, triggers state changes
2. **Touch Monitor** - Reads touch events from `/dev/input/event4`
3. **Stats Updater** - Fetches system/weather/Blocky stats (never blocks HTTP)
4. **Chromium Watchdog** - Auto-restarts Chromium if it crashes

All network calls have timeouts. Stats are cached and served instantly.

## Stats Sources

| Stat | Source | Update Interval |
|------|--------|-----------------|
| CPU Temp | `/sys/class/thermal/thermal_zone0/temp` | 10s |
| Memory | `/proc/meminfo` | 10s |
| Uptime | `/proc/uptime` | 10s |
| Blocked | Blocky Prometheus `/metrics` | 10s |
| Weather | wttr.in API | 10 min |
| Sunrise/Sunset | wttr.in API | 10 min |

## Testing

```bash
curl http://localhost:8888/status      # Check current state
curl http://localhost:8888/stats       # Get all stats as JSON
curl http://localhost:8888/wake        # Show clock
curl http://localhost:8888/to-desktop  # Back to desktop
```

## Customizing the Clock

Edit `clock.html` to change:
- Font (currently Exo 2 from Google Fonts)
- Colors and layout  
- Weather location
- Add more stats

## Hardware Requirements

- Raspberry Pi 4 (tested)
- Official DSI touchscreen (or compatible)
- Wayland compositor (labwc tested)

## Hardware Notes

- Touch device: `/dev/input/event4` (may vary)
- Backlight: `/sys/class/backlight/10-0045/brightness`
- User must be in `input` group for touch access

## Troubleshooting

**Screen won't wake:**
```bash
cat /sys/class/backlight/10-0045/brightness  # Must be ≥1
```

**Server not running:**
```bash
ps aux | grep screen-server
cat /tmp/screen.log
```

**Reset everything:**
```bash
pkill chromium
pkill -f screen-server
echo 255 > /sys/class/backlight/10-0045/brightness
python3 ~/screen-server.py &
```

**Check if Blocky is running:**
```bash
curl -s http://localhost:4000/metrics | grep blocky_blocking_enabled
```

## Dependencies

- Python 3 (standard library only)
- Chromium browser
- labwc (Wayland compositor)
- Blocky DNS (optional, for blocked stats)

## License

MIT
