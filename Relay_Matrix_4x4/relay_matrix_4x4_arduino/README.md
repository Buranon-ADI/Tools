# Relay Matrix 4x4 -- Arduino Nano Firmware

Sketch: `relay_matrix_4x4_arduino.ino`
Controls 4x4 relay matrices (K1-K16) via MCP23017 I/O expanders over I2C, plus relay K17 (DAC1 injection) via D2.
Serial: 115200 baud, commands terminated with CR or LF.

## Arduino Pins

| Pin    | Function                                    | Configured by               |
|--------|---------------------------------------------|-----------------------------|
| A4     | I2C SDA (4.7k pull-up R5)                   | `Wire.begin()`              |
| A5     | I2C SCL (4.7k pull-up R3)                   | `Wire.begin()`              |
| D8     | MCP23017 `RESET#` (10k pull-up), active low | `pinMode(8, OUTPUT)`        |
| D2     | K17 drive via Q2 (2N7002), active high      | `pinMode(2, OUTPUT)`        |
| D0/D1  | USB serial RX/TX                            | `Serial.begin(115200)`      |

Not used by the sketch: D6 (DAC1), D9 (DAC2), A0 (input current sense).

## MCP23017 Addressing

7-bit address = `0100 A2 A1 A0`. A2/A1/A0 are set by jumpers H6/H5/H3 (GND = 0, +5V = 1).

| Dev | A2 A1 A0 | I2C Addr |
|-----|----------|----------|
| 0   | 0 0 0    | 0x20     |
| 1   | 0 0 1    | 0x21     |
| ... | ...      | ...      |
| 7   | 1 1 1    | 0x27     |

Up to 8 devices (0-7). The bus is scanned at startup and on `SCAN`.

## GPIO to Relay Mapping (per device)

GPIO high -> ULN2803 sinks coil -> relay closed.
State is a 16-bit word: bit n = relay K(n+1), low byte = GPA, high byte = GPB.

| Row  | C1         | C2         | C3         | C4         |
|------|------------|------------|------------|------------|
| ROW1 | GPA0 / K1  | GPA1 / K2  | GPA2 / K3  | GPA3 / K4  |
| ROW2 | GPA4 / K5  | GPA5 / K6  | GPA6 / K7  | GPA7 / K8  |
| ROW3 | GPB0 / K9  | GPB1 / K10 | GPB2 / K11 | GPB3 / K12 |
| ROW4 | GPB4 / K13 | GPB5 / K14 | GPB6 / K15 | GPB7 / K16 |

Path: GPAx -> H10 jumper -> P0x_ULN -> U5 -> IO_cr. GPBx -> H11 jumper -> P1x_ULN -> U6 -> IO_cr.
(IO_cr: c = column, r = row.)

## Serial Commands

`d` = device 0-7. If omitted, defaults to device 0 (except `GET` / `ALLOFF`, which apply to all devices).

| Command        | Example   | Action                                              |
|----------------|-----------|-----------------------------------------------------|
| `[d]A<p><l>`   | `3A01`    | Set GPA\<p\> (0-7) on device d to level l (0/1)     |
| `[d]B<p><l>`   | `B30`     | Set GPB\<p\> (0-7) on device d to level l (0/1)     |
| `ON r c [d]`   | `ON 2 3`  | Close relay at row r, column c (1-4)                |
| `OFF r c [d]`  | `OFF 2 3` | Open relay at row r, column c                       |
| `K n l [d]`    | `K 16 1`  | Set relay Kn (1-16) to l (0/1)                      |
| `SET hhhh [d]` | `SET 8001`| Write 16-bit hex mask (bit0 = K1)                   |
| `PULSE n ms [d]` | `PULSE 3 50` | Close Kn (1-17) for ms (1-60000), then open; reply sent at pulse end |
| `ALLOFF [d]`   | `ALLOFF`  | Open all relays; no d = all devices + K17           |
| `GET [d]`      | `GET`     | Read back OLAT/GPIO, print matrix; no d = all + K17 |
| `K17 0\|1`     | `K17 1`   | Open/close K17 (DAC1 -> sig_in_4)                   |
| `SCAN`         | `SCAN`    | Rescan 0x20-0x27; init newly found devices          |
| `INIT`         | `INIT`    | Pulse D8 reset, rescan, reinit all devices          |
| `*IDN?`        | `*IDN?`   | Print firmware ID: `relay_matrix_v1.0`              |
| `HELP` / `?`   | `HELP`    | Print command list                                  |

Commands are case-insensitive. Replies start with `OK` or `ERR:` (except `*IDN?`, `GET`, `SCAN`, `HELP`).

Example replies:

```
OK 0 GPA0 HIGH
OK 2 0010
OK K17 CLOSED
OK PULSE 0 K3 50
ERR: dev 5 not present (SCAN)
```

`PULSE` blocks the Nano for the pulse duration; commands sent meanwhile are buffered and run afterwards.
Pin on-time = ms + one I2C write (~90 us at 400 kHz) for K1-K16; K17 (D2) has no I2C overhead.
`PULSE 17` ignores `d`.

Scan output:

```
  | Dev | Addr | Status   |
  |-----|------|----------|
  | 0   | 0x20 | INIT     |
  | 1   | 0x21 | --       |
```

Status: `INIT` = found and initialised (all off), `OK` = already present, state kept,
`LOST` = previously present, no longer responding, `--` = not present.

## Initialisation Sequence

1. D2 driven LOW (K17 open) -- first action in `setup()`.
2. D8 held HIGH, then pulsed LOW for 1 ms (hardware reset).
3. For each responding address 0x20-0x27:
   - `IOCON = 0x00` (BANK = 0, sequential addressing)
   - `OLATA/OLATB = 0x0000` (latch all-off before enabling outputs)
   - `IODIRA/IODIRB = 0x0000` (all outputs)

Registers used (BANK = 0): IODIRA 0x00, IOCON 0x0A, GPIOA 0x12, OLATA 0x14.

## Hardware Notes

- **K17 / R47 pull-up:** R47 (10k) pulls the Q2 gate up, so K17 closes (DAC1 connected to row 4)
  whenever D2 is not driven -- during power-up and the Nano bootloader (~1-2 s after reset).
  The sketch drives D2 LOW as early as possible, but cannot cover the bootloader window.
  Recommended fix: change R47 to a pull-down (to GND).
- **Open-drain on D2 is not needed:** Nano and pull-up share +5V, and Q2 is a low-side NMOS
  (high = on). Push-pull is correct.
- **D8 reset scope:** D8 only resets the MCP23017 whose `RESET#` is wired to it. The relay board
  headers do not carry reset; other devices are forced all-off by I2C writes during init.
- **Compilation:** sketch has not been compiled in this environment (no `arduino-cli`). Verify in the Arduino IDE.
