from datetime import datetime
import customtkinter as ctk
from instrument import Controller


def connect_controller(address=0x40):
    controller = Controller(auto_detect=False)
    controller.pmbus.set_default_addresses(A=address, B=address)
    controller.page_mode = True
    controller.pmbus.write_byte(address=address, register=0x00, data=0)

    device_id = controller.pmbus.read_block(address=address, register=0xAD)
    name = ''.join(chr(b) for b in device_id)
    print(f"Controller: {name} at 0x{address:02X}")

    return controller


STATUS_MONITOR_0xF9 = {
    0: [
        (7, "rsel_fault"),
        (6, "oen_filt"),
        (5, "slave_fault"),
        (4, "pwrgd"),
        (3, "vddh_uvlob_fault"),
        (2, "uvp"),
        (1, "ovp"),
        (0, "ocl"),
    ],
    1: [
        (7, "num_sl_det[4]"),
        (6, "num_sl_det[3]"),
        (5, "num_sl_det[2]"),
        (4, "num_sl_det[1]"),
        (3, "num_sl_det[0]"),
        (2, "system_on"),
        (1, "vout_max_fault"),
        (0, "vr_settled"),
    ],
    2: [
        (7, "smaddr_fault"),
        (6, "vrhot"),
        (5, "isense2vdd_short"),
        (4, "startup_waiting_for_pwm_fault"),
        (3, "ot_fault"),
        (2, "slave_population_fault"),
        (1, "slave_flt_startup"),
        (0, "pwm_open_fault"),
    ],
    3: [
        (7, "reserved"),
        (6, "tlvr_fault"),
        (5, "wdog"),
        (4, "vddh_uvlo_latch"),
        (3, "sensep_open"),
        (2, "ocp_warn_svi3"),
        (1, "ecc_uncorr_err"),
        (0, "ocp_fault_svi3"),
    ],
}

STATUS_BYTE_0x78 = [
    (7, "unused"),
    (6, "off"),
    (5, "vout_ov_fault"),
    (4, "iout_oc_fault"),
    (3, "vin_uv_fault"),
    (2, "temperature"),
    (1, "cml"),
    (0, "none_of_the_above"),
]

STATUS_WORD_0x79_HIGH = [
    (7, "vout"),
    (6, "iout_pout"),
    (5, "input"),
    (4, "mfr_specific"),
    (3, "power_good_n"),
    (2, "0x79_unused_2"),
    (1, "0x79_unused_1"),
    (0, "0x79_unused_0"),
]

STATUS_VOUT_0x7A = [
    (7, "vout_ov_fault"),
    (6, "0x7A_unused_6"),
    (5, "0x7A_unused_5"),
    (4, "vout_uv_fault"),
    (3, "vout_max_warning"),
    (2, "0x7A_unused_2"),
    (1, "0x7A_unused_1"),
    (0, "0x7A_unused_0"),
]

STATUS_IOUT_0x7B = [
    (7, "iout_oc_fault"),
    (6, "0x7B_unused_6"),
    (5, "iout_oc_warning"),
    (4, "0x7B_unused_4"),
    (3, "current_share_fault"),
    (2, "0x7B_unused_2"),
    (1, "0x7B_unused_1"),
    (0, "0x7B_unused_0"),
]

STATUS_INPUT_0x7C = [
    (7, "0x7C_unused_7"),
    (6, "0x7C_unused_6"),
    (5, "0x7C_unused_5"),
    (4, "vin_uv_fault"),
    (3, "unit_off_insuff_vin"),
    (2, "0x7C_unused_2"),
    (1, "iin_oc_warning"),
    (0, "0x7C_unused_0"),
]

STATUS_TEMP_0x7D = [
    (7, "ot_fault"),
    (6, "ot_warning"),
    (5, "0x7D_unused_5"),
    (4, "0x7D_unused_4"),
    (3, "0x7D_unused_3"),
    (2, "0x7D_unused_2"),
    (1, "0x7D_unused_1"),
    (0, "0x7D_unused_0"),
]

STATUS_CML_0x7E = [
    (7, "invalid_cmd"),
    (6, "invalid_data"),
    (5, "pec_failed"),
    (4, "0x7E_unused_4"),
    (3, "0x7E_unused_3"),
    (2, "0x7E_unused_2"),
    (1, "other_comm_fault"),
    (0, "0x7E_unused_0"),
]

STATUS_MFR_0x80 = [
    (7, "0x80_unused_7"),
    (6, "0x80_unused_6"),
    (5, "0x80_unused_5"),
    (4, "0x80_unused_4"),
    (3, "other_faults"),
    (2, "unprogrammed_rprog_fault"),
    (1, "user_config_max_rewrite_fault"),
    (0, "tsense_fault"),
]

STATUS_BITS = ["pwrgd", "system_on", "vr_settled", "oen_filt", "vddh_uvlob_fault"]


BYTE_LABELS = [
    "Byte 0: Fault Overview",
    "Byte 1: System Status",
    "Byte 2: Extended Faults",
    "Byte 3: Additional Faults",
]

COLOR_GREEN = "#27ae60"
COLOR_RED = "#e74c3c"
COLOR_GRAY = "#bdc3c7"
COLOR_DARK_BG = "#f0f2f5"
COLOR_CARD_BG = "#ffffff"
COLOR_TEXT = "#2c3e50"


RAILS = ["A", "B", "C", "D"]

