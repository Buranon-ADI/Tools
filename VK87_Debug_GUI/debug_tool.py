"""
VK87 Debug Tool — Unified GUI for SFR, PMBus, and SVI3 register access.

Tabs:
  1. SFR Read/Write      (peek/poke via 0xFC/0xFD)
  2. PMBus Read/Write     (byte/word/block)
  3. SVI3 Read/Write      (register + telemetry)
  4. SVI3 Settings        (read-all decoded table)
  5. PMBus Fault Status   (LED decode for all status registers)
"""

import sys
import os
import csv
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from instrument import Controller
import customtkinter as ctk

# ---------------------------------------------------------------------------
# SFR Constants
# ---------------------------------------------------------------------------
SWI_RAIL = [2048, 2304, 2560, 2816, 3072]
SWI_RAIL_NAMES = ["Global", "Rail A", "Rail B", "Rail C", "Rail D"]

# ---------------------------------------------------------------------------
# SVI3 Register Maps (v3.12 Type 1)
# ---------------------------------------------------------------------------
RO_REGISTERS = {
    0x01: "SVI3_VERSION", 0x02: "TYPE_MFG_ID", 0x03: "MODEL_ID",
    0x04: "TEN_BIT_TEL_AVAIL", 0x05: "SIXTEEN_BIT_TEL_AVAIL",
    0x06: "CRC_EN_PSI_VID8", 0x07: "VID[7:0]",
    0x08: "DEFAULT_SLEW_VID_DEFAULT", 0x09: "SCALING",
    0x0A: "MAX_VOUT", 0x0B: "MIN_VOUT", 0x0C: "P_SYS_SCALE",
    0x0D: "DEFAULT_VID", 0x0E: "DEFAULT_LL", 0x0F: "FIRMWARE_ID",
}
SVI3_STATUS_REGISTERS = {0x10: "FAULT_STATUS", 0x11: "NACK_STATUS"}
WRITABLE_REGISTERS = {
    0x20: "SLEW_DECAY", 0x21: "LL_ADJUST", 0x22: "VOUT_OFFSET",
    0x23: "VID_MAX", 0x24: "VID_MIN", 0x25: "TEN_BIT_TEL_EN",
    0x26: "SIXTEEN_BIT_TEL_EN", 0x27: "OCP_THRESH",
    0x28: "OCP_WARN_THRESH", 0x29: "OCP_WARN_PULSE_DELAY",
    0x2A: "VRHOT_THRESH", 0x2B: "OTP_THRESH", 0x2C: "OVP_UVP_CONFIG",
    0x2D: "PHASE_SHED", 0x2E: "I_IN_WARN_THRESH",
}
TELEMETRY_REGISTERS = {
    0x30: "TEL_IOUT", 0x31: "TEL_VOUT", 0x32: "TEL_TEMP", 0x33: "TEL_POWER",
}
ALL_SVI3_REGISTERS = {**RO_REGISTERS, **SVI3_STATUS_REGISTERS, **WRITABLE_REGISTERS, **TELEMETRY_REGISTERS}

FAULT_STATUS_BITS = [
    (7, "reserved"), (6, "Phase Fault"), (5, "VRHOT"), (4, "OCP_WARN"),
    (3, "OTP"), (2, "UVP"), (1, "OVP"), (0, "OCP"),
]
NACK_STATUS_BITS = [
    (7, "reserved"), (6, "reserved"), (5, "Cmd before ACK"),
    (4, "Framing Error"), (3, "CRC Error"), (2, "Undefined Register"),
    (1, "Undefined Payload"), (0, "Not Executable"),
]

SVI3_FAULT_DEFS = {
    0x10: ("FAULT_STATUS", FAULT_STATUS_BITS),
    0x11: ("NACK_STATUS", NACK_STATUS_BITS),
}

V_IN_SCALE_MAP    = {0b00: "Custom", 0b01: "Custom", 0b10: "32V", 0b11: "64V"}
V_IN_SCALE_VALUES = {0: 8, 1: 16, 2: 32, 3: 64}
I_OUT_SCALE_MAP = {
    0b000: "Custom", 0b001: "32A", 0b010: "64A", 0b011: "128A",
    0b100: "256A", 0b101: "512A", 0b110: "1024A", 0b111: "2048A",
}
I_IN_SCALE_MAP = {
    0b000: "Custom", 0b001: "4A", 0b010: "8A", 0b011: "16A",
    0b100: "32A", 0b101: "64A", 0b110: "128A", 0b111: "256A",
}
IOUT_FS = [0, 32, 64, 128, 256, 512, 1024, 2048]
IIN_FS = [0, 4, 8, 16, 32, 64, 128, 256]

# ---------------------------------------------------------------------------
# PMBus Fault Status Bit Definitions
# ---------------------------------------------------------------------------
PMBUS_STATUS_REGISTERS = {
    0x78: ("STATUS_BYTE", "byte"),
    0x79: ("STATUS_WORD", "word"),
    0x7A: ("STATUS_VOUT", "byte"),
    0x7B: ("STATUS_IOUT", "byte"),
    0x7C: ("STATUS_INPUT", "byte"),
    0x7D: ("STATUS_TEMPERATURE", "byte"),
    0x7E: ("STATUS_CML", "byte"),
    0x80: ("STATUS_MFR_SPECIFIC", "byte"),
}

REGISTER_BIT_DEFINITIONS = {
    0x78: ("STATUS_BYTE", [
        (7, "unused"), (6, "off"), (5, "vout_ov_fault"), (4, "iout_oc_fault"),
        (3, "vin_uv_fault"), (2, "temperature"), (1, "cml"), (0, "none_of_the_above"),
    ]),
    0x7A: ("STATUS_VOUT", [
        (7, "vout_ov_fault"), (6, "unused_6"), (5, "unused_5"), (4, "vout_uv_fault"),
        (3, "vout_max_warning"), (2, "unused_2"), (1, "unused_1"), (0, "unused_0"),
    ]),
    0x7B: ("STATUS_IOUT", [
        (7, "iout_oc_fault"), (6, "unused_6"), (5, "iout_oc_warning"), (4, "unused_4"),
        (3, "current_share_fault"), (2, "unused_2"), (1, "unused_1"), (0, "unused_0"),
    ]),
    0x7C: ("STATUS_INPUT", [
        (7, "unused_7"), (6, "unused_6"), (5, "unused_5"), (4, "vin_uv_fault"),
        (3, "unit_off_insuff_vin"), (2, "unused_2"), (1, "iin_oc_warning"), (0, "unused_0"),
    ]),
    0x7D: ("STATUS_TEMPERATURE", [
        (7, "ot_fault"), (6, "ot_warning"), (5, "unused_5"), (4, "unused_4"),
        (3, "unused_3"), (2, "unused_2"), (1, "unused_1"), (0, "unused_0"),
    ]),
    0x7E: ("STATUS_CML", [
        (7, "invalid_cmd"), (6, "invalid_data"), (5, "pec_failed"), (4, "unused_4"),
        (3, "unused_3"), (2, "unused_2"), (1, "other_comm_fault"), (0, "unused_0"),
    ]),
    0x80: ("STATUS_MFR_SPECIFIC", [
        (7, "unused_7"), (6, "unused_6"), (5, "unused_5"), (4, "unused_4"),
        (3, "other_faults"), (2, "unprogrammed_rprog_fault"),
        (1, "user_config_max_rewrite_fault"), (0, "tsense_fault"),
    ]),
}

STATUS_WORD_BIT_DEFINITIONS = {
    "high": [
        (7, "vout"), (6, "iout_pout"), (5, "input"), (4, "mfr_specific"),
        (3, "power_good_n"), (2, "unused_2"), (1, "unused_1"), (0, "unused_0"),
    ],
    "low": [
        (7, "unused_7"), (6, "off"), (5, "vout_ov_fault"), (4, "iout_oc_fault"),
        (3, "vin_uv_fault"), (2, "temperature"), (1, "cml"), (0, "none_of_the_above"),
    ],
}

FAULT_LOG_0xF7_BITS = [
    (7, "slave_fault"), (6, "ot_fault"), (5, "always_0"), (4, "ocp_svi3"),
    (3, "OCL"), (2, "vddh_fault"), (1, "UVP"), (0, "OVP"),
]

STATUS_MONITOR_0xF9 = {
    0: [
        (7, "rsel_fault"), (6, "oen_filt"), (5, "slave_fault"), (4, "pwrgd"),
        (3, "vddh_uvlob_fault"), (2, "ocl_mincmp"), (1, "ocl_in"), (0, "ocp"),
    ],
    1: [
        (7, "num_sl_det[4]"), (6, "num_sl_det[3]"), (5, "num_sl_det[2]"),
        (4, "num_sl_det[1]"), (3, "num_sl_det[0]"), (2, "system_on"),
        (1, "vout_max_fault"), (0, "vr_settled"),
    ],
    2: [
        (7, "smaddr_fault"), (6, "vrhot"), (5, "isense2vdd_short"),
        (4, "startup_waiting_for_pwm_fault"), (3, "slv_uvlo_mask"),
        (2, "slave_population_fault"), (1, "slave_flt_startup"), (0, "pwm_open_fault"),
    ],
    3: [
        (7, "i_in_warn_flag_latch"), (6, "tlvr_fault"), (5, "wdog"), (4, "vddh_uvlo_latch"),
        (3, "sensep_open"), (2, "ocp_warn_svi3"), (1, "ecc_uncorr_err"),
        (0, "i_in_ocl_cmpout"),
    ],
}

ACTIVE_HIGH_GOOD = {"pwrgd", "oen_filt", "system_on", "vr_settled", "vddh_uvlob_fault"}

RAILS = ["A", "B", "C", "D"]

DEVICE_RAIL_COUNT = {
    "0316": 3,
}

TELEMETRY_MEASUREMENTS = [
    ("VOUT (V)", 0x8B, "vid",  "vout",  ".4f"),
    ("IOUT (A)", 0x8C, "l11",  "iout",  ".2f"),
    ("VIN (V)",  0x88, "l11",  "vin",   ".3f"),
    ("IIN (A)",  0x89, "l11",  None,    ".3f"),
    ("TEMP (C)", 0x8D, "l11",  "temp",  ".1f"),
    ("POUT (W)", 0x96, "l11",  None,    ".2f"),
    ("PIN (W)",  0x97, "l11",  None,    ".2f"),
]

# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------
COLOR_GREEN = "#27ae60"
COLOR_RED = "#e74c3c"
COLOR_GRAY = "#bdc3c7"
COLOR_DARK_BG = "#f0f2f5"
COLOR_CARD_BG = "#ffffff"
COLOR_TEXT = "#2c3e50"

# ---------------------------------------------------------------------------
# Decode Utilities
# ---------------------------------------------------------------------------

def decode_linear11(raw):
    exponent = (raw >> 11) & 0x1F
    if exponent >= 16:
        exponent -= 32
    mantissa = raw & 0x7FF
    if mantissa >= 1024:
        mantissa -= 2048
    return mantissa * (2 ** exponent)


def decode_vout(raw):
    return ((raw - 1) / 200 + 0.25) * 1000


def load_sfr_map():
    sfr_map = {}
    csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "sfr_map.csv")
    if not os.path.exists(csv_path):
        return sfr_map
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            page = int(row["page"])
            addr = int(row["addr"].replace("x", "0x"), 16)
            name = row["name"]
            array_addr = int(row["array_addr"])
            sfr_map[(page, addr)] = (name, array_addr)
    return sfr_map


def load_svi3_descriptions():
    desc = {}
    csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "svi3_registers.csv")
    if not os.path.exists(csv_path):
        return desc
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            reg = int(row["reg"], 16)
            desc[reg] = row["description"]
    return desc


