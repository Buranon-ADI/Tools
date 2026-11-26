# Test Instrument Control GUI

## Overview
A tkinter-based GUI for controlling lab test instruments via PyVISA/SCPI. Single file app (`Test_Instrument_Control_GUI.py`) with a config file (`device_config.txt`) for auto-detection.

## Architecture
- **Class**: `InstrumentGUI` — single class containing all logic
- **Framework**: tkinter with ttk widgets
- **Communication**: PyVISA (`pyvisa.ResourceManager`) for all instrument I/O
- **Tabs** (in order): Power Supply, Waveform Generator, Oscilloscope, Electronic Load, DAQ, SCPI Low Level

## Startup Flow
1. Main window created but hidden (`withdraw`)
2. VISA resources scanned
3. `auto_detect_devices()` — shows progress window, queries `*IDN?` on each resource, matches against `device_config.txt` model keywords (exact field match, case-insensitive)
4. Scrollable summary dialog (550x450) shown with [PASS]/[FAIL] per device (green/red)
5. Tabs created
6. `apply_detected_devices()` — sets combo boxes and ID labels from detection results
7. Main window shown (`deiconify`)

## Instruments & Tabs
| Tab | Instrument | Model | Combo/Label vars |
|-----|-----------|-------|-----------------|
| High Power Supply | Keysight N8734A | N8734A | `n8734a_combo`, `n8734a_id_label` |
| Power Supply | Keysight E36311A (2-ch used) | E36311A | `psu_combo`, `psu_id_label` |
| Waveform Generator | Keysight 33500B series | 33511B | `wg_combo`, `wg_id_label` |
| Oscilloscope | Tektronix MDO34 | MDO34 | `scope_combo`, `scope_id_label` |
| Electronic Load | KIKUSUI PLZ664WA | PLZ664WA | `eload_combo`, `eload_id_label` |
| DAQ | Keysight DAQ973A + DAQM909A | 34972A (IDN) | `daq_combo`, `daq_id_label` |
| SCPI Low Level | Any device | N/A | `device_combo`, `device_id_label` |

## Key Files
- `Test_Instrument_Control_GUI.py` — entire application (~1700 lines)
- `device_config.txt` — auto-detect config, format: `tab_name=MODEL_KEYWORD` (one per line, `#` comments)
- `multi_res.ico` — app icon
- `ADTH Bench Control GUI.spec` — PyInstaller spec for building the exe

## Building & Distribution
```bash
pyinstaller "ADTH Bench Control GUI.spec" --noconfirm
```
Output: `dist/ADTH Bench Control GUI.exe`

**Distribution**: ship `device_config.txt` next to the exe (same folder). The app uses `os.path.dirname(sys.executable)` when frozen to locate the config file beside the exe, and `os.path.dirname(__file__)` in development.

## Electronic Load (ELoad) Features
- Inner class `ELoad` with methods: `measure_voltage`, `measure_current`, `measure_power`, `set_current`, `read_current_setting`, `set_cv`, `turn_on`, `turn_off`, `toggle_output`
- **Undervoltage protection**: ON and Toggle check voltage against `eload_uv_threshold_var` before enabling load
- **Current setting readback**: reads `:CURR?` from device after setting, plus a "Read" button
- **Auto-readback**: periodic voltage/current measurement display (configurable interval)
- `_eload_toggle_thread` is a top-level method (not inside ELoad class) — turns ON, waits delay, turns OFF

