import os
import sys
import threading
import tkinter.font as tkfont
from datetime import datetime
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap.dialogs import Messagebox
import pyvisa


class DeviceDetector:
    # A wedged USBTMC device (seen on PLZ664WA) blocks inside NI-VISA and ignores the VISA timeout,
    # so each probe runs in its own thread and is abandoned after this many seconds.
    PROBE_TIMEOUT_S = 6

    def __init__(self, rm, resources, config):
        self.rm = rm
        self.resources = resources
        self.config = config
        self.detected = {}
        self.hung = []

    def _probe(self, resource, out):
        try:
            with self.rm.open_resource(resource) as inst:
                inst.timeout = 3000
                out["idn"] = inst.query("*IDN?").strip()
        except Exception:
            pass

    def scan(self, progress_callback=None):
        total = len(self.resources)
        for i, resource in enumerate(self.resources):
            if progress_callback:
                progress_callback(i, total, resource)
            out = {}
            probe = threading.Thread(target=self._probe, args=(resource, out), daemon=True)
            probe.start()
            probe.join(self.PROBE_TIMEOUT_S)
            if probe.is_alive():
                self.hung.append(resource)
                continue
            idn = out.get("idn")
            if not idn:
                continue
            idn_fields = [f.strip().upper() for f in idn.split(",")]
            for tab_name, keyword in self.config.items():
                if keyword.upper() in idn_fields:
                    self.detected[tab_name] = (resource, idn)
        if progress_callback:
            progress_callback(total, total, "")
        return self.detected


class DetectProgressWindow:
    def __init__(self, parent, resources, config):
        self.parent = parent
        self.resources = resources
        self.config = config
        self.detected = {}
        self.rm = pyvisa.ResourceManager()

        self.window = ttk.Toplevel(parent)
        self.window.title("Detecting Instruments")
        self.window.geometry("500x180")
        self.window.resizable(True, True)
        self.window.grab_set()
        self._center_window(self.window, 500, 180)

        frame = ttk.Frame(self.window, padding=20)
        frame.pack(fill=BOTH, expand=True)

        ttk.Label(
            frame, text="Scanning connected instruments...",
            font=("Segoe UI", 11, "bold")
        ).pack(anchor=W)

        self.status_label = ttk.Label(
            frame, text="Initializing...",
            font=("Segoe UI", 9), bootstyle="secondary"
        )
        self.status_label.pack(anchor=W, pady=(8, 4))

        self.progress = ttk.Progressbar(
            frame, length=440, mode="determinate",
            maximum=len(resources), bootstyle="info-striped"
        )
        self.progress.pack(fill=X, pady=(4, 0))

        self.count_label = ttk.Label(
            frame, text="0 / {} resources".format(len(resources)),
            font=("Segoe UI", 9), bootstyle="secondary"
        )
        self.count_label.pack(anchor=E, pady=(4, 0))

    def start_scan(self):
        detector = DeviceDetector(self.rm, self.resources, self.config)
        thread = threading.Thread(target=self._run_scan, args=(detector,), daemon=True)
        thread.start()

    def _run_scan(self, detector):
        detector.scan(progress_callback=self._on_progress)
        self.detected = detector.detected
        self.window.after(0, self._on_complete, detector.hung)

    def _on_progress(self, current, total, resource):
        self.window.after(0, self._update_ui, current, total, resource)

    def _update_ui(self, current, total, resource):
        self.progress["value"] = current
        self.count_label.config(text=f"{current} / {total} resources")
        if resource:
            display = resource if len(resource) < 55 else resource[:52] + "..."
            self.status_label.config(text=display)
        else:
            self.status_label.config(text="Done.")

    def _on_complete(self, hung):
        if hung:
            Messagebox.show_warning(
                "No response within {} s (skipped):\n\n{}\n\n"
                "Replug USB or power-cycle the instrument, then Rescan.".format(
                    DeviceDetector.PROBE_TIMEOUT_S, "\n".join(hung)),
                title="Instrument not responding", parent=self.window,
            )
        self.window.destroy()

    def _center_window(self, win, w, h):
        x = (win.winfo_screenwidth() - w) // 2
        y = (win.winfo_screenheight() - h) // 2
        win.geometry(f"{w}x{h}+{x}+{y}")


class DetectSummaryWindow:
    def __init__(self, parent, config, detected, rm=None, on_open_device=None, on_open_scpi=None, on_rescan=None, on_open_quick_actions=None):
        self.parent = parent
        self.config = config
        self.detected = detected
        self.rm = rm
        self.on_open_device = on_open_device
        self.on_open_scpi = on_open_scpi
        self.on_rescan = on_rescan
        self.on_open_quick_actions = on_open_quick_actions
        self.result = None

        self.sm_active = False
        self.sm_inst_hps = None
        self.sm_inst_wg = None
        self.sm_condition_start = None

        self.window = ttk.Toplevel(parent)
        self.window.title("ADTH Application Bench Instrument Control")
        self.window.geometry("700x580")
        self.window.resizable(True, True)
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)
        self._center_window(self.window, 700, 580)

        main_frame = ttk.Frame(self.window, padding=20)
        main_frame.pack(fill=BOTH, expand=True)

        self._build_system_manager(main_frame)

        found = len(detected)
        total = len(config)
        header_style = "success" if found == total else "warning"
        ttk.Label(
            main_frame,
            text=f"Devices found: {found} / {total}",
            font=("Segoe UI", 12, "bold"),
            bootstyle=header_style
        ).pack(anchor=W, pady=(0, 12))

        scroll_frame = ttk.Frame(main_frame)
        scroll_frame.pack(fill=BOTH, expand=True)

        canvas = ttk.Canvas(scroll_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(scroll_frame, orient=VERTICAL, command=canvas.yview)
        self.inner_frame = ttk.Frame(canvas)

        self.inner_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.inner_frame, anchor=NW)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)

        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", lambda ev: canvas.yview_scroll(-ev.delta // 120, "units")))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        self._populate_results()

        if found < total:
            ttk.Label(
                main_frame,
                text="Some devices were not found. Check connections and device_config.txt.",
                font=("Segoe UI", 9),
                bootstyle="danger",
                wraplength=540
            ).pack(anchor=W, pady=(10, 0))

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=X, pady=(12, 0))

        ttk.Button(
            btn_frame, text="Open device_config.txt",
            bootstyle="outline",
            command=self._open_config
        ).pack(side=LEFT)

        if self.on_rescan:
            ttk.Button(
                btn_frame, text="Rescan Devices",
                bootstyle="warning",
                command=self._rescan
            ).pack(side=LEFT, padx=(8, 0))

        if self.on_open_scpi:
            ttk.Button(
                btn_frame, text="SCPI Low Level",
                bootstyle="secondary",
                command=self.on_open_scpi
            ).pack(side=RIGHT)

        if self.on_open_quick_actions:
            ttk.Button(
                btn_frame, text="Frequent Use",
                bootstyle="success",
                command=self.on_open_quick_actions
            ).pack(side=RIGHT, padx=(0, 8))

    def _build_system_manager(self, parent):
        sm_available = (
            "high_power_supply" in self.detected
            and "waveform_generator" in self.detected
            and self.rm is not None
        )
        sm_frame = ttk.Labelframe(parent, text="System Manager", padding=10)
        sm_frame.pack(fill=X, pady=(0, 12))

        ttk.Label(
            sm_frame,
            text="Auto-shutdown if HPS current > threshold and waveform generator is ON continuously.",
            font=("Segoe UI", 9), bootstyle="secondary"
        ).pack(anchor=W, pady=(0, 6))

        if not sm_available:
            ttk.Label(
                sm_frame,
                text="Requires High Power Supply and Waveform Generator to be detected.",
                bootstyle="danger", font=("Segoe UI", 9)
            ).pack(anchor=W)
            return

        row1 = ttk.Frame(sm_frame)
        row1.pack(fill=X, pady=(0, 6))

        ttk.Label(row1, text="Current Threshold (A):").pack(side=LEFT, padx=(0, 4))
        self.sm_current_var = ttk.StringVar(value="2.0")
        ttk.Entry(row1, textvariable=self.sm_current_var, width=8).pack(side=LEFT, padx=(0, 16))

        ttk.Label(row1, text="Time (min):").pack(side=LEFT, padx=(0, 4))
        self.sm_time_var = ttk.StringVar(value="10")
        ttk.Entry(row1, textvariable=self.sm_time_var, width=6).pack(side=LEFT, padx=(0, 16))

        ttk.Label(row1, text="Poll Interval (s):").pack(side=LEFT, padx=(0, 4))
        self.sm_poll_var = ttk.StringVar(value="30")
        ttk.Entry(row1, textvariable=self.sm_poll_var, width=6).pack(side=LEFT)

        row2 = ttk.Frame(sm_frame)
        row2.pack(fill=X)

        self.sm_start_btn = ttk.Button(
            row2, text="Start", bootstyle="success", width=8,
            command=self._sm_start
        )
        self.sm_start_btn.pack(side=LEFT, padx=(0, 8))
        self.sm_stop_btn = ttk.Button(
            row2, text="Stop", bootstyle="danger", width=8,
            command=self._sm_stop, state=DISABLED
        )
        self.sm_stop_btn.pack(side=LEFT, padx=(0, 12))

        self.sm_status = ttk.Label(
            row2, text="Stopped", font=("Segoe UI", 9), bootstyle="secondary"
        )
        self.sm_status.pack(side=LEFT)

    def _sm_start(self):
        hps_resource = self.detected["high_power_supply"][0]
        wg_resource = self.detected["waveform_generator"][0]
        try:
            self.sm_inst_hps = self.rm.open_resource(hps_resource)
            self.sm_inst_hps.timeout = 3000
            self.sm_inst_hps.write_termination = '\n'
            self.sm_inst_hps.read_termination = '\n'
        except Exception as e:
            Messagebox.show_error(
                f"Failed to connect to High Power Supply:\n{e}",
                title="System Manager", parent=self.window
            )
            return
        try:
            self.sm_inst_wg = self.rm.open_resource(wg_resource)
            self.sm_inst_wg.timeout = 3000
        except Exception as e:
            try:
                self.sm_inst_hps.close()
            except Exception:
                pass
            self.sm_inst_hps = None
            Messagebox.show_error(
                f"Failed to connect to Waveform Generator:\n{e}",
                title="System Manager", parent=self.window
            )
            return

        self.sm_active = True
        self.sm_condition_start = None
        self.sm_start_btn.config(state=DISABLED)
        self.sm_stop_btn.config(state=NORMAL)
        self.sm_status.config(text="Monitoring...", bootstyle="success")
        threading.Thread(target=self._sm_poll_loop, daemon=True).start()

    def _sm_stop(self):
        self.sm_active = False
        self.sm_condition_start = None
        for attr in ("sm_inst_hps", "sm_inst_wg"):
            inst = getattr(self, attr, None)
            if inst:
                try:
                    inst.close()
                except Exception:
                    pass
                setattr(self, attr, None)
        if hasattr(self, "sm_start_btn"):
            self.sm_start_btn.config(state=NORMAL)
            self.sm_stop_btn.config(state=DISABLED)
            self.sm_status.config(text="Stopped", bootstyle="secondary")

    def _sm_poll_loop(self):
        import time
        while self.sm_active:
            try:
                poll_s = max(1.0, float(self.sm_poll_var.get()))
            except (ValueError, TypeError):
                poll_s = 30.0
            try:
                current_threshold = float(self.sm_current_var.get())
            except (ValueError, TypeError):
                current_threshold = 2.0
            try:
                time_threshold_min = float(self.sm_time_var.get())
            except (ValueError, TypeError):
                time_threshold_min = 10.0

            hps_exceeded = False
            wg_on = False
            try:
                hps_out = self.sm_inst_hps.query("OUTP?").strip()
                hps_curr = float(self.sm_inst_hps.query("MEAS:CURR?").strip())
                hps_exceeded = (hps_out == "1" and hps_curr > current_threshold)
            except Exception:
                pass
            try:
                wg_out = self.sm_inst_wg.query("OUTP?").strip()
                wg_on = (wg_out == "1")
            except Exception:
                pass

            if hps_exceeded and wg_on:
                if self.sm_condition_start is None:
                    self.sm_condition_start = time.time()
                elapsed_min = (time.time() - self.sm_condition_start) / 60.0
                self.window.after(
                    0, self._sm_update_status,
                    f"Conditions met: {elapsed_min:.1f} / {time_threshold_min:.0f} min",
                    "warning"
                )
                if elapsed_min >= time_threshold_min:
                    self.window.after(0, self._sm_shutdown)
                    return
            else:
                self.sm_condition_start = None
                self.window.after(0, self._sm_update_status, "Monitoring...", "success")

            time.sleep(poll_s)

    def _sm_update_status(self, text, style="secondary"):
        if hasattr(self, "sm_status"):
            self.sm_status.config(text=text, bootstyle=style)

    def _sm_shutdown(self):
        try:
            self.sm_inst_wg.write("OUTP OFF")
        except Exception:
            pass
        try:
            self.sm_inst_hps.write("OUTP OFF")
        except Exception:
            pass
        self._sm_stop()
        Messagebox.show_warning(
            "System Manager has shut down the following instruments:\n\n"
            "  - High Power Supply (N8734A): Output OFF\n"
            "  - Waveform Generator (33500B): Output OFF\n\n"
            "Reason: HPS current exceeded threshold while waveform generator\n"
            "was active for longer than the configured time limit.",
            title="System Manager -- Auto Shutdown",
            parent=self.window
        )

    def _on_close(self):
        self._sm_stop()
        self.window.destroy()

    def _populate_results(self):
        DISPLAY_NAMES = {
            "high_power_supply": "High Power Supply",
            "power_supply": "Bias Power Supply",
            "waveform_generator": "Waveform Generator",
            "oscilloscope": "Oscilloscope",
            "electronic_load": "Electronic Load",
            "data_acquisition": "Data Acquisition",
        }

        DISPLAY_ORDER = [
            "high_power_supply", "power_supply", "waveform_generator",
            "oscilloscope", "electronic_load", "data_acquisition",
        ]

        ordered_items = []
        for key in DISPLAY_ORDER:
            if key in self.config:
                ordered_items.append((key, self.config[key]))
        for key, val in self.config.items():
            if key not in DISPLAY_ORDER:
                ordered_items.append((key, val))

        for tab_name, keyword in ordered_items:
            row = ttk.Frame(self.inner_frame, padding=(0, 4))
            row.pack(fill=X, padx=4)

            display_name = DISPLAY_NAMES.get(tab_name, tab_name.replace("_", " ").title())

            if tab_name in self.detected:
                resource, idn = self.detected[tab_name]
                badge = ttk.Label(row, text=" PASS ", font=("Segoe UI", 9, "bold"), bootstyle="inverse-success")
                badge.pack(side=LEFT, padx=(0, 8))
                ttk.Label(row, text=display_name, font=("Segoe UI", 10, "bold")).pack(side=LEFT)
                if self.on_open_device:
                    open_btn = ttk.Button(
                        row, text="Open", bootstyle="info-outline",
                        command=lambda tn=tab_name: self._open_device(tn)
                    )
                    open_btn.pack(side=RIGHT, padx=(8, 0))
                detail_frame = ttk.Frame(self.inner_frame, padding=(44, 0, 0, 4))
                detail_frame.pack(fill=X, padx=4)
                ttk.Label(detail_frame, text=resource, font=("Segoe UI", 9), bootstyle="secondary").pack(anchor=W)
                idn_short = idn if len(idn) < 70 else idn[:67] + "..."
                ttk.Label(detail_frame, text=idn_short, font=("Segoe UI", 8), bootstyle="secondary").pack(anchor=W)
            else:
                badge = ttk.Label(row, text=" FAIL ", font=("Segoe UI", 9, "bold"), bootstyle="inverse-danger")
                badge.pack(side=LEFT, padx=(0, 8))
                ttk.Label(row, text=display_name, font=("Segoe UI", 10, "bold")).pack(side=LEFT)
                ttk.Label(row, text=f"  ({keyword} not found)", font=("Segoe UI", 9), bootstyle="danger").pack(side=LEFT)
                if self.on_open_device:
                    open_btn = ttk.Button(
                        row, text="Open", bootstyle="warning-outline",
                        command=lambda tn=tab_name: self._open_device(tn)
                    )
                    open_btn.pack(side=RIGHT, padx=(8, 0))

            ttk.Separator(self.inner_frame, bootstyle="secondary").pack(fill=X, padx=4, pady=2)

    def _rescan(self):
        if self.on_rescan:
            new_detected = self.on_rescan()
            if new_detected is not None:
                self.detected = new_detected
                for widget in self.inner_frame.winfo_children():
                    widget.destroy()
                self._populate_results()

    def _open_device(self, tab_name):
        if self.on_open_device:
            self.on_open_device(tab_name)

    def _open_config(self):
        config_path = _device_config_path()
        if os.path.exists(config_path):
            os.startfile(config_path)

    def wait(self):
        self.window.wait_window()

    def _center_window(self, win, w, h):
        x = (win.winfo_screenwidth() - w) // 2
        y = (win.winfo_screenheight() - h) // 2
        win.geometry(f"{w}x{h}+{x}+{y}")


class PowerSupplyWindow:
    """Standalone control window for Keysight E36311A (2-channel)."""

    def __init__(self, parent, rm, resource, idn):
        self.rm = rm
        self.resource = resource
        self.idn = idn
        self.inst = None
        self.auto_readback_active = False
        self.after_id = None

        self.window = ttk.Toplevel(parent)
        self.window.title("Bias Power Supply -- E36311A")
        self.window.geometry("520x580")
        self.window.resizable(True, True)

        self.window.protocol("WM_DELETE_WINDOW", self._on_close)

        header = ttk.Frame(self.window, padding=(16, 12))
        header.pack(fill=X)
        ttk.Label(header, text="Bias Power Supply -- E36311A", font=("Segoe UI", 13, "bold")).pack(side=LEFT)
        ttk.Label(header, text=resource, font=("Segoe UI", 9), bootstyle="secondary").pack(side=RIGHT)

        ttk.Separator(self.window).pack(fill=X)

        scroll_container = ttk.Frame(self.window)
        scroll_container.pack(fill=BOTH, expand=True)
        canvas = ttk.Canvas(scroll_container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(scroll_container, orient=VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=RIGHT, fill=Y)
        canvas.pack(side=LEFT, fill=BOTH, expand=True)
        body = ttk.Frame(canvas, padding=16)
        body_id = canvas.create_window((0, 0), window=body, anchor=NW)
        body.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(body_id, width=e.width))
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", lambda ev: canvas.yview_scroll(-ev.delta // 120, "units")))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        # Connection
        conn_frame = ttk.Frame(body)
        conn_frame.pack(fill=X, pady=(0, 10))
        self.connect_btn = ttk.Button(conn_frame, text="Connect", bootstyle="success", command=self._connect)
        self.connect_btn.pack(side=LEFT, padx=(0, 8))
        self.disconnect_btn = ttk.Button(conn_frame, text="Disconnect", bootstyle="danger", command=self._disconnect, state=DISABLED)
        self.disconnect_btn.pack(side=LEFT)
        self.conn_status = ttk.Label(conn_frame, text="Disconnected", font=("Segoe UI", 9), bootstyle="danger")
        self.conn_status.pack(side=LEFT, padx=(12, 0))

        self.ch1_voltage_var = ttk.StringVar()
        self.ch1_current_var = ttk.StringVar()
        self.ch1_frame = self._create_channel_frame(body, "Channel 1 -- 0 to 6 V, 0 to 5 A", "1", self.ch1_voltage_var, self.ch1_current_var)
        self.ch1_frame.pack(fill=X, pady=(0, 12))

        sw_prot_row = ttk.Frame(self.ch1_frame)
        sw_prot_row.pack(fill=X, pady=(6, 0))
        ttk.Label(sw_prot_row, text="SW Protect (V):").pack(side=LEFT, padx=(0, 4))
        self.ch1_sw_protect_var = ttk.StringVar(value="3.5")
        ttk.Entry(sw_prot_row, textvariable=self.ch1_sw_protect_var, width=8).pack(side=LEFT)

        self.ch2_voltage_var = ttk.StringVar()
        self.ch2_current_var = ttk.StringVar()
        self.ch2_frame = self._create_channel_frame(body, "Channel 2 -- 0 to +25 V, 0 to 1 A", "2", self.ch2_voltage_var, self.ch2_current_var)
        self.ch2_frame.pack(fill=X, pady=(0, 12))

        sw_prot_row2 = ttk.Frame(self.ch2_frame)
        sw_prot_row2.pack(fill=X, pady=(6, 0))
        ttk.Label(sw_prot_row2, text="SW Protect (V):").pack(side=LEFT, padx=(0, 4))
        self.ch2_sw_protect_var = ttk.StringVar(value="13.0")
        ttk.Entry(sw_prot_row2, textvariable=self.ch2_sw_protect_var, width=8).pack(side=LEFT)

        readback_frame = ttk.Labelframe(body, text="Auto Readback", padding=10)
        readback_frame.pack(fill=X)

        ctrl_row = ttk.Frame(readback_frame)
        ctrl_row.pack(fill=X)

        self.auto_var = ttk.BooleanVar(value=False)
        ttk.Checkbutton(
            ctrl_row, text="Enable", variable=self.auto_var,
            bootstyle="round-toggle", command=self._toggle_auto_readback
        ).pack(side=LEFT)

        ttk.Label(ctrl_row, text="Interval (ms):").pack(side=LEFT, padx=(16, 4))
        self.interval_var = ttk.StringVar(value="1000")
        ttk.Entry(ctrl_row, textvariable=self.interval_var, width=6).pack(side=LEFT)

        ttk.Button(
            ctrl_row, text="Read Now", bootstyle="info-outline",
            command=self._update_readback
        ).pack(side=RIGHT)

        self.readback_frame = ttk.Frame(readback_frame, padding=(0, 8, 0, 0))
        self.readback_frame.pack(fill=X)

        self.ch1_v_label = ttk.Label(self.readback_frame, text="Ch1 V: ---", font=("Consolas", 10))
        self.ch1_v_label.grid(row=0, column=0, sticky=W, padx=(0, 24))
        self.ch1_i_label = ttk.Label(self.readback_frame, text="Ch1 I: ---", font=("Consolas", 10))
        self.ch1_i_label.grid(row=0, column=1, sticky=W)

        self.ch2_v_label = ttk.Label(self.readback_frame, text="Ch2 V: ---", font=("Consolas", 10))
        self.ch2_v_label.grid(row=1, column=0, sticky=W, padx=(0, 24), pady=(4, 0))
        self.ch2_i_label = ttk.Label(self.readback_frame, text="Ch2 I: ---", font=("Consolas", 10))
        self.ch2_i_label.grid(row=1, column=1, sticky=W, pady=(4, 0))

    def _create_channel_frame(self, parent, title, channel, voltage_var, current_var):
        frame = ttk.Labelframe(parent, text=title, padding=10)

        row1 = ttk.Frame(frame)
        row1.pack(fill=X, pady=(0, 6))

        ttk.Label(row1, text="Voltage (V):").pack(side=LEFT)
        ttk.Entry(row1, textvariable=voltage_var, width=8).pack(side=LEFT, padx=(4, 8))
        ttk.Button(
            row1, text="Set", bootstyle="primary", width=5,
            command=lambda: self._set_voltage(channel, voltage_var.get())
        ).pack(side=LEFT)

        ttk.Label(row1, text="Current (A):").pack(side=LEFT, padx=(16, 0))
        ttk.Entry(row1, textvariable=current_var, width=8).pack(side=LEFT, padx=(4, 8))
        ttk.Button(
            row1, text="Set", bootstyle="primary", width=5,
            command=lambda: self._set_current(channel, current_var.get())
        ).pack(side=LEFT)

        row2 = ttk.Frame(frame)
        row2.pack(fill=X)

        ttk.Button(
            row2, text="Output ON", bootstyle="success", width=10,
            command=lambda: self._output_on(channel)
        ).pack(side=LEFT, padx=(0, 8))
        ttk.Button(
            row2, text="Output OFF", bootstyle="danger", width=10,
            command=lambda: self._output_off(channel)
        ).pack(side=LEFT)
        ttk.Button(
            row2, text="Read Settings", bootstyle="info-outline", width=12,
            command=lambda: self._read_settings(channel)
        ).pack(side=LEFT, padx=(16, 0))

        return frame

    def _connect(self):
        try:
            self.inst = self.rm.open_resource(self.resource)
            self.inst.timeout = 3000
            self.inst.query("*IDN?")
            self.connect_btn.config(state=DISABLED)
            self.disconnect_btn.config(state=NORMAL)
            self.conn_status.config(text="Connected", bootstyle="success")
            self._read_settings("1")
            self._read_settings("2")
            self._update_readback()
        except Exception as e:
            Messagebox.show_error(f"Failed to connect:\n{e}", title="E36311A", parent=self.window)
            self.inst = None

    def _disconnect(self):
        self.auto_readback_active = False
        if self.after_id:
            self.window.after_cancel(self.after_id)
            self.after_id = None
        if self.inst:
            try:
                self.inst.close()
            except Exception:
                pass
            self.inst = None
        self.connect_btn.config(state=NORMAL)
        self.disconnect_btn.config(state=DISABLED)
        self.conn_status.config(text="Disconnected", bootstyle="danger")

    def _scpi_write(self, cmd):
        if not self.inst:
            Messagebox.show_error("Not connected.", title="E36311A", parent=self.window)
            return
        self.inst.write(cmd)

    def _scpi_query(self, cmd):
        if not self.inst:
            Messagebox.show_error("Not connected.", title="E36311A", parent=self.window)
            return ""
        return self.inst.query(cmd).strip()

    def _set_voltage(self, channel, value):
        try:
            v = float(value)
        except ValueError:
            Messagebox.show_error("Invalid voltage value.", title="Error", parent=self.window)
            return
        if channel == "1":
            try:
                limit = float(self.ch1_sw_protect_var.get())
            except ValueError:
                limit = None
            if limit is not None and v > limit:
                Messagebox.show_warning(
                    f"Voltage {v:.3f} V exceeds SW Protect limit ({limit:.3f} V).\n"
                    f"Command not sent.",
                    title="SW Protect - Ch1", parent=self.window
                )
                return
        elif channel == "2":
            try:
                limit = float(self.ch2_sw_protect_var.get())
            except ValueError:
                limit = None
            if limit is not None and v > limit:
                Messagebox.show_warning(
                    f"Voltage {v:.3f} V exceeds SW Protect limit ({limit:.3f} V).\n"
                    f"Command not sent.",
                    title="SW Protect - Ch2", parent=self.window
                )
                return
        self._scpi_write(f"SOUR:VOLT:LEV {v}, (@{channel})")
        self._update_readback()

    def _set_current(self, channel, value):
        try:
            i = float(value)
        except ValueError:
            Messagebox.show_error("Invalid current value.", title="Error", parent=self.window)
            return
        self._scpi_write(f"SOUR:CURR:LEV {i}, (@{channel})")
        self._update_readback()

    def _read_settings(self, channel):
        if not self.inst:
            Messagebox.show_error("Not connected.", title="E36311A", parent=self.window)
            return
        try:
            v = self._scpi_query(f"SOUR:VOLT:LEV? (@{channel})")
            i = self._scpi_query(f"SOUR:CURR:LEV? (@{channel})")
            if channel == "1":
                self.ch1_voltage_var.set(f"{float(v):.4f}")
                self.ch1_current_var.set(f"{float(i):.4f}")
            elif channel == "2":
                self.ch2_voltage_var.set(f"{float(v):.4f}")
                self.ch2_current_var.set(f"{float(i):.4f}")
        except Exception as e:
            Messagebox.show_error(f"Failed to read settings:\n{e}", title="E36311A", parent=self.window)

    def _output_on(self, channel):
        self._scpi_write(f"OUTP ON, (@{channel})")
        self._update_readback()

    def _output_off(self, channel):
        self._scpi_write(f"OUTP OFF, (@{channel})")
        self._update_readback()

    def _update_readback(self):
        try:
            v1 = float(self._scpi_query("MEAS:VOLT? (@1)"))
            i1 = float(self._scpi_query("MEAS:CURR? (@1)"))
            v2 = float(self._scpi_query("MEAS:VOLT? (@2)"))
            i2 = float(self._scpi_query("MEAS:CURR? (@2)"))
            self.ch1_v_label.config(text=f"Ch1 V: {v1:.4f} V")
            self.ch1_i_label.config(text=f"Ch1 I: {i1:.4f} A")
            self.ch2_v_label.config(text=f"Ch2 V: {v2:.4f} V")
            self.ch2_i_label.config(text=f"Ch2 I: {i2:.4f} A")
        except Exception:
            self.ch1_v_label.config(text="Ch1 V: N/A")
            self.ch1_i_label.config(text="Ch1 I: N/A")
            self.ch2_v_label.config(text="Ch2 V: N/A")
            self.ch2_i_label.config(text="Ch2 I: N/A")

    def _toggle_auto_readback(self):
        if self.auto_var.get():
            try:
                interval = int(self.interval_var.get())
                if interval < 100:
                    interval = 100
            except ValueError:
                interval = 1000
            self.auto_readback_active = True
            self._auto_readback_loop(interval)
        else:
            self.auto_readback_active = False

    def _auto_readback_loop(self, interval):
        if not self.auto_readback_active:
            return
        self._update_readback()
        self.after_id = self.window.after(interval, lambda: self._auto_readback_loop(interval))

    def _on_close(self):
        self.auto_readback_active = False
        if self.after_id:
            self.window.after_cancel(self.after_id)
        if self.inst:
            try:
                self.inst.close()
            except Exception:
                pass
        self.window.destroy()