# ---------------------------------------------------------------------------
# Main Application
# ---------------------------------------------------------------------------
class DebugToolApp:
    def __init__(self):
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.title("VK87 Debug Tool")
        self.root.geometry("1200x800")
        self.root.configure(fg_color=COLOR_DARK_BG)

        self.controller = None
        self.address = None
        self.device_name = ""
        self.fw_type = ""
        self.fw_signature = ""
        self.svi3_rails = ["A", "B"]
        self.svi3_version = ""
        self.pmbus_rails = RAILS[:]
        self.sfr_map = load_sfr_map()
        self.svi3_desc = load_svi3_descriptions()
        self.auto_refresh = False
        self.refresh_interval = 1000

        try:
            self._connect()
        except Exception as e:
            print(f"Connection failed: {e}")
            print("Check supply voltage and click Reconnect.")
        self._build_status_bar()
        self._build_tabs()
        self._build_log_panel()

    # ── Connection ─────────────────────────────────────────────────────────
    def _connect(self):
        self.controller = Controller()
        self.address = int(self.controller.pmbus.address.A)
        self.controller.page_mode = True
        self.controller.pmbus.write_byte(address=self.address, register=0x00, data=0)

        device_id = self.controller.pmbus.read_block(address=self.address, register=0xAD)
        self.device_name = "".join(chr(b) for b in device_id)
        self.pmbus_rails = self._detect_pmbus_rails()
        self.fw_signature = self.controller.get_firmware_signature()
        self.fw_type = self.controller.get_firmware_type()

        print(f"Controller: {self.device_name} at 0x{self.address:02X}")
        print(f"Firmware:   {self.fw_type} | {self.fw_signature}")
        if hasattr(self, "log_text"):
            self._log(f"Connected: {self.device_name} at 0x{self.address:02X} | FW: {self.fw_type} {self.fw_signature}")

        try:
            self.controller.svi3.reset()
            self.controller.svi3.initialize()
            addresses = self.controller.svi3.search()
            if len(addresses) >= 3:
                self.controller.svi3.address.C = addresses[2]
                if "C" not in self.svi3_rails:
                    self.svi3_rails.append("C")
            if len(addresses) >= 4:
                self.controller.svi3.address.D = addresses[3]
                if "D" not in self.svi3_rails:
                    self.svi3_rails.append("D")
            self.controller.svi3.reset()
            self.controller.svi3.initialize()
            try:
                data_0xC5 = self.controller.pmbus.read_block(address=self.address, register=0xC5)
                svi3_mode = (int(data_0xC5[0]) >> 6) & 0x03
                ver_name = {0b00: "v2.00", 0b01: "v3.12"}.get(svi3_mode, "unknown")
                self.svi3_version = f"0xC5_0[7:6]={svi3_mode:02b}b ({ver_name})"
                c5_hex = " ".join(f"0x{int(b):02X}" for b in data_0xC5)
                c5_msg = f"0xC5 ({len(data_0xC5)} bytes): [{c5_hex}]"
                print(c5_msg)
                if hasattr(self, "log_text"):
                    self._log(c5_msg)
            except Exception:
                self.svi3_version = "?"
            msg = f"SVI3: {len(addresses)} devices found ({', '.join(self.svi3_rails)}) {self.svi3_version}"
            print(msg)
            if hasattr(self, "log_text"):
                self._log(msg)
        except Exception as e:
            self.svi3_version = "N/A"
            msg = f"SVI3 init warning: {e}"
            print(msg)
            if hasattr(self, "log_text"):
                self._log(msg)

    def _set_page_checked(self, page, rail):
        self.controller.pmbus.set_page(page)
        readback = int(self.controller.pmbus.read_byte(address=self.address, register=0x00))
        if readback != page:
            self._log(f"Rail {rail}: set_page({page}) readback={readback} MISMATCH -- skipping")
            return False
        return True

    def _detect_pmbus_rails(self):
        for substr, count in DEVICE_RAIL_COUNT.items():
            if substr in self.device_name:
                return RAILS[:count]
        return RAILS[:]

    def _select_svi3_rail(self, rail):
        select = {
            "A": self.controller.svi3.select_rail_A,
            "B": self.controller.svi3.select_rail_B,
            "C": self.controller.svi3.select_rail_C,
            "D": self.controller.svi3.select_rail_D,
        }
        select[rail]()

    def _wake_svi3_rail(self, rail):
        self._select_svi3_rail(rail)
        try:
            self.controller.svi3.measure_output_voltage(split=True)
        except Exception:
            pass

    def _read_svi3_register(self, reg):
        try:
            return self.controller.svi3.read_register(reg)
        except Exception:
            return None

    def _disconnect(self):
        if self.controller is None:
            self._log("Already disconnected")
            return
        try:
            self.controller.disconnect()
            self._log("Disconnected from controller")
        except Exception as e:
            self._log(f"Disconnect error: {e}")
        self.controller = None
        self.address = None
        self.device_name = ""
        self.fw_type = ""
        self.fw_signature = ""
        self.svi3_rails = ["A", "B"]
        self.svi3_version = ""
        self.pmbus_rails = RAILS[:]
        self._update_status_bar()

    def _reconnect(self):
        self._log("Reconnecting...")
        try:
            if self.controller is not None:
                try:
                    self.controller.disconnect()
                except Exception:
                    pass
            self.svi3_rails = ["A", "B"]
            self.svi3_version = ""
            self._connect()
            self._update_status_bar()
            for rail in RAILS:
                default = "on" if rail in self.pmbus_rails else "off"
                if hasattr(self, "fault_rail_vars") and rail in self.fault_rail_vars:
                    self.fault_rail_vars[rail].set(default)
                if hasattr(self, "tel_rail_vars") and rail in self.tel_rail_vars:
                    self.tel_rail_vars[rail].set(default)
                if hasattr(self, "de_rail_vars") and rail in self.de_rail_vars:
                    self.de_rail_vars[rail].set(default)
                if hasattr(self, "svi3_settings_rail_vars") and rail in self.svi3_settings_rail_vars:
                    svi3_default = "on" if rail in self.svi3_rails else "off"
                    self.svi3_settings_rail_vars[rail].set(svi3_default)
            self._log(f"Reconnected: {self.device_name} at 0x{self.address:02X} | FW: {self.fw_type} {self.fw_signature}")
        except Exception as e:
            self._log(f"Reconnect failed: {e}")

    def _update_status_bar(self):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        addr_str = f"0x{self.address:02X}" if self.address is not None else "N/A"
        self.status_label.configure(
            text=f"{self.device_name} | FW: {self.fw_type} {self.fw_signature} "
                 f"| Addr: {addr_str} | SVI3: {', '.join(self.svi3_rails)} {self.svi3_version} | {now}"
        )

    # ── Status Bar ─────────────────────────────────────────────────────────
    def _build_status_bar(self):
        frame = ctk.CTkFrame(self.root, fg_color=COLOR_CARD_BG, corner_radius=10)
        frame.pack(fill="x", padx=10, pady=(10, 5))

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        addr_str = f"0x{self.address:02X}" if self.address is not None else "N/A"
        self.status_label = ctk.CTkLabel(
            frame,
            text=f"{self.device_name} | FW: {self.fw_type} {self.fw_signature} "
                 f"| Addr: {addr_str} | SVI3: {', '.join(self.svi3_rails)} {self.svi3_version} | {now}",
            font=("Consolas", 12), text_color=COLOR_TEXT,
        )
        self.status_label.pack(side="left", padx=15, pady=10)

        ctk.CTkButton(
            frame, text="Reconnect", width=90, height=28,
            font=("Segoe UI", 11), command=self._reconnect,
        ).pack(side="right", padx=15, pady=10)

        ctk.CTkButton(
            frame, text="Disconnect", width=90, height=28,
            font=("Segoe UI", 11), fg_color="#e74c3c", hover_color="#c0392b",
            command=self._disconnect,
        ).pack(side="right", padx=(0, 5), pady=10)

    # ── Tab Container ──────────────────────────────────────────────────────
    def _build_tabs(self):
        main_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=10, pady=5)

        sidebar = ctk.CTkFrame(main_frame, fg_color=COLOR_CARD_BG, corner_radius=10, width=150)
        sidebar.pack(side="left", fill="y", padx=(0, 5), pady=0)
        sidebar.pack_propagate(False)

        ctk.CTkLabel(sidebar, text="Actions", font=("Segoe UI", 11, "bold"),
                     text_color=COLOR_TEXT).pack(padx=10, pady=(10, 5))

        ctk.CTkButton(sidebar, text="0xB2_2[6] All Rails\nSPS No Handshake", width=130, height=40,
                      font=("Segoe UI", 9), fg_color="#8e44ad", hover_color="#7d3c98",
                      command=self._b2_precondition).pack(padx=10, pady=5)

        ctk.CTkButton(sidebar, text="0xB2_2[6] All Rails\nReset to 0", width=130, height=40,
                      font=("Segoe UI", 9), fg_color="#7f8c8d", hover_color="#6c7a89",
                      command=self._b2_reset).pack(padx=10, pady=5)

        ctk.CTkButton(sidebar, text="0xC5_0[7:6]\nSVI3 v2.00", width=130, height=40,
                      font=("Segoe UI", 9), fg_color="#2980b9", hover_color="#2471a3",
                      command=lambda: self._set_svi3_version(0b00)).pack(padx=10, pady=5)

        ctk.CTkButton(sidebar, text="0xC5_0[7:6]\nSVI3 v3.12", width=130, height=40,
                      font=("Segoe UI", 9), fg_color="#27ae60", hover_color="#219a52",
                      command=lambda: self._set_svi3_version(0b01)).pack(padx=10, pady=5)

        ctk.CTkButton(sidebar, text="Clear Fault\nAll Rails (0x03)", width=130, height=40,
                      font=("Segoe UI", 10), fg_color="#e67e22", hover_color="#cf6d17",
                      command=self._fault_clear).pack(padx=10, pady=5)

        self.tabview = ctk.CTkTabview(main_frame, fg_color=COLOR_DARK_BG)
        self.tabview.pack(side="left", fill="both", expand=True)

        self.tabview.add("Register R/W")
        self.tabview.add("Telemetry")
        self.tabview.add("SVI3 Settings")
        self.tabview.add("0xDE Settings")
        self.tabview.add("Fault Status")

        self._build_register_rw_tab(self.tabview.tab("Register R/W"))
        self._build_telemetry_tab(self.tabview.tab("Telemetry"))
        self._build_svi3_settings_tab(self.tabview.tab("SVI3 Settings"))
        self._build_de_settings_tab(self.tabview.tab("0xDE Settings"))
        self._build_fault_status_tab(self.tabview.tab("Fault Status"))

    # ── Log Panel ──────────────────────────────────────────────────────────
    def _build_log_panel(self):
        frame = ctk.CTkFrame(self.root, fg_color=COLOR_CARD_BG, corner_radius=10, height=240)
        frame.pack(fill="x", padx=10, pady=(0, 10))
        frame.pack_propagate(False)

        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(5, 0))
        ctk.CTkLabel(header, text="Log", font=("Segoe UI", 10, "bold"),
                     text_color=COLOR_TEXT).pack(side="left")
        ctk.CTkButton(header, text="Clear", width=50, height=24,
                      font=("Segoe UI", 9),
                      command=lambda: self.log_text.delete("0.0", "end")).pack(side="right")

        self.log_text = ctk.CTkTextbox(frame, font=("Consolas", 10), height=200,
                                        fg_color="#fafafa", text_color=COLOR_TEXT)
        self.log_text.pack(fill="both", expand=True, padx=10, pady=(2, 8))

    def _log(self, msg):
        now = datetime.now().strftime("%H:%M:%S")
        line = f"[{now}] {msg}\n"
        self.log_text.insert("end", line)
        self.log_text.see("end")
        print(msg)

    # ======================================================================
    # Combined Register R/W Tab
    # ======================================================================
    def _build_register_rw_tab(self, parent):
        scroll = ctk.CTkScrollableFrame(parent, fg_color=COLOR_DARK_BG)
        scroll.pack(fill="both", expand=True, padx=0, pady=0)

        self._add_section_label(scroll, "SFR Peek/Poke")
        sfr_frame = ctk.CTkFrame(scroll, fg_color=COLOR_CARD_BG, corner_radius=10)
        sfr_frame.pack(fill="x", padx=5, pady=(0, 5))
        self._build_sfr_controls(sfr_frame)

        self._add_section_label(scroll, "PMBus")
        pmbus_frame = ctk.CTkFrame(scroll, fg_color=COLOR_CARD_BG, corner_radius=10)
        pmbus_frame.pack(fill="x", padx=5, pady=(0, 5))
        self._build_pmbus_controls(pmbus_frame)

        self._add_section_label(scroll, "SVI3")
        svi3_frame = ctk.CTkFrame(scroll, fg_color=COLOR_CARD_BG, corner_radius=10)
        svi3_frame.pack(fill="x", padx=5, pady=(0, 5))
        self._build_svi3_controls(svi3_frame)

    def _add_section_label(self, parent, text):
        ctk.CTkLabel(parent, text=text, font=("Segoe UI", 12, "bold"),
                     text_color="#7f8c8d").pack(anchor="w", padx=10, pady=(8, 2))

    # ── SFR Controls ──────────────────────────────────────────────────────
    def _build_sfr_controls(self, top):
        row1 = ctk.CTkFrame(top, fg_color="transparent")
        row1.pack(fill="x", padx=10, pady=(10, 2))

        ctk.CTkLabel(row1, text="Page:", font=("Segoe UI", 11)).pack(side="left", padx=(0, 4))
        self.sfr_page_entry = ctk.CTkEntry(row1, width=50, font=("Consolas", 11),
                                            placeholder_text="0")
        self.sfr_page_entry.pack(side="left", padx=(0, 10))

        ctk.CTkLabel(row1, text="Addr (hex):", font=("Segoe UI", 11)).pack(side="left", padx=(0, 4))
        self.sfr_addr_entry = ctk.CTkEntry(row1, width=80, font=("Consolas", 11),
                                            placeholder_text="0x84")
        self.sfr_addr_entry.pack(side="left", padx=(0, 10))

        ctk.CTkButton(row1, text="Lookup", width=70, command=self._sfr_lookup).pack(side="left", padx=(0, 10))

        self.sfr_name_label = ctk.CTkLabel(row1, text="", font=("Consolas", 11),
                                            text_color="#2980b9")
        self.sfr_name_label.pack(side="left", padx=(5, 0))

        row2 = ctk.CTkFrame(top, fg_color="transparent")
        row2.pack(fill="x", padx=10, pady=2)

        ctk.CTkLabel(row2, text="Array Addr:", font=("Segoe UI", 11)).pack(side="left", padx=(0, 4))
        self.sfr_array_entry = ctk.CTkEntry(row2, width=80, font=("Consolas", 11),
                                             placeholder_text="86")
        self.sfr_array_entry.pack(side="left", padx=(0, 10))

        ctk.CTkButton(row2, text="Read", width=70, fg_color="#27ae60",
                      hover_color="#219a52", command=self._sfr_read).pack(side="left", padx=(0, 5))

        ctk.CTkLabel(row2, text="Write:", font=("Segoe UI", 11)).pack(side="left", padx=(10, 4))
        self.sfr_write_entry = ctk.CTkEntry(row2, width=80, font=("Consolas", 11),
                                             placeholder_text="0xFF")
        self.sfr_write_entry.pack(side="left", padx=(0, 5))

        ctk.CTkButton(row2, text="Write", width=70, fg_color="#e67e22",
                      hover_color="#cf6d17", command=self._sfr_write).pack(side="left")

        row3 = ctk.CTkFrame(top, fg_color="transparent")
        row3.pack(fill="x", padx=10, pady=(2, 10))

        ctk.CTkLabel(row3, text="SWI:", font=("Segoe UI", 11, "bold"),
                     text_color="#7f8c8d").pack(side="left", padx=(0, 4))
        self.swi_rail_var = ctk.StringVar(value="Global")
        ctk.CTkOptionMenu(row3, values=SWI_RAIL_NAMES, variable=self.swi_rail_var,
                          width=100).pack(side="left", padx=(0, 5))

        ctk.CTkLabel(row3, text="Offset:", font=("Segoe UI", 11)).pack(side="left", padx=(5, 4))
        self.swi_offset_entry = ctk.CTkEntry(row3, width=60, font=("Consolas", 11),
                                              placeholder_text="0x1E")
        self.swi_offset_entry.pack(side="left", padx=(0, 5))

        ctk.CTkButton(row3, text="Calc", width=50,
                      command=self._swi_calc).pack(side="left")

    def _sfr_lookup(self):
        try:
            page = int(self.sfr_page_entry.get() or "0")
            addr_str = self.sfr_addr_entry.get().strip()
            addr = int(addr_str, 16) if addr_str.startswith("0x") else int(addr_str, 16)
        except ValueError:
            self.sfr_name_label.configure(text="Invalid input")
            return

        entry = self.sfr_map.get((page, addr))
        if entry is None:
            self.sfr_name_label.configure(text=f"Not found: page {page}, 0x{addr:02X}")
            return

        name, array_addr = entry
        self.sfr_name_label.configure(text=f"{name} | array_addr = {array_addr}")
        self.sfr_array_entry.delete(0, "end")
        self.sfr_array_entry.insert(0, str(array_addr))

    def _sfr_read(self):
        try:
            array_addr = int(self.sfr_array_entry.get())
        except ValueError:
            self._log("SFR Read: invalid array_addr")
            return

        self.controller.pmbus.write_word(register=0xFC, data=array_addr)
        val = self.controller.pmbus.read_byte(register=0xFD)
        val = int(val)

        name = self._sfr_name_for(array_addr)
        line = f"SFR Read  [{name}]  array_addr={array_addr}  -> 0x{val:02X} ({val:08b}b)"
        self._log(line)

    def _sfr_write(self):
        try:
            array_addr = int(self.sfr_array_entry.get())
            write_str = self.sfr_write_entry.get().strip()
            data = int(write_str, 16) if write_str.startswith("0x") else int(write_str)
        except ValueError:
            self._log("SFR Write: invalid input")
            return

        self.controller.pmbus.write_word(register=0xFC, data=array_addr)
        self.controller.pmbus.write_byte(register=0xFD, data=data)

        self.controller.pmbus.write_word(register=0xFC, data=array_addr)
        readback = int(self.controller.pmbus.read_byte(register=0xFD))

        name = self._sfr_name_for(array_addr)
        match = "OK" if readback == data else "MISMATCH"
        line = (f"SFR Write [{name}]  array_addr={array_addr}  "
                f"wrote=0x{data:02X}  readback=0x{readback:02X}  {match}")
        self._log(line)

    def _swi_calc(self):
        rail_idx = SWI_RAIL_NAMES.index(self.swi_rail_var.get())
        try:
            offset_str = self.swi_offset_entry.get().strip()
            offset = int(offset_str, 16) if offset_str.startswith("0x") else int(offset_str)
        except ValueError:
            self._log("SWI Calc: invalid offset")
            return

        array_addr = SWI_RAIL[rail_idx] + offset
        self.sfr_array_entry.delete(0, "end")
        self.sfr_array_entry.insert(0, str(array_addr))
        self.sfr_name_label.configure(
            text=f"SWI {self.swi_rail_var.get()} + 0x{offset:02X} = {array_addr} (0x{array_addr:04X})")

    def _sfr_name_for(self, array_addr):
        for (page, addr), (name, aa) in self.sfr_map.items():
            if aa == array_addr:
                return f"{name} (p{page} 0x{addr:02X})"
        return f"addr {array_addr}"

    # ── PMBus Controls ────────────────────────────────────────────────────
    def _build_pmbus_controls(self, top):
        row1 = ctk.CTkFrame(top, fg_color="transparent")
        row1.pack(fill="x", padx=10, pady=(10, 2))

        ctk.CTkLabel(row1, text="Page:", font=("Segoe UI", 11)).pack(side="left", padx=(0, 4))
        self.pmbus_page_var = ctk.StringVar(value="0 (Rail A)")
        ctk.CTkOptionMenu(row1, values=["0 (Rail A)", "1 (Rail B)", "2 (Rail C)", "3 (Rail D)"],
                          variable=self.pmbus_page_var, width=120).pack(side="left", padx=(0, 10))

        ctk.CTkLabel(row1, text="Register:", font=("Segoe UI", 11)).pack(side="left", padx=(0, 4))
        self.pmbus_reg_entry = ctk.CTkEntry(row1, width=80, font=("Consolas", 11),
                                             placeholder_text="0x78")
        self.pmbus_reg_entry.pack(side="left", padx=(0, 10))

        ctk.CTkLabel(row1, text="Type:", font=("Segoe UI", 11)).pack(side="left", padx=(0, 4))
        self.pmbus_type_var = ctk.StringVar(value="byte")
        ctk.CTkOptionMenu(row1, values=["byte", "word", "block"],
                          variable=self.pmbus_type_var, width=80).pack(side="left")

        row2 = ctk.CTkFrame(top, fg_color="transparent")
        row2.pack(fill="x", padx=10, pady=(2, 2))

        ctk.CTkButton(row2, text="Read", width=80, fg_color="#27ae60",
                      hover_color="#219a52", command=self._pmbus_read).pack(side="left", padx=(0, 5))
        ctk.CTkButton(row2, text="Read All Rails", width=100, fg_color="#2980b9",
                      hover_color="#2471a3", command=self._pmbus_read_all_rails).pack(side="left", padx=(0, 10))

        ctk.CTkLabel(row2, text="Write Data:", font=("Segoe UI", 11)).pack(side="left", padx=(0, 4))
        self.pmbus_write_entry = ctk.CTkEntry(row2, width=200, font=("Consolas", 11),
                                               placeholder_text="0xFF or 0xAA 0xBB ...")
        self.pmbus_write_entry.pack(side="left", padx=(0, 5))

        ctk.CTkButton(row2, text="Write", width=80, fg_color="#e67e22",
                      hover_color="#cf6d17", command=self._pmbus_write).pack(side="left")

        row3 = ctk.CTkFrame(top, fg_color="transparent")
        row3.pack(fill="x", padx=10, pady=(2, 2))

        self.pmbus_linear11_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(row3, text="Linear11 decode", variable=self.pmbus_linear11_var,
                        font=("Segoe UI", 10)).pack(side="left", padx=(0, 15))

        self.pmbus_vid_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(row3, text="VID decode (VOUT)", variable=self.pmbus_vid_var,
                        font=("Segoe UI", 10)).pack(side="left")

        row4 = ctk.CTkFrame(top, fg_color="transparent")
        row4.pack(fill="x", padx=10, pady=(2, 10))

        ctk.CTkLabel(row4, text="Send Byte:", font=("Segoe UI", 11, "bold"),
                     text_color="#7f8c8d").pack(side="left", padx=(0, 8))

        ctk.CTkLabel(row4, text="Register:", font=("Segoe UI", 11)).pack(side="left", padx=(0, 4))
        self.pmbus_sb_reg_entry = ctk.CTkEntry(row4, width=80, font=("Consolas", 11))
        self.pmbus_sb_reg_entry.insert(0, "0x03")
        self.pmbus_sb_reg_entry.pack(side="left", padx=(0, 10))

        ctk.CTkButton(row4, text="Send Byte", width=80, fg_color="#8e44ad",
                      hover_color="#7d3c98", command=self._pmbus_send_byte).pack(side="left")

    def _pmbus_get_page(self):
        return int(self.pmbus_page_var.get()[0])

    def _pmbus_read(self):
        page = self._pmbus_get_page()
        try:
            reg_str = self.pmbus_reg_entry.get().strip()
            reg = int(reg_str, 16) if reg_str.startswith("0x") else int(reg_str)
        except ValueError:
            self._log("PMBus Read: invalid register")
            return

        self.controller.pmbus.set_page(page)
        dtype = self.pmbus_type_var.get()

        try:
            if dtype == "byte":
                val = int(self.controller.pmbus.read_byte(address=self.address, register=reg))
                line = f"PMBus Read  page={page} reg=0x{reg:02X} [byte] -> 0x{val:02X} ({val:08b}b) dec={val}"
                if self.pmbus_linear11_var.get():
                    pass
                if self.pmbus_vid_var.get():
                    pass

            elif dtype == "word":
                val = int(self.controller.pmbus.read_word(address=self.address, register=reg, merge=True))
                high = (val >> 8) & 0xFF
                low = val & 0xFF
                line = f"PMBus Read  page={page} reg=0x{reg:02X} [word] -> 0x{val:04X} (H=0x{high:02X} L=0x{low:02X})"
                if self.pmbus_linear11_var.get():
                    decoded = decode_linear11(val)
                    line += f"  Linear11={decoded:.4f}"
                if self.pmbus_vid_var.get():
                    decoded = decode_vout(val)
                    line += f"  VID={decoded/1000:.4f} V"

            elif dtype == "block":
                data = self.controller.pmbus.read_block(address=self.address, register=reg)
                hex_str = " ".join(f"0x{int(b):02X}" for b in data)
                line = f"PMBus Read  page={page} reg=0x{reg:02X} [block] -> [{hex_str}] ({len(data)} bytes)"

        except Exception as e:
            line = f"PMBus Read  page={page} reg=0x{reg:02X} ERROR: {e}"

        self._log(line)

    def _pmbus_read_all_rails(self):
        try:
            reg_str = self.pmbus_reg_entry.get().strip()
            reg = int(reg_str, 16) if reg_str.startswith("0x") else int(reg_str)
        except ValueError:
            self._log("PMBus Read All Rails: invalid register")
            return

        dtype = self.pmbus_type_var.get()
        rail_names = ["Rail A", "Rail B", "Rail C", "Rail D"]
        self._log(f"--- PMBus Read All Rails  reg=0x{reg:02X} [{dtype}] ---")

        for page in range(4):
            self.controller.pmbus.set_page(page)
            try:
                if dtype == "byte":
                    val = int(self.controller.pmbus.read_byte(address=self.address, register=reg))
                    line = f"  {rail_names[page]} (p{page}): 0x{val:02X} ({val:08b}b) dec={val}"
                    if self.pmbus_linear11_var.get():
                        pass
                    if self.pmbus_vid_var.get():
                        pass
                elif dtype == "word":
                    val = int(self.controller.pmbus.read_word(address=self.address, register=reg, merge=True))
                    high = (val >> 8) & 0xFF
                    low = val & 0xFF
                    line = f"  {rail_names[page]} (p{page}): 0x{val:04X} (H=0x{high:02X} L=0x{low:02X})"
                    if self.pmbus_linear11_var.get():
                        decoded = decode_linear11(val)
                        line += f"  Linear11={decoded:.4f}"
                    if self.pmbus_vid_var.get():
                        decoded = decode_vout(val)
                        line += f"  VID={decoded/1000:.4f} V"
                elif dtype == "block":
                    data = self.controller.pmbus.read_block(address=self.address, register=reg)
                    hex_str = " ".join(f"0x{int(b):02X}" for b in data)
                    line = f"  {rail_names[page]} (p{page}): [{hex_str}] ({len(data)} bytes)"
            except Exception as e:
                line = f"  {rail_names[page]} (p{page}): ERROR: {e}"

            self._log(line)
        self._log(f"PMBus Read All Rails  reg=0x{reg:02X} [{dtype}] done")

    def _pmbus_send_byte(self):
        page = self._pmbus_get_page()
        try:
            reg_str = self.pmbus_sb_reg_entry.get().strip()
            reg = int(reg_str, 16) if reg_str.startswith("0x") else int(reg_str, 16)
        except ValueError:
            self._log("PMBus Send Byte: invalid register")
            return

        self.controller.pmbus.set_page(page)
        try:
            self.controller.pmbus.send_byte(reg)
            line = f"PMBus Send Byte  page={page} reg=0x{reg:02X} -> OK"
        except Exception as e:
            line = f"PMBus Send Byte  page={page} reg=0x{reg:02X} -> ERROR: {e}"

        self._log(line)

    def _pmbus_write(self):
        page = self._pmbus_get_page()
        try:
            reg_str = self.pmbus_reg_entry.get().strip()
            reg = int(reg_str, 16) if reg_str.startswith("0x") else int(reg_str)
        except ValueError:
            self._log("PMBus Write: invalid register")
            return

        self.controller.pmbus.set_page(page)
        dtype = self.pmbus_type_var.get()
        write_str = self.pmbus_write_entry.get().strip()

        try:
            if dtype == "byte":
                data = int(write_str, 16) if write_str.startswith("0x") else int(write_str)
                self.controller.pmbus.write_byte(address=self.address, register=reg, data=data)
                readback = int(self.controller.pmbus.read_byte(address=self.address, register=reg))
                match = "OK" if readback == data else "MISMATCH"
                line = (f"PMBus Write page={page} reg=0x{reg:02X} [byte] "
                        f"wrote=0x{data:02X} readback=0x{readback:02X} {match}")

            elif dtype == "word":
                parts = write_str.split()
                if len(parts) == 1:
                    data = int(parts[0], 16) if parts[0].startswith("0x") else int(parts[0])
                else:
                    data = [int(p, 16) if p.startswith("0x") else int(p) for p in parts]
                self.controller.pmbus.write_word(address=self.address, register=reg, data=data)
                readback = int(self.controller.pmbus.read_word(address=self.address, register=reg, merge=True))
                line = f"PMBus Write page={page} reg=0x{reg:02X} [word] wrote={write_str} readback=0x{readback:04X}"

            elif dtype == "block":
                parts = write_str.split()
                data = [int(p, 16) if p.startswith("0x") else int(p) for p in parts]
                self.controller.pmbus.write_block(address=self.address, register=reg, data=data)
                readback = self.controller.pmbus.read_block(address=self.address, register=reg)
                rb_hex = " ".join(f"0x{int(b):02X}" for b in readback)
                line = f"PMBus Write page={page} reg=0x{reg:02X} [block] wrote={write_str} readback=[{rb_hex}]"

        except Exception as e:
            line = f"PMBus Write page={page} reg=0x{reg:02X} ERROR: {e}"

        self._log(line)

    # ── SVI3 Controls ─────────────────────────────────────────────────────
    def _build_svi3_controls(self, top):
        row1 = ctk.CTkFrame(top, fg_color="transparent")
        row1.pack(fill="x", padx=10, pady=(10, 2))

        ctk.CTkLabel(row1, text="Rail:", font=("Segoe UI", 11)).pack(side="left", padx=(0, 4))
        self.svi3_rail_var = ctk.StringVar(value="A")
        ctk.CTkOptionMenu(row1, values=self.svi3_rails, variable=self.svi3_rail_var,
                          width=80).pack(side="left", padx=(0, 10))

        ctk.CTkLabel(row1, text="Register:", font=("Segoe UI", 11)).pack(side="left", padx=(0, 4))
        reg_options = [f"0x{reg:02X} {name}" for reg, name in ALL_SVI3_REGISTERS.items()]
        self.svi3_reg_var = ctk.StringVar(value=reg_options[0])
        ctk.CTkOptionMenu(row1, values=reg_options, variable=self.svi3_reg_var,
                          width=250, command=self._svi3_reg_changed).pack(side="left", padx=(0, 10))

        self.svi3_desc_label = ctk.CTkLabel(top, text="", font=("Consolas", 10),
                                             text_color="#5d6d7e", wraplength=800,
                                             justify="left")
        self.svi3_desc_label.pack(fill="x", padx=14, pady=(0, 2))
        self._svi3_reg_changed(reg_options[0])

        row2 = ctk.CTkFrame(top, fg_color="transparent")
        row2.pack(fill="x", padx=10, pady=(2, 2))

        ctk.CTkButton(row2, text="Read", width=80, fg_color="#27ae60",
                      hover_color="#219a52", command=self._svi3_read).pack(side="left", padx=(0, 5))
        ctk.CTkButton(row2, text="Read All Rails", width=100, fg_color="#2980b9",
                      hover_color="#2471a3", command=self._svi3_read_all_rails).pack(side="left", padx=(0, 10))

        ctk.CTkLabel(row2, text="Write:", font=("Segoe UI", 11)).pack(side="left", padx=(0, 4))
        self.svi3_write_entry = ctk.CTkEntry(row2, width=80, font=("Consolas", 11),
                                              placeholder_text="0xFF")
        self.svi3_write_entry.pack(side="left", padx=(0, 5))

        ctk.CTkButton(row2, text="Write", width=80, fg_color="#e67e22",
                      hover_color="#cf6d17", command=self._svi3_write).pack(side="left")

        row3 = ctk.CTkFrame(top, fg_color="transparent")
        row3.pack(fill="x", padx=10, pady=(8, 2))

        ctk.CTkLabel(row3, text="Telemetry:", font=("Segoe UI", 11, "bold"),
                     text_color="#7f8c8d").pack(side="left", padx=(0, 8))
        for label, cmd in [
            ("VOUT", self._svi3_tel_vout), ("IOUT", self._svi3_tel_iout),
            ("VIN", self._svi3_tel_vin), ("TEMP", self._svi3_tel_temp),
            ("Read All Tel.", self._svi3_tel_all),
        ]:
            ctk.CTkButton(row3, text=label, width=70, height=28,
                          font=("Segoe UI", 10), command=cmd).pack(side="left", padx=2)

        row4 = ctk.CTkFrame(top, fg_color="transparent")
        row4.pack(fill="x", padx=10, pady=(2, 10))

        ctk.CTkLabel(row4, text="Set VOUT:", font=("Segoe UI", 11, "bold"),
                     text_color="#7f8c8d").pack(side="left", padx=(0, 8))

        ctk.CTkLabel(row4, text="Voltage (V):", font=("Segoe UI", 11)).pack(side="left", padx=(0, 4))
        self.svi3_set_vout_entry = ctk.CTkEntry(row4, width=80, font=("Consolas", 11))
        self.svi3_set_vout_entry.insert(0, "0.900")
        self.svi3_set_vout_entry.pack(side="left", padx=(0, 10))

        ctk.CTkButton(row4, text="Set VOUT", width=80, height=28, fg_color="#e67e22",
                      hover_color="#cf6d17", font=("Segoe UI", 10),
                      command=self._svi3_set_vout).pack(side="left", padx=2)

    def _svi3_reg_changed(self, selection):
        reg = int(selection.split()[0], 16)
        desc = self.svi3_desc.get(reg, "")
        self.svi3_desc_label.configure(text=desc)

    def _svi3_get_reg(self):
        sel = self.svi3_reg_var.get()
        return int(sel.split()[0], 16)

    def _svi3_read(self):
        rail = self.svi3_rail_var.get()
        reg = self._svi3_get_reg()
        name = ALL_SVI3_REGISTERS.get(reg, "?")

        self._wake_svi3_rail(rail)
        try:
            val = self.controller.svi3.read_register(reg)
            if val is None:
                line = f"SVI3 Read  Rail {rail}  0x{reg:02X} {name} -> NACK"
            else:
                val = int(val)
                line = f"SVI3 Read  Rail {rail}  0x{reg:02X} {name} -> 0x{val:02X} ({val:08b}b)"
        except Exception as e:
            line = f"SVI3 Read  Rail {rail}  0x{reg:02X} {name} -> ERROR: {e}"

        self._log(line)

    def _svi3_read_all_rails(self):
        reg = self._svi3_get_reg()
        name = ALL_SVI3_REGISTERS.get(reg, "?")
        self._log(f"--- SVI3 Read All Rails  0x{reg:02X} {name} ---")

        for rail in self.svi3_rails:
            self._wake_svi3_rail(rail)
            try:
                val = self.controller.svi3.read_register(reg)
                if val is None:
                    line = f"  Rail {rail}: NACK"
                else:
                    val = int(val)
                    line = f"  Rail {rail}: 0x{val:02X} ({val:08b}b)"
            except Exception as e:
                line = f"  Rail {rail}: ERROR: {e}"
            self._log(line)
        self._log(f"SVI3 Read All Rails  0x{reg:02X} {name} done")

    def _svi3_write(self):
        rail = self.svi3_rail_var.get()
        reg = self._svi3_get_reg()
        name = ALL_SVI3_REGISTERS.get(reg, "?")

        if reg in RO_REGISTERS or reg in SVI3_STATUS_REGISTERS or reg in TELEMETRY_REGISTERS:
            self._log(f"SVI3 Write  Rail {rail}  0x{reg:02X} {name} -> REFUSED (read-only)")
            return

        try:
            write_str = self.svi3_write_entry.get().strip()
            data = int(write_str, 16) if write_str.startswith("0x") else int(write_str)
        except ValueError:
            self._log("SVI3 Write: invalid data")
            return

        self._wake_svi3_rail(rail)
        try:
            self.controller.svi3.write_register(reg, data)
            readback = self.controller.svi3.read_register(reg)
            rb = int(readback) if readback is not None else None
            match = "OK" if rb == data else ("MISMATCH" if rb is not None else "NACK")
            rb_str = f"0x{rb:02X}" if rb is not None else "NACK"
            line = f"SVI3 Write Rail {rail}  0x{reg:02X} {name}  wrote=0x{data:02X}  readback={rb_str}  {match}"
        except Exception as e:
            line = f"SVI3 Write Rail {rail}  0x{reg:02X} {name}  ERROR: {e}"

        self._log(line)

    def _svi3_tel_vout(self):
        rail = self.svi3_rail_var.get()
        self._wake_svi3_rail(rail)
        try:
            result = self.controller.svi3.measure_output_voltage(split=True)
            if result is None or result[0] is None:
                line = f"SVI3 Tel  Rail {rail}  VOUT = NACK"
            else:
                vout, raw = result
                line = f"SVI3 Tel  Rail {rail}  VOUT = {vout:.4f} V  (raw=0x{raw:04X})"
        except Exception as e:
            line = f"SVI3 Tel  Rail {rail}  VOUT = ERROR: {e}"
        self._log(line)

    def _svi3_tel_iout(self):
        rail = self.svi3_rail_var.get()
        self._wake_svi3_rail(rail)
        try:
            iout, raw = self.controller.svi3.measure_output_current(split=True)
            line = f"SVI3 Tel  Rail {rail}  IOUT = {iout:.2f} A  (raw=0x{raw:04X})"
        except Exception as e:
            line = f"SVI3 Tel  Rail {rail}  IOUT = ERROR: {e}"
        self._log(line)

    def _svi3_tel_vin(self):
        rail = self.svi3_rail_var.get()
        self._wake_svi3_rail(rail)
        try:
            result = self.controller.svi3.measure_input_voltage(raw=True)
            if result is None:
                line = f"SVI3 Tel  Rail {rail}  VIN = NACK"
            else:
                raw = int(result)
                reg09 = int(self.controller.svi3.read_register(register=0x09))
                vin_scale_code = (reg09 >> 6) & 0x03
                vin = raw * V_IN_SCALE_VALUES[vin_scale_code] / 1024
                scale_label = V_IN_SCALE_MAP.get(vin_scale_code, "?")
                line = f"SVI3 Tel  Rail {rail}  VIN = {vin:.3f} V  (raw=0x{raw:04X}, scale={scale_label})"
        except Exception as e:
            line = f"SVI3 Tel  Rail {rail}  VIN = ERROR: {e}"
        self._log(line)

    def _svi3_tel_temp(self):
        rail = self.svi3_rail_var.get()
        self._wake_svi3_rail(rail)
        try:
            temp = self.controller.svi3.measure_temperature()
            if isinstance(temp, (list, tuple)):
                line = f"SVI3 Tel  Rail {rail}  TEMP = {temp[0]:.1f} C  (raw=0x{temp[1]:04X})"
            else:
                line = f"SVI3 Tel  Rail {rail}  TEMP = {temp:.1f} C"
        except Exception as e:
            line = f"SVI3 Tel  Rail {rail}  TEMP = ERROR: {e}"
        self._log(line)

    def _svi3_tel_all(self):
        rail = self.svi3_rail_var.get()
        self._wake_svi3_rail(rail)
        self._log(f"--- Telemetry Rail {rail} ---")
        self._svi3_tel_vout()
        self._svi3_tel_iout()
        self._svi3_tel_vin()
        self._svi3_tel_temp()

    def _svi3_set_vout(self):
        rail = self.svi3_rail_var.get()
        try:
            voltage = float(self.svi3_set_vout_entry.get().strip())
        except ValueError:
            self._log("SVI3 Set VOUT: invalid voltage")
            return

        self._wake_svi3_rail(rail)
        try:
            self.controller.svi3.set_output_voltage(voltage)
            self._log(f"SVI3 Set VOUT  Rail {rail}  target={voltage:.4f} V")
        except Exception as e:
            self._log(f"SVI3 Set VOUT  Rail {rail}  target={voltage:.4f} V  ERROR: {e}")
            return

        time.sleep(0.5)

        self._wake_svi3_rail(rail)
        try:
            result = self.controller.svi3.measure_output_voltage(split=True)
            if result is None or result[0] is None:
                self._log(f"SVI3 Set VOUT  Rail {rail}  readback=NACK")
            else:
                vout, raw = result
                self._log(f"SVI3 Set VOUT  Rail {rail}  readback={vout:.4f} V  (raw=0x{raw:04X})")
        except Exception as e:
            self._log(f"SVI3 Set VOUT  Rail {rail}  readback ERROR: {e}")

    # ======================================================================
    # Tab: Telemetry
    # ======================================================================
    def _build_telemetry_tab(self, parent):
        top = ctk.CTkFrame(parent, fg_color=COLOR_CARD_BG, corner_radius=10)
        top.pack(fill="x", padx=5, pady=5)

        ctk.CTkButton(top, text="Read All", width=100, fg_color="#27ae60",
                      hover_color="#219a52",
                      command=self._tel_read_all).pack(side="left", padx=(10, 5), pady=10)

        self.tel_auto_all_var = ctk.StringVar(value="off")
        ctk.CTkSwitch(top, text="Auto All", variable=self.tel_auto_all_var,
                      onvalue="on", offvalue="off",
                      command=self._tel_toggle_auto_all).pack(side="left", padx=10, pady=10)

        ctk.CTkLabel(top, text="ms:", font=("Segoe UI", 10)).pack(side="left", padx=(0, 2))
        self.tel_interval_entry = ctk.CTkEntry(top, width=60, font=("Consolas", 10))
        self.tel_interval_entry.insert(0, "1000")
        self.tel_interval_entry.pack(side="left", padx=(0, 10))

        self.tel_rail_vars = {}
        for rail in RAILS:
            var = ctk.StringVar(value="on" if rail in self.pmbus_rails else "off")
            self.tel_rail_vars[rail] = var
            ctk.CTkLabel(top, text=f"Rail {rail}:", font=("Segoe UI", 10)).pack(
                side="left", padx=(8, 0), pady=10)
            ctk.CTkSwitch(top, text="", variable=var,
                          onvalue="on", offvalue="off",
                          width=40).pack(side="left", padx=(2, 0), pady=10)

        self.tel_status_label = ctk.CTkLabel(top, text="", font=("Consolas", 9),
                                              text_color="#7f8c8d")
        self.tel_status_label.pack(side="right", padx=10)

        self.tel_scroll = ctk.CTkScrollableFrame(parent, fg_color=COLOR_DARK_BG)
        self.tel_scroll.pack(fill="both", expand=True, padx=5, pady=(0, 5))

        self.tel_labels = {}
        self.tel_auto_vars = {}
        self.tel_auto_running = False

        for page, rail in enumerate(RAILS):
            ctk.CTkLabel(self.tel_scroll, text=f"Rail {rail}",
                         font=("Segoe UI", 12, "bold"),
                         text_color=COLOR_TEXT).pack(anchor="w", padx=5, pady=(10, 2))

            card = ctk.CTkFrame(self.tel_scroll, fg_color=COLOR_CARD_BG, corner_radius=10)
            card.pack(fill="x", padx=5, pady=(0, 5))

            card.grid_columnconfigure(0, weight=2)
            card.grid_columnconfigure(1, weight=2)
            card.grid_columnconfigure(2, weight=2)
            card.grid_columnconfigure(3, weight=1)

            for col, hdr in enumerate(["Measurement", "PMBus", "SVI3", "Auto"]):
                ctk.CTkLabel(card, text=hdr, font=("Segoe UI", 10, "bold"),
                             text_color="#5d6d7e").grid(
                    row=0, column=col, padx=8, pady=(6, 2), sticky="w")

            for m_idx, (label, _, _, _, _) in enumerate(TELEMETRY_MEASUREMENTS):
                row = m_idx + 1
                bg = COLOR_CARD_BG if m_idx % 2 == 0 else "#f7f9fc"

                ctk.CTkLabel(card, text=label, font=("Consolas", 10),
                             text_color=COLOR_TEXT).grid(
                    row=row, column=0, padx=8, pady=2, sticky="w")

                pmbus_lbl = ctk.CTkLabel(card, text="--", font=("Consolas", 10),
                                          text_color=COLOR_TEXT)
                pmbus_lbl.grid(row=row, column=1, padx=8, pady=2, sticky="w")
                self.tel_labels[(rail, m_idx, "pmbus")] = pmbus_lbl

                svi3_lbl = ctk.CTkLabel(card, text="--", font=("Consolas", 10),
                                         text_color=COLOR_TEXT)
                svi3_lbl.grid(row=row, column=2, padx=8, pady=2, sticky="w")
                self.tel_labels[(rail, m_idx, "svi3")] = svi3_lbl

                auto_var = ctk.StringVar(value="off")
                self.tel_auto_vars[(rail, m_idx)] = auto_var
                sw = ctk.CTkSwitch(card, text="", variable=auto_var,
                                   onvalue="on", offvalue="off",
                                   width=40, command=self._tel_check_auto)
                sw.grid(row=row, column=3, padx=8, pady=2, sticky="w")

    def _tel_read_pmbus(self, page, reg, decode_type, fmt):
        self.controller.pmbus.set_page(page)
        readback = int(self.controller.pmbus.read_byte(address=self.address, register=0x00))
        if readback != page:
            self._log(f"Telemetry: set_page({page}) readback={readback} MISMATCH")
            return "PAGE ERR"
        raw = int(self.controller.pmbus.read_word(
            address=self.address, register=reg, merge=True))
        if decode_type == "vid":
            val = decode_vout(raw) / 1000
        else:
            val = decode_linear11(raw)
        return f"{val:{fmt}} (0x{raw:04X})"

    def _tel_read_svi3(self, rail, key, fmt):
        self._wake_svi3_rail(rail)
        if key == "vout":
            result = self.controller.svi3.measure_output_voltage(split=True)
            if result is None or result[0] is None:
                return "NACK"
            return f"{result[0]:{fmt}} (0x{result[1]:04X})"
        elif key == "iout":
            result = self.controller.svi3.measure_output_current(split=True)
            if result is None or result[0] is None:
                return "NACK"
            return f"{result[0]:{fmt}} (0x{result[1]:04X})"
        elif key == "vin":
            result = self.controller.svi3.measure_input_voltage(raw=True)
            if result is None:
                return "NACK"
            raw = int(result)
            reg09 = int(self.controller.svi3.read_register(register=0x09))
            vin_scale_code = (reg09 >> 6) & 0x03
            vin = raw * V_IN_SCALE_VALUES[vin_scale_code] / 1024
            return f"{vin:{fmt}} (0x{raw:04X})"
        elif key == "temp":
            result = self.controller.svi3.measure_temperature()
            if result is None:
                return "NACK"
            if isinstance(result, (list, tuple)):
                return f"{result[0]:{fmt}} (0x{result[1]:04X})"
            return f"{result:{fmt}}"
        return "--"

    def _tel_read_row(self, rail, page, m_idx):
        label, reg, decode_type, svi3_key, fmt = TELEMETRY_MEASUREMENTS[m_idx]

        try:
            pmbus_val = self._tel_read_pmbus(page, reg, decode_type, fmt)
        except Exception:
            pmbus_val = "ERR"
        self.tel_labels[(rail, m_idx, "pmbus")].configure(text=pmbus_val)

        if svi3_key is not None and rail in self.svi3_rails:
            try:
                svi3_val = self._tel_read_svi3(rail, svi3_key, fmt)
            except Exception:
                svi3_val = "ERR"
        else:
            svi3_val = "--"
        self.tel_labels[(rail, m_idx, "svi3")].configure(text=svi3_val)

    def _tel_read_all(self):
        for page, rail in enumerate(RAILS):
            if self.tel_rail_vars[rail].get() != "on":
                continue
            for m_idx in range(len(TELEMETRY_MEASUREMENTS)):
                self._tel_read_row(rail, page, m_idx)
        now = datetime.now().strftime("%H:%M:%S")
        self.tel_status_label.configure(text=f"Last: {now}")

    def _tel_toggle_auto_all(self):
        state = self.tel_auto_all_var.get()
        for key in self.tel_auto_vars:
            self.tel_auto_vars[key].set(state)
        if state == "on":
            try:
                interval = int(self.tel_interval_entry.get())
            except ValueError:
                interval = 1000
            self.tel_interval = interval
            self.tel_auto_running = True
            self._tel_auto_tick()
        else:
            self.tel_auto_running = False

    def _tel_check_auto(self):
        any_on = any(v.get() == "on" for v in self.tel_auto_vars.values())
        if any_on and not self.tel_auto_running:
            try:
                interval = int(self.tel_interval_entry.get())
            except ValueError:
                interval = 1000
            self.tel_interval = interval
            self.tel_auto_running = True
            self._tel_auto_tick()
        elif not any_on:
            self.tel_auto_running = False

    def _tel_auto_tick(self):
        if not self.tel_auto_running:
            return
        for page, rail in enumerate(RAILS):
            if self.tel_rail_vars[rail].get() != "on":
                continue
            for m_idx in range(len(TELEMETRY_MEASUREMENTS)):
                if self.tel_auto_vars[(rail, m_idx)].get() == "on":
                    self._tel_read_row(rail, page, m_idx)
        now = datetime.now().strftime("%H:%M:%S")
        self.tel_status_label.configure(text=f"Last: {now}")
        self.root.after(self.tel_interval, self._tel_auto_tick)

    # ======================================================================
    # Tab 4: SVI3 Settings (Read All)
    # ======================================================================
    def _build_svi3_settings_tab(self, parent):
        top = ctk.CTkFrame(parent, fg_color=COLOR_CARD_BG, corner_radius=10)
        top.pack(fill="x", padx=5, pady=5)

        ctk.CTkButton(top, text="Read All SVI3 Settings", width=200,
                      command=self._svi3_settings_read_all).pack(side="left", padx=10, pady=10)

        self.svi3_settings_rail_vars = {}
        for rail in RAILS:
            var = ctk.StringVar(value="on" if rail in self.svi3_rails else "off")
            self.svi3_settings_rail_vars[rail] = var
            ctk.CTkLabel(top, text=f"Rail {rail}:", font=("Segoe UI", 10)).pack(
                side="left", padx=(8, 0), pady=10)
            ctk.CTkSwitch(top, text="", variable=var,
                          onvalue="on", offvalue="off",
                          width=40).pack(side="left", padx=(2, 0), pady=10)

        self.svi3_settings_header = ctk.CTkFrame(parent, fg_color=COLOR_CARD_BG, corner_radius=8)
        self.svi3_settings_header.pack(fill="x", padx=8, pady=(0, 0))

        self.svi3_settings_scroll = ctk.CTkScrollableFrame(parent, fg_color=COLOR_DARK_BG)
        self.svi3_settings_scroll.pack(fill="both", expand=True, padx=5, pady=(0, 5))

    def _svi3_settings_read_all(self):
        for widget in self.svi3_settings_scroll.winfo_children():
            widget.destroy()

        rails = [r for r in RAILS if self.svi3_settings_rail_vars[r].get() == "on"]
        if not rails:
            self._log("SVI3 Settings: no rails enabled")
            return
        rail_data = {}

        for rail in rails:
            self._wake_svi3_rail(rail)
            time.sleep(0.1)
            rows = []
            iout_code = 0
            iin_code = 0

            val = self._read_svi3_safe(0x09)
            if val is None:
                rows.append(("0x09 SCALING", "NACK"))
            else:
                vin_code = (val >> 6) & 0x03
                iout_code = (val >> 3) & 0x07
                iin_code = val & 0x07
                rows.append(("0x09 SCALING", f"0x{val:02X}"))
                rows.append(("  V_IN_SCALE [7:6]", f"{vin_code:02b} -> {V_IN_SCALE_MAP.get(vin_code, '?')}"))
                rows.append(("  I_OUT_SCALE [5:3]", f"{iout_code:03b} -> {I_OUT_SCALE_MAP.get(iout_code, '?')}"))
                rows.append(("  I_IN_SCALE [2:0]", f"{iin_code:03b} -> {I_IN_SCALE_MAP.get(iin_code, '?')}"))

            val = self._read_svi3_safe(0x0A)
            if val is None:
                rows.append(("0x0A MAX_VOUT", "NACK"))
            else:
                rows.append(("0x0A MAX_VOUT", f"0x{val:02X} -> {val * 20 / 1000:.2f} V"))

            val = self._read_svi3_safe(0x0B)
            if val is None:
                rows.append(("0x0B MIN_VOUT", "NACK"))
            else:
                rows.append(("0x0B MIN_VOUT", f"0x{val:02X} -> {val * 5 / 1000:.3f} V"))

            val = self._read_svi3_safe(0x0C)
            if val is None:
                rows.append(("0x0C P_SYS_SCALE", "NACK"))
            else:
                psys_map = {0: "Custom", 1: "32W", 2: "64W", 3: "128W",
                            4: "256W", 5: "512W", 6: "1024W", 7: "2048W"}
                rows.append(("0x0C P_SYS_SCALE", f"{val & 0x07} -> {psys_map.get(val & 0x07)}"))

            rows.append(("--- Writable ---", ""))

            for reg, name, decode_fn in [
                (0x22, "VOUT_OFFSET", lambda v: "Disabled" if v == 0 else f"{v * 5 - 250} mV"),
                (0x23, "VID_MAX", lambda v: "Disabled" if v == 0 else f"{(v * 10 + 250)/1000:.3f} V"),
                (0x24, "VID_MIN", lambda v: "Disabled" if v == 0 else f"{(v * 10 + 250)/1000:.3f} V"),
            ]:
                val = self._read_svi3_safe(reg)
                if val is None:
                    rows.append((f"0x{reg:02X} {name}", "NACK"))
                else:
                    rows.append((f"0x{reg:02X} {name}", f"0x{val:02X} -> {decode_fn(val)}"))

            val = self._read_svi3_safe(0x27)
            if val is None:
                rows.append(("0x27 OCP_THRESH", "NACK"))
            elif val == 0:
                rows.append(("0x27 OCP_THRESH", "0x00 Disabled"))
            else:
                ocp = val * 4 * IOUT_FS[iout_code] / 512
                rows.append(("0x27 OCP_THRESH", f"0x{val:02X} -> {ocp:.1f} A"))

            val = self._read_svi3_safe(0x28)
            if val is None:
                rows.append(("0x28 OCP_WARN", "NACK"))
            elif val == 0:
                rows.append(("0x28 OCP_WARN", "0x00 Disabled"))
            else:
                ocp_w = val * 4 * IOUT_FS[iout_code] / 512
                rows.append(("0x28 OCP_WARN", f"0x{val:02X} -> {ocp_w:.1f} A"))

            val = self._read_svi3_safe(0x2A)
            if val is None:
                rows.append(("0x2A VRHOT_THRESH", "NACK"))
            elif val == 0:
                rows.append(("0x2A VRHOT_THRESH", "0x00 Disabled"))
            else:
                rows.append(("0x2A VRHOT_THRESH", f"0x{val:02X} -> {val - 40} C"))

            val = self._read_svi3_safe(0x2B)
            if val is None:
                rows.append(("0x2B OTP_THRESH", "NACK"))
            elif val == 0:
                rows.append(("0x2B OTP_THRESH", "0x00 Disabled"))
            else:
                rows.append(("0x2B OTP_THRESH", f"0x{val:02X} -> {val - 40} C"))

            val = self._read_svi3_safe(0x2C)
            if val is None:
                rows.append(("0x2C OVP_UVP_CONFIG", "NACK"))
            else:
                ovp_ref = (val >> 7) & 1
                ovp_d = (val >> 4) & 0x07
                uvp_ref = (val >> 3) & 1
                uvp_d = val & 0x07
                rows.append(("0x2C OVP_UVP_CONFIG", f"0x{val:02X}"))
                rows.append(("  OVP_REF [7]", f"{'VID_MAX' if ovp_ref else 'VID'}"))
                ovp_s = "Disabled" if ovp_d == 0 else f"{ovp_d * 50 + 50} mV"
                rows.append(("  OVP_DELTA [6:4]", ovp_s))
                rows.append(("  UVP_REF [3]", f"{'VID_MIN' if uvp_ref else 'VID'}"))
                uvp_s = "Disabled" if uvp_d == 0 else f"{uvp_d * 50 + 50} mV"
                rows.append(("  UVP_DELTA [2:0]", uvp_s))

            val = self._read_svi3_safe(0x2D)
            if val is None:
                rows.append(("0x2D PHASE_SHED", "NACK"))
            else:
                rows.append(("0x2D PHASE_SHED", f"PSI1={(val >> 4) & 0x0F} PSI2={val & 0x0F}"))

            val = self._read_svi3_safe(0x2E)
            if val is None:
                rows.append(("0x2E I_IN_WARN", "NACK"))
            elif val == 0:
                rows.append(("0x2E I_IN_WARN", "0x00 Disabled"))
            else:
                iin_t = val * 4 * IIN_FS[iin_code] / 512
                rows.append(("0x2E I_IN_WARN", f"0x{val:02X} -> {iin_t:.1f} A"))

            # Fault status
            rows.append(("--- Fault Status ---", ""))
            for reg, name in SVI3_STATUS_REGISTERS.items():
                val = self._read_svi3_safe(reg)
                if val is None:
                    rows.append((f"0x{reg:02X} {name}", "NACK"))
                else:
                    rows.append((f"0x{reg:02X} {name}", f"0x{val:02X} ({val:08b}b)"))

            rail_data[rail] = rows

        # Build frozen header row
        for widget in self.svi3_settings_header.winfo_children():
            widget.destroy()
        self.svi3_settings_header.grid_columnconfigure(0, weight=2)
        for i in range(len(rails)):
            self.svi3_settings_header.grid_columnconfigure(i + 1, weight=1)

        ctk.CTkLabel(self.svi3_settings_header, text="Register", font=("Segoe UI", 10, "bold"),
                     text_color=COLOR_TEXT).grid(row=0, column=0, padx=8, pady=4, sticky="w")
        for i, rail in enumerate(rails):
            ctk.CTkLabel(self.svi3_settings_header, text=f"Rail {rail}", font=("Segoe UI", 10, "bold"),
                         text_color=COLOR_TEXT).grid(row=0, column=i + 1, padx=8, pady=4, sticky="w")

        # Build data rows
        num_rows = max(len(rail_data[r]) for r in rails)

        for row_idx in range(num_rows):
            bg = COLOR_CARD_BG if row_idx % 2 == 0 else "#f7f9fc"
            row_frame = ctk.CTkFrame(self.svi3_settings_scroll, fg_color=bg, corner_radius=0)
            row_frame.pack(fill="x", padx=3, pady=0)
            row_frame.grid_columnconfigure(0, weight=2)
            for i in range(len(rails)):
                row_frame.grid_columnconfigure(i + 1, weight=1)

            label = rail_data[rails[0]][row_idx][0] if row_idx < len(rail_data[rails[0]]) else ""
            is_separator = label.startswith("---")
            font = ("Segoe UI", 9, "bold") if is_separator else ("Consolas", 9)
            ctk.CTkLabel(row_frame, text=label, font=font,
                         text_color="#5d6d7e" if is_separator else COLOR_TEXT).grid(
                row=0, column=0, padx=8, pady=2, sticky="w")

            for i, rail in enumerate(rails):
                val = rail_data[rail][row_idx][1] if row_idx < len(rail_data[rail]) else ""
                ctk.CTkLabel(row_frame, text=val, font=("Consolas", 9),
                             text_color=COLOR_TEXT).grid(
                    row=0, column=i + 1, padx=8, pady=2, sticky="w")

        self._log(f"SVI3 Settings: read {len(rails)} rails, {num_rows} rows each")

    def _read_svi3_safe(self, reg):
        try:
            val = self.controller.svi3.read_register(reg)
            return int(val) if val is not None else None
        except Exception:
            return None

    # ======================================================================
    # Tab: 0xDE AMD Settings Control
    # ======================================================================
    DE_IOUT_MAX = [16, 32, 64, 128, 256, 512, 1024, 2048]
    DE_SLEW_MAP = {0: "2.5", 1: "10", 2: "20", 3: "40"}
    DE_OCL_SLOPE = ["1/8", "1/4", "1/2", "1", "2", "4", "8", "16"]

    def _build_de_settings_tab(self, parent):
        top = ctk.CTkFrame(parent, fg_color=COLOR_CARD_BG, corner_radius=10)
        top.pack(fill="x", padx=5, pady=5)

        ctk.CTkButton(top, text="Read 0xDE All Rails", width=200,
                      command=self._de_settings_read_all).pack(side="left", padx=10, pady=10)

        self.de_rail_vars = {}
        for rail in RAILS:
            var = ctk.StringVar(value="on" if rail in self.pmbus_rails else "off")
            self.de_rail_vars[rail] = var
            ctk.CTkLabel(top, text=f"Rail {rail}:", font=("Segoe UI", 10)).pack(
                side="left", padx=(8, 0), pady=10)
            ctk.CTkSwitch(top, text="", variable=var,
                          onvalue="on", offvalue="off",
                          width=40).pack(side="left", padx=(2, 0), pady=10)

        self.de_settings_header = ctk.CTkFrame(parent, fg_color=COLOR_CARD_BG, corner_radius=8)
        self.de_settings_header.pack(fill="x", padx=8, pady=(0, 0))

        self.de_settings_scroll = ctk.CTkScrollableFrame(parent, fg_color=COLOR_DARK_BG)
        self.de_settings_scroll.pack(fill="both", expand=True, padx=5, pady=(0, 5))

    def _de_settings_read_all(self):
        for widget in self.de_settings_scroll.winfo_children():
            widget.destroy()

        rails = [r for r in RAILS if self.de_rail_vars[r].get() == "on"]
        if not rails:
            self._log("0xDE: no rails enabled")
            return
        rail_data = {}

        for rail in rails:
            page = RAILS.index(rail)
            if not self._set_page_checked(page, rail):
                rail_data[rail] = [("ERROR", "page select failed")]
                continue
            try:
                raw = self.controller.pmbus.read_block(address=self.address, register=0xDE)
                data = [int(b) for b in raw]
                if len(data) < 26:
                    data.extend([0] * (26 - len(data)))
            except Exception as e:
                self._log(f"0xDE Rail {rail}: {e}")
                rail_data[rail] = [("ERROR", str(e))]
                continue
            hex_str = " ".join(f"{b:02X}" for b in data)
            self._log(f"0xDE Rail {rail}: {hex_str}")
            rail_data[rail] = self._decode_de(data)

        for widget in self.de_settings_header.winfo_children():
            widget.destroy()
        self.de_settings_header.grid_columnconfigure(0, weight=2)
        for i in range(len(rails)):
            self.de_settings_header.grid_columnconfigure(i + 1, weight=1)

        ctk.CTkLabel(self.de_settings_header, text="Field", font=("Segoe UI", 10, "bold"),
                     text_color=COLOR_TEXT).grid(row=0, column=0, padx=8, pady=4, sticky="w")
        for i, rail in enumerate(rails):
            ctk.CTkLabel(self.de_settings_header, text=f"Rail {rail}", font=("Segoe UI", 10, "bold"),
                         text_color=COLOR_TEXT).grid(row=0, column=i + 1, padx=8, pady=4, sticky="w")

        num_rows = max(len(rail_data[r]) for r in rails)
        for row_idx in range(num_rows):
            bg = COLOR_CARD_BG if row_idx % 2 == 0 else "#f7f9fc"
            row_frame = ctk.CTkFrame(self.de_settings_scroll, fg_color=bg, corner_radius=0)
            row_frame.pack(fill="x", padx=3, pady=0)
            row_frame.grid_columnconfigure(0, weight=2)
            for i in range(len(rails)):
                row_frame.grid_columnconfigure(i + 1, weight=1)

            label = rail_data[rails[0]][row_idx][0] if row_idx < len(rail_data[rails[0]]) else ""
            is_header = not label.startswith("  ")
            font = ("Segoe UI", 9, "bold") if is_header else ("Consolas", 9)
            ctk.CTkLabel(row_frame, text=label, font=font,
                         text_color="#5d6d7e" if is_header else COLOR_TEXT).grid(
                row=0, column=0, padx=8, pady=2, sticky="w")

            for i, rail in enumerate(rails):
                val = rail_data[rail][row_idx][1] if row_idx < len(rail_data[rail]) else ""
                ctk.CTkLabel(row_frame, text=val, font=("Consolas", 9),
                             text_color=COLOR_TEXT).grid(
                    row=0, column=i + 1, padx=8, pady=2, sticky="w")

        self._log(f"0xDE Settings: read {len(rails)} rails, {num_rows} rows")

    def _decode_de(self, d):
        rows = []
        iout_code = d[0] & 0x07
        iout_max = self.DE_IOUT_MAX[iout_code]

        # Byte 0
        rows.append(("Byte 0 -- IOUT Scale / PS Config", f"0x{d[0]:02X}"))
        rows.append(("  IOUT_SCALE [2:0]", f"{iout_code:03b} -> {iout_max} A"))
        rows.append(("  bst_rfresh_pls [6]", "Variable" if (d[0] >> 6) & 1 else "Fixed"))

        # Byte 1
        rows.append(("Byte 1 -- Sys Power / IIN Tel", f"0x{d[1]:02X}"))
        rows.append(("  sys_pwr_telem [7]", "Enabled" if (d[1] >> 7) & 1 else "Disabled"))
        rows.append(("  Iin_telemetry_en [3]", "Enabled" if (d[1] >> 3) & 1 else "Disabled"))

        # Byte 2
        rows.append(("Byte 2 -- Decay / VIN Tel", f"0x{d[2]:02X}"))
        rows.append(("  PSI0/1/2 decay [7]", "Decay" if (d[2] >> 7) & 1 else "Active"))
        rows.append(("  PSI3 decay [6]", "Decay" if (d[2] >> 6) & 1 else "Active"))
        rows.append(("  PSI6/PWR_EN decay [5]", "Decay" if (d[2] >> 5) & 1 else "Active"))
        rows.append(("  Vin_telemetry_en [2]", "Enabled" if (d[2] >> 2) & 1 else "Disabled"))

        # Byte 3
        rows.append(("Byte 3 -- Slew / Boot Voltage", f"0x{d[3]:02X}"))
        rows.append(("  Down Slew Rate [7]", "1/4x" if (d[3] >> 7) & 1 else "1x"))
        rows.append(("  load_vboot_and_slew [6]", "Reload" if (d[3] >> 6) & 1 else "No reload"))
        legacy_slew = (d[3] >> 4) & 0x03
        rows.append(("  LEGACY_SLEW [5:4]", f"{self.DE_SLEW_MAP[legacy_slew]} mV/us"))
        vboot = d[3] & 0x0F
        vboot_str = "OFF" if vboot == 0 else f"{500 + (vboot - 1) * 100} mV"
        rows.append(("  LEGACY_VBOOT [3:0]", vboot_str))

        # Byte 4
        rows.append(("Byte 4 -- VOUT_OFFSET", f"0x{d[4]:02X}"))
        if d[4] == 0:
            rows.append(("  VOUT_OFFSET", "Disabled"))
        else:
            rows.append(("  VOUT_OFFSET", f"{d[4] * 5 - 250} mV"))

        # Byte 5-6
        vid_max_d = d[5] | ((d[6] & 0x01) << 8)
        rows.append(("Byte 5-6 -- VID_MAX_D", f"0x{d[5]:02X} 0x{d[6]:02X} -> {vid_max_d}"))

        # Byte 7
        rows.append(("Byte 7 -- VID_MAX", f"0x{d[7]:02X}"))
        rows.append(("  VID_MAX", "Disabled" if d[7] == 0 else f"{d[7] * 10 + 250} mV"))

        # Byte 8
        rows.append(("Byte 8 -- VID_MIN", f"0x{d[8]:02X}"))
        rows.append(("  VID_MIN", "Disabled" if d[8] == 0 else f"{d[8] * 10 + 250} mV"))

        # Byte 9
        rows.append(("Byte 9 -- OVP/UVP Config", f"0x{d[9]:02X}"))
        ovp_ref = (d[9] >> 7) & 1
        ovp_d = (d[9] >> 4) & 0x07
        uvp_ref = (d[9] >> 3) & 1
        uvp_d = d[9] & 0x07
        rows.append(("  OVP_REF [7]", "VID_MAX" if ovp_ref else "VID"))
        rows.append(("  OVP_DELTA [6:4]", "Disabled" if ovp_d == 0 else f"{ovp_d * 50 + 50} mV"))
        rows.append(("  UVP_REF [3]", "VID_MIN" if uvp_ref else "VID"))
        rows.append(("  UVP_DELTA [2:0]", "Disabled" if uvp_d == 0 else f"{uvp_d * 50 + 50} mV"))

        # Byte 10
        rows.append(("Byte 10 -- OCP_WARN", f"0x{d[10]:02X}"))
        if d[10] == 0:
            rows.append(("  OCP_WARN", "Disabled"))
        else:
            rows.append(("  OCP_WARN", f"{d[10] * 4 * iout_max / 512:.1f} A"))

        # Byte 11
        rows.append(("Byte 11 -- OCP_THRESH", f"0x{d[11]:02X}"))
        if d[11] == 0:
            rows.append(("  OCP_THRESH", "Disabled"))
        else:
            rows.append(("  OCP_THRESH", f"{d[11] * 4 * iout_max / 512:.1f} A"))

        # Byte 12
        rows.append(("Byte 12 -- OCP Timing", f"0x{d[12]:02X}"))
        ocp_delay = (d[12] >> 5) & 0x07
        rows.append(("  OCP_FAULT_DELAY [7:5]", "Instantaneous" if ocp_delay == 0 else f"{ocp_delay * 5} us"))
        ocp_pulse = d[12] & 0x1F
        rows.append(("  OCP_W_MIN_PULSE [4:0]", f"{ocp_pulse * 0.5:.1f} us"))

        # Byte 13
        rows.append(("Byte 13 -- LL_ADJUST", f"0x{d[13]:02X}"))
        ll = d[13] & 0x1F
        rows.append(("  LL_ADJUST [4:0]", f"{ll * 10}%"))

        # Byte 14
        rows.append(("Byte 14 -- Phase Shedding", f"0x{d[14]:02X}"))
        rows.append(("  PSI1 [7:4] / PSI2 [3:0]", f"PSI1={(d[14] >> 4) & 0x0F} PSI2={d[14] & 0x0F}"))

        # Byte 15
        rows.append(("Byte 15 -- VRHOT_THRESH", f"0x{d[15]:02X}"))
        rows.append(("  VRHOT_THRESH", "Disabled" if d[15] == 0 else f"{d[15] - 40} C"))

        # Byte 16
        rows.append(("Byte 16 -- OTP_THRESH", f"0x{d[16]:02X}"))
        rows.append(("  OTP_THRESH", "Disabled" if d[16] == 0 else f"{d[16] - 40} C"))

        # Byte 17
        rows.append(("Byte 17 -- 10b Tel Enables", f"0x{d[17]:02X} ({d[17]:08b}b)"))
        tel_names = ["IOUT", "VOUT", "Temp1", "Temp2", "IIN", "VIN", "PIN"]
        enabled = [tel_names[i] for i in range(7) if (d[17] >> i) & 1]
        rows.append(("  Enabled", ", ".join(enabled) if enabled else "None"))

        # Byte 18
        rows.append(("Byte 18 -- def_vid_D_low", f"0x{d[18]:02X}"))

        # Byte 19-20
        vid_9bit = ((d[20] & 0x01) << 8) | d[19]
        vid_str = "OFF" if vid_9bit == 0 else f"{vid_9bit * 5 + 245} mV"
        rows.append(("Byte 19-20 -- VID / Slew / OCL", f"0x{d[19]:02X} 0x{d[20]:02X}"))
        rows.append(("  Default VID", f"{vid_9bit} -> {vid_str}"))
        up_slew = (d[20] >> 4) & 0x0F
        rows.append(("  Up Slew Rate [7:4]", f"{up_slew * 2.5 + 2.5:.1f} mV/us"))
        ocl_slope = (d[20] >> 1) & 0x07
        rows.append(("  OCL Slope [3:1]", self.DE_OCL_SLOPE[ocl_slope]))

        # Byte 21
        rows.append(("Byte 21 -- Default Load-Line", f"0x{d[21]:02X}"))
        rows.append(("  Default_LL", f"{d[21] * 0.025:.3f} mOhm"))

        # Byte 22
        rows.append(("Byte 22 -- OCL_MAX", f"0x{d[22]:02X}"))
        rows.append(("  OCL_MAX", f"{d[22] * 4 * iout_max / 512:.1f} A"))

        # Byte 23
        rows.append(("Byte 23 -- OCL_MIN", f"0x{d[23]:02X}"))
        rows.append(("  OCL_MIN", f"{d[23] * 4 * iout_max / 512:.1f} A"))

        # Byte 24
        rows.append(("Byte 24 -- IOUT_TAU", f"0x{d[24]:02X}"))

        # Byte 25
        rows.append(("Byte 25 -- VOUT_TAU", f"0x{d[25]:02X}"))

        return rows

    # ======================================================================
    # Tab 5: PMBus Fault Status
    # ======================================================================
    def _build_fault_status_tab(self, parent):
        top = ctk.CTkFrame(parent, fg_color=COLOR_CARD_BG, corner_radius=10)
        top.pack(fill="x", padx=5, pady=5)

        ctk.CTkButton(top, text="Read All", width=100, fg_color="#27ae60",
                      hover_color="#219a52",
                      command=self._fault_read_all).pack(side="left", padx=(10, 5), pady=10)

        self.fault_auto_var = ctk.StringVar(value="off")
        ctk.CTkSwitch(top, text="Auto", variable=self.fault_auto_var,
                      onvalue="on", offvalue="off",
                      command=self._fault_toggle_auto).pack(side="left", padx=10, pady=10)

        ctk.CTkLabel(top, text="ms:", font=("Segoe UI", 10)).pack(side="left", padx=(0, 2))
        self.fault_interval_entry = ctk.CTkEntry(top, width=60, font=("Consolas", 10))
        self.fault_interval_entry.insert(0, "1000")
        self.fault_interval_entry.pack(side="left", padx=(0, 10))

        self.fault_rail_vars = {}
        for rail in RAILS:
            var = ctk.StringVar(value="on" if rail in self.pmbus_rails else "off")
            self.fault_rail_vars[rail] = var
            ctk.CTkLabel(top, text=f"Rail {rail}:", font=("Segoe UI", 10)).pack(
                side="left", padx=(8, 0), pady=10)
            ctk.CTkSwitch(top, text="", variable=var,
                          onvalue="on", offvalue="off",
                          width=40).pack(side="left", padx=(2, 0), pady=10)

        self.fault_status_label = ctk.CTkLabel(top, text="", font=("Consolas", 9),
                                                text_color="#7f8c8d")
        self.fault_status_label.pack(side="right", padx=10)

        self.fault_scroll = ctk.CTkScrollableFrame(parent, fg_color=COLOR_DARK_BG)
        self.fault_scroll.pack(fill="both", expand=True, padx=5, pady=(0, 5))

        self.fault_leds = {}
        self.fault_raw_labels = {}

    def _fault_read_all(self):
        for widget in self.fault_scroll.winfo_children():
            widget.destroy()
        self.fault_leds.clear()
        self.fault_raw_labels.clear()

        enabled = [r for r in RAILS if self.fault_rail_vars[r].get() == "on"]
        for page, rail in enumerate(RAILS):
            if rail not in enabled:
                continue
            if not self._set_page_checked(page, rail):
                continue

            rail_label = ctk.CTkLabel(self.fault_scroll, text=f"Rail {rail}",
                                       font=("Segoe UI", 12, "bold"), text_color=COLOR_TEXT)
            rail_label.pack(anchor="w", padx=5, pady=(10, 2))

            # 0x78 STATUS_BYTE
            name, bits = REGISTER_BIT_DEFINITIONS[0x78]
            try:
                val = int(self.controller.pmbus.read_byte(address=self.address, register=0x78))
            except Exception:
                val = None
            self._build_fault_byte_row(self.fault_scroll, rail, 0x78, name, bits, val)

            # 0x79 STATUS_WORD
            try:
                word_val = int(self.controller.pmbus.read_word(
                    address=self.address, register=0x79, merge=True))
            except Exception:
                word_val = None
            self._build_fault_word_row(self.fault_scroll, rail, word_val)

            # Byte registers: 0x7A-0x7E, 0x80
            byte_vals = {}
            for reg in [0x7A, 0x7B, 0x7C, 0x7D, 0x7E, 0x80]:
                name, bits = REGISTER_BIT_DEFINITIONS[reg]
                try:
                    bval = int(self.controller.pmbus.read_byte(address=self.address, register=reg))
                except Exception:
                    bval = None
                byte_vals[reg] = bval
                self._build_fault_byte_row(self.fault_scroll, rail, reg, name, bits, bval)

            # 0xF7 FAULT_LOG (block, 5 bytes)
            try:
                f7_data = self.controller.pmbus.read_block(address=self.address, register=0xF7)
            except Exception:
                f7_data = None
            if f7_data is not None:
                for byte_idx in range(min(5, len(f7_data))):
                    byte_val = int(f7_data[byte_idx])
                    self._build_fault_block_byte_row(
                        self.fault_scroll, f"0xF7 Log{byte_idx}", FAULT_LOG_0xF7_BITS, byte_val)

            # 0xF9 STATUS_MONITOR (block, 4 bytes)
            try:
                f9_data = self.controller.pmbus.read_block(address=self.address, register=0xF9)
            except Exception:
                f9_data = None
            if f9_data is not None:
                for byte_idx in range(min(4, len(f9_data))):
                    byte_val = int(f9_data[byte_idx])
                    bits = STATUS_MONITOR_0xF9[byte_idx]
                    label = f"0xF9 Byte{byte_idx}"
                    if byte_idx == 1:
                        num_phases = (byte_val >> 3) & 0x1F
                        label += f" (phases={num_phases})"
                    self._build_fault_monitor_row(self.fault_scroll, label, bits, byte_val)

            # SVI3 0x10 FAULT_STATUS, 0x11 NACK_STATUS
            svi3_vals = {}
            if rail in self.svi3_rails:
                self._wake_svi3_rail(rail)
                for reg, (name, bits) in SVI3_FAULT_DEFS.items():
                    sval = self._read_svi3_safe(reg)
                    svi3_vals[reg] = sval
                    if sval is not None:
                        self._build_fault_monitor_row(
                            self.fault_scroll, f"SVI3 0x{reg:02X} {name}", bits, sval)
                    else:
                        self._build_fault_nack_row(
                            self.fault_scroll, f"SVI3 0x{reg:02X} {name}")

            # Log raw data
            parts = [f"Rail {rail}:"]
            parts.append(f"0x78={self._fmt_fault_val(val, 'b')}")
            parts.append(f"0x79={self._fmt_fault_val(word_val, 'w')}")
            for reg in [0x7A, 0x7B, 0x7C, 0x7D, 0x7E, 0x80]:
                parts.append(f"0x{reg:02X}={self._fmt_fault_val(byte_vals[reg], 'b')}")
            if f7_data is not None:
                f7_hex = " ".join(f"{int(b):02X}" for b in f7_data)
                parts.append(f"0xF7=[{f7_hex}]")
            else:
                parts.append("0xF7=ERR")
            if f9_data is not None:
                f9_hex = " ".join(f"{int(b):02X}" for b in f9_data)
                parts.append(f"0xF9=[{f9_hex}]")
            else:
                parts.append("0xF9=ERR")
            for reg in svi3_vals:
                parts.append(f"SVI3_0x{reg:02X}={self._fmt_fault_val(svi3_vals[reg], 'b')}")
            self._log("  ".join(parts))

        now = datetime.now().strftime("%H:%M:%S")
        self.fault_status_label.configure(text=f"Last: {now}")
        self._log(f"Fault Status: read {', '.join(enabled)}")

    def _fmt_fault_val(self, val, size):
        if val is None:
            return "ERR"
        if size == "w":
            return f"0x{val:04X}"
        return f"0x{val:02X}"

    def _build_fault_byte_row(self, parent, rail, reg, name, bits, val):
        frame = ctk.CTkFrame(parent, fg_color=COLOR_CARD_BG, corner_radius=8)
        frame.pack(fill="x", padx=3, pady=(2, 0))

        ctk.CTkLabel(frame, text=f"0x{reg:02X} {name}",
                     font=("Segoe UI", 10, "bold"), text_color="#5d6d7e").pack(
            side="left", padx=(10, 5), pady=6)

        if val is not None:
            ctk.CTkLabel(frame, text=f"[0x{val:02X}]",
                         text_color=COLOR_TEXT, font=("Consolas", 10)).pack(
                side="left", padx=(0, 10), pady=6)
        else:
            ctk.CTkLabel(frame, text="[ERR]",
                         text_color=COLOR_RED, font=("Consolas", 10)).pack(
                side="left", padx=(0, 10), pady=6)
            return

        for bit_pos, bit_name in bits:
            bit_set = (val >> bit_pos) & 1
            if "unused" in bit_name:
                color = COLOR_RED if bit_set else COLOR_GRAY
                display = "UNUSED"
            elif bit_name == "none_of_the_above":
                color = COLOR_RED if bit_set else COLOR_GREEN
                display = "OTHER"
            else:
                color = COLOR_RED if bit_set else COLOR_GREEN
                display = bit_name.replace("_fault", "").replace("_", " ").upper()

            canvas = ctk.CTkCanvas(frame, width=14, height=14,
                                   bg=COLOR_CARD_BG, highlightthickness=0)
            canvas.pack(side="left", padx=(0, 2), pady=6)
            canvas.create_oval(1, 1, 13, 13, fill=color, outline="")

            ctk.CTkLabel(frame, text=display, font=("Segoe UI", 8),
                         text_color="#34495e").pack(side="left", padx=(0, 8), pady=6)

    def _build_fault_word_row(self, parent, rail, val):
        frame = ctk.CTkFrame(parent, fg_color=COLOR_CARD_BG, corner_radius=8)
        frame.pack(fill="x", padx=3, pady=(2, 0))

        ctk.CTkLabel(frame, text="0x79 STATUS_WORD",
                     font=("Segoe UI", 10, "bold"), text_color="#5d6d7e").pack(
            side="left", padx=(10, 5), pady=6)

        if val is None:
            ctk.CTkLabel(frame, text="[ERR]",
                         text_color=COLOR_RED, font=("Consolas", 10)).pack(
                side="left", padx=(0, 10), pady=6)
            return

        high = (val >> 8) & 0xFF
        low = val & 0xFF
        ctk.CTkLabel(frame, text=f"[0x{val:04X}]",
                     text_color=COLOR_TEXT, font=("Consolas", 10)).pack(
            side="left", padx=(0, 10), pady=6)

        ctk.CTkLabel(frame, text="|Hi:", font=("Consolas", 9),
                     text_color="#5d6d7e").pack(side="left", padx=(5, 3), pady=6)
        for bit_pos, bit_name in STATUS_WORD_BIT_DEFINITIONS["high"]:
            bit_set = (high >> bit_pos) & 1
            if "unused" in bit_name:
                color = COLOR_RED if bit_set else COLOR_GRAY
                display = "UNUSED"
            else:
                color = COLOR_RED if bit_set else COLOR_GREEN
                display = bit_name.replace("_n", "!").replace("_", " ").upper()

            canvas = ctk.CTkCanvas(frame, width=14, height=14,
                                   bg=COLOR_CARD_BG, highlightthickness=0)
            canvas.pack(side="left", padx=(0, 2), pady=6)
            canvas.create_oval(1, 1, 13, 13, fill=color, outline="")
            ctk.CTkLabel(frame, text=display, font=("Segoe UI", 8),
                         text_color="#34495e").pack(side="left", padx=(0, 6), pady=6)

        ctk.CTkLabel(frame, text=f"| Lo=0x{low:02X} (Identical to STATUS_BYTE 0x78)",
                     font=("Consolas", 9), text_color="#5d6d7e").pack(
            side="left", padx=(5, 0), pady=6)

    def _build_fault_block_byte_row(self, parent, label, bits, byte_val):
        frame = ctk.CTkFrame(parent, fg_color=COLOR_CARD_BG, corner_radius=8)
        frame.pack(fill="x", padx=3, pady=(2, 0))

        ctk.CTkLabel(frame, text=label,
                     font=("Segoe UI", 10, "bold"), text_color="#5d6d7e").pack(
            side="left", padx=(10, 5), pady=6)
        ctk.CTkLabel(frame, text=f"[0x{byte_val:02X}]",
                     text_color=COLOR_TEXT, font=("Consolas", 10)).pack(
            side="left", padx=(0, 10), pady=6)

        for bit_pos, bit_name in bits:
            bit_set = (byte_val >> bit_pos) & 1
            if bit_name == "always_0":
                color = COLOR_RED if bit_set else COLOR_GRAY
                display = "UNUSED"
            else:
                color = COLOR_RED if bit_set else COLOR_GREEN
                display = bit_name.replace("_fault", "").replace("_", " ").upper()

            canvas = ctk.CTkCanvas(frame, width=14, height=14,
                                   bg=COLOR_CARD_BG, highlightthickness=0)
            canvas.pack(side="left", padx=(0, 2), pady=6)
            canvas.create_oval(1, 1, 13, 13, fill=color, outline="")
            ctk.CTkLabel(frame, text=display, font=("Segoe UI", 8),
                         text_color="#34495e").pack(side="left", padx=(0, 8), pady=6)

    def _build_fault_monitor_row(self, parent, label, bits, byte_val):
        frame = ctk.CTkFrame(parent, fg_color=COLOR_CARD_BG, corner_radius=8)
        frame.pack(fill="x", padx=3, pady=(2, 0))

        ctk.CTkLabel(frame, text=label,
                     font=("Segoe UI", 10, "bold"), text_color="#5d6d7e").pack(
            side="left", padx=(10, 5), pady=6)
        ctk.CTkLabel(frame, text=f"[0x{byte_val:02X}]",
                     text_color=COLOR_TEXT, font=("Consolas", 10)).pack(
            side="left", padx=(0, 10), pady=6)

        for bit_pos, bit_name in bits:
            if bit_name.startswith("num_sl_det["):
                continue
            bit_set = (byte_val >> bit_pos) & 1
            if bit_name == "reserved":
                color = COLOR_RED if bit_set else COLOR_GRAY
                display = "RSVD"
            elif bit_name in ACTIVE_HIGH_GOOD:
                color = COLOR_GREEN if bit_set else COLOR_RED
                display = bit_name.replace("_", " ").upper()
            else:
                color = COLOR_RED if bit_set else COLOR_GREEN
                display = bit_name.replace("_fault", "").replace("_", " ").upper()

            canvas = ctk.CTkCanvas(frame, width=14, height=14,
                                   bg=COLOR_CARD_BG, highlightthickness=0)
            canvas.pack(side="left", padx=(0, 2), pady=6)
            canvas.create_oval(1, 1, 13, 13, fill=color, outline="")
            ctk.CTkLabel(frame, text=display, font=("Segoe UI", 8),
                         text_color="#34495e").pack(side="left", padx=(0, 8), pady=6)

    def _build_fault_nack_row(self, parent, label):
        frame = ctk.CTkFrame(parent, fg_color=COLOR_CARD_BG, corner_radius=8)
        frame.pack(fill="x", padx=3, pady=(2, 0))
        ctk.CTkLabel(frame, text=label,
                     font=("Segoe UI", 10, "bold"), text_color="#5d6d7e").pack(
            side="left", padx=(10, 5), pady=6)
        ctk.CTkLabel(frame, text="[NACK]",
                     text_color=COLOR_RED, font=("Consolas", 10)).pack(
            side="left", padx=(0, 10), pady=6)

    def _fault_clear(self):
        for page, rail in enumerate(self.pmbus_rails):
            if not self._set_page_checked(page, rail):
                continue
            try:
                self.controller.pmbus.send_byte(0x03)
            except Exception:
                pass
        self._log(f"Faults cleared (0x03 sent to rails {', '.join(self.pmbus_rails)})")

    def _set_svi3_version(self, mode):
        ver_name = {0b00: "v2.00", 0b01: "v3.12"}.get(mode, "unknown")
        self._log(f"Setting 0xC5_0[7:6] = {mode:02b}b ({ver_name})")
        try:
            data = self.controller.pmbus.read_block(address=self.address, register=0xC5)
            before_hex = " ".join(f"0x{int(b):02X}" for b in data)
            data_write = list(data)
            data_write[0] = (int(data_write[0]) & 0x3F) | (mode << 6)
            self.controller.pmbus.write_block(address=self.address, register=0xC5, data=data_write)
            readback = self.controller.pmbus.read_block(address=self.address, register=0xC5)
            after_hex = " ".join(f"0x{int(b):02X}" for b in readback)
            self._log(f"  0xC5: [{before_hex}] -> [{after_hex}]")
            svi3_mode = (int(readback[0]) >> 6) & 0x03
            self.svi3_version = f"0xC5_0[7:6]={svi3_mode:02b}b ({ver_name})"
            self._update_status_bar()
        except Exception as e:
            self._log(f"  ERROR: {e}")

    def _b2_precondition(self):
        self._log(f"0xB2 Pre-condition: setting byte[2] bit6 (SPS_3V_No_Handshake) on rails {', '.join(self.pmbus_rails)}")
        for page, rail in enumerate(self.pmbus_rails):
            if not self._set_page_checked(page, rail):
                continue
            try:
                b2_before = self.controller.pmbus.read_block(address=self.address, register=0xB2)
                before_hex = " ".join(f"0x{b:02X}" for b in b2_before)

                b2_write = list(b2_before)
                b2_write[2] = b2_write[2] | 0x40
                self.controller.pmbus.write_block(address=self.address, register=0xB2, data=b2_write)

                b2_after = self.controller.pmbus.read_block(address=self.address, register=0xB2)
                after_hex = " ".join(f"0x{b:02X}" for b in b2_after)

                self._log(f"  Rail {rail}: [{before_hex}] -> [{after_hex}]")
            except Exception as e:
                self._log(f"  Rail {rail}: ERROR: {e}")
        self._log("0xB2 Pre-condition done")

    def _b2_reset(self):
        self._log(f"0xB2 Reset: clearing byte[2] bit6 (SPS_3V_No_Handshake) on rails {', '.join(self.pmbus_rails)}")
        for page, rail in enumerate(self.pmbus_rails):
            if not self._set_page_checked(page, rail):
                continue
            try:
                b2_before = self.controller.pmbus.read_block(address=self.address, register=0xB2)
                before_hex = " ".join(f"0x{b:02X}" for b in b2_before)

                b2_write = list(b2_before)
                b2_write[2] = b2_write[2] & ~0x40
                self.controller.pmbus.write_block(address=self.address, register=0xB2, data=b2_write)

                b2_after = self.controller.pmbus.read_block(address=self.address, register=0xB2)
                after_hex = " ".join(f"0x{b:02X}" for b in b2_after)

                self._log(f"  Rail {rail}: [{before_hex}] -> [{after_hex}]")
            except Exception as e:
                self._log(f"  Rail {rail}: ERROR: {e}")
        self._log("0xB2 Reset done")

    def _fault_toggle_auto(self):
        if self.fault_auto_var.get() == "on":
            try:
                self.refresh_interval = int(self.fault_interval_entry.get())
            except ValueError:
                self.refresh_interval = 1000
            self.auto_refresh = True
            self._fault_auto_tick()
        else:
            self.auto_refresh = False

    def _fault_auto_tick(self):
        if not self.auto_refresh:
            return
        self._fault_read_all()
        self.root.after(self.refresh_interval, self._fault_auto_tick)

    # ── Run ────────────────────────────────────────────────────────────────
    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = DebugToolApp()
    app.run()
