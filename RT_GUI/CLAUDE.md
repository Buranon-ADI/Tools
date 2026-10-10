# RT_GUI Project

## Overview
VK87 Real-Time Status Monitor GUI — a CustomTkinter desktop app that connects to a VK87 multiphase voltage regulator controller via PMBus and displays live status register readbacks as LED indicators. Includes a log window and LED conditions reference.

## Architecture
Single-file GUI app (`VK87_RT_GUI.py`) with two window classes:
- `StatusMonitorGUI` — main window with register LED strips, log panel, and controls
- `LEDConditionsWindow` — CTkToplevel reference showing all bit conditions (green/red/gray)

### Key registers (display order top to bottom)
- **0x00** (PAGE) — PASS/FAIL check per rail (readback vs expected page)
- **0x78** (STATUS_BYTE) — 1-byte Read, Paged. All 8 bits have LEDs.
- **0x79** (STATUS_WORD) — 2-byte Word Read, Paged. High byte displayed (8 bits); low byte shown as text.
- **0x7A** (STATUS_VOUT) — 1-byte Read, Paged. Bits 7,4,3 active; rest unused.
- **0x7B** (STATUS_IOUT) — 1-byte Read, Paged. Bits 7,5,3 active; rest unused.
- **0x7C** (STATUS_INPUT) — 1-byte Read, Unpaged. Bits 4,3,1 active; rest unused.
- **0x7D** (STATUS_TEMPERATURE) — 1-byte Read, Paged. Bits 7,6 active; rest unused.
- **0x7E** (STATUS_CML) — 1-byte Read, Unpaged. Bits 7,6,5,1 active; rest unused.
- **0x80** (STATUS_MFR_SPECIFIC) — 1-byte Read, Unpaged. Bits 3,2,1,0 active; rest unused.
- **0xF9** (Status Monitoring) — 4-byte Block Read, Paged. Parsed per-byte into individual fault/status bits.

### LED color logic
- `STATUS_BITS` (pwrgd, system_on, vr_settled, oen_filt, vddh_uvlob_fault): green = 1, red = 0
- Fault bits: red = 1, green = 0
- Unused/reserved bits: gray = 0 (expected), red = 1 (unexpected)

### Hardware communication
- Uses `instrument.Controller` with `auto_detect=False`, `page_mode = True`
- `auto_detect=True` does NOT work for VK87 (ADPV0316A.01) — device not in detection list
- Must write page 0 via raw `write_byte(register=0x00, data=0)` before any library call that uses `rail_A_is_selected()` (validates page <= 1)
- `pmbus.read_word(merge=True)` returns single int instead of list of Hexadecimal objects
- `pmbus.set_page(n)` writes page without validation — use for reading all 4 rails
- `pmbus.get_address_A()` returns the configured address (no `default_addresses` attribute)

### Log window
- Scrollable textbox below the controls section
- Shows timestamped readback data for all rails per refresh cycle
- Clear button to reset log content

### LED Conditions window
- Opened via yellow "LED Conditions" button in the connection bar
- Frozen header row with scrollable table body
- Built from Python code definitions (no CSV dependency at runtime)
- Reference CSV (`RT_GUI_LED_Reference.csv`) also available as external document

## Dependencies
- Python 3.13
- `customtkinter` — GUI framework (light theme)
- `instrument` — internal hardware communication package (installed in user site-packages)

## Running
```
python VK87_RT_GUI.py
```
Requires USB dongle connected to VK87 controller hardware. Address defaults to 0x40 if left blank.

## Conventions
- Window geometry: 1050x800, light theme
- Horizontal strip layout: one strip per register byte, with inline raw hex and LED indicators
- Fault names displayed in UPPERCASE with `_fault` suffix stripped
- All register reads iterate all 4 rails, then page is reset to the currently selected tab
- Unused bits use unique names like `0x7A_unused_6` to avoid LED key collisions
- Red warning label above controls: "This GUI is not fully tested yet..."