## Power Supply (E36311A) Features
- 2 channels used (Ch1: VREN 3V, Ch2: Vin 12V)
- Per-channel: set voltage, set current limit, output ON/OFF
- Readback voltage/current per channel
- Auto-readback with configurable interval
- Model validation on commands (warns if IDN doesn't contain "E36311A")

## Waveform Generator Features
- Set voltage HIGH/LOW (mV), frequency (kHz), pulse width (us)
- Toggle output with delay (ON -> wait -> OFF)
- Load current calculator (voltage / ratio)

## Oscilloscope Features
- Horizontal scale control (increase/decrease by 2x)
- Run/Stop/Single/Sequence modes
- Trigger: Auto/Normal
- Screenshot save (PNG via HARDCOPY)
- Waveform save to reference
- Annotation display

## DAQ Tab (DAQ973A + DAQM909A)
- **Auto-detect keyword**: `DAQ973A`
- **3 slots**, each with 4 channels: Slot1=101–104, Slot2=201–204, Slot3=301–304
- **Per-channel config**: Range (18V default), Input Type (DIFF/SEND/IEPE), Coupling (DC/AC), Mode (TIME/FREQ), Rate (Sa/s dropdown), Samp Count (entry, default 512)
- **Acquire flow**: `ACQ3:VOLT` → `INIT3` → `*OPC?` → `FETCh3:STATistics? 1,1,256,(@ch)` → returns avg/std_dev/min/max
- **Samp count**: blank entry falls back to `DEF` (512) — avoids `-222 Data out of range` error with value `1`
- **Per-channel Acquire button** + **Acquire All SlotN** button per slot
- **Initialize SlotN** button — sends `INIT3 (@N01,N02,N03,N04)` without configuring or fetching
- **Check Connected Modules** button — queries `SYSTem:CTYPe? 1/2/3`; Slot2/3 widgets enabled only if DAQM909A detected
- **`SYSTem:CTYPe?` response format**: `Manufacturer,Model,Serial,FW` — model field `0` = empty slot
- **Slot status labels**: green `Slot N: DAQM909A` if supported, red `No module found` if empty, red `Model X is not supported` otherwise
- **Acquire operations run in daemon threads**; results posted via `root.after(0, ...)`
- **DAQ-specific vars**: `daq_ch_range`, `daq_ch_input_type`, `daq_ch_coupling`, `daq_ch_mode`, `daq_ch_rate`, `daq_ch_samp_count`, `daq_ch_results` — all keyed by channel number
- **Slot widget lists**: `daq_slot2_widgets`, `daq_slot3_widgets` — used to bulk enable/disable on module check

## High Power Supply (N8734A) Features
- **Persistent connection**: uses `self.n8734a_inst` (open_resource kept open) for frequent status queries
- Connect/Disconnect buttons control the session lifecycle
- Set voltage, current, OVP (over-voltage protection), UVL (under-voltage limit)
- Output ON/OFF with LED indicator (green=on, gray=off)
- CV/CC mode LEDs from `STAT:OPER:COND?` (bit 8=CV, bit 10=CC)
- OCP ON/OFF with LED from `CURR:PROT:STAT?`
- Fault LEDs: OV(1), OC(2), PF(4), OT(16), INH(512), UNR(1024) from `STAT:QUES:COND?`
- Clear and OFF button: `OUTP:PROT:CLE` + `OUTP OFF`
- Check Limits popup: queries OVP/UVL/Vmax/Imax/OCP state
- Auto-readback (1s interval): measures V/I, calculates power, updates all LEDs
- Auto-detect config key: `high_power_supply=N8734A`
- All methods prefixed `n8734a_`

## Common Patterns
- All SCPI communication uses `with self.rm.open_resource(resource) as inst:` with 3000ms timeout (except N8734A which keeps a persistent connection)
- Response boxes are `tk.Text` widgets (disabled state, use `show_response`/`clear_response`)
- Device selection per tab via `ttk.Combobox` bound to `self.resources`
- `refresh_devices(combobox)` rescans VISA resources
- `query_idn(resource, label)` queries `*IDN?` and updates label
- Threading used for operations with delays (toggle functions)
- Scrollable tabs via `_make_scrollable_tab()` with mousewheel bound on Enter/Leave

## v2 Architecture (`Test_Instrument_Control_GUI_v2.py`)

A rewrite using ttkbootstrap (darkly theme) with a multi-window design instead of tabs.

### Dependencies
- `ttkbootstrap` (replaces raw tkinter/ttk)
- `pyvisa`, a VISA backend (NI-VISA or pyvisa-py)

### Class Structure
| Class | Role |
|-------|------|
| `DeviceDetector` | Pure scan logic — iterates VISA resources, matches `*IDN?` fields against config keywords |
| `DetectProgressWindow` | Modal progress bar during scan (threaded) |
| `DetectSummaryWindow` | PASS/FAIL results with per-device "Open" button; stays open so user can launch multiple device windows |
| `HighPowerSupplyWindow` | Standalone N8734A control (persistent connection, V/I set, OVP/UVL, LEDs, auto-readback, monitor graph) |
| `MonitorGraphWindow` | Real-time matplotlib V/I graph for N8734A (opened from HighPowerSupplyWindow) |
| `PowerSupplyWindow` | Standalone E36311A control (2-ch voltage/current, output ON/OFF, auto-readback) |
| `WaveformGeneratorWindow` | Standalone 33500B control (HIGH/LOW/Freq/PW params, output toggle with delay, load current calculator) |
| `OscilloscopeWindow` | Standalone MDO34 control (Notebook: Controls + Channel Labels tabs) |
| `ElectronicLoadWindow` | Standalone PLZ664WA control |
| `DAQWindow` | Standalone DAQ973A control |
| `QuickActionsWindow` | Standalone consolidated control panel — own VISA connections, power/waveform/scope controls |
| `InstrumentGUIv2` | App orchestrator — detection flow, summary, device window dispatch |

### Startup Flow
1. `InstrumentGUIv2.__init__` — creates hidden ttkbootstrap Window (1100x750), inits VISA RM, loads config
2. `_run_detection()` (via `after(100)`) — branches on missing config / no resources / normal scan
3. `DetectProgressWindow` — threaded scan with progress bar
4. `DetectSummaryWindow` — user clicks "Open" per device (launches standalone window) or "Continue" (shows main)
5. `_show_main()` — deiconifies main window (tabs TODO)

### Device Window Dispatch (`_open_device_window`)
- `high_power_supply` → `HighPowerSupplyWindow`
- `power_supply` → `PowerSupplyWindow`
- `waveform_generator` → `WaveformGeneratorWindow`
- `oscilloscope` → `OscilloscopeWindow`
- `electronic_load` → `ElectronicLoadWindow`
- `data_acquisition` → `DAQWindow`

### System Manager (in DetectSummaryWindow)
- **Purpose**: auto-shutdown safety — prevents instruments running unattended with high current draw
- **Location**: Labelframe at top of DetectSummaryWindow, above device list
- **Requires**: both `high_power_supply` and `waveform_generator` detected; section disabled otherwise
- **Own VISA connections** (`sm_inst_hps`, `sm_inst_wg`) — independent of device windows
- **Condition**: N8734A output ON AND `MEAS:CURR?` > threshold AND waveform generator `OUTP?` == 1
- **Timer**: resets if either condition drops on any poll; triggers shutdown when continuously met for X minutes
- **Shutdown action**: sends `OUTP OFF` to both instruments, stops monitor, shows warning popup
- **Config entries** (defaults): current threshold 2A, time threshold 10 min, poll interval 30s
- **Status label**: "Stopped" / "Monitoring..." / "Conditions met: X.X / Y min"
- **Cleanup**: `_on_close` stops monitor and closes VISA sessions when summary window is closed

### Key Design Decisions
- Summary window stays open after "Open" click — allows launching multiple device windows
- "Open" button auto-connects the device (calls `_connect()` on the window)
- Each device window is self-contained with its own SCPI helpers (`_scpi_write`/`_scpi_query`)
- Threaded operations for anything with delays (toggle output)
- `time` import is local inside `_toggle_thread` to keep module-level imports clean
- **PLZ664WA USB hang**: the load can wedge inside NI-VISA (ignores VISA timeout) after a session is closed with an unread reply or after `clear()`. Never call `clear()` on it. `DeviceDetector` probes each resource in a thread (`PROBE_TIMEOUT_S` = 6) and lists hung ones in a warning; `ElectronicLoadWindow._connect` runs in a thread (`CONNECT_TIMEOUT_S` = 6), retries fast errors only (`CONNECT_RETRIES` = 2, `RETRY_DELAY_MS` = 1000), never retries a timeout; `_shutdown` (Disconnect/close) waits for a running toggle, sends `:INP OFF`, then closes

### Oscilloscope — Channel Labels Tab
- Scope window uses a `ttk.Notebook` with two tabs: "Controls" (all existing controls) and "Channel Labels"
- **Channel Labels tab** has three sections:
  - **Analog (CH1–4)**: entry + per-channel "Apply" button (writes `CH<x>:LABel "<text>"`)
  - **Digital (D0–15)**: 2-column grid (D15–D8 left, D7–D0 right), "Read Digital Labels" + "Apply All Digital Labels" buttons
  - **Reference (REF1–4)**: entry + per-channel "Apply" button (writes `REF<x>:LABel "<text>"`)
- **Read buttons** per section: queries `CH<x>:LABel?` / `D<x>:LABel?` / `REF<x>:LABel?`
- Labels propagate to comboboxes on Controls tab as `"CH1 - VOUT"` format
- SCPI commands use raw channel ID extracted via `_get_channel_id()`
- Status label (`lbl_status`) at bottom of Channel Labels tab for feedback

### Quick Actions Window (titled "Frequent Use")
- **Standalone window** with own VISA connections — does not depend on individual device windows
- Launched from DetectSummaryWindow ("Frequent Use" button) or main window; class name is still `QuickActionsWindow`
- Receives `rm` (shared ResourceManager) and `detected` dict from `InstrumentGUIv2`
- **Connect All / Disconnect All** buttons; per-device status dots (green=connected, red=not)
- Connect All auto-reads all settings (V/I entries, waveform params) and runs initial readback
- `self.instruments` dict keyed by device name holds own VISA handles

#### Layout (single column, compact, scrollable)
- Fixed top: row 1 Connect All / Disconnect All, row 2 status dots; fixed bottom: status label
- Middle (Power Control, Waveform Generator, Oscilloscope) is a canvas + scrollbar (`_build_scroll_area`); mousewheel bound on the Toplevel only
- `_fit_window` sizes the window to `HEIGHT_SCALE` (0.7) of full content height
- `_compact()` runs after build: fonts to `FONT_SIZE` (7), button padding `BTN_PADDING`, frame/pack/grid padding x `PAD_SCALE`. Uses derived `QA.*` styles so other windows are unaffected
- **Power Control**: N8734A card stacked above E36311A card
  - N8734A: V/I readback, CV/CC LEDs + Readback button, V/I set entries, Read/ON/OFF/Clr+OFF/Graph buttons
  - E36311A: Ch1/Ch2 each with V/I readback, V/I set entries, Set/Read/ON/OFF buttons; Readback button at bottom
  - Read All Now (own row), then Auto Readback toggle + interval
  - Readback buttons (`_readback_n8734a`, `_readback_e36`) = measurements + output LEDs for one device; "Read" buttons = setpoints into entries
- **Waveform Generator**: ON/OFF/Delay/Toggle row; params in grid, 2 per row (HIGH/LOW, DC/Freq, Rise/Fall); load calc row; SR row with Calc Rise/Fall + Read (`_readback_wg` = params + output LED)
- **Oscilloscope**: RUN/STOP/SINGLE/Sequence, trigger Auto/Normal, remote access (Get IP / Open Browser)

#### SCPI Commands (direct, not via device windows)
| Button | SCPI |
|--------|------|
| N8734A ON/OFF | `OUTP ON` / `OUTP OFF` |
| N8734A Clear+OFF | `OUTP:PROT:CLE` then `OUTP OFF` |
| E36311A Ch ON/OFF | `OUTP ON, (@N)` / `OUTP OFF, (@N)` |
| WG ON/OFF | `OUTP ON` / `OUTP OFF` |
| WG Set HIGH | `:VOLT:HIGH {val} mV` |
| WG Set DC | `FUNC:PULS:DCYC {val}` |
| WG Set Freq | `FREQ {val} E3` |
| Scope RUN/STOP | `ACQuire:STATE RUN` / `ACQuire:STATE STOP` |
| Scope SINGLE | `ACQuire:STOPAfter SEQuence` |
| Trigger Auto/Normal | `TRIG:A:MODE AUTO` / `TRIG:A:MODE NORM` |

#### Fast Graph Polling
- **"Graph" button** opens `MonitorGraphWindow` AND starts a background thread (`_fast_poll_loop`)
- Thread queries `MEAS:VOLT?` / `MEAS:CURR?` every 100ms, posts to UI via `window.after(0, ...)`
- Skips `STAT:OPER:COND?` (CV/CC LEDs) during fast poll to reduce query time
- Normal `_read_n8734a` skips history append when fast poll is active (no duplicates)
- Thread auto-stops when graph window is closed (`is_alive()` check)
- Rolling buffer: 600 points (1 min at 10Hz)

### High Power Supply — Monitor Graph
- **"Monitor Graph" button** in readback section opens `MonitorGraphWindow`
- `MonitorGraphWindow`: matplotlib embedded via `FigureCanvasTkAgg`, dark theme
- Two subplots: voltage (teal `#00d4aa`) on top, current (orange `#ff9f43`) on bottom
- Data source: `monitor_history` dict (time/voltage/current lists) appended in `_update_readback`
- Rolling buffer: 300 points max
- Controls: "Clear" (resets history + max hold), "Pause/Resume" (toggles graph updates)
- **Max current**: stats line `Now | Max | Min | Avg | Hold`; dashed line + dot + label at max sample; `hold_max` survives buffer roll-off (Reset Max / Clear)
- On open, `MonitorGraphWindow(parent, history, inst)` reads `CURR?` into Limit(A) and `CURR:PROT:STAT?` into the OCP label (skipped if `inst` is None)
- **Limit(A)** entry (default 2.0 if not read, blank = off): red line, y-axis extended to include it, `Over: x.x s` accumulates time above limit; hold/over tracking continues while paused
- Max is of polled `MEAS:CURR?` averages -- fast WG load pulses are not captured
- Requires `matplotlib` (shows error if missing)
- Graph auto-updates each time `_update_readback` runs (tied to auto-readback interval)

## Running
```bash
python Test_Instrument_Control_GUI.py       # v1
python Test_Instrument_Control_GUI_v2.py    # v2
```
Requires: `pyvisa`, `tkinter` (stdlib), a VISA backend (NI-VISA or pyvisa-py). v2 additionally requires `ttkbootstrap` and `matplotlib`.
