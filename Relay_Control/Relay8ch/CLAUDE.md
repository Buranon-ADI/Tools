# Relay 8ch Control

Multi-board 8-channel relay control via Arduino Nano over serial (9600 baud).
Supports up to 4 boards differentiated by hardware address pins.

## Hardware Address

Two pins (D14/A0, D15/A1) with INPUT_PULLUP set the board address:

| D14 (A0) | D15 (A1) | Address |
|-----------|-----------|---------|
| GND       | GND       | 0       |
| Float     | GND       | 1       |
| GND       | Float     | 2       |
| Float     | Float     | 3       |

## Pin Configuration

- Pins D2-D9: active-low relay outputs (HIGH = off, LOW = on)
- Pins D14-D15: address input (INPUT_PULLUP, jumper to GND for LOW)
- Startup state: all relay pins HIGH (relays off)

## Serial Protocol

| Command  | Action                         |
|----------|--------------------------------|
| `D2_L`   | Set pin D2 LOW (relay on)      |
| `D2_H`   | Set pin D2 HIGH (relay off)    |
| `D3_L`...`D9_L` | Set pin LOW (relay on)   |
| `D3_H`...`D9_H` | Set pin HIGH (relay off) |
| `*IDN?`  | Returns `8Ch Relay Control,<addr>` |

Commands are newline-terminated (`\n`). Format: `D<pin>_<L|H>` where pin is 2-9.

## Interlock

Pins can be assigned to interlock groups (1-8). Pins in the same group cannot be ON simultaneously. Two modes:

- **Block**: Refuses to turn on a pin if another in the same group is already on.
- **Auto-off**: Turns off conflicting pins, waits configurable delay, then turns on the requested pin.

Settings (mode, delay) and per-pin interlock groups are saved in `channels.csv`.

## Files

| File                         | Description                              |
|------------------------------|------------------------------------------|
| `arduino_code/arduino_code.ino` | Arduino Nano sketch (with address pins) |
| `gui.py`                     | Tkinter GUI, all boards on one page       |
| `example.py`                 | CLI script with multi-board commands      |
| `channels.csv`               | Saved config (notes, delays, interlocks)  |

## Requirements

- Python 3.x
- `pyserial` (`pip install pyserial`)

## Usage

```
python gui.py
python example.py
```

### CLI command format

```
0:D2_L      # Board 0, pin D2 ON
1:D5_H      # Board 1, pin D5 OFF
D3_L        # Board 0 (default), pin D3 ON
```

## Troubleshooting

### CH340 ghost device blocking COM port

The CH340 on a USB hub port can be blocked by a phantom device stuck with Code 43
(device descriptor request failed). Windows enumerates a ghost `USB\VID_0000&PID_0002`
on the same port, preventing the CH340 from initializing.

Fix (run as admin):

```powershell
pnputil /remove-device 'USB\VID_0000&PID_0002\6&3C021F3&0&1'
pnputil /restart-device 'USB\VID_05E3&PID_0610\5&2a506e64&0&4'
```

First command removes the stuck phantom device, second restarts the parent Genesys Logic
hub to force re-enumeration -- no physical replug needed.
