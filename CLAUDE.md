# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Touch-to-wake screensaver with clock dashboard for Raspberry Pi touchscreen running Wayland/labwc. Solves the problem that setting Pi DSI touchscreen brightness to 0 disables the touch controller entirely.

## Running the Server

```bash
# Run directly
python3 screen-server.py

# Or via autostart (logs to /tmp/screen.log)
python3 ~/screen-server.py > /tmp/screen.log 2>&1 &
```

No dependencies beyond Python 3 standard library.

## Testing Endpoints

```bash
curl http://localhost:8888/status      # Returns: desktop|clock|dimmed
curl http://localhost:8888/stats       # JSON with all cached stats
curl http://localhost:8888/wake        # Force transition to clock
curl http://localhost:8888/to-desktop  # Force transition to desktop
```

## Architecture

**State Machine:**
```
Desktop ─(5min idle)─► Clock ─(5min idle)─► Dimmed
   ▲                      │                     │
   └─────(touch)──────────┘                     │
                          ▲                     │
                          └──────(touch)────────┘
```

**Background Threads (4 total):**
1. `idle_monitor` - Checks every 5s, triggers state transitions after idle timeouts
2. `touch_monitor` - Reads raw events from `/dev/input/event4`, updates `last_activity`
3. `background_stats_updater` - Fetches system/weather/Blocky stats every 10s (weather every 10min)
4. `chromium_watchdog` - Checks every 5s, restarts Chromium if it crashes while in clock/dimmed state

**Thread Safety:** Uses `state_lock` for state transitions, `stats_lock` for cached stats. All network calls happen in background threads with timeouts, never blocking HTTP responses.

## Key Files

| File | Purpose |
|------|---------|
| `screen-server.py` | Python HTTP server, state machine, all background threads |
| `clock.html` | Dashboard UI (Exo 2 font, fetches `/stats` every 10s) |
| `labwc-autostart` | Wayland compositor autostart script |
| `99-backlight.rules` | udev rule for non-root backlight control |

## Configuration Constants (in screen-server.py)

```python
BACKLIGHT = "/sys/class/backlight/10-0045/brightness"
TOUCH_DEV = "/dev/input/event4"
IDLE_TO_CLOCK = 300   # 5 min to clock
IDLE_TO_DIM = 300     # 5 min to dimmed
DIM_LEVEL = 1         # Minimum (0 disables touch!)
PORT = 8888
```

Weather location is hardcoded in `get_weather()` function (San Diego).

## Hardware Assumptions

- Raspberry Pi 4 with official DSI touchscreen
- Touch device at `/dev/input/event4` (may vary)
- Backlight at `/sys/class/backlight/10-0045/brightness`
- User in `input` group for touch access
- Chromium browser available
- labwc Wayland compositor