class HighPowerSupplyWindow:
    """Standalone control window for Keysight N8734A (persistent connection)."""

    FAULT_BITS = [
        ("OV", 1), ("OC", 2), ("PF", 4),
        ("OT", 16), ("INH", 512), ("UNR", 1024),
    ]

    def __init__(self, parent, rm, resource, idn):
        self.rm = rm
        self.resource = resource
        self.idn = idn
        self.inst = None
        self.auto_read_active = False
        self.after_id = None
        self.monitor_history = {"time": [], "voltage": [], "current": []}
        self.monitor_start_time = None
        self.monitor_window = None

        self.window = ttk.Toplevel(parent)
        self.window.title("High Power Supply -- N8734A")
        self.window.geometry("600x700")
        self.window.resizable(True, True)
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)

        header = ttk.Frame(self.window, padding=(16, 12))
        header.pack(fill=X)
        ttk.Label(header, text="Keysight N8734A", font=("Segoe UI", 13, "bold")).pack(side=LEFT)
        ttk.Label(header, text=resource, font=("Segoe UI", 9), bootstyle="secondary").pack(side=RIGHT)

        ttk.Separator(self.window).pack(fill=X)

        scroll_container = ttk.Frame(self.window)
        scroll_container.pack(fill=BOTH, expand=True)
        canvas = ttk.Canvas(scroll_container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(scroll_container, orient=VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=RIGHT, fill=Y)
        canvas.pack(side=LEFT, fill=BOTH, expand=True)
        body = ttk.Frame(canvas, padding=16)
        body_id = canvas.create_window((0, 0), window=body, anchor=NW)
        body.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(body_id, width=e.width))
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", lambda ev: canvas.yview_scroll(-ev.delta // 120, "units")))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        # Connection
        conn_frame = ttk.Frame(body)
        conn_frame.pack(fill=X, pady=(0, 10))
        self.connect_btn = ttk.Button(conn_frame, text="Connect", bootstyle="success", command=self._connect)
        self.connect_btn.pack(side=LEFT, padx=(0, 8))
        self.disconnect_btn = ttk.Button(conn_frame, text="Disconnect", bootstyle="danger", command=self._disconnect, state=DISABLED)
        self.disconnect_btn.pack(side=LEFT)
        self.conn_status = ttk.Label(conn_frame, text="Disconnected", font=("Segoe UI", 9), bootstyle="danger")
        self.conn_status.pack(side=LEFT, padx=(12, 0))

        # Control
        ctrl_frame = ttk.Labelframe(body, text="Control", padding=10)
        ctrl_frame.pack(fill=X, pady=(0, 10))

        self.volt_var = ttk.StringVar(value="0.000")
        self.curr_var = ttk.StringVar(value="0.000")
        self.ovp_var = ttk.StringVar(value="0.000")
        self.uvl_var = ttk.StringVar(value="0.000")

        settings = [
            ("Voltage (V):", self.volt_var, "Set V", self._set_voltage, "VOLT?"),
            ("Current (A):", self.curr_var, "Set I", self._set_current, "CURR?"),
            ("OVP (V):", self.ovp_var, "Set OVP", self._set_ovp, "VOLT:PROT:LEV?"),
            ("UVL (V):", self.uvl_var, "Set UVL", self._set_uvl, "VOLT:LIM:LOW?"),
        ]
        for row, (label, var, btn_text, cmd, query) in enumerate(settings):
            ttk.Label(ctrl_frame, text=label).grid(row=row, column=0, sticky=E, padx=(0, 8), pady=4)
            ttk.Entry(ctrl_frame, textvariable=var, width=10).grid(row=row, column=1, padx=(0, 8), pady=4)
            ttk.Button(ctrl_frame, text=btn_text, bootstyle="primary", width=8, command=cmd).grid(row=row, column=2, pady=4)

        ttk.Button(ctrl_frame, text="Read All", bootstyle="info-outline",
                   command=self._read_initial_values).grid(row=len(settings), column=3, padx=(4, 0), pady=4, sticky=W)

        sw_row = len(settings)
        ttk.Label(ctrl_frame, text="SW Protect (V):").grid(row=sw_row, column=0, sticky=E, padx=(0, 8), pady=4)
        self.sw_protect_var = ttk.StringVar(value="14.0")
        ttk.Entry(ctrl_frame, textvariable=self.sw_protect_var, width=10).grid(row=sw_row, column=1, padx=(0, 8), pady=4)

        # Output + Status LEDs
        out_frame = ttk.Labelframe(body, text="Output", padding=10)
        out_frame.pack(fill=X, pady=(0, 10))

        btn_row = ttk.Frame(out_frame)
        btn_row.pack(fill=X, pady=(0, 8))
        ttk.Button(btn_row, text="ON", bootstyle="success", width=6, command=self._output_on).pack(side=LEFT, padx=(0, 6))
        ttk.Button(btn_row, text="OFF", bootstyle="danger", width=6, command=self._output_off).pack(side=LEFT, padx=(0, 12))
        ttk.Button(btn_row, text="Check Limits", bootstyle="info-outline", command=self._check_limits).pack(side=LEFT, padx=(0, 12))
        ttk.Button(btn_row, text="Clear + OFF", bootstyle="warning", command=self._clear_protection).pack(side=LEFT)

        led_row = ttk.Frame(out_frame)
        led_row.pack(fill=X, pady=(0, 6))

        self.led_canvases = {}
        for name in ["OUT", "CV", "CC"]:
            f = ttk.Frame(led_row)
            f.pack(side=LEFT, padx=(0, 16))
            led_lbl = ttk.Label(f, text="●", font=("Segoe UI", 12), foreground="gray")
            led_lbl.pack(side=LEFT, padx=(0, 2))
            ttk.Label(f, text=name, font=("Consolas", 9)).pack(side=LEFT)
            self.led_canvases[name] = led_lbl

        # Readback
        read_frame = ttk.Labelframe(body, text="Readback", padding=10)
        read_frame.pack(fill=X, pady=(0, 10))

        # Fault LEDs
        fault_frame = ttk.Labelframe(body, text="Faults", padding=10)
        fault_frame.pack(fill=X, pady=(0, 10))

        self.fault_leds = {}
        fault_inner = ttk.Frame(fault_frame)
        fault_inner.pack(fill=X)
        for name, _ in self.FAULT_BITS:
            f = ttk.Frame(fault_inner)
            f.pack(side=LEFT, padx=(0, 16))
            led_lbl = ttk.Label(f, text="●", font=("Segoe UI", 12), foreground="gray")
            led_lbl.pack()
            ttk.Label(f, text=name, font=("Consolas", 9)).pack()
            self.fault_leds[name] = led_lbl

        # OCP control
        ocp_row = ttk.Frame(fault_frame)
        ocp_row.pack(fill=X, pady=(8, 0))
        ttk.Button(ocp_row, text="OCP ON", bootstyle="outline-success", width=8, command=self._ocp_on).pack(side=LEFT, padx=(0, 6))
        ttk.Button(ocp_row, text="OCP OFF", bootstyle="outline-danger", width=8, command=self._ocp_off).pack(side=LEFT, padx=(0, 12))
        ocp_led_lbl = ttk.Label(ocp_row, text="●", font=("Segoe UI", 12), foreground="gray")
        ocp_led_lbl.pack(side=LEFT, padx=(0, 2))
        ttk.Label(ocp_row, text="OCP", font=("Consolas", 9)).pack(side=LEFT)
        self.led_canvases["OCP"] = ocp_led_lbl

        ctrl_row = ttk.Frame(read_frame)
        ctrl_row.pack(fill=X, pady=(0, 8))

        self.auto_read_var = ttk.BooleanVar(value=True)
        ttk.Checkbutton(
            ctrl_row, text="Auto Read", variable=self.auto_read_var,
            bootstyle="round-toggle", command=self._toggle_auto_read
        ).pack(side=LEFT)
        self.auto_read_interval_var = ttk.StringVar(value="1")
        ttk.Entry(ctrl_row, textvariable=self.auto_read_interval_var, width=4).pack(side=LEFT, padx=(6, 2))
        ttk.Label(ctrl_row, text="s").pack(side=LEFT)

        ttk.Button(ctrl_row, text="Read Now", bootstyle="info-outline", command=self._update_readback).pack(side=RIGHT)
        ttk.Button(ctrl_row, text="Monitor Graph", bootstyle="primary", command=self._open_monitor_graph).pack(side=RIGHT, padx=(0, 8))

        self.meas_label = ttk.Label(read_frame, text="Meas:  -- V  /  -- A", font=("Consolas", 11))
        self.meas_label.pack(anchor=W)
        self.power_label = ttk.Label(read_frame, text="Power: -- W", font=("Consolas", 11))
        self.power_label.pack(anchor=W, pady=(4, 0))

    def _connect(self):
        try:
            self.inst = self.rm.open_resource(self.resource)
            self.inst.timeout = 5000
            self.inst.write_termination = '\n'
            self.inst.read_termination = '\n'
            self.inst.query("*IDN?")
            self.connect_btn.config(state=DISABLED)
            self.disconnect_btn.config(state=NORMAL)
            self.conn_status.config(text="Connected", bootstyle="success")
            self._read_initial_values()
            if self.auto_read_var.get():
                self.auto_read_active = True
                self._auto_read_loop()
        except Exception as e:
            Messagebox.show_error(f"Failed to connect:\n{e}", title="N8734A", parent=self.window)
            self.inst = None

    def _disconnect(self):
        self.auto_read_active = False
        if self.after_id:
            self.window.after_cancel(self.after_id)
            self.after_id = None
        if self.inst:
            try:
                self.inst.close()
            except Exception:
                pass
            self.inst = None
        self.connect_btn.config(state=NORMAL)
        self.disconnect_btn.config(state=DISABLED)
        self.conn_status.config(text="Disconnected", bootstyle="danger")
        self.meas_label.config(text="Meas:  -- V  /  -- A")
        self.power_label.config(text="Power: -- W")
        self._set_led("OUT", "gray")
        self._set_led("CV", "gray")
        self._set_led("CC", "gray")
        self._set_led("OCP", "gray")
        for name, _ in self.FAULT_BITS:
            self.fault_leds[name].config(foreground="gray")

    def _read_initial_values(self):
        if not self.inst:
            return
        try:
            self.volt_var.set(f"{float(self.inst.query('VOLT?').strip()):.3f}")
            self.curr_var.set(f"{float(self.inst.query('CURR?').strip()):.3f}")
            self.ovp_var.set(f"{float(self.inst.query('VOLT:PROT:LEV?').strip()):.3f}")
            self.uvl_var.set(f"{float(self.inst.query('VOLT:LIM:LOW?').strip()):.3f}")
        except Exception:
            pass


    def _set_led(self, name, color):
        self.led_canvases[name].config(foreground=color)

    def _set_voltage(self):
        if self.inst:
            try:
                v = float(self.volt_var.get())
            except ValueError:
                Messagebox.show_error("Invalid voltage value.", title="N8734A", parent=self.window)
                return
            try:
                limit = float(self.sw_protect_var.get())
            except ValueError:
                limit = None
            if limit is not None and v > limit:
                Messagebox.show_warning(
                    f"Voltage {v:.3f} V exceeds SW Protect limit ({limit:.3f} V).\n"
                    f"Command not sent.",
                    title="SW Protect - N8734A", parent=self.window
                )
                return
            self.inst.write(f"VOLT {v}")

    def _set_current(self):
        if self.inst:
            self.inst.write(f"CURR {self.curr_var.get()}")

    def _set_ovp(self):
        if self.inst:
            self.inst.write(f"VOLT:PROT:LEV {self.ovp_var.get()}")

    def _set_uvl(self):
        if self.inst:
            self.inst.write(f"VOLT:LIM:LOW {self.uvl_var.get()}")

    def _output_on(self):
        if self.inst:
            self.inst.write("OUTP ON")

    def _output_off(self):
        if self.inst:
            self.inst.write("OUTP OFF")

    def _ocp_on(self):
        if self.inst:
            self.inst.write("CURR:PROT:STAT ON")

    def _ocp_off(self):
        if self.inst:
            self.inst.write("CURR:PROT:STAT OFF")

    def _clear_protection(self):
        if self.inst:
            self.inst.write("OUTP:PROT:CLE")
            self.inst.write("OUTP OFF")

    def _check_limits(self):
        if not self.inst:
            Messagebox.show_warning("Not connected.", title="N8734A", parent=self.window)
            return
        try:
            ovp = float(self.inst.query("VOLT:PROT:LEV?").strip())
            vlow = float(self.inst.query("VOLT:LIM:LOW?").strip())
            ocp = self.inst.query("CURR:PROT:STAT?").strip()
            curr_max = float(self.inst.query("CURR? MAX").strip())
            volt_max = float(self.inst.query("VOLT? MAX").strip())
            info = (
                f"OVP:       {ovp:.3f} V\n"
                f"V Low Lim: {vlow:.3f} V\n"
                f"V Max:     {volt_max:.3f} V\n"
                f"I Max:     {curr_max:.3f} A\n"
                f"OCP:       {'ON' if ocp == '1' else 'OFF'}"
            )
            Messagebox.ok(info, title="N8734A Limits", parent=self.window)
        except Exception as e:
            Messagebox.show_error(f"Failed to query limits:\n{e}", title="N8734A", parent=self.window)

    def _toggle_auto_read(self):
        if self.auto_read_var.get():
            self.auto_read_active = True
            self._auto_read_loop()
        else:
            self.auto_read_active = False
            if self.after_id:
                self.window.after_cancel(self.after_id)
                self.after_id = None

    def _auto_read_loop(self):
        if not self.auto_read_active:
            return
        self._update_readback()
        try:
            interval_ms = int(float(self.auto_read_interval_var.get()) * 1000)
        except (ValueError, TypeError):
            interval_ms = 1000
        interval_ms = max(100, interval_ms)
        self.after_id = self.window.after(interval_ms, self._auto_read_loop)

    def _update_readback(self):
        if not self.inst:
            return
        try:
            v = float(self.inst.query("MEAS:VOLT?").strip())
            i = float(self.inst.query("MEAS:CURR?").strip())
            self.meas_label.config(text=f"Meas:  {v:.3f} V  /  {i:.3f} A")
            self.power_label.config(text=f"Power: {v * i:.3f} W")
            import time
            if self.monitor_start_time is None:
                self.monitor_start_time = time.time()
            elapsed = time.time() - self.monitor_start_time
            self.monitor_history["time"].append(elapsed)
            self.monitor_history["voltage"].append(v)
            self.monitor_history["current"].append(i)
            max_pts = 300
            if len(self.monitor_history["time"]) > max_pts:
                self.monitor_history["time"] = self.monitor_history["time"][-max_pts:]
                self.monitor_history["voltage"] = self.monitor_history["voltage"][-max_pts:]
                self.monitor_history["current"] = self.monitor_history["current"][-max_pts:]
            if self.monitor_window and self.monitor_window.is_alive():
                self.monitor_window.update_plot()
        except Exception:
            self.meas_label.config(text="Meas:  -- V  /  -- A")
            self.power_label.config(text="Power: -- W")
        self._update_output_led()
        self._update_cv_cc_leds()
        self._update_ocp_led()
        self._update_fault_leds()

    def _update_output_led(self):
        try:
            out = self.inst.query("OUTP?").strip()
            self._set_led("OUT", "green" if out == "1" else "gray")
        except Exception:
            self._set_led("OUT", "yellow")

    def _update_cv_cc_leds(self):
        try:
            status = int(self.inst.query("STAT:OPER:COND?").strip())
            self._set_led("CV", "green" if status & 256 else "gray")
            self._set_led("CC", "orange" if status & 1024 else "gray")
        except Exception:
            self._set_led("CV", "gray")
            self._set_led("CC", "gray")

    def _update_ocp_led(self):
        try:
            ocp = self.inst.query("CURR:PROT:STAT?").strip()
            self._set_led("OCP", "green" if ocp == "1" else "gray")
        except Exception:
            self._set_led("OCP", "red")

    def _update_fault_leds(self):
        try:
            status = int(self.inst.query("STAT:QUES:COND?").strip())
            for name, mask in self.FAULT_BITS:
                self.fault_leds[name].config(foreground="red" if status & mask else "gray")
        except Exception:
            for name, _ in self.FAULT_BITS:
                self.fault_leds[name].config(foreground="yellow")

    def _open_monitor_graph(self):
        if self.monitor_window and self.monitor_window.is_alive():
            self.monitor_window.window.lift()
            return
        self.monitor_window = MonitorGraphWindow(self.window, self.monitor_history, self.inst)

    def _on_close(self):
        self._disconnect()
        if self.monitor_window and self.monitor_window.is_alive():
            self.monitor_window.window.destroy()
        self.window.destroy()


class MonitorGraphWindow:
    """Real-time voltage/current graph for N8734A."""

    def __init__(self, parent, history, inst=None):
        try:
            import matplotlib
            matplotlib.use("TkAgg")
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        except ImportError:
            Messagebox.show_error(
                "matplotlib is required.\nInstall with: pip install matplotlib",
                title="Missing dependency", parent=parent
            )
            return

        self.history = history
        self.paused = False
        self.hold_max  = None
        self.over_time = 0.0
        self.last_t    = None

        self.window = ttk.Toplevel(parent)
        self.window.title("N8734A Monitor Graph")
        self.window.geometry("800x500")
        self.window.resizable(True, True)

        toolbar = ttk.Frame(self.window, padding=(8, 4))
        toolbar.pack(fill=X)
        ttk.Button(toolbar, text="Clear", bootstyle="warning-outline", command=self._clear).pack(side=LEFT, padx=(0, 8))
        self.pause_btn = ttk.Button(toolbar, text="Pause", bootstyle="secondary-outline", command=self._toggle_pause)
        self.pause_btn.pack(side=LEFT)

        stats_row = ttk.Frame(self.window, padding=(8, 0, 8, 4))
        stats_row.pack(fill=X)
        self.stats_label = ttk.Label(stats_row, text="", font=("Consolas", 9))
        self.stats_label.pack(side=LEFT)

        limit_row = ttk.Frame(self.window, padding=(8, 0, 8, 4))
        limit_row.pack(fill=X)
        ttk.Label(limit_row, text="Limit(A):").pack(side=LEFT, padx=(0, 2))
        self.limit_var = ttk.StringVar(value="2.0")
        ttk.Entry(limit_row, textvariable=self.limit_var, width=6).pack(side=LEFT, padx=(0, 8))
        self.over_label = ttk.Label(limit_row, text="", font=("Consolas", 9))
        self.over_label.pack(side=LEFT, padx=(0, 8))
        ttk.Button(limit_row, text="Reset Max", bootstyle="info-outline", command=self._reset_max).pack(side=LEFT, padx=(0, 8))
        self.ocp_label = ttk.Label(limit_row, text="OCP: --", font=("Consolas", 9))
        self.ocp_label.pack(side=LEFT)
        self._read_limit(inst)

        self.fig = Figure(figsize=(8, 4), dpi=100)
        self.fig.set_facecolor("#2b2b2b")
        self.ax_v = self.fig.add_subplot(211)
        self.ax_i = self.fig.add_subplot(212)

        for ax in (self.ax_v, self.ax_i):
            ax.set_facecolor("#1e1e1e")
            ax.tick_params(colors="white", labelsize=8)
            ax.xaxis.label.set_color("white")
            ax.yaxis.label.set_color("white")
            ax.title.set_color("white")
            for spine in ax.spines.values():
                spine.set_color("#555")

        self.ax_v.set_ylabel("Voltage (V)")
        self.ax_v.set_title("N8734A Monitor", fontsize=10)
        self.ax_i.set_ylabel("Current (A)")
        self.ax_i.set_xlabel("Time (s)")

        self.line_v, = self.ax_v.plot([], [], color="#00d4aa", linewidth=1.2)
        self.line_i, = self.ax_i.plot([], [], color="#ff9f43", linewidth=1.2)

        self.max_line   = self.ax_i.axhline(0, color="#ff9f43", linestyle="--", linewidth=0.8, alpha=0.7, visible=False)
        self.limit_line = self.ax_i.axhline(0, color="#ff4757", linewidth=1.0, visible=False)
        self.max_dot,   = self.ax_i.plot([], [], "o", color="#ff4757", markersize=5)
        self.max_text   = self.ax_i.annotate("", xy=(0, 0), xytext=(6, 6), textcoords="offset points", color="white", fontsize=8)

        self.fig.tight_layout(pad=2.0)

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.window)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self.canvas.draw()
        self.update_plot()

    def is_alive(self):
        try:
            return self.window.winfo_exists()
        except Exception:
            return False

    def _read_limit(self, inst):
        if inst is None:
            return
        try:
            self.limit_var.set(f"{float(inst.query('CURR?').strip()):.3f}")
            ocp_on = inst.query("CURR:PROT:STAT?").strip() == "1"
            self.ocp_label.config(text=f"OCP: {'ON' if ocp_on else 'OFF'}", foreground="#00d4aa" if ocp_on else "gray")
        except Exception:
            self.ocp_label.config(text="OCP: read error", foreground="#ff4757")

    def _limit(self):
        try:
            return float(self.limit_var.get())
        except ValueError:
            return None

    # Hold max and over-limit time keep accumulating while paused and after samples leave the rolling buffer.
    def _track(self, t, i, limit):
        if i:
            self.hold_max = max(i) if self.hold_max is None else max(self.hold_max, max(i))
        if limit is not None:
            for k in range(1, len(t)):
                if (self.last_t is None or t[k] > self.last_t) and i[k] > limit:
                    self.over_time += t[k] - t[k - 1]
        self.last_t = t[-1] if t else None

    def update_plot(self):
        if not self.is_alive():
            return
        t = self.history["time"]
        v = self.history["voltage"]
        i = self.history["current"]
        limit = self._limit()
        self._track(t, i, limit)
        if self.paused:
            return

        self.line_v.set_data(t, v)
        self.line_i.set_data(t, i)

        if t:
            self.ax_v.set_xlim(t[0], t[-1] if t[-1] > t[0] else t[0] + 1)
            self.ax_i.set_xlim(t[0], t[-1] if t[-1] > t[0] else t[0] + 1)
        if v:
            vmin, vmax = min(v), max(v)
            margin = max((vmax - vmin) * 0.1, 0.1)
            self.ax_v.set_ylim(vmin - margin, vmax + margin)
        if i:
            imin, imax = min(i), max(i)
            margin = max((imax - imin) * 0.1, 0.01)
            self.ax_i.set_ylim(imin - margin, imax + margin)

        if i:
            imax = max(i)
            k = i.index(imax)
            self.stats_label.config(
                text=f"Now {i[-1]:.3f} A | Max {imax:.3f} A | Min {min(i):.3f} A | Avg {sum(i) / len(i):.3f} A | Hold {self.hold_max:.3f} A",
                foreground="#ff4757" if limit is not None and self.hold_max > limit else "",
            )
            self.max_line.set_ydata([imax, imax])
            self.max_line.set_visible(True)
            self.max_dot.set_data([t[k]], [imax])
            right_half = t[-1] > t[0] and (t[k] - t[0]) / (t[-1] - t[0]) > 0.5
            self.max_text.xy = (t[k], imax)
            self.max_text.set_horizontalalignment("right" if right_half else "left")
            self.max_text.set_position((-6 if right_half else 6, 6))
            self.max_text.set_text(f"Max {imax:.3f} A @ {t[k]:.1f} s")
        else:
            self.stats_label.config(text="Now -- | Max -- | Min -- | Avg -- | Hold --", foreground="")
            self.max_line.set_visible(False)
            self.max_dot.set_data([], [])
            self.max_text.set_text("")

        if limit is not None:
            self.limit_line.set_ydata([limit, limit])
            self.limit_line.set_visible(True)
            lo, hi = self.ax_i.get_ylim()
            if not lo < limit < hi:
                lo, hi = min(lo, limit), max(hi, limit)
                margin = max((hi - lo) * 0.05, 0.01)
                self.ax_i.set_ylim(lo - margin, hi + margin)
        else:
            self.limit_line.set_visible(False)
        self.over_label.config(text=f"Over: {self.over_time:.1f} s", foreground="#ff4757" if self.over_time else "")

        self.canvas.draw_idle()

    def _reset_max(self):
        self.hold_max  = None
        self.over_time = 0.0
        self.update_plot()

    def _clear(self):
        self.history["time"].clear()
        self.history["voltage"].clear()
        self.history["current"].clear()
        self.line_v.set_data([], [])
        self.line_i.set_data([], [])
        self._reset_max()

    def _toggle_pause(self):
        self.paused = not self.paused
        self.pause_btn.config(text="Resume" if self.paused else "Pause")