class StatusMonitorGUI:
    def __init__(self):
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.title("VK87 Status Monitor")
        self.root.geometry("1050x800")
        self.root.configure(fg_color=COLOR_DARK_BG)

        self.controller = None
        self.auto_refresh_running = False
        self.after_id = None
        self.leds = {}
        self.num_phases_labels = {}
        self.raw_data = {}
        self.raw_0xF9_byte_labels = {}
        self.raw_0x78_data = {}
        self.raw_0x78_labels = {}
        self.raw_0x79_data = {}
        self.raw_0x79_labels = {}
        self.status_byte_in_0x79_labels = {}
        self.raw_0x7A_data = {}
        self.raw_0x7A_labels = {}
        self.raw_0x7B_data = {}
        self.raw_0x7B_labels = {}
        self.raw_0x7C_data = {}
        self.raw_0x7C_labels = {}
        self.raw_0x7D_data = {}
        self.raw_0x7D_labels = {}
        self.raw_0x7E_data = {}
        self.raw_0x7E_labels = {}
        self.raw_0x80_data = {}
        self.raw_0x80_labels = {}
        self.page_check_labels = {}

        self._build_connection_frame()
        self._build_tabs()
        self._build_controls()
        self._build_log_window()

    def _build_connection_frame(self):
        frame = ctk.CTkFrame(self.root, fg_color=COLOR_CARD_BG, corner_radius=10)
        frame.pack(fill="x", padx=15, pady=(15, 5))

        top_row = ctk.CTkFrame(frame, fg_color="transparent")
        top_row.pack(fill="x", padx=15, pady=(10, 0))

        ctk.CTkLabel(top_row, text="Connection", font=("Segoe UI", 14, "bold"),
                     text_color=COLOR_TEXT).pack(side="left")

        ctk.CTkLabel(top_row, text="Address:", text_color=COLOR_TEXT).pack(side="left", padx=(20, 5))
        self.addr_entry = ctk.CTkEntry(top_row, width=80, placeholder_text="0x40")
        self.addr_entry.pack(side="left", padx=5)

        self.connect_btn = ctk.CTkButton(top_row, text="Connect", width=100,
                                         command=self.connect, fg_color="#2980b9",
                                         hover_color="#3498db")
        self.connect_btn.pack(side="left", padx=15)

        self.disconnect_btn = ctk.CTkButton(top_row, text="Disconnect", width=100,
                                            command=self.disconnect, fg_color="#c0392b",
                                            hover_color="#e74c3c", state="disabled")
        self.disconnect_btn.pack(side="left", padx=(0, 15))

        self.conn_status = ctk.CTkLabel(top_row, text="Disconnected",
                                        text_color=COLOR_GRAY, font=("Segoe UI", 12))
        self.conn_status.pack(side="left", padx=10)

        ctk.CTkButton(top_row, text="LED Conditions", width=120,
                      command=self._open_led_conditions, fg_color="#d4ac0d",
                      hover_color="#f1c40f", text_color="#000000").pack(side="right", padx=5)

        self.device_info_label = ctk.CTkLabel(frame, text="",
                                              text_color="#5d6d7e", font=("Consolas", 11))
        self.device_info_label.pack(anchor="w", padx=15, pady=(2, 10))

    def _build_tabs(self):
        self.tabview = ctk.CTkTabview(self.root, fg_color=COLOR_DARK_BG,
                                      segmented_button_fg_color="#dce1e8",
                                      segmented_button_selected_color="#2980b9",
                                      command=self._on_tab_change)
        self.tabview.pack(fill="both", expand=True, padx=15, pady=5)

        for rail in RAILS:
            tab = self.tabview.add(f"Rail {rail}")
            self._build_rail_tab(tab, rail)

        self.page_reg_label = ctk.CTkLabel(self.tabview, text="PAGE (0x00): --",
                                           text_color="#5d6d7e", font=("Consolas", 10))
        self.page_reg_label.place(x=10, y=28, anchor="w")

        self.raw_data_label = ctk.CTkLabel(self.tabview, text="0xF9 Raw: --",
                                           text_color="#5d6d7e", font=("Consolas", 10))
        self.raw_data_label.place(x=250, y=28, anchor="w")

    def _build_rail_tab(self, tab, rail):
        # 0x00 PAGE check strip
        page_frame = ctk.CTkFrame(tab, fg_color=COLOR_CARD_BG, corner_radius=8)
        page_frame.pack(fill="x", padx=3, pady=(3, 0))

        page_idx = RAILS.index(rail)
        ctk.CTkLabel(page_frame, text=f"0x00 PAGE (expect 0x{page_idx:02X}):",
                     font=("Segoe UI", 10, "bold"), text_color="#5d6d7e").pack(side="left", padx=(10, 5), pady=6)

        page_result_lbl = ctk.CTkLabel(page_frame, text="--",
                                       text_color=COLOR_GRAY, font=("Consolas", 10))
        page_result_lbl.pack(side="left", padx=(0, 15), pady=6)
        self.page_check_labels[rail] = page_result_lbl

        # 0x78 Status Byte horizontal strip
        sb_frame = ctk.CTkFrame(tab, fg_color=COLOR_CARD_BG, corner_radius=8)
        sb_frame.pack(fill="x", padx=3, pady=(3, 0))

        ctk.CTkLabel(sb_frame, text="0x78 Status Byte:",
                     font=("Segoe UI", 10, "bold"), text_color="#5d6d7e").pack(side="left", padx=(10, 5), pady=6)

        raw_lbl = ctk.CTkLabel(sb_frame, text="[--]",
                               text_color="#5d6d7e", font=("Consolas", 10))
        raw_lbl.pack(side="left", padx=(0, 15), pady=6)
        self.raw_0x78_labels[rail] = raw_lbl

        for _bit_pos, name in STATUS_BYTE_0x78:
            canvas = ctk.CTkCanvas(sb_frame, width=14, height=14,
                                   bg="#ffffff", highlightthickness=0)
            canvas.pack(side="left", padx=(0, 3), pady=6)
            led_circle = canvas.create_oval(1, 1, 13, 13, fill=COLOR_GRAY, outline="")

            if name == "unused":
                display_name = "UNUSED"
            elif name == "none_of_the_above":
                display_name = "OTHER"
            else:
                display_name = name.replace("_fault", "").replace("_", " ").upper()
            ctk.CTkLabel(sb_frame, text=display_name, font=("Segoe UI", 9),
                         text_color="#34495e").pack(side="left", padx=(0, 12), pady=6)

            self.leds[(f"0x78_{name}", rail)] = (canvas, led_circle)

        # 0x79 Status Word (high byte) horizontal strip
        sw_frame = ctk.CTkFrame(tab, fg_color=COLOR_CARD_BG, corner_radius=8)
        sw_frame.pack(fill="x", padx=3, pady=(0, 3))

        ctk.CTkLabel(sw_frame, text="0x79 Status Word (High):",
                     font=("Segoe UI", 10, "bold"), text_color="#5d6d7e").pack(side="left", padx=(10, 5), pady=6)

        raw_sw_lbl = ctk.CTkLabel(sw_frame, text="[--]",
                                  text_color="#5d6d7e", font=("Consolas", 10))
        raw_sw_lbl.pack(side="left", padx=(0, 15), pady=6)
        self.raw_0x79_labels[rail] = raw_sw_lbl

        for bit_pos, name in STATUS_WORD_0x79_HIGH:
            canvas = ctk.CTkCanvas(sw_frame, width=14, height=14,
                                   bg="#ffffff", highlightthickness=0)
            canvas.pack(side="left", padx=(0, 3), pady=6)
            led_circle = canvas.create_oval(1, 1, 13, 13, fill=COLOR_GRAY, outline="")

            if name.startswith("0x79_unused"):
                display_name = "UNUSED"
            else:
                display_name = name.replace("_n", "#").replace("_", " ").upper()
            ctk.CTkLabel(sw_frame, text=display_name, font=("Segoe UI", 9),
                         text_color="#34495e").pack(side="left", padx=(0, 10), pady=6)

            self.leds[(f"0x79_{name}", rail)] = (canvas, led_circle)

        sb_text_lbl = ctk.CTkLabel(sw_frame, text="| Low Byte = -- (Status Byte)",
                                   text_color="#5d6d7e", font=("Consolas", 10))
        sb_text_lbl.pack(side="left", padx=(15, 0), pady=6)
        self.status_byte_in_0x79_labels[rail] = sb_text_lbl

        # 0x7A STATUS_VOUT horizontal strip
        vout_frame = ctk.CTkFrame(tab, fg_color=COLOR_CARD_BG, corner_radius=8)
        vout_frame.pack(fill="x", padx=3, pady=(0, 3))

        ctk.CTkLabel(vout_frame, text="0x7A Status VOUT:",
                     font=("Segoe UI", 10, "bold"), text_color="#5d6d7e").pack(side="left", padx=(10, 5), pady=6)

        raw_7a_lbl = ctk.CTkLabel(vout_frame, text="[--]",
                                  text_color="#5d6d7e", font=("Consolas", 10))
        raw_7a_lbl.pack(side="left", padx=(0, 15), pady=6)
        self.raw_0x7A_labels[rail] = raw_7a_lbl

        for _bit_pos, name in STATUS_VOUT_0x7A:
            canvas = ctk.CTkCanvas(vout_frame, width=14, height=14,
                                   bg="#ffffff", highlightthickness=0)
            canvas.pack(side="left", padx=(0, 3), pady=6)
            led_circle = canvas.create_oval(1, 1, 13, 13, fill=COLOR_GRAY, outline="")

            if name.startswith("0x7A_unused"):
                display_name = "UNUSED"
            else:
                display_name = name.replace("_fault", "").replace("_", " ").upper()
            ctk.CTkLabel(vout_frame, text=display_name, font=("Segoe UI", 9),
                         text_color="#34495e").pack(side="left", padx=(0, 12), pady=6)

            self.leds[(f"0x7A_{name}", rail)] = (canvas, led_circle)

        # 0x7B STATUS_IOUT horizontal strip
        iout_frame = ctk.CTkFrame(tab, fg_color=COLOR_CARD_BG, corner_radius=8)
        iout_frame.pack(fill="x", padx=3, pady=(0, 3))

        ctk.CTkLabel(iout_frame, text="0x7B Status IOUT:",
                     font=("Segoe UI", 10, "bold"), text_color="#5d6d7e").pack(side="left", padx=(10, 5), pady=6)

        raw_7b_lbl = ctk.CTkLabel(iout_frame, text="[--]",
                                  text_color="#5d6d7e", font=("Consolas", 10))
        raw_7b_lbl.pack(side="left", padx=(0, 15), pady=6)
        self.raw_0x7B_labels[rail] = raw_7b_lbl

        for _bit_pos, name in STATUS_IOUT_0x7B:
            canvas = ctk.CTkCanvas(iout_frame, width=14, height=14,
                                   bg="#ffffff", highlightthickness=0)
            canvas.pack(side="left", padx=(0, 3), pady=6)
            led_circle = canvas.create_oval(1, 1, 13, 13, fill=COLOR_GRAY, outline="")

            if name.startswith("0x7B_unused"):
                display_name = "UNUSED"
            else:
                display_name = name.replace("_fault", "").replace("_", " ").upper()
            ctk.CTkLabel(iout_frame, text=display_name, font=("Segoe UI", 9),
                         text_color="#34495e").pack(side="left", padx=(0, 12), pady=6)

            self.leds[(f"0x7B_{name}", rail)] = (canvas, led_circle)

        # 0x7C STATUS_INPUT horizontal strip
        input_frame = ctk.CTkFrame(tab, fg_color=COLOR_CARD_BG, corner_radius=8)
        input_frame.pack(fill="x", padx=3, pady=(0, 3))

        ctk.CTkLabel(input_frame, text="0x7C Status Input:",
                     font=("Segoe UI", 10, "bold"), text_color="#5d6d7e").pack(side="left", padx=(10, 5), pady=6)

        raw_7c_lbl = ctk.CTkLabel(input_frame, text="[--]",
                                  text_color="#5d6d7e", font=("Consolas", 10))
        raw_7c_lbl.pack(side="left", padx=(0, 15), pady=6)
        self.raw_0x7C_labels[rail] = raw_7c_lbl

        for _bit_pos, name in STATUS_INPUT_0x7C:
            canvas = ctk.CTkCanvas(input_frame, width=14, height=14,
                                   bg="#ffffff", highlightthickness=0)
            canvas.pack(side="left", padx=(0, 3), pady=6)
            led_circle = canvas.create_oval(1, 1, 13, 13, fill=COLOR_GRAY, outline="")

            if name.startswith("0x7C_unused"):
                display_name = "UNUSED"
            else:
                display_name = name.replace("_fault", "").replace("_", " ").upper()
            ctk.CTkLabel(input_frame, text=display_name, font=("Segoe UI", 9),
                         text_color="#34495e").pack(side="left", padx=(0, 12), pady=6)

            self.leds[(f"0x7C_{name}", rail)] = (canvas, led_circle)

        # 0x7D STATUS_TEMPERATURE horizontal strip
        temp_frame = ctk.CTkFrame(tab, fg_color=COLOR_CARD_BG, corner_radius=8)
        temp_frame.pack(fill="x", padx=3, pady=(0, 3))

        ctk.CTkLabel(temp_frame, text="0x7D Status Temp:",
                     font=("Segoe UI", 10, "bold"), text_color="#5d6d7e").pack(side="left", padx=(10, 5), pady=6)

        raw_7d_lbl = ctk.CTkLabel(temp_frame, text="[--]",
                                  text_color="#5d6d7e", font=("Consolas", 10))
        raw_7d_lbl.pack(side="left", padx=(0, 15), pady=6)
        self.raw_0x7D_labels[rail] = raw_7d_lbl

        for _bit_pos, name in STATUS_TEMP_0x7D:
            canvas = ctk.CTkCanvas(temp_frame, width=14, height=14,
                                   bg="#ffffff", highlightthickness=0)
            canvas.pack(side="left", padx=(0, 3), pady=6)
            led_circle = canvas.create_oval(1, 1, 13, 13, fill=COLOR_GRAY, outline="")

            if name.startswith("0x7D_unused"):
                display_name = "UNUSED"
            else:
                display_name = name.replace("_fault", "").replace("_", " ").upper()
            ctk.CTkLabel(temp_frame, text=display_name, font=("Segoe UI", 9),
                         text_color="#34495e").pack(side="left", padx=(0, 12), pady=6)

            self.leds[(f"0x7D_{name}", rail)] = (canvas, led_circle)

        # 0x7E STATUS_CML horizontal strip
        cml_frame = ctk.CTkFrame(tab, fg_color=COLOR_CARD_BG, corner_radius=8)
        cml_frame.pack(fill="x", padx=3, pady=(0, 3))

        ctk.CTkLabel(cml_frame, text="0x7E Status CML:",
                     font=("Segoe UI", 10, "bold"), text_color="#5d6d7e").pack(side="left", padx=(10, 5), pady=6)

        raw_7e_lbl = ctk.CTkLabel(cml_frame, text="[--]",
                                  text_color="#5d6d7e", font=("Consolas", 10))
        raw_7e_lbl.pack(side="left", padx=(0, 15), pady=6)
        self.raw_0x7E_labels[rail] = raw_7e_lbl

        for _bit_pos, name in STATUS_CML_0x7E:
            canvas = ctk.CTkCanvas(cml_frame, width=14, height=14,
                                   bg="#ffffff", highlightthickness=0)
            canvas.pack(side="left", padx=(0, 3), pady=6)
            led_circle = canvas.create_oval(1, 1, 13, 13, fill=COLOR_GRAY, outline="")

            if name.startswith("0x7E_unused"):
                display_name = "UNUSED"
            else:
                display_name = name.replace("_fault", "").replace("_", " ").upper()
            ctk.CTkLabel(cml_frame, text=display_name, font=("Segoe UI", 9),
                         text_color="#34495e").pack(side="left", padx=(0, 12), pady=6)

            self.leds[(f"0x7E_{name}", rail)] = (canvas, led_circle)

        # 0x80 STATUS_MFR_SPECIFIC horizontal strip
        mfr_frame = ctk.CTkFrame(tab, fg_color=COLOR_CARD_BG, corner_radius=8)
        mfr_frame.pack(fill="x", padx=3, pady=(0, 3))

        ctk.CTkLabel(mfr_frame, text="0x80 Status MFR:",
                     font=("Segoe UI", 10, "bold"), text_color="#5d6d7e").pack(side="left", padx=(10, 5), pady=6)

        raw_80_lbl = ctk.CTkLabel(mfr_frame, text="[--]",
                                  text_color="#5d6d7e", font=("Consolas", 10))
        raw_80_lbl.pack(side="left", padx=(0, 15), pady=6)
        self.raw_0x80_labels[rail] = raw_80_lbl

        for _bit_pos, name in STATUS_MFR_0x80:
            canvas = ctk.CTkCanvas(mfr_frame, width=14, height=14,
                                   bg="#ffffff", highlightthickness=0)
            canvas.pack(side="left", padx=(0, 3), pady=6)
            led_circle = canvas.create_oval(1, 1, 13, 13, fill=COLOR_GRAY, outline="")

            if name.startswith("0x80_unused"):
                display_name = "UNUSED"
            else:
                display_name = name.replace("_fault", "").replace("_", " ").upper()
            ctk.CTkLabel(mfr_frame, text=display_name, font=("Segoe UI", 9),
                         text_color="#34495e").pack(side="left", padx=(0, 12), pady=6)

            self.leds[(f"0x80_{name}", rail)] = (canvas, led_circle)

        # 0xF9 bytes as horizontal strips
        for byte_idx in range(4):
            frame = ctk.CTkFrame(tab, fg_color=COLOR_CARD_BG, corner_radius=8)
            frame.pack(fill="x", padx=3, pady=(0, 3))

            ctk.CTkLabel(frame, text=f"0xF9 {BYTE_LABELS[byte_idx]}:",
                         font=("Segoe UI", 10, "bold"), text_color="#5d6d7e").pack(side="left", padx=(10, 5), pady=6)

            raw_byte_lbl = ctk.CTkLabel(frame, text="[--]",
                                        text_color="#5d6d7e", font=("Consolas", 10))
            raw_byte_lbl.pack(side="left", padx=(0, 15), pady=6)
            self.raw_0xF9_byte_labels[(byte_idx, rail)] = raw_byte_lbl

            for _bit_pos, name in STATUS_MONITOR_0xF9[byte_idx]:
                if name.startswith("num_sl_det["):
                    continue

                canvas = ctk.CTkCanvas(frame, width=14, height=14,
                                       bg="#ffffff", highlightthickness=0)
                canvas.pack(side="left", padx=(0, 3), pady=6)
                led_circle = canvas.create_oval(1, 1, 13, 13, fill=COLOR_GRAY, outline="")

                display_name = name.replace("_fault", "").replace("_", " ").upper()
                ctk.CTkLabel(frame, text=display_name, font=("Segoe UI", 9),
                             text_color="#34495e").pack(side="left", padx=(0, 10), pady=6)

                self.leds[(name, rail)] = (canvas, led_circle)

            if byte_idx == 1:
                ctk.CTkLabel(frame, text="| PS[4:0]=", font=("Segoe UI", 9),
                             text_color="#34495e").pack(side="left", padx=(10, 0), pady=6)
                lbl = ctk.CTkLabel(frame, text="--", font=("Segoe UI", 9, "bold"),
                                   text_color=COLOR_TEXT)
                lbl.pack(side="left", padx=3, pady=6)
                self.num_phases_labels[rail] = lbl

    def _on_tab_change(self):
        if self.controller is None:
            self.page_reg_label.configure(text="PAGE (0x00): --")
            self.raw_data_label.configure(text="0xF9 Raw: --")
            return
        try:
            address = self._get_address()
            tab_name = self.tabview.get()
            page = RAILS.index(tab_name.replace("Rail ", ""))
            self.controller.pmbus.write_byte(address=address, register=0x00, data=page)
            readback = self.controller.pmbus.read_byte(address=address, register=0x00)
            self.page_reg_label.configure(
                text=f"PAGE (0x00): {int(readback)} (Rail {RAILS[int(readback)]})",
                text_color=COLOR_TEXT)
            self._update_raw_data_label()
        except Exception as e:
            self.page_reg_label.configure(text=f"PAGE (0x00): Error - {e}",
                                          text_color=COLOR_RED)

    def _update_raw_data_label(self):
        tab_name = self.tabview.get()
        rail = tab_name.replace("Rail ", "")
        data = self.raw_data.get(rail)
        if data is None:
            self.raw_data_label.configure(text="0xF9 Raw: --")
        else:
            hex_str = " ".join(f"0x{b:02X}" for b in data)
            self.raw_data_label.configure(text=f"0xF9 Raw: [{hex_str}]", text_color=COLOR_TEXT)

        for r in RAILS:
            rd = self.raw_data.get(r)
            for byte_idx in range(4):
                lbl_key = (byte_idx, r)
                byte_lbl = self.raw_0xF9_byte_labels.get(lbl_key)
                if byte_lbl is not None:
                    if rd is None:
                        byte_lbl.configure(text="[--]")
                    else:
                        byte_lbl.configure(text=f"[0x{rd[byte_idx]:02X}]", text_color=COLOR_TEXT)

        for r in RAILS:
            lbl = self.raw_0x78_labels.get(r)
            if lbl is not None:
                sb = self.raw_0x78_data.get(r)
                if sb is None:
                    lbl.configure(text="[--]")
                else:
                    lbl.configure(text=f"[0x{sb:02X}]", text_color=COLOR_TEXT)

            lbl79 = self.raw_0x79_labels.get(r)
            sb_lbl = self.status_byte_in_0x79_labels.get(r)
            sw = self.raw_0x79_data.get(r)
            if lbl79 is not None:
                if sw is None:
                    lbl79.configure(text="[--]")
                else:
                    lbl79.configure(text=f"[0x{sw:04X}]", text_color=COLOR_TEXT)
            if sb_lbl is not None:
                if sw is None:
                    sb_lbl.configure(text="| Low Byte = -- (Status Byte)")
                else:
                    low_byte = sw & 0xFF
                    sb_lbl.configure(text=f"| Low Byte = 0x{low_byte:02X} (Status Byte)", text_color=COLOR_TEXT)

            lbl7a = self.raw_0x7A_labels.get(r)
            if lbl7a is not None:
                val7a = self.raw_0x7A_data.get(r)
                if val7a is None:
                    lbl7a.configure(text="[--]")
                else:
                    lbl7a.configure(text=f"[0x{val7a:02X}]", text_color=COLOR_TEXT)

            lbl7b = self.raw_0x7B_labels.get(r)
            if lbl7b is not None:
                val7b = self.raw_0x7B_data.get(r)
                if val7b is None:
                    lbl7b.configure(text="[--]")
                else:
                    lbl7b.configure(text=f"[0x{val7b:02X}]", text_color=COLOR_TEXT)

            lbl7c = self.raw_0x7C_labels.get(r)
            if lbl7c is not None:
                val7c = self.raw_0x7C_data.get(r)
                if val7c is None:
                    lbl7c.configure(text="[--]")
                else:
                    lbl7c.configure(text=f"[0x{val7c:02X}]", text_color=COLOR_TEXT)

            lbl7d = self.raw_0x7D_labels.get(r)
            if lbl7d is not None:
                val7d = self.raw_0x7D_data.get(r)
                if val7d is None:
                    lbl7d.configure(text="[--]")
                else:
                    lbl7d.configure(text=f"[0x{val7d:02X}]", text_color=COLOR_TEXT)

            lbl7e = self.raw_0x7E_labels.get(r)
            if lbl7e is not None:
                val7e = self.raw_0x7E_data.get(r)
                if val7e is None:
                    lbl7e.configure(text="[--]")
                else:
                    lbl7e.configure(text=f"[0x{val7e:02X}]", text_color=COLOR_TEXT)

            lbl80 = self.raw_0x80_labels.get(r)
            if lbl80 is not None:
                val80 = self.raw_0x80_data.get(r)
                if val80 is None:
                    lbl80.configure(text="[--]")
                else:
                    lbl80.configure(text=f"[0x{val80:02X}]", text_color=COLOR_TEXT)

    def _build_controls(self):
        ctk.CTkLabel(self.root,
                     text="⚠ This GUI is not fully tested yet, please verify with PMBus UserGuide and Digital Interface",
                     font=("Segoe UI", 10, "bold"), text_color=COLOR_RED
                     ).pack(anchor="w", padx=18, pady=(5, 0))

        frame = ctk.CTkFrame(self.root, fg_color=COLOR_CARD_BG, corner_radius=10)
        frame.pack(fill="x", padx=15, pady=(5, 15))

        self.refresh_btn = ctk.CTkButton(frame, text="Refresh", width=100,
                                         command=self.refresh, fg_color="#2980b9",
                                         hover_color="#3498db")
        self.refresh_btn.pack(side="left", padx=15, pady=10)

        self.auto_btn = ctk.CTkButton(frame, text="Start Auto", width=110,
                                      command=self.toggle_auto_refresh, fg_color="#2980b9",
                                      hover_color="#3498db")
        self.auto_btn.pack(side="left", padx=5, pady=10)

        ctk.CTkLabel(frame, text="Interval (ms):", text_color=COLOR_TEXT).pack(side="left", padx=(20, 5))
        self.interval_entry = ctk.CTkEntry(frame, width=70)
        self.interval_entry.insert(0, "1000")
        self.interval_entry.pack(side="left", padx=5)

        self.fault_summary = ctk.CTkLabel(frame, text="", font=("Segoe UI", 11),
                                          text_color=COLOR_GREEN)
        self.fault_summary.pack(side="right", padx=15, pady=10)


    def _build_log_window(self):
        log_frame = ctk.CTkFrame(self.root, fg_color=COLOR_CARD_BG, corner_radius=10)
        log_frame.pack(fill="both", expand=True, padx=15, pady=(5, 15))

        header = ctk.CTkFrame(log_frame, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(5, 0))
        ctk.CTkLabel(header, text="Log", font=("Segoe UI", 10, "bold"),
                     text_color="#5d6d7e").pack(side="left")
        ctk.CTkButton(header, text="Clear", width=50, height=22,
                      font=("Segoe UI", 9), command=self._clear_log).pack(side="right")

        self.log_textbox = ctk.CTkTextbox(log_frame, font=("Consolas", 10),
                                          fg_color="#f8f9fa", text_color=COLOR_TEXT,
                                          height=120)
        self.log_textbox.pack(fill="both", expand=True, padx=10, pady=(2, 10))
        self.log_textbox.configure(state="disabled")

    def _log(self, text):
        self.log_textbox.configure(state="normal")
        self.log_textbox.insert("end", text + "\n")
        self.log_textbox.see("end")
        self.log_textbox.configure(state="disabled")

    def _clear_log(self):
        self.log_textbox.configure(state="normal")
        self.log_textbox.delete("1.0", "end")
        self.log_textbox.configure(state="disabled")

    def connect(self):
        try:
            addr_text = self.addr_entry.get().strip()
            if addr_text:
                address = int(addr_text, 16) if addr_text.startswith("0x") else int(addr_text)
            else:
                address = 0x40

            self.conn_status.configure(text="Connecting...", text_color="#f39c12")
            self.root.update_idletasks()

            self.controller = connect_controller(address)

            device_name = self.controller.get_name()
            fw_signature = self.controller.get_firmware_signature()

            self.conn_status.configure(
                text=f"Connected (0x{address:02X})", text_color=COLOR_GREEN)
            self.device_info_label.configure(
                text=f"{device_name} | FW: {fw_signature}")
            self.connect_btn.configure(state="disabled")
            self.disconnect_btn.configure(state="normal")
            self.refresh()
        except ValueError as e:
            self.conn_status.configure(text=f"Invalid address: {e}", text_color=COLOR_RED)
            self.device_info_label.configure(text="")
            self.controller = None
        except ConnectionError as e:
            self.conn_status.configure(text="No device found", text_color=COLOR_RED)
            self.device_info_label.configure(text=str(e))
            self.controller = None
        except OSError as e:
            self.conn_status.configure(text="No dongle found", text_color=COLOR_RED)
            self.device_info_label.configure(text=str(e))
            self.controller = None
        except Exception as e:
            self.conn_status.configure(text=f"Error: {e}", text_color=COLOR_RED)
            self.device_info_label.configure(text="")
            if self.controller is not None:
                try:
                    self.controller.disconnect()
                except Exception:
                    pass
            self.controller = None

    def disconnect(self):
        if self.auto_refresh_running:
            self.toggle_auto_refresh()
        if self.controller is not None:
            self.controller.disconnect()
        self.controller = None
        self.conn_status.configure(text="Disconnected", text_color=COLOR_GRAY)
        self.device_info_label.configure(text="")
        self.connect_btn.configure(state="normal")
        self.disconnect_btn.configure(state="disabled")
        self._set_all_gray()
        self.fault_summary.configure(text="")

    def _get_address(self):
        addr_text = self.addr_entry.get().strip()
        if addr_text:
            return int(addr_text, 16) if addr_text.startswith("0x") else int(addr_text)
        return int(self.controller.pmbus.get_address_A())

    def refresh(self):
        if self.controller is None:
            self.conn_status.configure(text="Not connected", text_color=COLOR_RED)
            return

        try:
            address = self._get_address()
            all_results = {}

            all_status_byte = {}

            for page, rail in enumerate(RAILS):
                self.controller.pmbus.set_page(page)

                page_readback = int(self.controller.pmbus.read_byte(address=address, register=0x00))
                lbl = self.page_check_labels.get(rail)
                if lbl:
                    if page_readback == page:
                        lbl.configure(text=f"Read=0x{page_readback:02X} PASS", text_color=COLOR_GREEN)
                    else:
                        lbl.configure(text=f"Read=0x{page_readback:02X} FAIL", text_color=COLOR_RED)

                data = self.controller.pmbus.read_block(address=address, register=0xF9)
                if len(data) < 4:
                    all_results[rail] = None
                    self.raw_data[rail] = None
                else:
                    self.raw_data[rail] = data[:4]
                    all_results[rail] = self._parse_data(data)

                sb = self.controller.pmbus.read_byte(address=address, register=0x78)
                all_status_byte[rail] = int(sb)
                self.raw_0x78_data[rail] = int(sb)

                sw = self.controller.pmbus.read_word(address=address, register=0x79, merge=True)
                self.raw_0x79_data[rail] = int(sw)

                sv = self.controller.pmbus.read_byte(address=address, register=0x7A)
                self.raw_0x7A_data[rail] = int(sv)

                si = self.controller.pmbus.read_byte(address=address, register=0x7B)
                self.raw_0x7B_data[rail] = int(si)

                sin = self.controller.pmbus.read_byte(address=address, register=0x7C)
                self.raw_0x7C_data[rail] = int(sin)

                st = self.controller.pmbus.read_byte(address=address, register=0x7D)
                self.raw_0x7D_data[rail] = int(st)

                scml = self.controller.pmbus.read_byte(address=address, register=0x7E)
                self.raw_0x7E_data[rail] = int(scml)

                smfr = self.controller.pmbus.read_byte(address=address, register=0x80)
                self.raw_0x80_data[rail] = int(smfr)

            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            parts = []
            for rail in RAILS:
                f9 = self.raw_data.get(rail)
                f9_str = " ".join(f"{b:02X}" for b in f9) if f9 else "--"
                sb_val = self.raw_0x78_data.get(rail)
                sw_val = self.raw_0x79_data.get(rail)
                parts.append(
                    f"Rail{rail}: 0x78={sb_val:02X} 0x79={sw_val:04X} "
                    f"0x7A={self.raw_0x7A_data.get(rail, 0):02X} "
                    f"0x7B={self.raw_0x7B_data.get(rail, 0):02X} "
                    f"0x7C={self.raw_0x7C_data.get(rail, 0):02X} "
                    f"0x7D={self.raw_0x7D_data.get(rail, 0):02X} "
                    f"0x7E={self.raw_0x7E_data.get(rail, 0):02X} "
                    f"0x80={self.raw_0x80_data.get(rail, 0):02X} "
                    f"0xF9=[{f9_str}]"
                )
            self._log(f"[{ts}] " + " | ".join(parts))

            tab_name = self.tabview.get()
            selected_page = RAILS.index(tab_name.replace("Rail ", ""))
            self.controller.pmbus.set_page(selected_page)
            readback = self.controller.pmbus.read_byte(address=address, register=0x00)
            self.page_reg_label.configure(
                text=f"PAGE (0x00): {int(readback)} (Rail {RAILS[int(readback)]})",
                text_color=COLOR_TEXT)
            self._update_raw_data_label()
            self._update_all_leds(all_results, all_status_byte)

        except Exception as e:
            self.fault_summary.configure(text=f"Read error: {e}", text_color=COLOR_RED)
            self._set_all_gray()

    def _parse_data(self, data):
        result = {}
        for byte_idx in range(4):
            byte_val = data[byte_idx]
            for bit_pos, name in STATUS_MONITOR_0xF9[byte_idx]:
                result[name] = (byte_val >> bit_pos) & 1

        num_sl_det = 0
        for i in range(5):
            num_sl_det |= result[f"num_sl_det[{i}]"] << i
        result["num_sl_det"] = num_sl_det
        return result

    def _update_all_leds(self, all_results, all_status_byte=None):
        total_faults = 0

        for rail in RAILS:
            result = all_results.get(rail)

            if result is None:
                for key, (canvas, circle) in self.leds.items():
                    if key[1] == rail:
                        canvas.itemconfig(circle, fill=COLOR_GRAY)
                self.num_phases_labels[rail].configure(text="--")
                continue

            rail_faults = 0
            for byte_idx in range(4):
                for _, name in STATUS_MONITOR_0xF9[byte_idx]:
                    if name.startswith("num_sl_det["):
                        continue
                    key = (name, rail)
                    if key not in self.leds:
                        continue

                    canvas, circle = self.leds[key]
                    val = result.get(name, 0)

                    if name == "reserved":
                        color = COLOR_RED if val else COLOR_GRAY
                    elif name in STATUS_BITS:
                        color = COLOR_GREEN if val else COLOR_RED
                        if not val:
                            rail_faults += 1
                    else:
                        color = COLOR_RED if val else COLOR_GREEN
                        if val:
                            rail_faults += 1

                    canvas.itemconfig(circle, fill=color)

            # Update 0x78 STATUS_BYTE LEDs
            if all_status_byte and rail in all_status_byte:
                sb_val = all_status_byte[rail]
                for bit_pos, name in STATUS_BYTE_0x78:
                    key = (f"0x78_{name}", rail)
                    if key not in self.leds:
                        continue
                    canvas, circle = self.leds[key]
                    val = (sb_val >> bit_pos) & 1

                    if name == "unused":
                        color = COLOR_RED if val else COLOR_GRAY
                    else:
                        color = COLOR_RED if val else COLOR_GREEN
                    if val:
                        rail_faults += 1

                    canvas.itemconfig(circle, fill=color)

            # Update 0x79 STATUS_WORD (high byte) LEDs
            sw_val = self.raw_0x79_data.get(rail)
            if sw_val is not None:
                high_byte = (sw_val >> 8) & 0xFF
                for bit_pos, name in STATUS_WORD_0x79_HIGH:
                    key = (f"0x79_{name}", rail)
                    if key not in self.leds:
                        continue
                    canvas, circle = self.leds[key]
                    val = (high_byte >> bit_pos) & 1

                    if name.startswith("0x79_unused"):
                        color = COLOR_RED if val else COLOR_GRAY
                        if val:
                            rail_faults += 1
                    elif name == "power_good_n":
                        color = COLOR_RED if val else COLOR_GREEN
                        if val:
                            rail_faults += 1
                    else:
                        color = COLOR_RED if val else COLOR_GREEN
                        if val:
                            rail_faults += 1

                    canvas.itemconfig(circle, fill=color)

            # Update 0x7A STATUS_VOUT LEDs
            val_7a = self.raw_0x7A_data.get(rail)
            if val_7a is not None:
                for bit_pos, name in STATUS_VOUT_0x7A:
                    key = (f"0x7A_{name}", rail)
                    if key not in self.leds:
                        continue
                    canvas, circle = self.leds[key]
                    val = (val_7a >> bit_pos) & 1
                    if name.startswith("0x7A_unused"):
                        color = COLOR_RED if val else COLOR_GRAY
                    else:
                        color = COLOR_RED if val else COLOR_GREEN
                    if val:
                        rail_faults += 1
                    canvas.itemconfig(circle, fill=color)

            # Update 0x7B STATUS_IOUT LEDs
            val_7b = self.raw_0x7B_data.get(rail)
            if val_7b is not None:
                for bit_pos, name in STATUS_IOUT_0x7B:
                    key = (f"0x7B_{name}", rail)
                    if key not in self.leds:
                        continue
                    canvas, circle = self.leds[key]
                    val = (val_7b >> bit_pos) & 1
                    if name.startswith("0x7B_unused"):
                        color = COLOR_RED if val else COLOR_GRAY
                    else:
                        color = COLOR_RED if val else COLOR_GREEN
                    if val:
                        rail_faults += 1
                    canvas.itemconfig(circle, fill=color)

            # Update 0x7C STATUS_INPUT LEDs
            val_7c = self.raw_0x7C_data.get(rail)
            if val_7c is not None:
                for bit_pos, name in STATUS_INPUT_0x7C:
                    key = (f"0x7C_{name}", rail)
                    if key not in self.leds:
                        continue
                    canvas, circle = self.leds[key]
                    val = (val_7c >> bit_pos) & 1
                    if name.startswith("0x7C_unused"):
                        color = COLOR_RED if val else COLOR_GRAY
                    else:
                        color = COLOR_RED if val else COLOR_GREEN
                    if val:
                        rail_faults += 1
                    canvas.itemconfig(circle, fill=color)

            # Update 0x7D STATUS_TEMPERATURE LEDs
            val_7d = self.raw_0x7D_data.get(rail)
            if val_7d is not None:
                for bit_pos, name in STATUS_TEMP_0x7D:
                    key = (f"0x7D_{name}", rail)
                    if key not in self.leds:
                        continue
                    canvas, circle = self.leds[key]
                    val = (val_7d >> bit_pos) & 1
                    if name.startswith("0x7D_unused"):
                        color = COLOR_RED if val else COLOR_GRAY
                    else:
                        color = COLOR_RED if val else COLOR_GREEN
                    if val:
                        rail_faults += 1
                    canvas.itemconfig(circle, fill=color)

            # Update 0x7E STATUS_CML LEDs
            val_7e = self.raw_0x7E_data.get(rail)
            if val_7e is not None:
                for bit_pos, name in STATUS_CML_0x7E:
                    key = (f"0x7E_{name}", rail)
                    if key not in self.leds:
                        continue
                    canvas, circle = self.leds[key]
                    val = (val_7e >> bit_pos) & 1
                    if name.startswith("0x7E_unused"):
                        color = COLOR_RED if val else COLOR_GRAY
                    else:
                        color = COLOR_RED if val else COLOR_GREEN
                    if val:
                        rail_faults += 1
                    canvas.itemconfig(circle, fill=color)

            # Update 0x80 STATUS_MFR_SPECIFIC LEDs
            val_80 = self.raw_0x80_data.get(rail)
            if val_80 is not None:
                for bit_pos, name in STATUS_MFR_0x80:
                    key = (f"0x80_{name}", rail)
                    if key not in self.leds:
                        continue
                    canvas, circle = self.leds[key]
                    val = (val_80 >> bit_pos) & 1
                    if name.startswith("0x80_unused"):
                        color = COLOR_RED if val else COLOR_GRAY
                    else:
                        color = COLOR_RED if val else COLOR_GREEN
                    if val:
                        rail_faults += 1
                    canvas.itemconfig(circle, fill=color)

            self.num_phases_labels[rail].configure(text=str(result.get("num_sl_det", 0)))
            total_faults += rail_faults

        if total_faults:
            self.fault_summary.configure(text=f"{total_faults} fault(s)", text_color=COLOR_RED)
        else:
            self.fault_summary.configure(text="All rails OK", text_color=COLOR_GREEN)

    def _set_all_gray(self):
        for canvas, circle in self.leds.values():
            canvas.itemconfig(circle, fill=COLOR_GRAY)
        for rail in RAILS:
            self.num_phases_labels[rail].configure(text="--")

    def toggle_auto_refresh(self):
        if self.auto_refresh_running:
            self.auto_refresh_running = False
            self.auto_btn.configure(text="Start Auto")
            if self.after_id:
                self.root.after_cancel(self.after_id)
                self.after_id = None
        else:
            self.auto_refresh_running = True
            self.auto_btn.configure(text="Stop Auto")
            self._auto_loop()

    def _auto_loop(self):
        if not self.auto_refresh_running:
            return
        self.refresh()
        try:
            interval = int(self.interval_entry.get())
        except ValueError:
            interval = 1000
        self.after_id = self.root.after(interval, self._auto_loop)

    def _open_led_conditions(self):
        LEDConditionsWindow(self.root)

    def run(self):
        self.root.mainloop()


