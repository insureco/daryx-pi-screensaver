# daryx-pi-screensaver

Touch-to-wake screensaver with clock dashboard for Raspberry Pi touchscreen running Wayland/labwc.

## Features

- **Clock Dashboard** - Clean time display with Exo 2 font
- **Three States** - Desktop → Clock → Dimmed
- **Touch Navigation** - Touch to cycle through states
- **Zero Dependencies** - Pure Python, no pip installs needed

## The Problem This Solves

On Raspberry Pi with DSI touchscreen running Wayland:
- Setting `brightness=0` completely disables the touch controller
- No way to wake the screen without a keyboard
- Traditional screensavers (xscreensaver, swaylock) don't work well

## The Solution

- Keep brightness at minimum (1) instead of 0
- Display fullscreen black page via Chromium kiosk
- Touch triggers HTTP endpoint to wake

## How It Works

```
Desktop ──(5 min idle)──► Clock ──(5 min idle)──► Dimmed
   ▲                        │                        │
   └────────(touch)─────────┘                        │
                            ▲                        │
                            └───────(touch)──────────┘
```

## Installation

### 1. Set up backlight permissions

```bash
sudo cp 99-backlight.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
```

### 2. Copy files

```bash
cp screen-server.py ~/screen-server.py
cp clock.html ~/clock.html
chmod +x ~/screen-server.py
```

### 3. Configure autostart

```bash
mkdir -p ~/.config/labwc
cp labwc-autostart ~/.config/labwc/autostart
```

### 4. Reboot or start manually

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

## API Endpoints

| Endpoint | Action |
|----------|--------|
| `/clock` | Serves clock HTML |
| `/black` | Serves black overlay |
| `/wake` | Transition: dimmed → clock |
| `/to-desktop` | Transition: clock → desktop |
| `/status` | Returns current state |

## Testing

```bash
curl http://localhost:8888/status    # Check current state
curl http://localhost:8888/wake      # Show clock
curl http://localhost:8888/to-desktop # Back to desktop
```

## Customizing the Clock

Edit `clock.html` to change:
- Font (currently Exo 2 from Google Fonts)
- Colors and layout
- Add weather, calendar, etc.

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
```

## License

MIT