WG_EDGE_MIN_NS   = 8.4
WG_EDGE_MAX_NS   = 1000.0
WG_EDGE_PW_RATIO = 0.625


# D0 (PWM_1) at top down to D15 (PWM_16); SMA-height slot positions read back from 16PWM.csv
PWM16_DIGITAL_POS = [3.90, 3.76, 3.64, 3.52, 3.40, 3.26, 3.14, 3.02, 2.90, 2.76, 2.64, 2.52, 2.40, 2.26, 2.14, 2.02]


def arrange_16pwm(inst) -> str:
    inst.write("DISplay:DIGital:HEIght SMA")
    for d, pos in enumerate(PWM16_DIGITAL_POS):
        inst.write(f"SELect:D{d} 1")
        inst.write(f"D{d}:POSition {pos}")
        inst.write(f'D{d}:LABel "PWM_{d + 1}"')
    inst.query("*OPC?")
    bad = [f"D{d}" for d, pos in enumerate(PWM16_DIGITAL_POS) if round(float(inst.query(f"D{d}:POSition?")), 2) != pos]
    return "Arrange 16 PWM: PASS" if not bad else f"Arrange 16 PWM: FAIL ({', '.join(bad)} out of place)"


# MDO34 snaps Dx:POSition to the slot grid of the current digital height and swaps channels
# that land on the same slot, so the height must be applied before any digital position.
def order_scope_settings(settings: list[tuple[str, str]]) -> list[tuple[str, str]]:
    first = [kv for kv in settings if kv[0].upper().startswith("DISPLAY:DIGITAL:")]
    return first + [kv for kv in settings if kv not in first]


def calc_edge_time(high_mv: float, low_mv: float, ratio: float, sr_ka_us: float, pw_us: float | None = None) -> tuple[str, float]:
    if ratio == 0 or sr_ka_us == 0:
        raise ValueError
    di_a = abs(high_mv - low_mv) / ratio
    # 33500B edge time is 10%-90%; 1 kA/us == 1 A/ns
    edge_ns = 0.8 * di_a / sr_ka_us
    text = f"dI {di_a:.3f} A, Rise/Fall {edge_ns:.1f} ns"
    if edge_ns < WG_EDGE_MIN_NS:
        text += f"  [WARN < {WG_EDGE_MIN_NS} ns min]"
    elif edge_ns > WG_EDGE_MAX_NS:
        text += f"  [WARN > {WG_EDGE_MAX_NS:.0f} ns max]"
    if pw_us and edge_ns > WG_EDGE_PW_RATIO * pw_us * 1000:
        text += f"  [WARN > {WG_EDGE_PW_RATIO} x PW]"
    return text, edge_ns


class WaveformGeneratorWindow:
    """Standalone control window for Keysight 33500B series."""

    def __init__(self, parent, rm, resource, idn):
        self.rm = rm
        self.resource = resource
        self.idn = idn
        self.inst = None

        self.window = ttk.Toplevel(parent)
        self.window.title("Waveform Generator -- 33500B")
        self.window.geometry("560x620")
        self.window.resizable(True, True)
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)

        header = ttk.Frame(self.window, padding=(16, 12))
        header.pack(fill=X)
        ttk.Label(header, text="Keysight 33500B", font=("Segoe UI", 13, "bold")).pack(side=LEFT)
        ttk.Label(header, text=resource, font=("Segoe UI", 9), bootstyle="secondary").pack(side=RIGHT)

        ttk.Separator(self.window).pack(fill=X)

        scroll_container = ttk.Frame(self.window)
        scroll_container.pack(fill=BOTH, expand=True)
        canvas = ttk.Canvas(scroll_container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(scroll_container, orient=VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=RIGHT, fill=Y)
        canvas.pack(side=LEFT, fill=BOTH, expand=True)
        body = ttk.Frame(canvas, padding=16)
        body_id = canvas.create_window((0, 0), window=body, anchor=NW)
        body.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(body_id, width=e.width))
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", lambda ev: canvas.yview_scroll(-ev.delta // 120, "units")))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        # Connection
        conn_frame = ttk.Frame(body)
        conn_frame.pack(fill=X, pady=(0, 10))
        self.connect_btn = ttk.Button(conn_frame, text="Connect", bootstyle="success", command=self._connect)
        self.connect_btn.pack(side=LEFT, padx=(0, 8))
        self.disconnect_btn = ttk.Button(conn_frame, text="Disconnect", bootstyle="danger", command=self._disconnect, state=DISABLED)
        self.disconnect_btn.pack(side=LEFT)
        self.conn_status = ttk.Label(conn_frame, text="Disconnected", font=("Segoe UI", 9), bootstyle="danger")
        self.conn_status.pack(side=LEFT, padx=(12, 0))

        # Waveform Type
        type_frame = ttk.Labelframe(body, text="Waveform Type", padding=10)
        type_frame.pack(fill=X, pady=(0, 12))

        ttk.Label(type_frame, text="Type:").pack(side=LEFT, padx=(0, 8))
        self.waveform_type_var = ttk.StringVar(value="PULS")
        type_combo = ttk.Combobox(
            type_frame, textvariable=self.waveform_type_var,
            values=["SIN", "SQU", "PULS", "RAMP", "TRI", "DC", "NOIS", "PRBS"],
            state="readonly", width=10
        )
        type_combo.pack(side=LEFT)
        type_combo.bind("<<ComboboxSelected>>", self._on_type_changed)

        # Parameters
        param_frame = ttk.Labelframe(body, text="Parameters", padding=10)
        param_frame.pack(fill=X, pady=(0, 12))

        self.high_var = ttk.StringVar()
        self.low_var = ttk.StringVar()
        self.freq_var = ttk.StringVar()
        self.pulse_width_var = ttk.StringVar()
        self.duty_cycle_var = ttk.StringVar()
        self.rise_var = ttk.StringVar()
        self.fall_var = ttk.StringVar()

        self.high_readback = ttk.StringVar(value="---")
        self.low_readback = ttk.StringVar(value="---")
        self.freq_readback = ttk.StringVar(value="---")
        self.pw_readback = ttk.StringVar(value="---")
        self.dc_readback = ttk.StringVar(value="---")
        self.rise_readback = ttk.StringVar(value="---")
        self.fall_readback = ttk.StringVar(value="---")

        params = [
            ("Voltage HIGH (mV):", self.high_var, "Send HIGH", self._send_high, self.high_readback),
            ("Voltage LOW (mV):", self.low_var, "Send LOW", self._send_low, self.low_readback),
            ("Frequency (kHz):", self.freq_var, "Send Freq", self._send_frequency, self.freq_readback),
            ("Pulse Width (us):", self.pulse_width_var, "Send PW", self._send_pulse_width, self.pw_readback),
            ("Duty Cycle (%):", self.duty_cycle_var, "Send DC", self._send_duty_cycle, self.dc_readback),
            ("Rise Time (ns):", self.rise_var, "Send Rise", self._send_rise, self.rise_readback),
            ("Fall Time (ns):", self.fall_var, "Send Fall", self._send_fall, self.fall_readback),
        ]

        for row_idx, (label, var, btn_text, cmd, rb_var) in enumerate(params):
            ttk.Label(param_frame, text=label).grid(row=row_idx, column=0, sticky=W, padx=(0, 8), pady=4)
            ttk.Entry(param_frame, textvariable=var, width=12).grid(row=row_idx, column=1, padx=(0, 8), pady=4)
            ttk.Button(param_frame, text=btn_text, bootstyle="primary", width=10, command=cmd).grid(row=row_idx, column=2, padx=(0, 8), pady=4)
            ttk.Label(param_frame, textvariable=rb_var, font=("Consolas", 9), bootstyle="secondary").grid(row=row_idx, column=3, sticky=W, pady=4)

        ttk.Button(param_frame, text="Read All", bootstyle="info-outline", command=self._readback_params).grid(
            row=len(params), column=2, pady=(8, 0), sticky=W)

        # Output Control
        output_frame = ttk.Labelframe(body, text="Output Control", padding=10)
        output_frame.pack(fill=X, pady=(0, 12))

        btn_row = ttk.Frame(output_frame)
        btn_row.pack(fill=X)

        ttk.Button(btn_row, text="ON", bootstyle="success", width=8, command=self._output_on).pack(side=LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="OFF", bootstyle="danger", width=8, command=self._output_off).pack(side=LEFT, padx=(0, 16))

        ttk.Label(btn_row, text="Delay (s):").pack(side=LEFT, padx=(0, 4))
        self.delay_var = ttk.StringVar()
        ttk.Entry(btn_row, textvariable=self.delay_var, width=8).pack(side=LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="Toggle", bootstyle="warning", width=8, command=self._toggle_output).pack(side=LEFT)

        # Load Tool Calculation
        calc_frame = ttk.Labelframe(body, text="Load Tool Calculation", padding=10)
        calc_frame.pack(fill=X, pady=(0, 12))

        row1 = ttk.Frame(calc_frame)
        row1.pack(fill=X, pady=(0, 6))

        ttk.Label(row1, text="Voltage (mV):").pack(side=LEFT)
        self.calc_voltage_var = ttk.StringVar()
        ttk.Entry(row1, textvariable=self.calc_voltage_var, width=10).pack(side=LEFT, padx=(4, 16))

        ttk.Label(row1, text="Max Load (A):").pack(side=LEFT)
        self.max_load_var = ttk.StringVar()
        ttk.Entry(row1, textvariable=self.max_load_var, width=10).pack(side=LEFT, padx=(4, 0))

        row2 = ttk.Frame(calc_frame)
        row2.pack(fill=X, pady=(0, 6))

        ttk.Label(row2, text="Ratio (mV/A):").pack(side=LEFT)
        self.calc_ratio_var = ttk.StringVar(value="2.5")
        ttk.Entry(row2, textvariable=self.calc_ratio_var, width=10).pack(side=LEFT, padx=(4, 0))

        row3 = ttk.Frame(calc_frame)
        row3.pack(fill=X)

        ttk.Button(row3, text="Calc Load Current", bootstyle="info", command=self._calculate_load_current).pack(side=LEFT, padx=(0, 8))
        ttk.Button(row3, text="Calc Voltage HIGH", bootstyle="info-outline", command=self._calculate_voltage_high).pack(side=LEFT)

        row4 = ttk.Frame(calc_frame)
        row4.pack(fill=X, pady=(6, 0))

        ttk.Label(row4, text="Current SR (kA/us):").pack(side=LEFT)
        self.calc_sr_var = ttk.StringVar()
        ttk.Entry(row4, textvariable=self.calc_sr_var, width=10).pack(side=LEFT, padx=(4, 8))
        ttk.Button(row4, text="Calc Rise/Fall", bootstyle="info", command=self._calculate_edge_time).pack(side=LEFT)

        # Result
        result_frame = ttk.Labelframe(body, text="Result", padding=10)
        result_frame.pack(fill=X)

        self.result_var = ttk.StringVar(value="---")
        ttk.Label(result_frame, textvariable=self.result_var, font=("Consolas", 11), bootstyle="success").pack(anchor=W)

    def _connect(self):
        try:
            self.inst = self.rm.open_resource(self.resource)
            self.inst.timeout = 3000
            self.inst.query("*IDN?")
            high = self.inst.query("VOLT:HIGH?").strip()
            low = self.inst.query("VOLT:LOW?").strip()
            self.inst.write(f"VOLT:HIGH {high}")
            self.inst.write(f"VOLT:LOW {low}")
            self.connect_btn.config(state=DISABLED)
            self.disconnect_btn.config(state=NORMAL)
            self.conn_status.config(text="Connected", bootstyle="success")
        except Exception as e:
            Messagebox.show_error(f"Failed to connect:\n{e}", title="33500B", parent=self.window)
            self.inst = None

    def _disconnect(self):
        if self.inst:
            try:
                self.inst.close()
            except Exception:
                pass
            self.inst = None
        self.connect_btn.config(state=NORMAL)
        self.disconnect_btn.config(state=DISABLED)
        self.conn_status.config(text="Disconnected", bootstyle="danger")

    def _scpi_write(self, cmd):
        if not self.inst:
            Messagebox.show_error("Not connected.", title="33500B", parent=self.window)
            return
        self.inst.write(cmd)

    def _on_type_changed(self, event=None):
        selected = self.waveform_type_var.get()
        self._scpi_write(f"FUNC {selected}")

    def _readback_params(self):
        if not self.inst:
            Messagebox.show_error("Not connected.", title="33500B", parent=self.window)
            return
        try:
            high = float(self.inst.query("VOLT:HIGH?").strip())
            self.high_readback.set(f"{high * 1000:.2f} mV")
            low = float(self.inst.query("VOLT:LOW?").strip())
            self.low_readback.set(f"{low * 1000:.2f} mV")
            freq = float(self.inst.query("FREQ?").strip())
            self.freq_readback.set(f"{freq / 1000:.4f} kHz")
            pw = float(self.inst.query("PULS:WIDT?").strip())
            self.pw_readback.set(f"{pw * 1e6:.3f} us")
            wtype = self.waveform_type_var.get()
            dc_cmd = "FUNC:SQU:DCYC?" if wtype == "SQU" else "FUNC:PULS:DCYC?"
            dc = float(self.inst.query(dc_cmd).strip())
            self.dc_readback.set(f"{dc:.2f} %")
            rise = float(self.inst.query("FUNC:PULS:TRAN:LEAD?").strip())
            self.rise_readback.set(f"{rise * 1e9:.1f} ns")
            fall = float(self.inst.query("FUNC:PULS:TRAN:TRA?").strip())
            self.fall_readback.set(f"{fall * 1e9:.1f} ns")
        except Exception as e:
            self.high_readback.set("Error")
            self.low_readback.set("Error")
            self.freq_readback.set("Error")
            self.pw_readback.set("Error")
            self.dc_readback.set("Error")
            self.rise_readback.set("Error")
            self.fall_readback.set("Error")

    def _send_high(self):
        val = self.high_var.get()
        if not val:
            return
        self._scpi_write(f":VOLT:HIGH {val} mV")
        self.calc_voltage_var.set(val)

    def _send_low(self):
        val = self.low_var.get()
        if not val:
            return
        self._scpi_write(f":VOLT:LOW {val} mV")

    def _send_frequency(self):
        val = self.freq_var.get()
        if not val:
            return
        self._scpi_write(f"FREQ {val} E3")

    def _send_pulse_width(self):
        val = self.pulse_width_var.get()
        if not val:
            return
        self._scpi_write(f":PULS:WIDT {val} E-6")

    def _send_duty_cycle(self):
        val = self.duty_cycle_var.get()
        if not val:
            return
        wtype = self.waveform_type_var.get()
        if wtype == "SQU":
            self._scpi_write(f"FUNC:SQU:DCYC {val}")
        else:
            self._scpi_write(f"FUNC:PULS:DCYC {val}")

    def _send_rise(self):
        val = self.rise_var.get()
        if not val:
            return
        self._scpi_write(f"FUNC:PULS:TRAN:LEAD {val} E-9")

    def _send_fall(self):
        val = self.fall_var.get()
        if not val:
            return
        self._scpi_write(f"FUNC:PULS:TRAN:TRA {val} E-9")

    def _output_on(self):
        self._scpi_write("OUTP ON")

    def _output_off(self):
        self._scpi_write("OUTP OFF")

    def _toggle_output(self):
        try:
            delay = float(self.delay_var.get())
        except ValueError:
            Messagebox.show_error("Delay must be numeric.", title="Error", parent=self.window)
            return
        threading.Thread(target=self._toggle_thread, args=(delay,), daemon=True).start()

    def _toggle_thread(self, delay):
        import time
        if not self.inst:
            return
        try:
            self.inst.write("OUTP ON")
            time.sleep(delay)
            self.inst.write("OUTP OFF")
        except Exception:
            pass

    def _calculate_load_current(self):
        try:
            voltage = float(self.calc_voltage_var.get())
            ratio = float(self.calc_ratio_var.get())
            if ratio == 0:
                raise ValueError
            load_current = voltage / ratio
            self.result_var.set(f"Load Current = {load_current:.6f} A")
        except ValueError:
            Messagebox.show_error("Enter valid numeric values (ratio != 0).", title="Error", parent=self.window)

    def _calculate_voltage_high(self):
        try:
            max_load = float(self.max_load_var.get())
            ratio = float(self.calc_ratio_var.get())
            if ratio == 0:
                raise ValueError
            voltage_high = max_load * ratio
            self.high_var.set(str(voltage_high))
            self.result_var.set(f"Voltage HIGH = {voltage_high:.6f} mV")
        except ValueError:
            Messagebox.show_error("Enter valid numeric values (ratio != 0).", title="Error", parent=self.window)

    def _calculate_edge_time(self):
        try:
            pw = self.pulse_width_var.get()
            text, edge_ns = calc_edge_time(
                float(self.high_var.get()), float(self.low_var.get()),
                float(self.calc_ratio_var.get()), float(self.calc_sr_var.get()),
                float(pw) if pw else None,
            )
        except ValueError:
            Messagebox.show_error("Enter valid HIGH, LOW, Ratio and SR (ratio, SR != 0).", title="Error", parent=self.window)
            return
        self.rise_var.set(f"{edge_ns:.1f}")
        self.fall_var.set(f"{edge_ns:.1f}")
        self.result_var.set(text)

    def _on_close(self):
        if self.inst:
            try:
                self.inst.close()
            except Exception:
                pass
        self.window.destroy()