class LEDConditionsWindow(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("LED Conditions Reference")
        self.geometry("900x600")

        header = ctk.CTkLabel(self, text="LED Color Conditions",
                              font=("Segoe UI", 14, "bold"), text_color="#2c3e50")
        header.pack(pady=(10, 5))

        legend = ctk.CTkLabel(self,
                              text="GREEN = normal/expected  |  RED = fault/unexpected  |  GRAY = unused bit reads 0 (expected)",
                              font=("Segoe UI", 10), text_color="#5d6d7e")
        legend.pack(pady=(0, 10))

        hdr = f"{'Register':<12}{'Bit':<5}{'Name':<35}{'Green':<25}{'Red':<25}{'Gray':<20}"
        hdr_label = ctk.CTkLabel(self, text=hdr, font=("Consolas", 10, "bold"),
                                 text_color="#2c3e50", anchor="w", justify="left")
        hdr_label.pack(fill="x", padx=15, pady=(0, 0))

        sep = ctk.CTkLabel(self, text="-" * len(hdr), font=("Consolas", 10),
                           text_color="#5d6d7e", anchor="w", justify="left")
        sep.pack(fill="x", padx=15, pady=(0, 2))

        textbox = ctk.CTkTextbox(self, font=("Consolas", 10), fg_color="#f8f9fa",
                                 text_color="#2c3e50")
        textbox.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        lines = self._build_table()
        textbox.insert("1.0", "\n".join(lines))
        textbox.configure(state="disabled")

    def _build_table(self):
        lines = []

        lines.append("--- 0x00 PAGE ---")
        lines.append(f"{'0x00':<12}{'N/A':<5}{'page_check':<35}{'Readback matches page':<25}{'Readback mismatch':<25}{'Never':<20}")

        register_defs = [
            ("0x78", "STATUS_BYTE", STATUS_BYTE_0x78, None),
            ("0x79", "STATUS_WORD (High)", STATUS_WORD_0x79_HIGH, None),
            ("0x7A", "STATUS_VOUT", STATUS_VOUT_0x7A, "0x7A_unused"),
            ("0x7B", "STATUS_IOUT", STATUS_IOUT_0x7B, "0x7B_unused"),
            ("0x7C", "STATUS_INPUT", STATUS_INPUT_0x7C, "0x7C_unused"),
            ("0x7D", "STATUS_TEMPERATURE", STATUS_TEMP_0x7D, "0x7D_unused"),
            ("0x7E", "STATUS_CML", STATUS_CML_0x7E, "0x7E_unused"),
            ("0x80", "STATUS_MFR_SPECIFIC", STATUS_MFR_0x80, "0x80_unused"),
        ]

        for reg, label, bits, unused_prefix in register_defs:
            lines.append("")
            lines.append(f"--- {reg} {label} ---")
            for bit_pos, name in bits:
                if name == "unused" or (unused_prefix and name.startswith(unused_prefix)) or name.startswith("0x79_unused"):
                    green, red, gray = "Never", "Bit=1 (unexpected)", "Bit=0 (expected)"
                elif name == "none_of_the_above":
                    green, red, gray = "Bit=0", "Bit=1", "Never"
                elif name == "power_good_n":
                    green, red, gray = "Bit=0", "Bit=1", "Never"
                else:
                    green, red, gray = "Bit=0", "Bit=1", "Never"
                lines.append(f"{reg:<12}{bit_pos:<5}{name:<35}{green:<25}{red:<25}{gray:<20}")

        for byte_idx in range(4):
            byte_label = f"Byte{byte_idx}"
            lines.append("")
            lines.append(f"--- 0xF9 STATUS_MONITOR {byte_label} ---")
            for bit_pos, name in STATUS_MONITOR_0xF9[byte_idx]:
                if name == "reserved":
                    green, red, gray = "Never", "Bit=1 (unexpected)", "Bit=0 (expected)"
                elif name in STATUS_BITS:
                    green, red, gray = "Bit=1", "Bit=0", "Never"
                else:
                    green, red, gray = "Bit=0", "Bit=1", "Never"
                lines.append(f"{'0xF9':<12}{bit_pos:<5}{name:<35}{green:<25}{red:<25}{gray:<20}")

        return lines


if __name__ == "__main__":
    app = StatusMonitorGUI()
    app.run()