class OscilloscopeWindow:
    """Standalone control window for Tektronix MDO34 oscilloscope."""

    H_SCALES = [1e-9, 2e-9, 4e-9, 8e-9, 10e-9, 20e-9, 40e-9, 80e-9,
                100e-9, 200e-9, 400e-9, 800e-9,
                1e-6, 2e-6, 4e-6, 8e-6, 10e-6, 20e-6, 40e-6, 80e-6,
                100e-6, 200e-6, 400e-6, 800e-6,
                1e-3, 2e-3, 4e-3, 8e-3, 10e-3, 20e-3, 40e-3, 80e-3,
                100e-3, 200e-3, 400e-3, 800e-3, 1.0]

    V_SCALES = [0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0]

    def __init__(self, parent, rm, resource, idn):
        self.rm = rm
        self.resource = resource
        self.idn = idn
        self.inst = None
        self.save_folder = os.getcwd()

        self.window = ttk.Toplevel(parent)
        self.window.title("Oscilloscope -- MDO34")
        self.window.geometry("700x820")
        self.window.resizable(True, True)
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)

        header = ttk.Frame(self.window, padding=(16, 12))
        header.pack(fill=X)
        ttk.Label(header, text="Tektronix MDO34", font=("Segoe UI", 13, "bold")).pack(side=LEFT)
        ttk.Label(header, text=resource, font=("Segoe UI", 9), bootstyle="secondary").pack(side=RIGHT)

        ttk.Separator(self.window).pack(fill=X)

        # Channel label storage
        self.ch_labels = {}
        for i in range(1, 5):
            self.ch_labels[f"CH{i}"] = ttk.StringVar()
        for i in range(16):
            self.ch_labels[f"D{i}"] = ttk.StringVar()
        for i in range(1, 5):
            self.ch_labels[f"REF{i}"] = ttk.StringVar()

        # Notebook (tabs within scope window)
        self.notebook = ttk.Notebook(self.window)
        self.notebook.pack(fill=BOTH, expand=True)

        # --- Controls Tab ---
        controls_tab = ttk.Frame(self.notebook)
        self.notebook.add(controls_tab, text="Controls")

        scroll_container = ttk.Frame(controls_tab)
        scroll_container.pack(fill=BOTH, expand=True)

        canvas = ttk.Canvas(scroll_container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(scroll_container, orient=VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=RIGHT, fill=Y)
        canvas.pack(side=LEFT, fill=BOTH, expand=True)

        body = ttk.Frame(canvas, padding=16)
        body_id = canvas.create_window((0, 0), window=body, anchor=NW)

        def _on_body_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(e):
            canvas.itemconfig(body_id, width=e.width)

        body.bind("<Configure>", _on_body_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", lambda ev: canvas.yview_scroll(-ev.delta // 120, "units")))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        # Connection
        conn_frame = ttk.Frame(body)
        conn_frame.pack(fill=X, pady=(0, 10))
        self.connect_btn = ttk.Button(conn_frame, text="Connect", bootstyle="success", command=self._connect)
        self.connect_btn.pack(side=LEFT, padx=(0, 8))
        self.disconnect_btn = ttk.Button(conn_frame, text="Disconnect", bootstyle="danger", command=self._disconnect, state=DISABLED)
        self.disconnect_btn.pack(side=LEFT)
        self.conn_status = ttk.Label(conn_frame, text="Disconnected", font=("Segoe UI", 9), bootstyle="danger")
        self.conn_status.pack(side=LEFT, padx=(12, 0))

        # Remote Access
        remote_frame = ttk.Labelframe(body, text="Remote Access", padding=10)
        remote_frame.pack(fill=X, pady=(0, 10))

        remote_row = ttk.Frame(remote_frame)
        remote_row.pack(fill=X)

        self.scope_ip_var = ttk.StringVar(value="---")
        ttk.Button(remote_row, text="Get IP", bootstyle="info-outline", command=self._get_ip).pack(side=LEFT, padx=(0, 8))
        ttk.Label(remote_row, textvariable=self.scope_ip_var, font=("Consolas", 10)).pack(side=LEFT, padx=(0, 12))
        ttk.Button(remote_row, text="Open Browser", bootstyle="primary", command=self._open_browser).pack(side=LEFT)

        # Horizontal Scale
        scale_frame = ttk.Labelframe(body, text="Horizontal Scale", padding=10)
        scale_frame.pack(fill=X, pady=(0, 10))

        self.h_scale_var = ttk.StringVar(value="Current Scale: ---")
        ttk.Label(scale_frame, textvariable=self.h_scale_var, font=("Consolas", 10)).pack(anchor=W, pady=(0, 6))

        scale_btns = ttk.Frame(scale_frame)
        scale_btns.pack(fill=X)
        ttk.Button(scale_btns, text="Increase (x2)", bootstyle="primary", command=self._increase_scale).pack(side=LEFT, padx=(0, 8))
        ttk.Button(scale_btns, text="Decrease (/2)", bootstyle="primary", command=self._decrease_scale).pack(side=LEFT, padx=(0, 8))
        ttk.Button(scale_btns, text="Read Scale", bootstyle="info-outline", command=self._read_scale).pack(side=LEFT)

        # Acquisition Control
        acq_frame = ttk.Labelframe(body, text="Acquisition", padding=10)
        acq_frame.pack(fill=X, pady=(0, 10))

        acq_row = ttk.Frame(acq_frame)
        acq_row.pack(fill=X)
        ttk.Button(acq_row, text="RUN", bootstyle="success", width=8, command=self._run).pack(side=LEFT, padx=(0, 6))
        ttk.Button(acq_row, text="STOP", bootstyle="danger", width=8, command=self._stop).pack(side=LEFT, padx=(0, 6))
        ttk.Button(acq_row, text="SINGLE", bootstyle="warning", width=8, command=self._single).pack(side=LEFT, padx=(0, 6))
        ttk.Button(acq_row, text="Sequence", bootstyle="info", width=8, command=self._sequence).pack(side=LEFT)

        # Trigger
        trig_frame = ttk.Labelframe(body, text="Trigger", padding=10)
        trig_frame.pack(fill=X, pady=(0, 10))

        trig_row = ttk.Frame(trig_frame)
        trig_row.pack(fill=X)
        ttk.Button(trig_row, text="Auto", bootstyle="primary", width=8, command=self._trigger_auto).pack(side=LEFT, padx=(0, 6))
        ttk.Button(trig_row, text="Normal", bootstyle="primary", width=8, command=self._trigger_normal).pack(side=LEFT)

        # Edge Auto-Adjust
        rise_frame = ttk.Labelframe(body, text="Edge Auto-Adjust", padding=10)
        rise_frame.pack(fill=X, pady=(0, 10))

        rise_row1 = ttk.Frame(rise_frame)
        rise_row1.pack(fill=X, pady=(0, 6))

        ttk.Label(rise_row1, text="Channel:").pack(side=LEFT, padx=(0, 4))
        self.rise_channel_var = ttk.StringVar(value="CH1")
        self.rise_channel_combo = ttk.Combobox(rise_row1, textvariable=self.rise_channel_var, values=["CH1", "CH2", "CH3", "CH4"], state="readonly", width=18)
        self.rise_channel_combo.pack(side=LEFT, padx=(0, 12))

        ttk.Label(rise_row1, text="Edge:").pack(side=LEFT, padx=(0, 4))
        self.edge_type_var = ttk.StringVar(value="Rising")
        ttk.Combobox(rise_row1, textvariable=self.edge_type_var, values=["Rising", "Falling"], state="readonly", width=8).pack(side=LEFT, padx=(0, 12))

        ttk.Label(rise_row1, text="Fill (%):").pack(side=LEFT, padx=(0, 4))
        self.rise_pct_var = ttk.StringVar(value="60")
        ttk.Entry(rise_row1, textvariable=self.rise_pct_var, width=5).pack(side=LEFT, padx=(0, 12))

        ttk.Button(rise_row1, text="Auto Adjust", bootstyle="success", command=self._auto_adjust_edge).pack(side=LEFT)

        rise_row2 = ttk.Frame(rise_frame)
        rise_row2.pack(fill=X, pady=(0, 6))

        ttk.Label(rise_row2, text="Cursor Low (%):").pack(side=LEFT, padx=(0, 4))
        self.cursor_low_var = ttk.StringVar(value="20")
        ttk.Entry(rise_row2, textvariable=self.cursor_low_var, width=5).pack(side=LEFT, padx=(0, 12))

        ttk.Label(rise_row2, text="Cursor High (%):").pack(side=LEFT, padx=(0, 4))
        self.cursor_high_var = ttk.StringVar(value="80")
        ttk.Entry(rise_row2, textvariable=self.cursor_high_var, width=5).pack(side=LEFT, padx=(0, 12))

        ttk.Button(rise_row2, text="Place Cursors", bootstyle="primary", command=self._place_edge_cursors).pack(side=LEFT)

        self.rise_result_label = ttk.Label(rise_frame, text="", font=("Consolas", 9), bootstyle="secondary", wraplength=540)
        self.rise_result_label.pack(anchor=W)

        # Save Waveform to Reference
        ref_frame = ttk.Labelframe(body, text="Save Waveform to Reference", padding=10)
        ref_frame.pack(fill=X, pady=(0, 10))

        ref_row = ttk.Frame(ref_frame)
        ref_row.pack(fill=X)

        ttk.Label(ref_row, text="Source:").pack(side=LEFT, padx=(0, 4))
        self.channel_var = ttk.StringVar(value="CH1")
        self.ref_source_combo = ttk.Combobox(ref_row, textvariable=self.channel_var, values=["CH1", "CH2", "CH3", "CH4"], state="readonly", width=18)
        self.ref_source_combo.pack(side=LEFT, padx=(0, 12))

        ttk.Label(ref_row, text="Dest:").pack(side=LEFT, padx=(0, 4))
        self.ref_var = ttk.StringVar(value="REF1")
        self.ref_dest_combo = ttk.Combobox(ref_row, textvariable=self.ref_var, values=["REF1", "REF2", "REF3", "REF4"], state="readonly", width=18)
        self.ref_dest_combo.pack(side=LEFT, padx=(0, 12))

        ttk.Button(ref_row, text="Save to Ref", bootstyle="primary", command=self._save_to_ref).pack(side=LEFT)

        # Screenshot
        shot_frame = ttk.Labelframe(body, text="Screenshot", padding=10)
        shot_frame.pack(fill=X, pady=(0, 10))

        folder_row = ttk.Frame(shot_frame)
        folder_row.pack(fill=X, pady=(0, 6))
        self.folder_var = ttk.StringVar(value=self.save_folder)
        ttk.Entry(folder_row, textvariable=self.folder_var, state="readonly").pack(side=LEFT, fill=X, expand=True, padx=(0, 8))
        ttk.Button(folder_row, text="Browse", bootstyle="outline", command=self._select_folder).pack(side=LEFT, padx=(0, 4))
        ttk.Button(folder_row, text="Open", bootstyle="outline", command=self._open_folder).pack(side=LEFT)

        name_row = ttk.Frame(shot_frame)
        name_row.pack(fill=X, pady=(0, 6))
        ttk.Label(name_row, text="Name:").pack(side=LEFT, padx=(0, 4))
        self.waveform_name_var = ttk.StringVar()
        ttk.Entry(name_row, textvariable=self.waveform_name_var, width=30).pack(side=LEFT, padx=(0, 8))
        ttk.Button(name_row, text="Save Screenshot", bootstyle="success", command=self._save_screenshot).pack(side=LEFT)

        self.shot_status = ttk.Label(shot_frame, text="", font=("Segoe UI", 9), bootstyle="secondary")
        self.shot_status.pack(anchor=W)

        # Annotation
        ann_frame = ttk.Labelframe(body, text="Annotation", padding=10)
        ann_frame.pack(fill=X, pady=(0, 10))

        ann_row = ttk.Frame(ann_frame)
        ann_row.pack(fill=X)
        self.annotation_var = ttk.StringVar()
        ttk.Entry(ann_row, textvariable=self.annotation_var, width=40).pack(side=LEFT, padx=(0, 8))
        ttk.Button(ann_row, text="Send", bootstyle="primary", command=self._send_annotation).pack(side=LEFT)

        # Status
        self.status_label = ttk.Label(body, text="", font=("Segoe UI", 9), bootstyle="secondary")
        self.status_label.pack(anchor=W, pady=(8, 0))

        # --- Channel Labels Tab ---
        labels_tab = ttk.Frame(self.notebook)
        self.notebook.add(labels_tab, text="Channel Labels")

        labels_scroll = ttk.Frame(labels_tab)
        labels_scroll.pack(fill=BOTH, expand=True)

        lbl_canvas = ttk.Canvas(labels_scroll, highlightthickness=0)
        lbl_scrollbar = ttk.Scrollbar(labels_scroll, orient=VERTICAL, command=lbl_canvas.yview)
        lbl_canvas.configure(yscrollcommand=lbl_scrollbar.set)

        lbl_scrollbar.pack(side=RIGHT, fill=Y)
        lbl_canvas.pack(side=LEFT, fill=BOTH, expand=True)

        lbl_body = ttk.Frame(lbl_canvas, padding=16)
        lbl_body_id = lbl_canvas.create_window((0, 0), window=lbl_body, anchor=NW)

        lbl_body.bind("<Configure>", lambda e: lbl_canvas.configure(scrollregion=lbl_canvas.bbox("all")))
        lbl_canvas.bind("<Configure>", lambda e: lbl_canvas.itemconfig(lbl_body_id, width=e.width))
        lbl_canvas.bind("<Enter>", lambda e: lbl_canvas.bind_all("<MouseWheel>", lambda ev: lbl_canvas.yview_scroll(-ev.delta // 120, "units")))
        lbl_canvas.bind("<Leave>", lambda e: lbl_canvas.unbind_all("<MouseWheel>"))

        # Analog Channels
        analog_frame = ttk.Labelframe(lbl_body, text="Analog Channels", padding=10)
        analog_frame.pack(fill=X, pady=(0, 10))
        for i in range(1, 5):
            row = ttk.Frame(analog_frame)
            row.pack(fill=X, pady=2)
            ttk.Label(row, text=f"CH{i}:", width=6, font=("Consolas", 10)).pack(side=LEFT, padx=(0, 8))
            ttk.Entry(row, textvariable=self.ch_labels[f"CH{i}"], width=30).pack(side=LEFT, padx=(0, 8))
            ttk.Button(row, text="Apply", bootstyle="success-outline", width=5, command=lambda ch=i: self._apply_single_analog_label(ch)).pack(side=LEFT)
        ttk.Button(analog_frame, text="Read Analog Labels", bootstyle="info-outline", command=self._read_analog_labels).pack(anchor=W, pady=(6, 0))

        # Digital Channels
        digital_frame = ttk.Labelframe(lbl_body, text="Digital Channels", padding=10)
        digital_frame.pack(fill=X, pady=(0, 10))
        dig_grid = ttk.Frame(digital_frame)
        dig_grid.pack(fill=X)
        # Layout: col0 = D15..D8 (top to bottom), col1 = D7..D0 (top to bottom)
        for row in range(8):
            left_ch = 15 - row   # D15, D14, ..., D8
            right_ch = 7 - row   # D7, D6, ..., D0
            sub_l = ttk.Frame(dig_grid)
            sub_l.grid(row=row, column=0, sticky=W, padx=(0, 20), pady=2)
            ttk.Label(sub_l, text=f"D{left_ch:2d}:", width=5, font=("Consolas", 10)).pack(side=LEFT, padx=(0, 8))
            ttk.Entry(sub_l, textvariable=self.ch_labels[f"D{left_ch}"], width=20).pack(side=LEFT)
            sub_r = ttk.Frame(dig_grid)
            sub_r.grid(row=row, column=1, sticky=W, padx=(0, 20), pady=2)
            ttk.Label(sub_r, text=f"D{right_ch}:", width=5, font=("Consolas", 10)).pack(side=LEFT, padx=(0, 8))
            ttk.Entry(sub_r, textvariable=self.ch_labels[f"D{right_ch}"], width=20).pack(side=LEFT)
        dig_btn_row = ttk.Frame(digital_frame)
        dig_btn_row.pack(anchor=W, pady=(6, 0))
        ttk.Button(dig_btn_row, text="Read Digital Labels", bootstyle="info-outline", command=self._read_digital_labels).pack(side=LEFT, padx=(0, 8))
        ttk.Button(dig_btn_row, text="Apply All Digital Labels", bootstyle="success-outline", command=self._apply_digital_labels).pack(side=LEFT, padx=(0, 8))
        ttk.Button(dig_btn_row, text="Arrange 16 PWM", bootstyle="warning-outline", command=self._arrange_16pwm).pack(side=LEFT)

        # Reference Channels
        ref_label_frame = ttk.Labelframe(lbl_body, text="Reference Channels", padding=10)
        ref_label_frame.pack(fill=X, pady=(0, 10))
        for i in range(1, 5):
            row = ttk.Frame(ref_label_frame)
            row.pack(fill=X, pady=2)
            ttk.Label(row, text=f"REF{i}:", width=6, font=("Consolas", 10)).pack(side=LEFT, padx=(0, 8))
            ttk.Entry(row, textvariable=self.ch_labels[f"REF{i}"], width=30).pack(side=LEFT, padx=(0, 8))
            ttk.Button(row, text="Apply", bootstyle="success-outline", width=5, command=lambda ref=i: self._apply_single_ref_label(ref)).pack(side=LEFT)
        ttk.Button(ref_label_frame, text="Read Reference Labels", bootstyle="info-outline", command=self._read_ref_labels).pack(anchor=W, pady=(6, 0))

        # Status on labels tab
        self.lbl_status = ttk.Label(lbl_body, text="", font=("Consolas", 9), bootstyle="secondary", wraplength=600)
        self.lbl_status.pack(anchor=W, pady=(8, 0))

        # --- Setups Tab ---
        setups_tab = ttk.Frame(self.notebook)
        self.notebook.add(setups_tab, text="Setups")

        setups_body = ttk.Frame(setups_tab, padding=16)
        setups_body.pack(fill=BOTH, expand=True)

        self.setup_names = {}
        for slot in range(1, 11):
            self.setup_names[slot] = ttk.StringVar()
        self._load_setup_names()

        setup_grid = ttk.Frame(setups_body)
        setup_grid.pack(fill=X)
        for slot in range(1, 11):
            r = (slot - 1) % 5
            c = 0 if slot <= 5 else 1
            sub = ttk.Frame(setup_grid)
            sub.grid(row=r, column=c, sticky=W, padx=(0, 16), pady=2)
            ttk.Label(sub, text=f"{slot:2d}:", width=3, font=("Consolas", 10)).pack(side=LEFT, padx=(0, 4))
            entry = ttk.Entry(sub, textvariable=self.setup_names[slot], width=14)
            entry.pack(side=LEFT, padx=(0, 4))
            entry.bind("<FocusOut>", lambda e, s=slot: self._save_setup_names())
            ttk.Button(sub, text="Save", bootstyle="success-outline", width=4, command=lambda s=slot: self._save_setup(s)).pack(side=LEFT, padx=(0, 2))
            ttk.Button(sub, text="Recall", bootstyle="info-outline", width=5, command=lambda s=slot: self._recall_setup(s)).pack(side=LEFT)

        # --- PC Setup Save/Load Section ---
        sep = ttk.Separator(setups_body, orient=HORIZONTAL)
        sep.pack(fill=X, pady=(12, 8))

        pc_frame = ttk.Labelframe(setups_body, text="PC Setup Files (CSV)", padding=10)
        pc_frame.pack(fill=X)

        btn_row = ttk.Frame(pc_frame)
        btn_row.pack(fill=X, pady=(0, 6))
        ttk.Button(btn_row, text="Save Settings to PC", bootstyle="success", command=self._save_settings_to_pc).pack(side=LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="Load Settings from PC", bootstyle="info", command=self._load_settings_from_pc).pack(side=LEFT)

        self.setup_status = ttk.Label(setups_body, text="", font=("Consolas", 9), bootstyle="secondary")
        self.setup_status.pack(anchor=W, pady=(10, 0))

    def _load_setup_names(self):
        """Load setup slot names from JSON file."""
        import json
        path = os.path.join(
            os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else __file__),
            'scope_setups.json'
        )
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            for slot in range(1, 11):
                name = data.get(str(slot), "")
                self.setup_names[slot].set(name)
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    def _save_setup_names(self):
        """Persist setup slot names to JSON file."""
        import json
        path = os.path.join(
            os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else __file__),
            'scope_setups.json'
        )
        data = {str(slot): self.setup_names[slot].get() for slot in range(1, 11)}
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)

    def _save_setup(self, slot):
        """Save current scope state to internal slot."""
        if not self.inst:
            Messagebox.show_error("Not connected.", title="MDO34", parent=self.window)
            return
        try:
            self.inst.write(f"*SAV {slot}")
            self._save_setup_names()
            name = self.setup_names[slot].get().strip()
            label = f'"{name}"' if name else f"slot {slot}"
            self.setup_status.config(text=f"Setup saved to {label}")
        except Exception as e:
            self.setup_status.config(text=f"Save error: {e}")

    def _recall_setup(self, slot):
        """Recall scope state from internal slot."""
        if not self.inst:
            Messagebox.show_error("Not connected.", title="MDO34", parent=self.window)
            return
        try:
            self.inst.write(f"*RCL {slot}")
            name = self.setup_names[slot].get().strip()
            label = f'"{name}"' if name else f"slot {slot}"
            self.setup_status.config(text=f"Setup recalled from {label}")
        except Exception as e:
            self.setup_status.config(text=f"Recall error: {e}")

    _PC_SETUP_QUERIES = [
        "HORizontal:SCAle",
        "HORizontal:POSition",
        "HORizontal:RECOrdlength",
        "SELect:CH1", "SELect:CH2", "SELect:CH3", "SELect:CH4",
        "CH1:SCAle", "CH2:SCAle", "CH3:SCAle", "CH4:SCAle",
        "CH1:POSition", "CH2:POSition", "CH3:POSition", "CH4:POSition",
        "CH1:LABel", "CH2:LABel", "CH3:LABel", "CH4:LABel",
        "CH1:COUPling", "CH2:COUPling", "CH3:COUPling", "CH4:COUPling",
        "CH1:BANdwidth", "CH2:BANdwidth", "CH3:BANdwidth", "CH4:BANdwidth",
        "TRIGger:A:EDGE:SOUrce",
        "TRIGger:A:EDGE:SLOpe",
        "TRIGger:A:LEVel",
        "SELect:D0", "SELect:D1", "SELect:D2", "SELect:D3",
        "SELect:D4", "SELect:D5", "SELect:D6", "SELect:D7",
        "SELect:D8", "SELect:D9", "SELect:D10", "SELect:D11",
        "SELect:D12", "SELect:D13", "SELect:D14", "SELect:D15",
        "D0:LABel", "D1:LABel", "D2:LABel", "D3:LABel",
        "D4:LABel", "D5:LABel", "D6:LABel", "D7:LABel",
        "D8:LABel", "D9:LABel", "D10:LABel", "D11:LABel",
        "D12:LABel", "D13:LABel", "D14:LABel", "D15:LABel",
        "D0:POSition", "D1:POSition", "D2:POSition", "D3:POSition",
        "D4:POSition", "D5:POSition", "D6:POSition", "D7:POSition",
        "D8:POSition", "D9:POSition", "D10:POSition", "D11:POSition",
        "D12:POSition", "D13:POSition", "D14:POSition", "D15:POSition",
        "D0:THReshold", "D1:THReshold", "D2:THReshold", "D3:THReshold",
        "D4:THReshold", "D5:THReshold", "D6:THReshold", "D7:THReshold",
        "D8:THReshold", "D9:THReshold", "D10:THReshold", "D11:THReshold",
        "D12:THReshold", "D13:THReshold", "D14:THReshold", "D15:THReshold",
        "DISplay:DIGital:HEIght",
        # Measurements
        "MEASUrement:MEAS1:STATE", "MEASUrement:MEAS1:TYPe", "MEASUrement:MEAS1:SOUrce1",
        "MEASUrement:MEAS2:STATE", "MEASUrement:MEAS2:TYPe", "MEASUrement:MEAS2:SOUrce1",
        "MEASUrement:MEAS3:STATE", "MEASUrement:MEAS3:TYPe", "MEASUrement:MEAS3:SOUrce1",
        "MEASUrement:MEAS4:STATE", "MEASUrement:MEAS4:TYPe", "MEASUrement:MEAS4:SOUrce1",
        "MEASUrement:MEAS5:STATE", "MEASUrement:MEAS5:TYPe", "MEASUrement:MEAS5:SOUrce1",
        "MEASUrement:MEAS6:STATE", "MEASUrement:MEAS6:TYPe", "MEASUrement:MEAS6:SOUrce1",
        "MEASUrement:MEAS7:STATE", "MEASUrement:MEAS7:TYPe", "MEASUrement:MEAS7:SOUrce1",
        "MEASUrement:MEAS8:STATE", "MEASUrement:MEAS8:TYPe", "MEASUrement:MEAS8:SOUrce1",
        "MEASUrement:STATIstics:MODe",
        "MEASUrement:GATing",
        # Reference channels
        "SELect:REF1", "SELect:REF2", "SELect:REF3", "SELect:REF4",
        "REF1:LABel", "REF2:LABel", "REF3:LABel", "REF4:LABel",
        "REF1:VERTical:SCAle", "REF2:VERTical:SCAle", "REF3:VERTical:SCAle", "REF4:VERTical:SCAle",
        "REF1:VERTical:POSition", "REF2:VERTical:POSition", "REF3:VERTical:POSition", "REF4:VERTical:POSition",
        "REF1:HORizontal:SCAle", "REF2:HORizontal:SCAle", "REF3:HORizontal:SCAle", "REF4:HORizontal:SCAle",
    ]

    def _save_settings_to_pc(self):
        """Query scope settings and save to a user-chosen CSV file."""
        import csv
        from tkinter import filedialog

        if not self.inst:
            Messagebox.show_error("Not connected.", title="MDO34", parent=self.window)
            return

        filepath = filedialog.asksaveasfilename(
            parent=self.window,
            title="Save Scope Settings",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile="scope_setup.csv",
        )
        if not filepath:
            return

        self.setup_status.config(text="Reading settings from scope...")
        self.window.update_idletasks()

        def _do_save():
            results = []
            errors = 0
            for cmd in self._PC_SETUP_QUERIES:
                try:
                    value = self.inst.query(f"{cmd}?").strip()
                    results.append((cmd, value))
                except Exception:
                    errors += 1

            with open(filepath, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["command", "value"])
                for cmd, val in results:
                    writer.writerow([cmd, val])

            fname = os.path.basename(filepath)
            msg = f"Saved {len(results)} settings to {fname}"
            if errors:
                msg += f" ({errors} errors skipped)"
            self.window.after(0, lambda: self.setup_status.config(text=msg))

        threading.Thread(target=_do_save, daemon=True).start()

    def _load_settings_from_pc(self):
        """Load settings from a CSV file and apply to scope."""
        import csv
        from tkinter import filedialog

        if not self.inst:
            Messagebox.show_error("Not connected.", title="MDO34", parent=self.window)
            return

        filepath = filedialog.askopenfilename(
            parent=self.window,
            title="Load Scope Settings",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not filepath:
            return

        try:
            with open(filepath, "r") as f:
                reader = csv.DictReader(f)
                settings = order_scope_settings([(row["command"], row["value"]) for row in reader])
        except Exception as e:
            Messagebox.show_error(f"Failed to read file:\n{e}", title="MDO34", parent=self.window)
            return

        self.setup_status.config(text=f"Applying {len(settings)} settings...")
        self.window.update_idletasks()

        def _do_load():
            import time
            ok = 0
            errors = 0
            for cmd, value in settings:
                if "LABel" in cmd:
                    val_clean = value.strip('"')
                    full_cmd = f'{cmd} "{val_clean}"'
                else:
                    full_cmd = f"{cmd} {value}"
                try:
                    self.inst.write(full_cmd)
                    ok += 1
                except Exception:
                    errors += 1
                time.sleep(0.05)

            fname = os.path.basename(filepath)
            msg = f"Applied {ok} settings from {fname}"
            if errors:
                msg += f" ({errors} errors)"
            self.window.after(0, lambda: self.setup_status.config(text=msg))

        threading.Thread(target=_do_load, daemon=True).start()

    def _get_channel_display(self, ch_id):
        """Return display string for a channel: 'CH1 - VOUT' or just 'CH1'."""
        label = self.ch_labels.get(ch_id, None)
        if label and label.get().strip():
            return f"{ch_id} - {label.get().strip()}"
        return ch_id

    def _get_channel_id(self, display_str):
        """Extract raw channel ID from display string (e.g. 'CH1 - VOUT' -> 'CH1')."""
        return display_str.split(" - ")[0].strip()

    def _set_lbl_status(self, text):
        self.lbl_status.config(text=text)

    def _apply_single_analog_label(self, ch_num):
        """Write label to a single analog channel on the scope."""
        if not self.inst:
            Messagebox.show_error("Not connected.", title="MDO34", parent=self.window)
            return
        lbl = self.ch_labels[f"CH{ch_num}"].get().strip()
        try:
            self.inst.write(f'CH{ch_num}:LABel "{lbl}"')
            self._set_lbl_status(f"CH{ch_num} label set to \"{lbl}\"")
        except Exception as e:
            self._set_lbl_status(f"CH{ch_num} label error: {e}")

    def _apply_digital_labels(self):
        """Write all digital channel labels to scope."""
        if not self.inst:
            Messagebox.show_error("Not connected.", title="MDO34", parent=self.window)
            return
        errors = []
        for i in range(16):
            lbl = self.ch_labels[f"D{i}"].get().strip()
            try:
                self.inst.write(f'D{i}:LABel "{lbl}"')
            except Exception:
                errors.append(f"D{i}")
        if errors:
            self._set_lbl_status(f"Digital labels applied (failed: {', '.join(errors)})")
        else:
            self._set_lbl_status("All digital labels applied")

    def _apply_single_ref_label(self, ref_num):
        """Write label to a single reference channel on the scope."""
        if not self.inst:
            Messagebox.show_error("Not connected.", title="MDO34", parent=self.window)
            return
        lbl = self.ch_labels[f"REF{ref_num}"].get().strip()
        try:
            self.inst.write(f'REF{ref_num}:LABel "{lbl}"')
            self._set_lbl_status(f"REF{ref_num} label set to \"{lbl}\"")
        except Exception as e:
            self._set_lbl_status(f"REF{ref_num} label error: {e}")

    def _read_analog_labels(self):
        """Read analog channel labels (CH1-4) from scope."""
        if not self.inst:
            Messagebox.show_error("Not connected.", title="MDO34", parent=self.window)
            return
        errors = []
        for i in range(1, 5):
            try:
                raw = self.inst.query(f"CH{i}:LABel?").strip()
                lbl = raw.strip('"')
                self.ch_labels[f"CH{i}"].set(lbl)
            except Exception as e:
                errors.append(f"CH{i}({e})")
        self._apply_channel_labels()
        if errors:
            self._set_lbl_status(f"Analog read done (failed: {', '.join(errors)})")
        else:
            self._set_lbl_status("Analog labels read OK")

    def _arrange_16pwm(self):
        if not self.inst:
            Messagebox.show_error("Not connected.", title="MDO34", parent=self.window)
            return
        inst = self.inst
        self._set_lbl_status("Arranging D0-D15 as PWM_1-PWM_16...")

        def _do():
            try:
                msg = arrange_16pwm(inst)
            except Exception as e:
                err = f"Arrange 16 PWM error: {e}"
                self.window.after(0, lambda: self._set_lbl_status(err))
                return
            self.window.after(0, lambda: self._arrange_16pwm_done(msg))

        threading.Thread(target=_do, daemon=True).start()

    def _arrange_16pwm_done(self, msg):
        for d in range(16):
            self.ch_labels[f"D{d}"].set(f"PWM_{d + 1}")
        self._apply_channel_labels()
        self._set_lbl_status(msg)

    def _read_digital_labels(self):
        """Read digital channel labels (D0-15) from scope."""
        if not self.inst:
            Messagebox.show_error("Not connected.", title="MDO34", parent=self.window)
            return
        errors = []
        for i in range(16):
            try:
                raw = self.inst.query(f"D{i}:LABel?").strip()
                lbl = raw.strip('"')
                self.ch_labels[f"D{i}"].set(lbl)
            except Exception as e:
                errors.append(f"D{i}({e})")
        self._apply_channel_labels()
        if errors:
            self._set_lbl_status(f"Digital read done (failed: {', '.join(errors)})")
        else:
            self._set_lbl_status("Digital labels read OK")

    def _read_ref_labels(self):
        """Read reference channel labels (REF1-4) from scope."""
        if not self.inst:
            Messagebox.show_error("Not connected.", title="MDO34", parent=self.window)
            return
        errors = []
        for i in range(1, 5):
            try:
                raw = self.inst.query(f"REF{i}:LABel?").strip()
                lbl = raw.strip('"')
                self.ch_labels[f"REF{i}"].set(lbl)
            except Exception as e:
                errors.append(f"REF{i}({e})")
        self._apply_channel_labels()
        if errors:
            self._set_lbl_status(f"Reference read done (failed: {', '.join(errors)})")
        else:
            self._set_lbl_status("Reference labels read OK")

    def _apply_channel_labels(self):
        """Update all comboboxes with labeled channel names."""
        analog_vals = [self._get_channel_display(f"CH{i}") for i in range(1, 5)]
        ref_vals = [self._get_channel_display(f"REF{i}") for i in range(1, 5)]

        self.rise_channel_combo.config(values=analog_vals)
        self.ref_source_combo.config(values=analog_vals)
        self.ref_dest_combo.config(values=ref_vals)

        self._set_status("Channel labels applied")

    def _get_ip(self):
        try:
            ip = self._scpi_query("ETHERnet:IPADDress?")
            ip = ip.strip('"')
            self.scope_ip_var.set(ip)
            self._set_status(f"IP: {ip}")
        except Exception as e:
            self.scope_ip_var.set("Error")
            self._set_status(f"Error: {e}")

    def _open_browser(self):
        import webbrowser
        ip = self.scope_ip_var.get()
        if ip and ip not in ("---", "Error"):
            webbrowser.open(f"http://{ip}")
        else:
            self._set_status("Get IP first")

    def _connect(self):
        try:
            self.inst = self.rm.open_resource(self.resource)
            self.inst.timeout = 3000
            self.inst.query("*IDN?")
            self.connect_btn.config(state=DISABLED)
            self.disconnect_btn.config(state=NORMAL)
            self.conn_status.config(text="Connected", bootstyle="success")
        except Exception as e:
            Messagebox.show_error(f"Failed to connect:\n{e}", title="MDO34", parent=self.window)
            self.inst = None

    def _disconnect(self):
        if self.inst:
            try:
                self.inst.close()
            except Exception:
                pass
            self.inst = None
        self.connect_btn.config(state=NORMAL)
        self.disconnect_btn.config(state=DISABLED)
        self.conn_status.config(text="Disconnected", bootstyle="danger")

    def _scpi_write(self, cmd):
        if not self.inst:
            Messagebox.show_error("Not connected.", title="MDO34", parent=self.window)
            return
        self.inst.write(cmd)

    def _scpi_query(self, cmd):
        if not self.inst:
            Messagebox.show_error("Not connected.", title="MDO34", parent=self.window)
            return ""
        return self.inst.query(cmd).strip()

    def _set_status(self, text):
        self.status_label.config(text=text)

    def _on_close(self):
        if self.inst:
            try:
                self.inst.close()
            except Exception:
                pass
        self.window.destroy()

    def _read_scale(self):
        try:
            scale = float(self._scpi_query("HORIZONTAL:SCALE?"))
            self.h_scale_var.set(f"Current Scale: {scale} s/div")
        except Exception as e:
            self.h_scale_var.set(f"Error: {e}")

    def _increase_scale(self):
        try:
            scale = float(self._scpi_query("HORIZONTAL:SCALE?"))
            new_scale = scale * 2
            self._scpi_write(f"HORIZONTAL:SCALE {new_scale}")
            self.h_scale_var.set(f"Current Scale: {new_scale} s/div")
        except Exception as e:
            self.h_scale_var.set(f"Error: {e}")

    def _decrease_scale(self):
        try:
            scale = float(self._scpi_query("HORIZONTAL:SCALE?"))
            new_scale = scale / 2
            self._scpi_write(f"HORIZONTAL:SCALE {new_scale}")
            self.h_scale_var.set(f"Current Scale: {new_scale} s/div")
        except Exception as e:
            self.h_scale_var.set(f"Error: {e}")

    def _run(self):
        try:
            self._scpi_write("ACQuire:STATE RUN")
            self._set_status("Run mode")
        except Exception as e:
            self._set_status(f"Error: {e}")

    def _stop(self):
        try:
            self._scpi_write("ACQuire:STATE STOP")
            self._set_status("Stopped")
        except Exception as e:
            self._set_status(f"Error: {e}")

    def _single(self):
        try:
            self._scpi_write("ACQuire:STOPAfter SEQuence")
            self._set_status("Single acquisition")
        except Exception as e:
            self._set_status(f"Error: {e}")

    def _sequence(self):
        try:
            self._scpi_write("ACQuire:STOPAfter RUNSTop")
            self._set_status("Sequence mode")
        except Exception as e:
            self._set_status(f"Error: {e}")

    def _trigger_auto(self):
        try:
            self._scpi_write("TRIG:A:MODE AUTO")
            self._set_status("Trigger: Auto")
        except Exception as e:
            self._set_status(f"Error: {e}")

    def _trigger_normal(self):
        try:
            self._scpi_write("TRIG:A:MODE NORM")
            self._set_status("Trigger: Normal")
        except Exception as e:
            self._set_status(f"Error: {e}")

    def _download_channel_data(self, channel):
        self.inst.read_termination = None
        self.inst.write(f'DATa:SOUrce {channel}')
        self.inst.write('DATa:ENCdg ASCII')
        self.inst.write('DATa:START 1')

        nr_pt = int(float(self.inst.query('WFMOutpre:NR_Pt?').strip()))
        self.inst.write(f'DATa:STOP {nr_pt}')

        ymult = float(self.inst.query('WFMOutpre:YMUlt?').strip())
        yoff = float(self.inst.query('WFMOutpre:YOFf?').strip())
        yzero = float(self.inst.query('WFMOutpre:YZEro?').strip())
        xincr = float(self.inst.query('WFMOutpre:XINcr?').strip())
        xzero = float(self.inst.query('WFMOutpre:XZEro?').strip())
        pt_off = float(self.inst.query('WFMOutpre:PT_Off?').strip())

        old_timeout = self.inst.timeout
        self.inst.timeout = 60000
        raw = self.inst.query('CURVe?')
        self.inst.timeout = old_timeout

        values = [int(x) for x in raw.strip().split(',')]

        step = max(1, len(values) // 10000)
        sampled_idx = list(range(0, len(values), step))
        times_us = [(i - pt_off) * xincr * 1e6 + xzero * 1e6 for i in sampled_idx]
        voltages = [(values[i] - yoff) * ymult + yzero for i in sampled_idx]

        self.inst.read_termination = '\n'
        return times_us, voltages

    def _measure_rise(self, times_us, voltages):
        v_min = min(voltages)
        v_max = max(voltages)
        v_10 = v_min + 0.1 * (v_max - v_min)
        v_90 = v_min + 0.9 * (v_max - v_min)

        t_10 = None
        t_90 = None
        for i in range(len(voltages) - 1):
            if t_10 is None and voltages[i] <= v_10 and voltages[i + 1] > v_10:
                t_10 = times_us[i]
            if t_90 is None and voltages[i] <= v_90 and voltages[i + 1] > v_90:
                t_90 = times_us[i]
            if t_10 is not None and t_90 is not None:
                break

        if t_10 is None or t_90 is None:
            return None
        return {
            'v_min': v_min, 'v_max': v_max,
            'v_10': v_10, 'v_90': v_90,
            't_10_us': t_10, 't_90_us': t_90,
            'edge_time_us': t_90 - t_10,
        }

    def _measure_fall(self, times_us, voltages):
        v_min = min(voltages)
        v_max = max(voltages)
        v_90 = v_min + 0.9 * (v_max - v_min)
        v_10 = v_min + 0.1 * (v_max - v_min)

        t_90 = None
        t_10 = None
        for i in range(len(voltages) - 1):
            if t_90 is None and voltages[i] >= v_90 and voltages[i + 1] < v_90:
                t_90 = times_us[i]
            if t_90 is not None and t_10 is None and voltages[i] >= v_10 and voltages[i + 1] < v_10:
                t_10 = times_us[i]
            if t_90 is not None and t_10 is not None:
                break

        if t_90 is None or t_10 is None:
            return None
        return {
            'v_min': v_min, 'v_max': v_max,
            'v_90': v_90, 'v_10': v_10,
            't_90_us': t_90, 't_10_us': t_10,
            'edge_time_us': t_10 - t_90,
        }

    def _snap_scale(self, value, scales):
        for s in scales:
            if s >= value * 0.95:
                return s
        return scales[-1]

    def _auto_adjust_edge(self):
        if not self.inst:
            Messagebox.show_error("Not connected.", title="MDO34", parent=self.window)
            return
        channel = self._get_channel_id(self.rise_channel_var.get())
        edge = self.edge_type_var.get()
        try:
            target_pct = int(self.rise_pct_var.get()) / 100.0
        except ValueError:
            target_pct = 0.60
        self._set_status(f"Downloading {channel} data ({edge})...")
        self.window.update()
        threading.Thread(target=self._auto_adjust_thread, args=(channel, target_pct, edge), daemon=True).start()

    def _auto_adjust_thread(self, channel, target_pct, edge):
        from time import sleep
        try:
            times_us, voltages = self._download_channel_data(channel)
            if edge == "Falling":
                meas = self._measure_fall(times_us, voltages)
            else:
                meas = self._measure_rise(times_us, voltages)
            if meas is None:
                self.window.after(0, lambda: self._rise_result(f"Could not detect {edge.lower()} edge."))
                return

            total_time_needed_us = meas['edge_time_us'] / target_pct
            h_scale = total_time_needed_us / 10.0 * 1e-6
            h_scale = self._snap_scale(h_scale, self.H_SCALES)
            total_screen_us = h_scale * 10 * 1e6

            margin_us = 2 * h_scale * 1e6
            t_start = meas['t_90_us'] if edge == "Falling" else meas['t_10_us']
            h_pos = (-t_start + margin_us) / total_screen_us * 100
            h_pos = max(10, min(90, h_pos))

            v_range = meas['v_max'] - meas['v_min']
            v_scale = v_range / 8.0
            v_scale = self._snap_scale(v_scale, self.V_SCALES)

            v_mid = (meas['v_min'] + meas['v_max']) / 2.0
            v_pos = -(v_mid / v_scale)

            self.inst.write(f'HORizontal:SCAle {h_scale}')
            self.inst.write(f'HORizontal:POSition {h_pos}')
            self.inst.write(f'{channel}:SCAle {v_scale}')
            self.inst.write(f'{channel}:POSition {v_pos}')
            self.inst.write(f'{channel}:OFFSet 0')
            sleep(0.5)

            h_s = float(self.inst.query('HORizontal:SCAle?').strip())
            v_s = float(self.inst.query(f'{channel}:SCAle?').strip())

            msg = (f"{edge}: {meas['edge_time_us']:.1f} us | "
                   f"H: {h_s*1e6:.0f} us/div | V: {v_s*1000:.0f} mV/div | "
                   f"Vrange: {meas['v_min']:.4f}-{meas['v_max']:.4f} V")
            self.window.after(0, lambda: self._rise_result(msg))
        except Exception as e:
            self.window.after(0, lambda msg=f"Error: {e}": self._rise_result(msg))

    def _place_edge_cursors(self):
        if not self.inst:
            Messagebox.show_error("Not connected.", title="MDO34", parent=self.window)
            return
        channel = self._get_channel_id(self.rise_channel_var.get())
        edge = self.edge_type_var.get()
        try:
            low_pct = int(self.cursor_low_var.get())
            high_pct = int(self.cursor_high_var.get())
        except ValueError:
            low_pct, high_pct = 20, 80
        self._set_status(f"Downloading {channel} data for cursors ({edge})...")
        self.window.update()
        threading.Thread(target=self._place_cursors_thread, args=(channel, low_pct, high_pct, edge), daemon=True).start()

    def _place_cursors_thread(self, channel, low_pct, high_pct, edge):
        from time import sleep
        try:
            times_us, voltages = self._download_channel_data(channel)

            v_min = min(voltages)
            v_max = max(voltages)
            v_low = v_min + (low_pct / 100.0) * (v_max - v_min)
            v_high = v_min + (high_pct / 100.0) * (v_max - v_min)

            t_low = None
            t_high = None

            if edge == "Falling":
                for i in range(len(voltages) - 1):
                    if t_high is None and voltages[i] >= v_high and voltages[i + 1] < v_high:
                        t_high = times_us[i]
                    if t_high is not None and t_low is None and voltages[i] >= v_low and voltages[i + 1] < v_low:
                        t_low = times_us[i]
                    if t_low is not None and t_high is not None:
                        break
            else:
                for i in range(len(voltages) - 1):
                    if t_low is None and voltages[i] <= v_low and voltages[i + 1] > v_low:
                        t_low = times_us[i]
                    if t_high is None and voltages[i] <= v_high and voltages[i + 1] > v_high:
                        t_high = times_us[i]
                    if t_low is not None and t_high is not None:
                        break

            if t_low is None or t_high is None:
                self.window.after(0, lambda: self._rise_result(f"Could not find {edge.lower()} edge crossings."))
                return

            if edge == "Falling":
                t_first_s = t_high * 1e-6
                t_second_s = t_low * 1e-6
            else:
                t_first_s = t_low * 1e-6
                t_second_s = t_high * 1e-6

            self.inst.write('CURSor:STATE ON')
            self.inst.write('CURSor:FUNCtion VBArs')
            self.inst.write('CURSor:VBArs:UNIts SECOnds')
            self.inst.write(f'CURSor:VBArs:POSITION1 {t_first_s}')
            self.inst.write(f'CURSor:VBArs:POSITION2 {t_second_s}')
            sleep(0.3)

            edge_time_us = abs(t_high - t_low)
            delta_v_mv = (v_high - v_low) * 1000
            slew_rate = delta_v_mv / edge_time_us if edge_time_us > 0 else 0

            msg = (f"Cursors ({edge}): {low_pct}%={t_first_s*1e6:.2f}us, {high_pct}%={t_second_s*1e6:.2f}us | "
                   f"dT={edge_time_us:.2f}us | dV={delta_v_mv:.1f}mV | "
                   f"Slew={slew_rate:.2f} mV/us")
            self.window.after(0, lambda: self._rise_result(msg))
        except Exception as e:
            self.window.after(0, lambda msg=f"Error: {e}": self._rise_result(msg))

    def _rise_result(self, text):
        self.rise_result_label.config(text=text)
        self._set_status(text[:60])

    def _save_to_ref(self):
        try:
            src = self._get_channel_id(self.channel_var.get())
            dest = self._get_channel_id(self.ref_var.get())
            self._scpi_write(f"SAVE:WAVEFORM {src},{dest}")
            self._set_status(f"Saved {src} to {dest}")
        except Exception as e:
            self._set_status(f"Error: {e}")

    def _select_folder(self):
        from tkinter import filedialog
        folder = filedialog.askdirectory(initialdir=self.save_folder, parent=self.window)
        if folder:
            self.save_folder = folder
            self.folder_var.set(folder)

    def _open_folder(self):
        os.startfile(self.save_folder)

    def _save_screenshot(self):
        if not self.inst:
            self.shot_status.config(text="Not connected.", bootstyle="danger")
            return
        name = self.waveform_name_var.get()
        if not name:
            self.shot_status.config(text="Enter a waveform name.", bootstyle="danger")
            return
        try:
            self.inst.timeout = 10000
            self.inst.write("HARDCOPY:FORMAT PNG")
            self.inst.write("HARDCOPY START")
            image_data = self.inst.read_raw()
            self.inst.timeout = 3000
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = os.path.join(self.save_folder, f"{name}_{timestamp}.png")
            with open(file_path, "wb") as f:
                f.write(image_data)
            self.shot_status.config(text=f"Saved: {file_path}", bootstyle="success")
        except Exception as e:
            self.shot_status.config(text=f"Error: {e}", bootstyle="danger")

    def _send_annotation(self):
        text = self.annotation_var.get()
        if not text:
            self._set_status("Enter annotation text.")
            return
        try:
            self._scpi_write(f'MESSage:SHOW "{text}"')
            self._set_status("Annotation sent")
        except Exception as e:
            self._set_status(f"Error: {e}")


class ElectronicLoadWindow:
    """Standalone control window for KIKUSUI PLZ664WA electronic load."""

    CONNECT_TIMEOUT_S = 6
    CONNECT_RETRIES   = 2
    RETRY_DELAY_MS    = 1000

    def __init__(self, parent, rm, resource, idn):
        self.rm = rm
        self.resource = resource
        self.idn = idn
        self.inst = None
        self.auto_readback_active = False
        self.after_id = None
        self.stop_evt = threading.Event()
        self.toggle_thread = None

        self.window = ttk.Toplevel(parent)
        self.window.title("Electronic Load -- PLZ664WA")
        self.window.geometry("520x560")
        self.window.resizable(True, True)
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)

        header = ttk.Frame(self.window, padding=(16, 12))
        header.pack(fill=X)
        ttk.Label(header, text="KIKUSUI PLZ664WA", font=("Segoe UI", 13, "bold")).pack(side=LEFT)
        ttk.Label(header, text=resource, font=("Segoe UI", 9), bootstyle="secondary").pack(side=RIGHT)

        ttk.Separator(self.window).pack(fill=X)

        scroll_container = ttk.Frame(self.window)
        scroll_container.pack(fill=BOTH, expand=True)
        canvas = ttk.Canvas(scroll_container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(scroll_container, orient=VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=RIGHT, fill=Y)
        canvas.pack(side=LEFT, fill=BOTH, expand=True)
        body = ttk.Frame(canvas, padding=16)
        body_id = canvas.create_window((0, 0), window=body, anchor=NW)
        body.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(body_id, width=e.width))
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", lambda ev: canvas.yview_scroll(-ev.delta // 120, "units")))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        # Connection
        conn_frame = ttk.Frame(body)
        conn_frame.pack(fill=X, pady=(0, 10))
        self.connect_btn = ttk.Button(conn_frame, text="Connect", bootstyle="success", command=self._connect)
        self.connect_btn.pack(side=LEFT, padx=(0, 8))
        self.disconnect_btn = ttk.Button(conn_frame, text="Disconnect", bootstyle="danger", command=self._disconnect, state=DISABLED)
        self.disconnect_btn.pack(side=LEFT)
        self.conn_status = ttk.Label(conn_frame, text="Disconnected", font=("Segoe UI", 9), bootstyle="danger")
        self.conn_status.pack(side=LEFT, padx=(12, 0))

        # Current Control
        ctrl_frame = ttk.Labelframe(body, text="Load Current Control", padding=10)
        ctrl_frame.pack(fill=X, pady=(0, 10))

        curr_row = ttk.Frame(ctrl_frame)
        curr_row.pack(fill=X, pady=(0, 6))
        ttk.Label(curr_row, text="Set Current (A):").pack(side=LEFT, padx=(0, 4))
        self.current_var = ttk.StringVar()
        ttk.Entry(curr_row, textvariable=self.current_var, width=10).pack(side=LEFT, padx=(0, 8))
        ttk.Button(curr_row, text="Set", bootstyle="primary", width=6, command=self._set_current).pack(side=LEFT, padx=(0, 8))
        self.curr_setting_label = ttk.Label(curr_row, text="Setting: ---", font=("Consolas", 9))
        self.curr_setting_label.pack(side=LEFT, padx=(0, 8))
        ttk.Button(curr_row, text="Read", bootstyle="info-outline", width=6, command=self._read_current_setting).pack(side=LEFT)

        # CV Mode
        cv_row = ttk.Frame(ctrl_frame)
        cv_row.pack(fill=X, pady=(0, 6))
        ttk.Label(cv_row, text="CV Voltage (V):").pack(side=LEFT, padx=(0, 4))
        self.cv_var = ttk.StringVar()
        ttk.Entry(cv_row, textvariable=self.cv_var, width=10).pack(side=LEFT, padx=(0, 8))
        ttk.Button(cv_row, text="Set CV", bootstyle="primary", width=6, command=self._set_cv).pack(side=LEFT)

        # Output ON/OFF
        out_row = ttk.Frame(ctrl_frame)
        out_row.pack(fill=X)
        ttk.Button(out_row, text="ON", bootstyle="success", width=6, command=self._turn_on).pack(side=LEFT, padx=(0, 6))
        ttk.Button(out_row, text="OFF", bootstyle="danger", width=6, command=self._turn_off).pack(side=LEFT)

        # Undervoltage Threshold
        uv_frame = ttk.Labelframe(body, text="Undervoltage Protection", padding=10)
        uv_frame.pack(fill=X, pady=(0, 10))

        uv_row = ttk.Frame(uv_frame)
        uv_row.pack(fill=X)
        ttk.Label(uv_row, text="Threshold (V):").pack(side=LEFT, padx=(0, 4))
        self.uv_threshold_var = ttk.StringVar(value="0.1")
        ttk.Entry(uv_row, textvariable=self.uv_threshold_var, width=8).pack(side=LEFT)
        ttk.Label(uv_row, text="(ON/Toggle blocked if voltage below threshold)", font=("Segoe UI", 8), bootstyle="secondary").pack(side=LEFT, padx=(12, 0))

        # Toggle
        toggle_frame = ttk.Labelframe(body, text="Toggle Load", padding=10)
        toggle_frame.pack(fill=X, pady=(0, 10))

        tog_row = ttk.Frame(toggle_frame)
        tog_row.pack(fill=X)
        ttk.Label(tog_row, text="Delay (s):").pack(side=LEFT, padx=(0, 4))
        self.delay_var = ttk.StringVar()
        ttk.Entry(tog_row, textvariable=self.delay_var, width=8).pack(side=LEFT, padx=(0, 8))
        ttk.Button(tog_row, text="Toggle", bootstyle="warning", width=8, command=self._toggle_output).pack(side=LEFT)

        # Readback
        read_frame = ttk.Labelframe(body, text="Readback", padding=10)
        read_frame.pack(fill=X, pady=(0, 10))

        ctrl_row = ttk.Frame(read_frame)
        ctrl_row.pack(fill=X, pady=(0, 8))

        self.auto_var = ttk.BooleanVar(value=False)
        ttk.Checkbutton(
            ctrl_row, text="Auto", variable=self.auto_var,
            bootstyle="round-toggle", command=self._toggle_auto_readback
        ).pack(side=LEFT)

        ttk.Label(ctrl_row, text="Interval (ms):").pack(side=LEFT, padx=(12, 4))
        self.interval_var = ttk.StringVar(value="1000")
        ttk.Entry(ctrl_row, textvariable=self.interval_var, width=6).pack(side=LEFT)

        ttk.Button(ctrl_row, text="Read Now", bootstyle="info-outline", command=self._update_readback).pack(side=RIGHT)

        self.v_label = ttk.Label(read_frame, text="Voltage: ---", font=("Consolas", 10))
        self.v_label.pack(anchor=W)
        self.i_label = ttk.Label(read_frame, text="Current: ---", font=("Consolas", 10))
        self.i_label.pack(anchor=W, pady=(4, 0))
        self.p_label = ttk.Label(read_frame, text="Power:   ---", font=("Consolas", 10))
        self.p_label.pack(anchor=W, pady=(4, 0))

        # Status
        self.status_label = ttk.Label(body, text="", font=("Segoe UI", 9), bootstyle="secondary")
        self.status_label.pack(anchor=W, pady=(4, 0))

    # PLZ664WA can wedge inside NI-VISA (ignores the VISA timeout), so connect runs in a
    # worker thread and is abandoned after CONNECT_TIMEOUT_S instead of freezing the GUI.
    def _connect(self, retry=0):
        import time
        if not self.window.winfo_exists():
            return
        self.connect_btn.config(state=DISABLED)
        status = f"Retrying ({retry}/{self.CONNECT_RETRIES})..." if retry else "Connecting..."
        self.conn_status.config(text=status, bootstyle="warning")
        self.stop_evt.clear()
        attempt = {"retry": retry, "inst": None, "error": None, "done": False, "abandoned": False, "lock": threading.Lock()}

        def _open():
            inst, error = None, None
            try:
                inst = self.rm.open_resource(self.resource)
                inst.timeout = 3000
                inst.query("*IDN?")
            except Exception as e:
                error = e
            with attempt["lock"]:
                attempt["inst"], attempt["error"], attempt["done"] = inst, error, True
                abandoned = attempt["abandoned"]
            if abandoned and inst:
                inst.close()

        threading.Thread(target=_open, daemon=True).start()
        self._poll_connect(attempt, time.monotonic() + self.CONNECT_TIMEOUT_S)

    def _poll_connect(self, attempt, deadline):
        import time
        with attempt["lock"]:
            done = attempt["done"]
            if not done and (time.monotonic() >= deadline or not self.window.winfo_exists()):
                attempt["abandoned"] = True
        if not self.window.winfo_exists():
            return
        if not done and not attempt["abandoned"]:
            self.window.after(100, self._poll_connect, attempt, deadline)
            return
        if done and attempt["error"] is None:
            self.inst = attempt["inst"]
            self.disconnect_btn.config(state=NORMAL)
            self.conn_status.config(text="Connected", bootstyle="success")
            return
        # Retry only fast errors; a timeout means the device is wedged and retrying just stacks stuck threads.
        if done and attempt["retry"] < self.CONNECT_RETRIES:
            self.window.after(self.RETRY_DELAY_MS, self._connect, attempt["retry"] + 1)
            return
        self.connect_btn.config(state=NORMAL)
        self.conn_status.config(text="Not responding" if not done else "Disconnected", bootstyle="danger")
        if done:
            Messagebox.show_error(f"Failed to connect after {attempt['retry'] + 1} attempts:\n{attempt['error']}", title="PLZ664WA", parent=self.window)
        else:
            Messagebox.show_error(
                f"PLZ664WA did not respond within {self.CONNECT_TIMEOUT_S} s.\n\n"
                "Replug USB or power-cycle the load, then Connect again.",
                title="PLZ664WA", parent=self.window,
            )

    # Never close the session with a toggle mid-flight: stop readback, let the toggle thread
    # finish its INP OFF, then force INP OFF and close.
    def _shutdown(self, then):
        self.auto_readback_active = False
        if self.after_id:
            self.window.after_cancel(self.after_id)
            self.after_id = None
        self.stop_evt.set()
        if self.toggle_thread and self.toggle_thread.is_alive():
            self.window.after(50, self._shutdown, then)
            return
        if self.inst:
            try:
                self.inst.write(":INP OFF")
            except Exception:
                pass
            try:
                self.inst.close()
            except Exception:
                pass
            self.inst = None
        then()

    def _disconnect(self):
        self.disconnect_btn.config(state=DISABLED)
        self._shutdown(self._after_disconnect)

    def _after_disconnect(self):
        self.connect_btn.config(state=NORMAL)
        self.conn_status.config(text="Disconnected", bootstyle="danger")

    def _scpi_write(self, cmd):
        if not self.inst:
            Messagebox.show_error("Not connected.", title="PLZ664WA", parent=self.window)
            return
        self.inst.write(cmd)

    def _scpi_query(self, cmd):
        if not self.inst:
            Messagebox.show_error("Not connected.", title="PLZ664WA", parent=self.window)
            return ""
        return self.inst.query(cmd).strip()

    def _set_status(self, text, style="secondary"):
        self.status_label.config(text=text, bootstyle=style)

    def _set_current(self):
        val = self.current_var.get()
        if not val:
            self._set_status("Enter a current value.", "danger")
            return
        try:
            self._scpi_write(f":CURR {val}")
            self._read_current_setting()
            self._set_status(f"Current set to {val} A", "success")
        except Exception as e:
            self._set_status(f"Error: {e}", "danger")

    def _read_current_setting(self):
        try:
            setting = float(self._scpi_query(":CURR?"))
            self.curr_setting_label.config(text=f"Setting: {setting:.4f} A")
        except Exception as e:
            self.curr_setting_label.config(text="Setting: Error")
            self._set_status(f"Error: {e}", "danger")

    def _set_cv(self):
        val = self.cv_var.get()
        if not val:
            self._set_status("Enter a CV voltage value.", "danger")
            return
        try:
            self._scpi_write(f":VOLT {val}")
            self._set_status(f"CV set to {val} V", "success")
        except Exception as e:
            self._set_status(f"Error: {e}", "danger")

    def _check_undervoltage(self):
        try:
            threshold = float(self.uv_threshold_var.get())
        except ValueError:
            threshold = 0.1
        try:
            voltage = float(self._scpi_query(":MEAS:VOLT?"))
            if voltage < threshold:
                self._set_status(f"Blocked: voltage {voltage:.4f} V < {threshold} V threshold", "danger")
                return False
        except Exception as e:
            self._set_status(f"Error reading voltage: {e}", "danger")
            return False
        return True

    def _turn_on(self):
        if not self._check_undervoltage():
            return
        try:
            self._scpi_write(":INP ON")
            self._set_status("Load ON", "success")
        except Exception as e:
            self._set_status(f"Error: {e}", "danger")

    def _turn_off(self):
        try:
            self._scpi_write(":INP OFF")
            self._set_status("Load OFF", "success")
        except Exception as e:
            self._set_status(f"Error: {e}", "danger")

    def _toggle_output(self):
        try:
            delay = float(self.delay_var.get())
        except ValueError:
            self._set_status("Delay must be numeric.", "danger")
            return
        if self.toggle_thread and self.toggle_thread.is_alive():
            self._set_status("Toggle already running.", "danger")
            return
        self.toggle_thread = threading.Thread(target=self._toggle_thread, args=(delay,), daemon=True)
        self.toggle_thread.start()

    def _toggle_thread(self, delay):
        inst = self.inst
        if not inst:
            self.window.after(0, lambda: self._set_status("Not connected.", "danger"))
            return
        try:
            threshold = float(self.uv_threshold_var.get())
        except ValueError:
            threshold = 0.1
        try:
            voltage = float(inst.query(":MEAS:VOLT?"))
            if voltage < threshold:
                self.window.after(0, lambda: self._set_status(
                    f"Blocked: voltage {voltage:.4f} V < {threshold} V threshold", "danger"))
                return
            inst.write(":INP ON")
            self.stop_evt.wait(delay)
            inst.write(":INP OFF")
            if not self.stop_evt.is_set():
                self.window.after(0, lambda: self._set_status("Toggle complete (ON -> OFF)", "success"))
        except Exception as e:
            self.window.after(0, lambda msg=f"Error: {e}": self._set_status(msg, "danger"))

    def _update_readback(self):
        try:
            v = float(self._scpi_query(":MEAS:VOLT?"))
            i = float(self._scpi_query(":MEAS:CURR?"))
            p = float(self._scpi_query(":MEAS:POW?"))
            self.v_label.config(text=f"Voltage: {v:.4f} V")
            self.i_label.config(text=f"Current: {i:.4f} A")
            self.p_label.config(text=f"Power:   {p:.4f} W")
        except Exception:
            self.v_label.config(text="Voltage: Error")
            self.i_label.config(text="Current: Error")
            self.p_label.config(text="Power:   Error")

    def _toggle_auto_readback(self):
        if self.auto_var.get():
            try:
                interval = int(self.interval_var.get())
                if interval < 100:
                    interval = 100
            except ValueError:
                interval = 1000
            self.auto_readback_active = True
            self._auto_readback_loop(interval)
        else:
            self.auto_readback_active = False
            if self.after_id:
                self.window.after_cancel(self.after_id)
                self.after_id = None

    def _auto_readback_loop(self, interval):
        if not self.auto_readback_active:
            return
        self._update_readback()
        self.after_id = self.window.after(interval, lambda: self._auto_readback_loop(interval))

    def _on_close(self):
        self._shutdown(self.window.destroy)


class DAQWindow:
    """Standalone control window for Keysight DAQ973A + DAQM909A."""

    RANGES = ["300mV", "1V", "3V", "18V"]
    INPUT_TYPES = ["DIFF", "SEND", "IEPE"]
    COUPLINGS = ["DC", "AC"]
    MODES = ["TIME", "FREQ"]
    RATES = ["1562.5", "3125", "6250", "12500", "25000", "50000", "100000", "200000", "400000", "800000"]

    def __init__(self, parent, rm, resource, idn):
        self.rm = rm
        self.resource = resource
        self.idn = idn
        self.inst = None
        self.auto_acquire_active = False
        self.after_id = None
        self.slot_avail = {1: True, 2: False, 3: False}

        self.ch_range = {}
        self.ch_input_type = {}
        self.ch_coupling = {}
        self.ch_mode = {}
        self.ch_rate = {}
        self.ch_samp_count = {}
        self.ch_results = {}
        self.slot_widgets = {2: [], 3: []}
        self.slot_status_labels = {}

        self.window = ttk.Toplevel(parent)
        self.window.title("DAQ -- DAQ973A + DAQM909A")
        self.window.geometry("1100x700")
        self.window.resizable(True, True)
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)

        header = ttk.Frame(self.window, padding=(16, 12))
        header.pack(fill=X)
        ttk.Label(header, text="Keysight DAQ973A", font=("Segoe UI", 13, "bold")).pack(side=LEFT)
        ttk.Label(header, text=resource, font=("Segoe UI", 9), bootstyle="secondary").pack(side=RIGHT)

        ttk.Separator(self.window).pack(fill=X)

        # Scrollable body
        container = ttk.Frame(self.window)
        container.pack(fill=BOTH, expand=True)
        canvas = ttk.Canvas(container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient=VERTICAL, command=canvas.yview)
        self.body = ttk.Frame(canvas, padding=16)
        self.body.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.body, anchor=NW)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", lambda ev: canvas.yview_scroll(-ev.delta // 120, "units")))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        # Connection
        conn_frame = ttk.Frame(self.body)
        conn_frame.pack(fill=X, pady=(0, 10))
        self.connect_btn = ttk.Button(conn_frame, text="Connect", bootstyle="success", command=self._connect)
        self.connect_btn.pack(side=LEFT, padx=(0, 8))
        self.disconnect_btn = ttk.Button(conn_frame, text="Disconnect", bootstyle="danger", command=self._disconnect, state=DISABLED)
        self.disconnect_btn.pack(side=LEFT)
        self.conn_status = ttk.Label(conn_frame, text="Disconnected", font=("Segoe UI", 9), bootstyle="danger")
        self.conn_status.pack(side=LEFT, padx=(12, 0))

        # Check Modules button
        mod_frame = ttk.Frame(self.body)
        mod_frame.pack(fill=X, pady=(0, 10))
        ttk.Button(mod_frame, text="Check Connected Modules", bootstyle="info", command=self._check_modules).pack(side=LEFT)

        # Build slot sections
        self._build_slot(1, [101, 102, 103, 104])
        self._build_slot(2, [201, 202, 203, 204])
        self._build_slot(3, [301, 302, 303, 304])

        # Bottom buttons
        btn_frame = ttk.Frame(self.body)
        btn_frame.pack(fill=X, pady=(10, 0))

        for slot_num in [1, 2, 3]:
            ttk.Button(btn_frame, text=f"Acquire All Slot{slot_num}", bootstyle="primary",
                       command=lambda s=slot_num: self._acquire_all_slot(s)).pack(side=LEFT, padx=(0, 4))
            ttk.Button(btn_frame, text=f"Init Slot{slot_num}", bootstyle="outline",
                       command=lambda s=slot_num: self._init_slot(s)).pack(side=LEFT, padx=(0, 10))

        ttk.Button(btn_frame, text="Clear (*CLS)", bootstyle="warning-outline", command=self._clear_error).pack(side=LEFT, padx=(0, 4))
        ttk.Button(btn_frame, text="Query Error", bootstyle="warning-outline", command=self._query_error).pack(side=LEFT)

        # Auto-acquire
        auto_frame = ttk.Frame(self.body)
        auto_frame.pack(fill=X, pady=(10, 0))
        self.auto_var = ttk.BooleanVar(value=False)
        ttk.Checkbutton(auto_frame, text="Auto Acquire", variable=self.auto_var,
                        bootstyle="round-toggle", command=self._toggle_auto_acquire).pack(side=LEFT)
        ttk.Label(auto_frame, text="Interval (ms):").pack(side=LEFT, padx=(12, 4))
        self.interval_var = ttk.StringVar(value="500")
        ttk.Entry(auto_frame, textvariable=self.interval_var, width=6).pack(side=LEFT)

        # Status
        self.status_label = ttk.Label(self.body, text="", font=("Consolas", 9), bootstyle="secondary", wraplength=1050)
        self.status_label.pack(anchor=W, pady=(8, 0))

    def _build_slot(self, slot_num, channels):
        frame = ttk.Labelframe(self.body, text=f"Slot {slot_num}", padding=8)
        frame.pack(fill=X, pady=(0, 8))

        status_lbl = ttk.Label(frame, text="(check modules)", font=("Segoe UI", 8), bootstyle="secondary")
        status_lbl.pack(anchor=W, pady=(0, 4))
        self.slot_status_labels[slot_num] = status_lbl

        # Header
        hdr = ttk.Frame(frame)
        hdr.pack(fill=X)
        headers = ["Ch", "Range", "Input", "Coupl", "Mode", "Rate", "Samp", "Avg", "Std", "Min", "Max", ""]
        col_widths = [4, 7, 6, 5, 5, 9, 6, 10, 10, 10, 10, 7]
        for col, (txt, w) in enumerate(zip(headers, col_widths)):
            ttk.Label(hdr, text=txt, font=("Segoe UI", 8, "bold"), width=w).grid(row=0, column=col, padx=2)

        for row_idx, ch in enumerate(channels, start=1):
            ttk.Label(hdr, text=str(ch), width=4).grid(row=row_idx, column=0, padx=2, pady=2)

            rng = ttk.StringVar(value="18V")
            self.ch_range[ch] = rng
            w = ttk.Combobox(hdr, textvariable=rng, values=self.RANGES, state="readonly", width=5)
            w.grid(row=row_idx, column=1, padx=2, pady=2)
            if slot_num > 1:
                self.slot_widgets[slot_num].append(w)

            itype = ttk.StringVar(value="DIFF")
            self.ch_input_type[ch] = itype
            w = ttk.Combobox(hdr, textvariable=itype, values=self.INPUT_TYPES, state="readonly", width=4)
            w.grid(row=row_idx, column=2, padx=2, pady=2)
            if slot_num > 1:
                self.slot_widgets[slot_num].append(w)

            coup = ttk.StringVar(value="DC")
            self.ch_coupling[ch] = coup
            w = ttk.Combobox(hdr, textvariable=coup, values=self.COUPLINGS, state="readonly", width=3)
            w.grid(row=row_idx, column=3, padx=2, pady=2)
            if slot_num > 1:
                self.slot_widgets[slot_num].append(w)

            mode = ttk.StringVar(value="TIME")
            self.ch_mode[ch] = mode
            w = ttk.Combobox(hdr, textvariable=mode, values=self.MODES, state="readonly", width=4)
            w.grid(row=row_idx, column=4, padx=2, pady=2)
            if slot_num > 1:
                self.slot_widgets[slot_num].append(w)

            rate = ttk.StringVar(value="100000")
            self.ch_rate[ch] = rate
            w = ttk.Combobox(hdr, textvariable=rate, values=self.RATES, state="readonly", width=7)
            w.grid(row=row_idx, column=5, padx=2, pady=2)
            if slot_num > 1:
                self.slot_widgets[slot_num].append(w)

            samp = ttk.StringVar(value="512")
            self.ch_samp_count[ch] = samp
            w = ttk.Entry(hdr, textvariable=samp, width=5)
            w.grid(row=row_idx, column=6, padx=2, pady=2)
            if slot_num > 1:
                self.slot_widgets[slot_num].append(w)

            result_labels = {}
            for col_off, key in enumerate(["avg", "std", "min", "max"]):
                lbl = ttk.Label(hdr, text="--", width=10, font=("Consolas", 8))
                lbl.grid(row=row_idx, column=7 + col_off, padx=2, pady=2)
                result_labels[key] = lbl
            self.ch_results[ch] = result_labels

            btn = ttk.Button(hdr, text="Acq", bootstyle="primary-outline", width=4,
                             command=lambda c=ch: self._acquire_channel(c))
            btn.grid(row=row_idx, column=11, padx=2, pady=2)
            if slot_num > 1:
                self.slot_widgets[slot_num].append(btn)

    def _set_status(self, text):
        self.status_label.config(text=text)

    def _connect(self):
        try:
            self.inst = self.rm.open_resource(self.resource)
            self.inst.timeout = 30000
            self.inst.query("*IDN?")
            self.connect_btn.config(state=DISABLED)
            self.disconnect_btn.config(state=NORMAL)
            self.conn_status.config(text="Connected", bootstyle="success")
        except Exception as e:
            Messagebox.show_error(f"Failed to connect:\n{e}", title="DAQ973A", parent=self.window)
            self.inst = None

    def _disconnect(self):
        self.auto_acquire_active = False
        if self.after_id:
            self.window.after_cancel(self.after_id)
            self.after_id = None
        if self.inst:
            try:
                self.inst.close()
            except Exception:
                pass
            self.inst = None
        self.connect_btn.config(state=NORMAL)
        self.disconnect_btn.config(state=DISABLED)
        self.conn_status.config(text="Disconnected", bootstyle="danger")

    def _check_modules(self):
        threading.Thread(target=self._check_modules_thread, daemon=True).start()

    def _check_modules_thread(self):
        if not self.inst:
            self.window.after(0, lambda: self._set_status("Not connected."))
            return
        try:
            ctype1 = self.inst.query("SYSTem:CTYPe? 1").strip()
            ctype2 = self.inst.query("SYSTem:CTYPe? 2").strip()
            ctype3 = self.inst.query("SYSTem:CTYPe? 3").strip()
            self.window.after(0, lambda: self._apply_module_states(ctype1, ctype2, ctype3))
        except Exception as e:
            self.window.after(0, lambda msg=f"Module check error: {e}": self._set_status(msg))

    def _parse_model(self, ctype):
        parts = [p.strip() for p in ctype.split(",")]
        return parts[1] if len(parts) >= 2 else ctype

    def _apply_module_states(self, ctype1, ctype2, ctype3):
        for slot_num, ctype in [(1, ctype1), (2, ctype2), (3, ctype3)]:
            model = self._parse_model(ctype)
            lbl = self.slot_status_labels[slot_num]
            if model == "0" or model == "":
                lbl.config(text="No module found", bootstyle="danger")
                if slot_num > 1:
                    self.slot_avail[slot_num] = False
            elif model.upper() == "DAQM909A":
                lbl.config(text=f"Slot {slot_num}: {model}", bootstyle="success")
                self.slot_avail[slot_num] = True
            else:
                lbl.config(text=f"Slot {slot_num}: {model} (not supported)", bootstyle="warning")
                if slot_num > 1:
                    self.slot_avail[slot_num] = False
        for slot_num in [2, 3]:
            avail = self.slot_avail[slot_num]
            for w in self.slot_widgets[slot_num]:
                try:
                    if isinstance(w, ttk.Combobox):
                        w.config(state="readonly" if avail else DISABLED)
                    else:
                        w.config(state=NORMAL if avail else DISABLED)
                except Exception:
                    pass

    def _acquire_channel(self, ch):
        threading.Thread(target=self._acquire_channel_thread, args=(ch,), daemon=True).start()

    def _acquire_channel_thread(self, ch):
        if not self.inst:
            self.window.after(0, lambda: self._set_status("Not connected."))
            return
        try:
            stats = self._configure_and_acquire(self.inst, ch)
            self.window.after(0, lambda: self._update_results(ch, stats))
            self.window.after(0, lambda: self._set_status(
                f"Ch{ch}: avg={stats['avg']:.6f} std={stats['std']:.6f} min={stats['min']:.6f} max={stats['max']:.6f}"))
        except Exception as e:
            self.window.after(0, lambda msg=f"Ch{ch} ERROR: {e}": self._set_status(msg))

    def _acquire_all_slot(self, slot_num):
        channels = [slot_num * 100 + i for i in range(1, 5)]
        threading.Thread(target=self._acquire_all_slot_thread, args=(channels,), daemon=True).start()

    def _acquire_all_slot_thread(self, channels):
        if not self.inst:
            self.window.after(0, lambda: self._set_status("Not connected."))
            return
        try:
            results = self._configure_and_acquire_slot(self.inst, channels)
            lines = []
            for ch, stats in results.items():
                self.window.after(0, lambda c=ch, s=stats: self._update_results(c, s))
                lines.append(f"Ch{ch}: avg={stats['avg']:.6f} std={stats['std']:.6f}")
            self.window.after(0, lambda: self._set_status(" | ".join(lines)))
        except Exception as e:
            self.window.after(0, lambda msg=f"Acquire slot ERROR: {e}": self._set_status(msg))

    def _init_slot(self, slot_num):
        if not self.inst:
            self._set_status("Not connected.")
            return
        channels = [slot_num * 100 + i for i in range(1, 5)]
        ch_list = ",".join(str(c) for c in channels)
        try:
            self.inst.write(f"INIT3 (@{ch_list})")
            self._set_status(f"INIT3 (@{ch_list}) sent")
        except Exception as e:
            self._set_status(f"INIT3 ERROR: {e}")

    def _configure_and_acquire(self, inst, ch):
        rng = self.ch_range[ch].get()
        itype = self.ch_input_type[ch].get()
        coup = self.ch_coupling[ch].get()
        mode = self.ch_mode[ch].get()
        rate = self.ch_rate[ch].get()
        samp_count = self.ch_samp_count[ch].get().strip() or "DEF"
        inst.write("ABOR3")
        inst.write("*CLS")
        inst.write(f"ACQ3:VOLT {rng},{itype},{coup},{mode},{samp_count},{rate},(@{ch})")
        inst.write(f"INIT3 (@{ch})")
        inst.query("*OPC?")
        raw = inst.query(f"FETCh3:STATistics? 1,1,256,(@{ch})").strip()
        parts = [float(x) for x in raw.split(",")]
        return {"avg": parts[0], "std": parts[1], "min": parts[2], "max": parts[3]}

    def _configure_and_acquire_slot(self, inst, channels):
        inst.write("ABOR3")
        inst.write("*CLS")
        for ch in channels:
            rng = self.ch_range[ch].get()
            itype = self.ch_input_type[ch].get()
            coup = self.ch_coupling[ch].get()
            mode = self.ch_mode[ch].get()
            rate = self.ch_rate[ch].get()
            samp_count = self.ch_samp_count[ch].get().strip() or "DEF"
            inst.write(f"ACQ3:VOLT {rng},{itype},{coup},{mode},{samp_count},{rate},(@{ch})")
        ch_list = ",".join(str(c) for c in channels)
        inst.write(f"INIT3 (@{ch_list})")
        inst.query("*OPC?")
        results = {}
        for ch in channels:
            raw = inst.query(f"FETCh3:STATistics? 1,1,256,(@{ch})").strip()
            parts = [float(x) for x in raw.split(",")]
            results[ch] = {"avg": parts[0], "std": parts[1], "min": parts[2], "max": parts[3]}
        return results

    def _update_results(self, ch, stats):
        labels = self.ch_results[ch]
        labels["avg"].config(text=f"{stats['avg']:.6f}")
        labels["std"].config(text=f"{stats['std']:.6f}")
        labels["min"].config(text=f"{stats['min']:.6f}")
        labels["max"].config(text=f"{stats['max']:.6f}")

    def _clear_error(self):
        if not self.inst:
            self._set_status("Not connected.")
            return
        try:
            self.inst.write("*CLS")
            self._set_status("*CLS sent")
        except Exception as e:
            self._set_status(f"*CLS ERROR: {e}")

    def _query_error(self):
        if not self.inst:
            self._set_status("Not connected.")
            return
        try:
            resp = self.inst.query("SYST:ERR?").strip()
            self._set_status(f"SYST:ERR? -> {resp}")
        except Exception as e:
            self._set_status(f"SYST:ERR? ERROR: {e}")

    def _toggle_auto_acquire(self):
        if self.auto_var.get():
            try:
                interval = int(self.interval_var.get())
                if interval < 100:
                    interval = 100
            except ValueError:
                interval = 500
            self.auto_acquire_active = True
            self._auto_acquire_loop(interval)
        else:
            self.auto_acquire_active = False
            if self.after_id:
                self.window.after_cancel(self.after_id)
                self.after_id = None

    def _auto_acquire_loop(self, interval):
        if not self.auto_acquire_active:
            return
        threading.Thread(target=self._auto_acquire_thread, args=(interval,), daemon=True).start()

    def _auto_acquire_thread(self, interval):
        if not self.inst:
            self.window.after(0, lambda: self._set_status("Not connected."))
            return
        try:
            lines = []
            for slot_num in [1, 2, 3]:
                if not self.slot_avail[slot_num]:
                    continue
                channels = [slot_num * 100 + i for i in range(1, 5)]
                results = self._configure_and_acquire_slot(self.inst, channels)
                for ch, stats in results.items():
                    self.window.after(0, lambda c=ch, s=stats: self._update_results(c, s))
                    lines.append(f"Ch{ch}={stats['avg']:.4f}V")
            self.window.after(0, lambda: self._set_status(" | ".join(lines)))
        except Exception as e:
            self.window.after(0, lambda msg=f"Auto-acquire ERROR: {e}": self._set_status(msg))
        finally:
            if self.auto_acquire_active:
                self.after_id = self.window.after(interval, lambda: self._auto_acquire_loop(interval))

    def _on_close(self):
        self.auto_acquire_active = False
        if self.after_id:
            self.window.after_cancel(self.after_id)
        if self.inst:
            try:
                self.inst.close()
            except Exception:
                pass
        self.window.destroy()


class SCPILowLevelWindow:
    """Standalone SCPI low-level command window for any VISA device."""

    def __init__(self, parent, rm):
        self.rm = rm
        self.resources = list(rm.list_resources())

        self.window = ttk.Toplevel(parent)
        self.window.title("SCPI Low Level")
        self.window.geometry("700x560")
        self.window.resizable(True, True)

        header = ttk.Frame(self.window, padding=(16, 12))
        header.pack(fill=X)
        ttk.Label(header, text="SCPI Low Level", font=("Segoe UI", 13, "bold")).pack(side=LEFT)

        ttk.Separator(self.window).pack(fill=X)

        body = ttk.Frame(self.window, padding=16)
        body.pack(fill=BOTH, expand=True)

        # Device selection
        dev_frame = ttk.Labelframe(body, text="Device", padding=10)
        dev_frame.pack(fill=X, pady=(0, 10))

        dev_row = ttk.Frame(dev_frame)
        dev_row.pack(fill=X)

        self.device_var = ttk.StringVar()
        self.device_combo = ttk.Combobox(dev_row, textvariable=self.device_var, values=self.resources, width=50)
        self.device_combo.pack(side=LEFT, padx=(0, 8))
        ttk.Button(dev_row, text="Refresh", bootstyle="outline", command=self._refresh_devices).pack(side=LEFT, padx=(0, 8))
        ttk.Button(dev_row, text="*IDN?", bootstyle="info-outline", command=self._query_idn).pack(side=LEFT)

        self.idn_label = ttk.Label(dev_frame, text="", font=("Consolas", 9), bootstyle="secondary")
        self.idn_label.pack(anchor=W, pady=(6, 0))

        # SCPI command rows
        cmd_frame = ttk.Labelframe(body, text="Commands", padding=10)
        cmd_frame.pack(fill=X, pady=(0, 10))

        self.cmd_vars = []
        for i in range(4):
            row = ttk.Frame(cmd_frame)
            row.pack(fill=X, pady=3)
            ttk.Label(row, text=f"Cmd {i+1}:", width=6).pack(side=LEFT)
            var = ttk.StringVar()
            self.cmd_vars.append(var)
            ttk.Entry(row, textvariable=var, width=50).pack(side=LEFT, padx=(0, 8))
            ttk.Button(row, text="Send", bootstyle="primary", width=6,
                       command=lambda v=var: self._send(v)).pack(side=LEFT, padx=(0, 4))
            ttk.Button(row, text="Query", bootstyle="info", width=6,
                       command=lambda v=var: self._query(v)).pack(side=LEFT)

        # Response
        resp_frame = ttk.Labelframe(body, text="Response", padding=10)
        resp_frame.pack(fill=BOTH, expand=True)

        self.response_text = ttk.Text(resp_frame, height=10, wrap="word", state=DISABLED, font=("Consolas", 9))
        self.response_text.pack(fill=BOTH, expand=True, pady=(0, 6))

        ttk.Button(resp_frame, text="Clear", bootstyle="warning-outline", command=self._clear_response).pack(anchor=E)

    def _refresh_devices(self):
        self.resources = list(self.rm.list_resources())
        self.device_combo.config(values=self.resources)

    def _query_idn(self):
        resource = self.device_var.get()
        if not resource:
            self.idn_label.config(text="No device selected")
            return
        try:
            with self.rm.open_resource(resource) as inst:
                inst.timeout = 3000
                idn = inst.query("*IDN?").strip()
            self.idn_label.config(text=idn)
        except Exception as e:
            self.idn_label.config(text=f"Error: {e}")

    def _send(self, var):
        cmd = var.get().strip()
        if not cmd:
            self._show_response("No command entered.")
            return
        resource = self.device_var.get()
        if not resource:
            self._show_response("No device selected.")
            return
        try:
            with self.rm.open_resource(resource) as inst:
                inst.timeout = 3000
                if "?" in cmd:
                    resp = inst.query(cmd).strip()
                    self._show_response(f"> {cmd}\n{resp}")
                else:
                    inst.write(cmd)
                    self._show_response(f"> {cmd}\nOK")
        except Exception as e:
            self._show_response(f"> {cmd}\nERROR: {e}")

    def _query(self, var):
        cmd = var.get().strip()
        if not cmd:
            self._show_response("No command entered.")
            return
        if "?" not in cmd:
            cmd += "?"
        resource = self.device_var.get()
        if not resource:
            self._show_response("No device selected.")
            return
        try:
            with self.rm.open_resource(resource) as inst:
                inst.timeout = 3000
                resp = inst.query(cmd).strip()
            self._show_response(f"> {cmd}\n{resp}")
        except Exception as e:
            self._show_response(f"> {cmd}\nERROR: {e}")

    def _show_response(self, text):
        self.response_text.config(state=NORMAL)
        self.response_text.insert("end", text + "\n\n")
        self.response_text.see("end")
        self.response_text.config(state=DISABLED)

    def _clear_response(self):
        self.response_text.config(state=NORMAL)
        self.response_text.delete("1.0", "end")
        self.response_text.config(state=DISABLED)


def _device_config_path():
    if getattr(sys, "frozen", False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, "device_config.txt")


def load_device_config():
    config_path = _device_config_path()
    config = {}
    if not os.path.exists(config_path):
        return config
    with open(config_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                tab_name, model_keyword = line.split("=", 1)
                config[tab_name.strip()] = model_keyword.strip()
    return config


class QuickActionsWindow:
    DEVICES = [
        ("high_power_supply", "N8734A"),
        ("power_supply", "E36311A"),
        ("waveform_generator", "WaveGen"),
        ("oscilloscope", "Scope"),
    ]
    TIMEOUTS = {
        "high_power_supply": 5000,
        "power_supply": 3000,
        "waveform_generator": 3000,
        "oscilloscope": 3000,
    }
    FONT_SIZE    = 7
    BTN_PADDING  = (4, 1)
    PAD_SCALE    = 0.5
    HEIGHT_SCALE = 0.7

    def __init__(self, parent, rm, detected):
        self.parent = parent
        self.rm = rm
        self.detected = detected
        self.instruments = {}
        self.auto_readback_active = False
        self.after_id = None
        self.monitor_history = {"time": [], "voltage": [], "current": []}
        self.monitor_start_time = None
        self.monitor_window = None
        self.fast_poll_active = False

        self.window = ttk.Toplevel(parent)
        self.window.title("Frequent Use")
        self.window.resizable(True, True)
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)

        main = ttk.Frame(self.window, padding=12)
        main.pack(fill=BOTH, expand=True)

        self._build_connection_bar(main)
        body = self._build_scroll_area(main)
        self._build_power_control(body)
        self._build_waveform_section(body)
        self._build_scope_section(body)

        self.status_label = ttk.Label(main, text="", font=("Segoe UI", 9))
        self.status_label.pack(anchor=W, pady=(8, 0))

        self._compact()
        self._fit_window()

    def _build_scroll_area(self, parent):
        area = ttk.Frame(parent)
        area.pack(fill=BOTH, expand=True)
        bg = ttk.Style.get_instance().lookup("TFrame", "background")
        self._canvas = ttk.Canvas(area, highlightthickness=0, background=bg)
        sb = ttk.Scrollbar(area, orient=VERTICAL, command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=sb.set)
        sb.pack(side=RIGHT, fill=Y)
        self._canvas.pack(side=LEFT, fill=BOTH, expand=True)
        self._body = ttk.Frame(self._canvas)
        body_id = self._canvas.create_window((0, 0), window=self._body, anchor=NW)
        self._body.bind("<Configure>", lambda _e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>", lambda e: self._canvas.itemconfigure(body_id, width=e.width))
        self.window.bind("<MouseWheel>", lambda e: self._canvas.yview_scroll(int(-e.delta / 120), "units"))
        return self._body

    def _fit_window(self):
        self.window.update_idletasks()
        body_h = self._body.winfo_reqheight()
        self._canvas.configure(width=self._body.winfo_reqwidth(), height=body_h)
        self.window.update_idletasks()
        full_h = self.window.winfo_reqheight()
        self._canvas.configure(height=body_h - (full_h - int(full_h * self.HEIGHT_SCALE)))
        self.window.update_idletasks()
        self._center_window(self.window, self.window.winfo_reqwidth(), self.window.winfo_reqheight())

    # Post-build shrink so the build methods keep their normal-size layout values.
    # Derived "QA.*" styles inherit from the ttkbootstrap styles without changing other windows.
    def _compact(self):
        style = ttk.Style.get_instance()
        base_font = ("Segoe UI", self.FONT_SIZE)
        style.configure("QA.TEntry", padding=2)
        configured = set()

        def derive(widget, default):
            name = f"QA.{widget.cget('style') or default}"
            if name not in configured:
                opts = {"font": base_font}
                if default == "TButton":
                    opts["padding"] = self.BTN_PADDING
                style.configure(name, **opts)
                configured.add(name)
            widget.configure(style=name)

        def shrink(pad):
            vals = pad if isinstance(pad, (tuple, list)) else str(pad).split()
            return tuple(int(int(str(p)) * self.PAD_SCALE) for p in vals)

        def walk(w):
            cls = w.winfo_class()
            if cls in ("TButton", "TCheckbutton"):
                derive(w, cls)
            elif cls == "TLabel":
                f = w.cget("font")
                if f:
                    a = tkfont.Font(font=f).actual()
                    w.configure(font=(a["family"], max(abs(a["size"]) - 2, self.FONT_SIZE), a["weight"]))
                else:
                    w.configure(font=base_font)
            elif cls == "TEntry":
                w.configure(font=base_font, style="QA.TEntry")
            elif cls == "Labelframe":
                w.configure(font=("Segoe UI", self.FONT_SIZE + 1, "bold"))
            elif cls == "TFrame":
                pad = w.cget("padding")
                if pad:
                    w.configure(padding=shrink(pad))
            if w.winfo_manager() == "pack":
                info = w.pack_info()
                w.pack_configure(padx=shrink(info["padx"]), pady=shrink(info["pady"]))
            elif w.winfo_manager() == "grid":
                info = w.grid_info()
                w.grid_configure(padx=shrink(info["padx"]), pady=shrink(info["pady"]))
            for child in w.winfo_children():
                walk(child)

        walk(self.window)

    def _build_connection_bar(self, parent):
        btn_row = ttk.Frame(parent)
        btn_row.pack(fill=X, pady=(0, 4))
        ttk.Button(btn_row, text="Connect All", bootstyle="success", command=self._connect_all).pack(side=LEFT, padx=(0, 6))
        ttk.Button(btn_row, text="Disconnect All", bootstyle="danger", command=self._disconnect_all).pack(side=LEFT)

        dot_row = ttk.Frame(parent)
        dot_row.pack(fill=X, pady=(0, 8))
        self.status_dots = {}
        for key, label in self.DEVICES:
            dot = ttk.Label(dot_row, text="●", font=("Segoe UI", 10))
            dot.pack(side=LEFT, padx=(0, 2))
            ttk.Label(dot_row, text=label, font=("Segoe UI", 9)).pack(side=LEFT, padx=(0, 12))
            self.status_dots[key] = dot
        self._refresh_status_dots()

    def _connect_all(self):
        connected = []
        failed = []
        for key, label in self.DEVICES:
            if key in self.instruments:
                connected.append(label)
                continue
            if key not in self.detected:
                continue
            resource, _ = self.detected[key]
            try:
                inst = self.rm.open_resource(resource)
                inst.timeout = self.TIMEOUTS.get(key, 3000)
                if key == "high_power_supply":
                    inst.write_termination = "\n"
                    inst.read_termination = "\n"
                inst.query("*IDN?")
                self.instruments[key] = inst
                connected.append(label)
            except Exception:
                failed.append(label)
        self._refresh_status_dots()
        parts = []
        if connected:
            parts.append(f"Connected: {', '.join(connected)}")
        if failed:
            parts.append(f"Failed: {', '.join(failed)}")
        self._set_status("  |  ".join(parts) if parts else "No detected devices to connect")
        self._read_all_settings()

    def _read_all_settings(self):
        self._read_n8734a_settings()
        self._read_e36_settings("1")
        self._read_e36_settings("2")
        self._wg_read_params()
        self._update_readback()

    def _disconnect_all(self):
        for key in list(self.instruments.keys()):
            try:
                self.instruments[key].close()
            except Exception:
                pass
            del self.instruments[key]
        self._refresh_status_dots()
        self._set_status("All disconnected")

    def _refresh_status_dots(self):
        for key, _ in self.DEVICES:
            connected = key in self.instruments
            color = "#00d4aa" if connected else "#ff4757"
            self.status_dots[key].config(foreground=color)

    def _build_power_control(self, parent):
        outer = ttk.LabelFrame(parent, text="Power Control")
        outer.pack(fill=X, pady=(0, 8))
        lf = ttk.Frame(outer, padding=10)
        lf.pack(fill=BOTH, expand=True)

        columns = ttk.Frame(lf)
        columns.pack(fill=X, pady=(0, 6))
        columns.columnconfigure(0, weight=1)

        # ===== N8734A =====
        left = ttk.LabelFrame(columns, text="N8734A")
        left.grid(row=0, column=0, sticky="nsew")
        left_inner = ttk.Frame(left, padding=8)
        left_inner.pack(fill=BOTH, expand=True)

        # Readback
        self.n8734a_meas = ttk.Label(left_inner, text="-- V  /  -- A  /  -- W", font=("Consolas", 10))
        self.n8734a_meas.pack(anchor=W)

        led_row = ttk.Frame(left_inner)
        led_row.pack(fill=X, pady=(2, 6))
        self.n8734a_out = ttk.Label(led_row, text="●", font=("Segoe UI", 12), foreground="gray")
        self.n8734a_out.pack(side=LEFT, padx=(0, 8))
        self.n8734a_cv = ttk.Label(led_row, text="CV", font=("Segoe UI", 9, "bold"), foreground="gray")
        self.n8734a_cv.pack(side=LEFT, padx=(0, 8))
        self.n8734a_cc = ttk.Label(led_row, text="CC", font=("Segoe UI", 9, "bold"), foreground="gray")
        self.n8734a_cc.pack(side=LEFT)
        ttk.Button(led_row, text="Readback", bootstyle="info-outline", command=self._readback_n8734a).pack(side=RIGHT)

        # Set V/I
        set_row1 = ttk.Frame(left_inner)
        set_row1.pack(fill=X, pady=(0, 4))
        ttk.Label(set_row1, text="V:").pack(side=LEFT)
        self.n8734a_volt_var = ttk.StringVar()
        ttk.Entry(set_row1, textvariable=self.n8734a_volt_var, width=8).pack(side=LEFT, padx=(2, 2))
        ttk.Button(set_row1, text="Set", bootstyle="primary", width=4, command=lambda: self._set_value("high_power_supply", "VOLT", self.n8734a_volt_var)).pack(side=LEFT, padx=(0, 8))
        ttk.Label(set_row1, text="I:").pack(side=LEFT)
        self.n8734a_curr_var = ttk.StringVar()
        ttk.Entry(set_row1, textvariable=self.n8734a_curr_var, width=8).pack(side=LEFT, padx=(2, 2))
        ttk.Button(set_row1, text="Set", bootstyle="primary", width=4, command=lambda: self._set_value("high_power_supply", "CURR", self.n8734a_curr_var)).pack(side=LEFT)

        # Read + buttons
        btn_row = ttk.Frame(left_inner)
        btn_row.pack(fill=X, pady=(0, 4))
        ttk.Button(btn_row, text="Read", bootstyle="info-outline", width=5, command=self._read_n8734a_settings).pack(side=LEFT, padx=(0, 4))
        ttk.Button(btn_row, text="ON", bootstyle="success", width=4, command=lambda: self._output_cmd("high_power_supply", "OUTP ON", self.n8734a_out)).pack(side=LEFT, padx=(0, 2))
        ttk.Button(btn_row, text="OFF", bootstyle="danger", width=4, command=lambda: self._output_cmd("high_power_supply", "OUTP OFF", self.n8734a_out)).pack(side=LEFT, padx=(0, 2))
        ttk.Button(btn_row, text="Clr+OFF", bootstyle="warning", width=7, command=self._n8734a_clear_off).pack(side=LEFT, padx=(0, 2))
        ttk.Button(btn_row, text="Graph", bootstyle="primary", width=5, command=self._open_monitor_graph).pack(side=LEFT)

        # ===== E36311A =====
        right = ttk.LabelFrame(columns, text="E36311A")
        right.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        right_inner = ttk.Frame(right, padding=8)
        right_inner.pack(fill=BOTH, expand=True)

        # Ch1
        ch1_hdr = ttk.Frame(right_inner)
        ch1_hdr.pack(fill=X)
        self.e36_ch1_meas = ttk.Label(ch1_hdr, text="Ch1: -- V  /  -- A", font=("Consolas", 10))
        self.e36_ch1_meas.pack(side=LEFT)
        self.e36_ch1_out = ttk.Label(ch1_hdr, text="●", font=("Segoe UI", 12), foreground="gray")
        self.e36_ch1_out.pack(side=RIGHT)

        ch1_set = ttk.Frame(right_inner)
        ch1_set.pack(fill=X, pady=(2, 2))
        ttk.Label(ch1_set, text="V:").pack(side=LEFT)
        self.e36_ch1_volt_var = ttk.StringVar()
        ttk.Entry(ch1_set, textvariable=self.e36_ch1_volt_var, width=7).pack(side=LEFT, padx=(2, 2))
        ttk.Label(ch1_set, text="I:").pack(side=LEFT)
        self.e36_ch1_curr_var = ttk.StringVar()
        ttk.Entry(ch1_set, textvariable=self.e36_ch1_curr_var, width=7).pack(side=LEFT, padx=(2, 2))

        ch1_btn = ttk.Frame(right_inner)
        ch1_btn.pack(fill=X, pady=(0, 6))
        ttk.Button(ch1_btn, text="Set", bootstyle="primary", width=4, command=self._set_e36_ch1).pack(side=LEFT, padx=(0, 2))
        ttk.Button(ch1_btn, text="Read", bootstyle="info-outline", width=5, command=lambda: self._read_e36_settings("1")).pack(side=LEFT, padx=(0, 4))
        ttk.Button(ch1_btn, text="ON", bootstyle="success", width=4, command=lambda: self._output_cmd("power_supply", "OUTP ON, (@1)", self.e36_ch1_out, "(@1)")).pack(side=LEFT, padx=(0, 2))
        ttk.Button(ch1_btn, text="OFF", bootstyle="danger", width=4, command=lambda: self._output_cmd("power_supply", "OUTP OFF, (@1)", self.e36_ch1_out, "(@1)")).pack(side=LEFT)

        ttk.Separator(right_inner).pack(fill=X, pady=(0, 6))

        # Ch2
        ch2_hdr = ttk.Frame(right_inner)
        ch2_hdr.pack(fill=X)
        self.e36_ch2_meas = ttk.Label(ch2_hdr, text="Ch2: -- V  /  -- A", font=("Consolas", 10))
        self.e36_ch2_meas.pack(side=LEFT)
        self.e36_ch2_out = ttk.Label(ch2_hdr, text="●", font=("Segoe UI", 12), foreground="gray")
        self.e36_ch2_out.pack(side=RIGHT)

        ch2_set = ttk.Frame(right_inner)
        ch2_set.pack(fill=X, pady=(2, 2))
        ttk.Label(ch2_set, text="V:").pack(side=LEFT)
        self.e36_ch2_volt_var = ttk.StringVar()
        ttk.Entry(ch2_set, textvariable=self.e36_ch2_volt_var, width=7).pack(side=LEFT, padx=(2, 2))
        ttk.Label(ch2_set, text="I:").pack(side=LEFT)
        self.e36_ch2_curr_var = ttk.StringVar()
        ttk.Entry(ch2_set, textvariable=self.e36_ch2_curr_var, width=7).pack(side=LEFT, padx=(2, 2))

        ch2_btn = ttk.Frame(right_inner)
        ch2_btn.pack(fill=X)
        ttk.Button(ch2_btn, text="Set", bootstyle="primary", width=4, command=self._set_e36_ch2).pack(side=LEFT, padx=(0, 2))
        ttk.Button(ch2_btn, text="Read", bootstyle="info-outline", width=5, command=lambda: self._read_e36_settings("2")).pack(side=LEFT, padx=(0, 4))
        ttk.Button(ch2_btn, text="ON", bootstyle="success", width=4, command=lambda: self._output_cmd("power_supply", "OUTP ON, (@2)", self.e36_ch2_out, "(@2)")).pack(side=LEFT, padx=(0, 2))
        ttk.Button(ch2_btn, text="OFF", bootstyle="danger", width=4, command=lambda: self._output_cmd("power_supply", "OUTP OFF, (@2)", self.e36_ch2_out, "(@2)")).pack(side=LEFT)

        e36_row = ttk.Frame(right_inner)
        e36_row.pack(fill=X, pady=(6, 0))
        ttk.Button(e36_row, text="Readback", bootstyle="info-outline", command=self._readback_e36).pack(side=LEFT)

        # --- Readback controls ---
        read_row = ttk.Frame(lf)
        read_row.pack(fill=X, pady=(6, 0))
        ttk.Button(read_row, text="Read All Now", bootstyle="info-outline", command=self._update_readback).pack(side=LEFT)

        ctrl = ttk.Frame(lf)
        ctrl.pack(fill=X, pady=(6, 0))
        self.auto_var = ttk.BooleanVar(value=False)
        ttk.Checkbutton(ctrl, text="Auto Readback", variable=self.auto_var, bootstyle="round-toggle", command=self._toggle_auto_readback).pack(side=LEFT)
        ttk.Label(ctrl, text="Interval (ms):").pack(side=LEFT, padx=(12, 4))
        self.interval_var = ttk.StringVar(value="1000")
        ttk.Entry(ctrl, textvariable=self.interval_var, width=6).pack(side=LEFT)

    def _build_waveform_section(self, parent):
        outer = ttk.LabelFrame(parent, text="Waveform Generator")
        outer.pack(fill=X, pady=(0, 8))
        lf = ttk.Frame(outer, padding=10)
        lf.pack(fill=BOTH, expand=True)

        row = ttk.Frame(lf)
        row.pack(fill=X, pady=(0, 4))
        ttk.Label(row, text="33500B", font=("Segoe UI", 10, "bold")).pack(side=LEFT, padx=(0, 8))
        self.wg_out = ttk.Label(row, text="●", font=("Segoe UI", 12), foreground="gray")
        self.wg_out.pack(side=LEFT, padx=(0, 8))
        ttk.Button(row, text="ON", bootstyle="success", width=5, command=lambda: self._output_cmd("waveform_generator", "OUTP ON", self.wg_out)).pack(side=LEFT, padx=(0, 4))
        ttk.Button(row, text="OFF", bootstyle="danger", width=5, command=lambda: self._output_cmd("waveform_generator", "OUTP OFF", self.wg_out)).pack(side=LEFT, padx=(0, 8))
        ttk.Label(row, text="Delay(s):").pack(side=LEFT, padx=(0, 2))
        self.wg_delay_var = ttk.StringVar(value="0.5")
        ttk.Entry(row, textvariable=self.wg_delay_var, width=6).pack(side=LEFT, padx=(0, 4))
        ttk.Button(row, text="Toggle", bootstyle="warning", width=7, command=self._wg_toggle).pack(side=LEFT)

        params = ttk.Frame(lf)
        params.pack(fill=X, pady=(0, 4))
        self.wg_high_var = ttk.StringVar()
        self.wg_low_var  = ttk.StringVar()
        self.wg_dc_var   = ttk.StringVar()
        self.wg_freq_var = ttk.StringVar()
        self.wg_rise_var = ttk.StringVar()
        self.wg_fall_var = ttk.StringVar()
        layout = [
            [("HIGH(mV):", self.wg_high_var, self._wg_send_high), ("LOW(mV):", self.wg_low_var, self._wg_send_low)],
            [("DC(%):", self.wg_dc_var, self._wg_send_dc), ("Freq(kHz):", self.wg_freq_var, self._wg_send_freq)],
            [("Rise(ns):", self.wg_rise_var, self._wg_send_rise), ("Fall(ns):", self.wg_fall_var, self._wg_send_fall)],
        ]
        for r, pair in enumerate(layout):
            for c, (text, var, cmd) in enumerate(pair):
                col = c * 3
                ttk.Label(params, text=text).grid(row=r, column=col, sticky=W, padx=(8 if c else 0, 2), pady=(0, 4))
                ttk.Entry(params, textvariable=var, width=8).grid(row=r, column=col + 1, padx=(0, 4), pady=(0, 4))
                ttk.Button(params, text="Set", bootstyle="primary", width=4, command=cmd).grid(row=r, column=col + 2, pady=(0, 4))

        calc_row = ttk.Frame(lf)
        calc_row.pack(fill=X, pady=(0, 2))
        ttk.Label(calc_row, text="V(mV):").pack(side=LEFT)
        self.wg_calc_v_var = ttk.StringVar()
        ttk.Entry(calc_row, textvariable=self.wg_calc_v_var, width=8).pack(side=LEFT, padx=(2, 4))
        ttk.Label(calc_row, text="Ratio(mV/A):").pack(side=LEFT)
        self.wg_calc_ratio_var = ttk.StringVar(value="2.5")
        ttk.Entry(calc_row, textvariable=self.wg_calc_ratio_var, width=6).pack(side=LEFT, padx=(2, 4))
        ttk.Button(calc_row, text="Calc Load", bootstyle="info", width=9, command=self._wg_calc_load).pack(side=LEFT, padx=(0, 4))
        self.wg_calc_result = ttk.Label(calc_row, text="", font=("Consolas", 9), bootstyle="success")
        self.wg_calc_result.pack(side=LEFT, padx=(4, 0))

        sr_row = ttk.Frame(lf)
        sr_row.pack(fill=X, pady=(4, 2))
        ttk.Label(sr_row, text="SR(kA/us):").pack(side=LEFT)
        self.wg_calc_sr_var = ttk.StringVar()
        ttk.Entry(sr_row, textvariable=self.wg_calc_sr_var, width=6).pack(side=LEFT, padx=(2, 4))
        ttk.Button(sr_row, text="Calc Rise/Fall", bootstyle="info", width=12, command=self._wg_calc_edge).pack(side=LEFT, padx=(0, 4))
        ttk.Button(sr_row, text="Read", bootstyle="info-outline", width=5, command=self._readback_wg).pack(side=LEFT, padx=(0, 4))
        self.wg_calc_edge_result = ttk.Label(sr_row, text="", font=("Consolas", 9), bootstyle="success")
        self.wg_calc_edge_result.pack(side=LEFT, padx=(4, 0))

    def _build_scope_section(self, parent):
        outer = ttk.LabelFrame(parent, text="Oscilloscope")
        outer.pack(fill=X, pady=(0, 8))
        lf = ttk.Frame(outer, padding=10)
        lf.pack(fill=BOTH, expand=True)

        # Acquisition row
        row = ttk.Frame(lf)
        row.pack(fill=X, pady=(0, 4))
        ttk.Label(row, text="MDO34", font=("Segoe UI", 10, "bold"), width=10).pack(side=LEFT)
        ttk.Button(row, text="RUN", bootstyle="success", width=6, command=lambda: self._scpi_write("oscilloscope", "ACQuire:STATE RUN")).pack(side=LEFT, padx=(0, 4))
        ttk.Button(row, text="STOP", bootstyle="danger", width=6, command=lambda: self._scpi_write("oscilloscope", "ACQuire:STATE STOP")).pack(side=LEFT, padx=(0, 4))
        ttk.Button(row, text="SINGLE", bootstyle="warning", width=7, command=lambda: self._scpi_write("oscilloscope", "ACQuire:STOPAfter SEQuence")).pack(side=LEFT, padx=(0, 4))
        ttk.Button(row, text="Sequence", bootstyle="info", width=8, command=lambda: self._scpi_write("oscilloscope", "ACQuire:STOPAfter RUNSTop")).pack(side=LEFT)

        # Trigger row
        trig_row = ttk.Frame(lf)
        trig_row.pack(fill=X, pady=(0, 4))
        ttk.Label(trig_row, text="", width=10).pack(side=LEFT)
        ttk.Label(trig_row, text="Trigger:").pack(side=LEFT, padx=(0, 4))
        ttk.Button(trig_row, text="Auto", bootstyle="primary", width=7, command=lambda: self._scpi_write("oscilloscope", "TRIG:A:MODE AUTO")).pack(side=LEFT, padx=(0, 4))
        ttk.Button(trig_row, text="Normal", bootstyle="primary", width=7, command=lambda: self._scpi_write("oscilloscope", "TRIG:A:MODE NORM")).pack(side=LEFT)

        # Remote Access row
        remote_row = ttk.Frame(lf)
        remote_row.pack(fill=X)
        ttk.Label(remote_row, text="", width=10).pack(side=LEFT)
        ttk.Button(remote_row, text="Get IP", bootstyle="info-outline", width=6, command=self._scope_get_ip).pack(side=LEFT, padx=(0, 4))
        self.scope_ip_label = ttk.Label(remote_row, text="---", font=("Consolas", 10))
        self.scope_ip_label.pack(side=LEFT, padx=(0, 8))
        ttk.Button(remote_row, text="Open Browser", bootstyle="primary", command=self._scope_open_browser).pack(side=LEFT)

        setup_row = ttk.Frame(lf)
        setup_row.pack(fill=X, pady=(4, 0))
        ttk.Label(setup_row, text="", width=10).pack(side=LEFT)
        ttk.Button(setup_row, text="Load Settings from PC", bootstyle="info", command=self._scope_load_settings).pack(side=LEFT, padx=(0, 4))
        ttk.Button(setup_row, text="Arrange 16 PWM", bootstyle="warning-outline", command=self._scope_arrange_16pwm).pack(side=LEFT)

    def _scope_arrange_16pwm(self):
        inst = self.instruments.get("oscilloscope")
        if not inst:
            self._set_status("oscilloscope: not connected")
            return
        self._set_status("Arranging D0-D15 as PWM_1-PWM_16...")

        def _do():
            try:
                msg = arrange_16pwm(inst)
            except Exception as e:
                msg = f"Arrange 16 PWM error: {e}"
            self.window.after(0, lambda: self._set_status(msg))

        threading.Thread(target=_do, daemon=True).start()

    def _scope_load_settings(self):
        import csv
        from tkinter import filedialog

        inst = self.instruments.get("oscilloscope")
        if not inst:
            self._set_status("oscilloscope: not connected")
            return
        filepath = filedialog.askopenfilename(
            parent=self.window,
            title="Load Scope Settings",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not filepath:
            return
        try:
            with open(filepath, "r") as f:
                settings = order_scope_settings([(row["command"], row["value"]) for row in csv.DictReader(f)])
        except Exception as e:
            self._set_status(f"Scope load: {e}")
            return

        self._set_status(f"Applying {len(settings)} scope settings...")

        def _do_load():
            import time
            ok = 0
            errors = 0
            for cmd, value in settings:
                full_cmd = f'{cmd} "{value.strip(chr(34))}"' if "LABel" in cmd else f"{cmd} {value}"
                try:
                    inst.write(full_cmd)
                    ok += 1
                except Exception:
                    errors += 1
                time.sleep(0.05)
            msg = f"Applied {ok} scope settings from {os.path.basename(filepath)}"
            if errors:
                msg += f" ({errors} errors)"
            self.window.after(0, lambda: self._set_status(msg))

        threading.Thread(target=_do_load, daemon=True).start()

    def _set_led(self, device_key, query, led):
        inst = self.instruments.get(device_key)
        try:
            on = inst is not None and inst.query(query).strip() == "1"
        except Exception:
            on = False
        led.config(foreground="#00d4aa" if on else "gray")

    def _readback_n8734a(self):
        self._refresh_status_dots()
        self._read_n8734a()
        self._set_led("high_power_supply", "OUTP?", self.n8734a_out)

    def _readback_e36(self):
        self._refresh_status_dots()
        self._read_e36311a()
        self._set_led("power_supply", "OUTP? (@1)", self.e36_ch1_out)
        self._set_led("power_supply", "OUTP? (@2)", self.e36_ch2_out)

    def _readback_wg(self):
        self._refresh_status_dots()
        self._wg_read_params()
        self._set_led("waveform_generator", "OUTP?", self.wg_out)

    # --- SCPI helpers ---

    def _scpi_write(self, device_key, cmd):
        inst = self.instruments.get(device_key)
        if not inst:
            self._set_status(f"{device_key}: not connected")
            return
        try:
            inst.write(cmd)
            self._set_status("")
        except Exception as e:
            self._set_status(f"{device_key}: {e}")

    def _scpi_query(self, device_key, cmd):
        inst = self.instruments.get(device_key)
        if not inst:
            return None
        return inst.query(cmd).strip()

    def _output_cmd(self, device_key, cmd, led_label, channel_suffix=None):
        self._scpi_write(device_key, cmd)
        inst = self.instruments.get(device_key)
        if not inst:
            return
        try:
            q = f"OUTP? {channel_suffix}" if channel_suffix else "OUTP?"
            out = inst.query(q).strip()
            led_label.config(foreground="#00d4aa" if out == "1" else "gray")
        except Exception:
            led_label.config(foreground="gray")

    def _n8734a_clear_off(self):
        inst = self.instruments.get("high_power_supply")
        if not inst:
            self._set_status("high_power_supply: not connected")
            return
        try:
            inst.write("OUTP:PROT:CLE")
            inst.write("OUTP OFF")
            self.n8734a_out.config(foreground="gray")
            self._set_status("")
        except Exception as e:
            self._set_status(f"N8734A: {e}")

    def _wg_toggle(self):
        inst = self.instruments.get("waveform_generator")
        if not inst:
            self._set_status("waveform_generator: not connected")
            return
        try:
            delay = float(self.wg_delay_var.get())
        except ValueError:
            self._set_status("Invalid delay value")
            return
        def _toggle():
            import time
            try:
                inst.write("OUTP ON")
                time.sleep(delay)
                inst.write("OUTP OFF")
                self.window.after(0, lambda: self._set_status("WG toggle complete"))
            except Exception as e:
                self.window.after(0, lambda msg=f"WG: {e}": self._set_status(msg))
        threading.Thread(target=_toggle, daemon=True).start()

    def _wg_send_high(self):
        inst = self.instruments.get("waveform_generator")
        if not inst:
            self._set_status("waveform_generator: not connected")
            return
        val = self.wg_high_var.get()
        if not val:
            return
        try:
            inst.write(f":VOLT:HIGH {val} mV")
            self.wg_calc_v_var.set(val)
            self._set_status("")
        except Exception as e:
            self._set_status(f"WG: {e}")

    def _wg_send_dc(self):
        inst = self.instruments.get("waveform_generator")
        if not inst:
            self._set_status("waveform_generator: not connected")
            return
        val = self.wg_dc_var.get()
        if not val:
            return
        try:
            inst.write(f"FUNC:PULS:DCYC {val}")
            self._set_status("")
        except Exception as e:
            self._set_status(f"WG: {e}")

    def _wg_send_freq(self):
        inst = self.instruments.get("waveform_generator")
        if not inst:
            self._set_status("waveform_generator: not connected")
            return
        val = self.wg_freq_var.get()
        if not val:
            return
        try:
            inst.write(f"FREQ {val} E3")
            self._set_status("")
        except Exception as e:
            self._set_status(f"WG: {e}")

    def _wg_write_value(self, var, cmd_fmt):
        inst = self.instruments.get("waveform_generator")
        if not inst:
            self._set_status("waveform_generator: not connected")
            return
        val = var.get()
        if not val:
            return
        try:
            inst.write(cmd_fmt.format(val))
            self._set_status("")
        except Exception as e:
            self._set_status(f"WG: {e}")

    def _wg_send_low(self):
        self._wg_write_value(self.wg_low_var, ":VOLT:LOW {} mV")

    def _wg_send_rise(self):
        self._wg_write_value(self.wg_rise_var, "FUNC:PULS:TRAN:LEAD {} E-9")

    def _wg_send_fall(self):
        self._wg_write_value(self.wg_fall_var, "FUNC:PULS:TRAN:TRA {} E-9")

    def _wg_read_params(self):
        inst = self.instruments.get("waveform_generator")
        if not inst:
            self._set_status("waveform_generator: not connected")
            return
        try:
            high = float(inst.query("VOLT:HIGH?").strip())
            self.wg_high_var.set(f"{high * 1000:.2f}")
            dc = float(inst.query("FUNC:PULS:DCYC?").strip())
            self.wg_dc_var.set(f"{dc:.2f}")
            freq = float(inst.query("FREQ?").strip())
            self.wg_freq_var.set(f"{freq / 1000:.4f}")
            low = float(inst.query("VOLT:LOW?").strip())
            self.wg_low_var.set(f"{low * 1000:.2f}")
            rise = float(inst.query("FUNC:PULS:TRAN:LEAD?").strip())
            self.wg_rise_var.set(f"{rise * 1e9:.1f}")
            fall = float(inst.query("FUNC:PULS:TRAN:TRA?").strip())
            self.wg_fall_var.set(f"{fall * 1e9:.1f}")
            self._set_status("")
        except Exception as e:
            self._set_status(f"WG read: {e}")

    def _wg_calc_edge(self):
        try:
            dc, freq = self.wg_dc_var.get(), self.wg_freq_var.get()
            pw_us = float(dc) / 100 / float(freq) * 1000 if dc and freq and float(freq) else None
            text, edge_ns = calc_edge_time(
                float(self.wg_high_var.get()), float(self.wg_low_var.get()),
                float(self.wg_calc_ratio_var.get()), float(self.wg_calc_sr_var.get()),
                pw_us,
            )
        except ValueError:
            self._set_status("Invalid HIGH/LOW/Ratio/SR (ratio, SR != 0)")
            return
        self.wg_rise_var.set(f"{edge_ns:.1f}")
        self.wg_fall_var.set(f"{edge_ns:.1f}")
        self.wg_calc_edge_result.config(text=text)
        self._set_status("")

    def _wg_calc_load(self):
        try:
            voltage = float(self.wg_calc_v_var.get())
            ratio = float(self.wg_calc_ratio_var.get())
            if ratio == 0:
                raise ValueError
            load_current = voltage / ratio
            self.wg_calc_result.config(text=f"= {load_current:.6f} A")
        except ValueError:
            self.wg_calc_result.config(text="Invalid input")

    def _scope_get_ip(self):
        inst = self.instruments.get("oscilloscope")
        if not inst:
            self._set_status("oscilloscope: not connected")
            return
        try:
            ip = inst.query("ETHERnet:IPADDress?").strip().strip('"')
            self.scope_ip_label.config(text=ip)
            self._set_status(f"Scope IP: {ip}")
        except Exception as e:
            self.scope_ip_label.config(text="Error")
            self._set_status(f"Scope: {e}")

    def _scope_open_browser(self):
        import webbrowser
        ip = self.scope_ip_label.cget("text")
        if ip and ip not in ("---", "Error"):
            webbrowser.open(f"http://{ip}")
        else:
            self._set_status("Get IP first")

    def _set_value(self, device_key, scpi_cmd, var, channel=None):
        inst = self.instruments.get(device_key)
        if not inst:
            self._set_status(f"{device_key}: not connected")
            return
        try:
            val = float(var.get())
        except ValueError:
            self._set_status("Invalid value")
            return
        try:
            if channel:
                inst.write(f"{scpi_cmd} {val}, (@{channel})")
            else:
                inst.write(f"{scpi_cmd} {val}")
            self._set_status("")
        except Exception as e:
            self._set_status(f"{device_key}: {e}")

    def _read_n8734a_settings(self):
        inst = self.instruments.get("high_power_supply")
        if not inst:
            self._set_status("high_power_supply: not connected")
            return
        try:
            v = float(inst.query("VOLT?").strip())
            i = float(inst.query("CURR?").strip())
            self.n8734a_volt_var.set(f"{v:.3f}")
            self.n8734a_curr_var.set(f"{i:.3f}")
            self._set_status("")
        except Exception as e:
            self._set_status(f"N8734A read: {e}")

    def _read_e36_settings(self, channel):
        inst = self.instruments.get("power_supply")
        if not inst:
            self._set_status("power_supply: not connected")
            return
        try:
            v = float(inst.query(f"SOUR:VOLT:LEV? (@{channel})").strip())
            i = float(inst.query(f"SOUR:CURR:LEV? (@{channel})").strip())
            if channel == "1":
                self.e36_ch1_volt_var.set(f"{v:.4f}")
                self.e36_ch1_curr_var.set(f"{i:.4f}")
            elif channel == "2":
                self.e36_ch2_volt_var.set(f"{v:.4f}")
                self.e36_ch2_curr_var.set(f"{i:.4f}")
            self._set_status("")
        except Exception as e:
            self._set_status(f"E36311A read: {e}")

    def _set_e36_ch1(self):
        self._set_value("power_supply", "SOUR:VOLT:LEV", self.e36_ch1_volt_var, "1")
        self._set_value("power_supply", "SOUR:CURR:LEV", self.e36_ch1_curr_var, "1")

    def _set_e36_ch2(self):
        self._set_value("power_supply", "SOUR:VOLT:LEV", self.e36_ch2_volt_var, "2")
        self._set_value("power_supply", "SOUR:CURR:LEV", self.e36_ch2_curr_var, "2")

    # --- Readback ---

    def _update_readback(self):
        self._refresh_status_dots()
        self._read_n8734a()
        self._read_e36311a()
        self._update_output_leds()

    def _update_output_leds(self):
        # N8734A
        inst = self.instruments.get("high_power_supply")
        if inst:
            try:
                out = inst.query("OUTP?").strip()
                self.n8734a_out.config(foreground="#00d4aa" if out == "1" else "gray")
            except Exception:
                self.n8734a_out.config(foreground="gray")
        else:
            self.n8734a_out.config(foreground="gray")

        # E36311A
        inst = self.instruments.get("power_supply")
        if inst:
            try:
                ch1 = inst.query("OUTP? (@1)").strip()
                self.e36_ch1_out.config(foreground="#00d4aa" if ch1 == "1" else "gray")
            except Exception:
                self.e36_ch1_out.config(foreground="gray")
            try:
                ch2 = inst.query("OUTP? (@2)").strip()
                self.e36_ch2_out.config(foreground="#00d4aa" if ch2 == "1" else "gray")
            except Exception:
                self.e36_ch2_out.config(foreground="gray")
        else:
            self.e36_ch1_out.config(foreground="gray")
            self.e36_ch2_out.config(foreground="gray")

        # Waveform Generator
        inst = self.instruments.get("waveform_generator")
        if inst:
            try:
                out = inst.query("OUTP?").strip()
                self.wg_out.config(foreground="#00d4aa" if out == "1" else "gray")
            except Exception:
                self.wg_out.config(foreground="gray")
        else:
            self.wg_out.config(foreground="gray")

    def _read_n8734a(self):
        inst = self.instruments.get("high_power_supply")
        if not inst:
            self.n8734a_meas.config(text="-- V  /  -- A  /  -- W")
            self.n8734a_cv.config(foreground="gray")
            self.n8734a_cc.config(foreground="gray")
            return
        try:
            v = float(inst.query("MEAS:VOLT?").strip())
            i = float(inst.query("MEAS:CURR?").strip())
            self.n8734a_meas.config(text=f"{v:.3f} V  /  {i:.3f} A  /  {v*i:.3f} W")
            status = int(inst.query("STAT:OPER:COND?").strip())
            self.n8734a_cv.config(foreground="#00d4aa" if status & 256 else "gray")
            self.n8734a_cc.config(foreground="#ff9f43" if status & 1024 else "gray")
            if not self.fast_poll_active:
                self._append_monitor_point(v, i)
        except Exception:
            self.n8734a_meas.config(text="-- V  /  -- A  /  -- W")
            self.n8734a_cv.config(foreground="gray")
            self.n8734a_cc.config(foreground="gray")

    def _append_monitor_point(self, v, i):
        import time
        if self.monitor_start_time is None:
            self.monitor_start_time = time.time()
        elapsed = time.time() - self.monitor_start_time
        self.monitor_history["time"].append(elapsed)
        self.monitor_history["voltage"].append(v)
        self.monitor_history["current"].append(i)
        max_pts = 600
        if len(self.monitor_history["time"]) > max_pts:
            self.monitor_history["time"] = self.monitor_history["time"][-max_pts:]
            self.monitor_history["voltage"] = self.monitor_history["voltage"][-max_pts:]
            self.monitor_history["current"] = self.monitor_history["current"][-max_pts:]

    def _open_monitor_graph(self):
        if self.monitor_window and self.monitor_window.is_alive():
            self.monitor_window.window.lift()
            return
        inst = self.instruments.get("high_power_supply")
        if not inst:
            self._set_status("high_power_supply: not connected")
            return
        self.monitor_window = MonitorGraphWindow(self.window, self.monitor_history, inst)
        self.fast_poll_active = True
        threading.Thread(target=self._fast_poll_loop, daemon=True).start()

    def _fast_poll_loop(self):
        import time
        inst = self.instruments.get("high_power_supply")
        while self.fast_poll_active and inst:
            try:
                v = float(inst.query("MEAS:VOLT?").strip())
                i = float(inst.query("MEAS:CURR?").strip())
                self._append_monitor_point(v, i)
                self.window.after(0, self._fast_poll_ui_update, v, i)
            except Exception:
                pass
            time.sleep(0.1)
            if not (self.monitor_window and self.monitor_window.is_alive()):
                self.fast_poll_active = False
                break

    def _fast_poll_ui_update(self, v, i):
        self.n8734a_meas.config(text=f"{v:.3f} V  /  {i:.3f} A  /  {v*i:.3f} W")
        if self.monitor_window and self.monitor_window.is_alive():
            self.monitor_window.update_plot()

    def _read_e36311a(self):
        inst = self.instruments.get("power_supply")
        if not inst:
            self.e36_ch1_meas.config(text="Ch1: -- V  /  -- A")
            self.e36_ch2_meas.config(text="Ch2: -- V  /  -- A")
            return
        try:
            v1 = float(inst.query("MEAS:VOLT? (@1)").strip())
            i1 = float(inst.query("MEAS:CURR? (@1)").strip())
            v2 = float(inst.query("MEAS:VOLT? (@2)").strip())
            i2 = float(inst.query("MEAS:CURR? (@2)").strip())
            self.e36_ch1_meas.config(text=f"Ch1: {v1:.4f} V  /  {i1:.4f} A")
            self.e36_ch2_meas.config(text=f"Ch2: {v2:.4f} V  /  {i2:.4f} A")
        except Exception:
            self.e36_ch1_meas.config(text="Ch1: -- V  /  -- A")
            self.e36_ch2_meas.config(text="Ch2: -- V  /  -- A")

    def _toggle_auto_readback(self):
        if self.auto_var.get():
            self.auto_readback_active = True
            self._auto_readback_loop()
        else:
            self.auto_readback_active = False
            if self.after_id:
                self.window.after_cancel(self.after_id)
                self.after_id = None

    def _auto_readback_loop(self):
        if not self.auto_readback_active:
            return
        self._update_readback()
        try:
            interval = int(self.interval_var.get())
            if interval < 100:
                interval = 100
        except (ValueError, TypeError):
            interval = 1000
        self.after_id = self.window.after(interval, self._auto_readback_loop)

    def _set_status(self, text):
        self.status_label.config(text=text)

    def _on_close(self):
        self.auto_readback_active = False
        self.fast_poll_active = False
        if self.after_id:
            self.window.after_cancel(self.after_id)
            self.after_id = None
        if self.monitor_window and self.monitor_window.is_alive():
            self.monitor_window.window.destroy()
        for key in list(self.instruments.keys()):
            try:
                self.instruments[key].close()
            except Exception:
                pass
        self.instruments.clear()
        self.window.destroy()

    def _center_window(self, win, w, h):
        x = (win.winfo_screenwidth() - w) // 2
        y = (win.winfo_screenheight() - h) // 2
        win.geometry(f"{w}x{h}+{x}+{y}")


class InstrumentGUIv2:
    def __init__(self):
        self.root = ttk.Window(
            title="ADTH Bench Control v2",
            themename="darkly",
            size=(1100, 750),
            resizable=(True, True),
        )
        self.root.withdraw()

        self.rm = pyvisa.ResourceManager()
        self.resources = self.rm.list_resources()
        self.config = load_device_config()
        self.detected = {}
        self.open_windows = {}
        self.quick_actions_window = None

        self.root.after(100, self._run_detection)

    def _run_detection(self):
        if not self.config:
            Messagebox.show_info(
                "No device_config.txt found or file is empty.\n"
                "Place device_config.txt next to the application.",
                title="Configuration Missing",
                parent=self.root,
            )
            self._show_main()
            return

        if not self.resources:
            Messagebox.show_warning(
                "No VISA resources found.\nCheck instrument connections.",
                title="No Instruments",
                parent=self.root,
            )
            self._show_summary()
            return

        progress = DetectProgressWindow(self.root, self.resources, self.config)
        progress.start_scan()
        progress.window.wait_window()
        self.detected = progress.detected
        self._show_summary()

    def _show_summary(self):
        summary = DetectSummaryWindow(
            self.root, self.config, self.detected,
            rm=self.rm,
            on_open_device=self._open_device_window,
            on_open_scpi=self._open_scpi_window,
            on_rescan=self._rescan_devices,
            on_open_quick_actions=self._open_quick_actions,
        )
        summary.wait()

    def _rescan_devices(self):
        self.resources = self.rm.list_resources()
        if not self.resources:
            Messagebox.show_warning(
                "No VISA resources found.\nCheck instrument connections.",
                title="No Instruments",
                parent=self.root,
            )
            self.detected = {}
            return self.detected
        progress = DetectProgressWindow(self.root, self.resources, self.config)
        progress.start_scan()
        progress.window.wait_window()
        self.detected = progress.detected
        return self.detected

    def _open_scpi_window(self):
        SCPILowLevelWindow(self.root, self.rm)

    def _open_device_window(self, tab_name):
        if tab_name in self.detected:
            resource, idn = self.detected[tab_name]
        else:
            resource, idn = "", ""
        win = None
        if tab_name == "high_power_supply":
            win = HighPowerSupplyWindow(self.root, self.rm, resource, idn)
        elif tab_name == "power_supply":
            win = PowerSupplyWindow(self.root, self.rm, resource, idn)
        elif tab_name == "waveform_generator":
            win = WaveformGeneratorWindow(self.root, self.rm, resource, idn)
        elif tab_name == "oscilloscope":
            win = OscilloscopeWindow(self.root, self.rm, resource, idn)
        elif tab_name == "electronic_load":
            win = ElectronicLoadWindow(self.root, self.rm, resource, idn)
        elif tab_name == "data_acquisition":
            win = DAQWindow(self.root, self.rm, resource, idn)
        if win:
            self.open_windows[tab_name] = win
            if resource:
                win._connect()

    def _open_quick_actions(self):
        if self.quick_actions_window:
            try:
                self.quick_actions_window.window.lift()
                return
            except Exception:
                self.quick_actions_window = None
        self.quick_actions_window = QuickActionsWindow(self.root, self.rm, self.detected)

    def _show_main(self):
        self.root.deiconify()
        self._center_window(self.root, 1100, 750)
        btn_frame = ttk.Frame(self.root, padding=20)
        btn_frame.pack(fill=X)
        ttk.Button(
            btn_frame, text="Frequent Use",
            bootstyle="success", command=self._open_quick_actions
        ).pack(side=LEFT)

    def _center_window(self, win, w, h):
        x = (win.winfo_screenwidth() - w) // 2
        y = (win.winfo_screenheight() - h) // 2
        win.geometry(f"{w}x{h}+{x}+{y}")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = InstrumentGUIv2()
    app.run()
