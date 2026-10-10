import csv
import os
import subprocess
import time
import tkinter as tk
from tkinter import ttk
import serial
import serial.tools.list_ports

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "channels.csv")

PINS = list(range(2, 10))
MAX_BOARDS = 4


class BoardPanel:
    def __init__(self, parent, addr, row, col, log_func=None, interlock_mode_var=None, interlock_delay_entry=None):
        self.addr = addr
        self.ser = None
        self.log_func = log_func
        self.interlock_mode_var = interlock_mode_var
        self.interlock_delay_entry = interlock_delay_entry
        self.frame = ttk.LabelFrame(parent, text=f"Board {addr}", padding=5)
        self.frame.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")

        self.port_label = ttk.Label(self.frame, text="--")
        self.port_label.grid(row=0, column=0, columnspan=7, sticky="w")

        self.led = {}
        self.btn_on = {}
        self.btn_off = {}
        self.btn_toggle = {}
        self.delay_entry = {}
        self.desc_entry = {}
        self.interlock_entry = {}
        self.pin_state = {pin: False for pin in PINS}

        ttk.Label(self.frame, text="").grid(row=0, column=0, columnspan=5)
        ttk.Label(self.frame, text="ms").grid(row=0, column=5, sticky="e")
        ttk.Label(self.frame, text="Interlock").grid(row=0, column=7, sticky="w")

        for i, pin in enumerate(PINS):
            r = i + 1
            ttk.Label(self.frame, text=f"D{pin}").grid(row=r, column=0, padx=2, pady=1)
            led = tk.Canvas(self.frame, width=14, height=14, highlightthickness=0)
            led.grid(row=r, column=1, padx=2, pady=1)
            led.create_oval(1, 1, 13, 13, fill="red", outline="darkred", tags="led")
            self.led[pin] = led

            btn_on = ttk.Button(self.frame, text="ON", width=5,
                                command=lambda p=pin: self.relay_on(p), state="disabled")
            btn_on.grid(row=r, column=2, padx=2, pady=1)
            btn_off = ttk.Button(self.frame, text="OFF", width=5,
                                 command=lambda p=pin: self.relay_off(p), state="disabled")
            btn_off.grid(row=r, column=3, padx=2, pady=1)
            btn_toggle = ttk.Button(self.frame, text="Toggle", width=5,
                                    command=lambda p=pin: self.relay_toggle(p), state="disabled")
            btn_toggle.grid(row=r, column=4, padx=2, pady=1)

            delay = ttk.Entry(self.frame, width=5)
            delay.insert(0, "500")
            delay.grid(row=r, column=5, padx=1, pady=1)

            desc = ttk.Entry(self.frame, width=25)
            desc.grid(row=r, column=6, padx=2, pady=1)

            interlock = ttk.Combobox(self.frame, width=3, state="readonly",
                                     values=["", "1", "2", "3", "4", "5", "6", "7", "8"])
            interlock.grid(row=r, column=7, padx=2, pady=1)

            self.btn_on[pin] = btn_on
            self.btn_off[pin] = btn_off
            self.btn_toggle[pin] = btn_toggle
            self.delay_entry[pin] = delay
            self.desc_entry[pin] = desc
            self.interlock_entry[pin] = interlock

        self.all_off_btn = ttk.Button(self.frame, text="All OFF",
                                      command=self.all_off, state="disabled")
        self.all_off_btn.grid(row=len(PINS) + 1, column=0, columnspan=7, pady=(5, 0), sticky="ew")

    def connect(self, ser, port):
        self.ser = ser
        self.port = port
        self.port_label.config(text=port)
        self.set_state("normal")

    def disconnect(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
        self.ser = None
        self.port_label.config(text="--")
        self.set_state("disabled")
        self.reset_leds()

    def set_state(self, state):
        for pin in PINS:
            self.btn_on[pin].config(state=state)
            self.btn_off[pin].config(state=state)
            self.btn_toggle[pin].config(state=state)
        self.all_off_btn.config(state=state)

    def reset_leds(self):
        for pin in PINS:
            self.led[pin].itemconfig("led", fill="red", outline="darkred")

    def send(self, cmd):
        if self.ser and self.ser.is_open:
            try:
                self.ser.write(f"{cmd}\n".encode())
            except serial.SerialException as e:
                if self.log_func:
                    self.log_func(f"[Board {self.addr}] Write failed: {e}")
                self.disconnect()

    def get_conflicting_pins(self, pin):
        group = self.interlock_entry[pin].get().strip()
        if not group:
            return []
        conflicts = []
        for other_pin in PINS:
            if other_pin == pin:
                continue
            if self.interlock_entry[other_pin].get().strip() == group and self.pin_state[other_pin]:
                conflicts.append(other_pin)
        return conflicts

    def get_interlock_delay(self):
        try:
            return int(self.interlock_delay_entry.get()) if self.interlock_delay_entry else 50
        except ValueError:
            return 50

    def relay_on(self, pin):
        conflicts = self.get_conflicting_pins(pin)
        if conflicts:
            mode = self.interlock_mode_var.get() if self.interlock_mode_var else "block"
            group = self.interlock_entry[pin].get().strip()
            if mode == "auto_off":
                for cp in conflicts:
                    self.relay_off(cp)
                    desc = self.desc_entry[cp].get().strip()
                    name = f"D{cp}" + (f" ({desc})" if desc else "")
                    if self.log_func:
                        self.log_func(f"[Board {self.addr}] Auto-off {name} (interlock {group})")
                delay = self.get_interlock_delay()
                self.frame.after(delay, lambda: self._do_relay_on(pin))
                return
            else:
                for cp in conflicts:
                    desc = self.desc_entry[cp].get().strip()
                    name = f"D{cp}" + (f" ({desc})" if desc else "")
                    if self.log_func:
                        self.log_func(f"[Board {self.addr}] BLOCKED: D{pin} -- {name} is ON (interlock {group})")
                return
        self._do_relay_on(pin)

    def _do_relay_on(self, pin):
        self.send(f"D{pin}_L")
        self.pin_state[pin] = True
        self.led[pin].itemconfig("led", fill="green", outline="darkgreen")

    def relay_off(self, pin):
        self.send(f"D{pin}_H")
        self.pin_state[pin] = False
        self.led[pin].itemconfig("led", fill="red", outline="darkred")

    def relay_toggle(self, pin):
        try:
            delay_ms = int(self.delay_entry[pin].get())
        except ValueError:
            return
        conflicts = self.get_conflicting_pins(pin)
        if conflicts:
            mode = self.interlock_mode_var.get() if self.interlock_mode_var else "block"
            if mode == "block":
                group = self.interlock_entry[pin].get().strip()
                for cp in conflicts:
                    desc = self.desc_entry[cp].get().strip()
                    name = f"D{cp}" + (f" ({desc})" if desc else "")
                    if self.log_func:
                        self.log_func(f"[Board {self.addr}] BLOCKED: D{pin} -- {name} is ON (interlock {group})")
                return
        self.relay_on(pin)
        self.frame.after(delay_ms, lambda: self.relay_off(pin))

    def all_off(self):
        for pin in PINS:
            self.relay_off(pin)

    def load_config(self, rows):
        for row in rows:
            pin = int(row["pin"])
            if pin in self.desc_entry:
                self.desc_entry[pin].delete(0, "end")
                self.desc_entry[pin].insert(0, row.get("note", ""))
            if pin in self.delay_entry and row.get("delay_ms"):
                self.delay_entry[pin].delete(0, "end")
                self.delay_entry[pin].insert(0, row["delay_ms"])
            if pin in self.interlock_entry:
                self.interlock_entry[pin].set(row.get("interlock", ""))

    def get_config(self):
        rows = []
        for pin in PINS:
            rows.append({
                "board": self.addr,
                "pin": pin,
                "note": self.desc_entry[pin].get(),
                "delay_ms": self.delay_entry[pin].get(),
                "interlock": self.interlock_entry[pin].get().strip(),
            })
        return rows


class RelayGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Relay 8ch Control - Multi Board")
        self.root.resizable(False, False)

        top_frame = ttk.Frame(self.root, padding=10)
        top_frame.grid(row=0, column=0, sticky="ew")

        ttk.Button(top_frame, text="Auto Detect", command=self.auto_detect).pack(side="left", padx=5)
        ttk.Button(top_frame, text="Disconnect All", command=self.disconnect_all).pack(side="left", padx=5)
        ttk.Button(top_frame, text="Save", command=self.save_and_log).pack(side="left", padx=5)
        ttk.Button(top_frame, text="View Settings", command=self.open_config).pack(side="left", padx=5)

        ttk.Separator(top_frame, orient="vertical").pack(side="left", fill="y", padx=10)
        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(top_frame, textvariable=self.port_var, width=10, state="readonly")
        self.port_combo.pack(side="left", padx=2)
        ttk.Button(top_frame, text="Refresh", command=self.refresh_ports).pack(side="left", padx=2)
        ttk.Button(top_frame, text="Reconnect", command=self.reconnect).pack(side="left", padx=2)
        ttk.Button(top_frame, text="Dev Mgr", command=lambda: os.startfile("devmgmt.msc")).pack(side="left", padx=2)
        ttk.Button(top_frame, text="Reset USB", command=self.reset_usb).pack(side="left", padx=2)

        self.status_var = tk.StringVar(value="Disconnected")
        ttk.Label(top_frame, textvariable=self.status_var).pack(side="left", padx=20)

        ttk.Separator(top_frame, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Label(top_frame, text="Interlock:").pack(side="left")
        self.interlock_mode_var = tk.StringVar(value="block")
        ttk.Radiobutton(top_frame, text="Block", variable=self.interlock_mode_var,
                        value="block").pack(side="left", padx=3)
        ttk.Radiobutton(top_frame, text="Auto-off", variable=self.interlock_mode_var,
                        value="auto_off").pack(side="left", padx=3)
        ttk.Label(top_frame, text="Delay:").pack(side="left", padx=(10, 2))
        self.interlock_delay_entry = ttk.Entry(top_frame, width=5)
        self.interlock_delay_entry.insert(0, "50")
        self.interlock_delay_entry.pack(side="left")
        ttk.Label(top_frame, text="ms").pack(side="left", padx=2)

        boards_frame = ttk.Frame(self.root, padding=5)
        boards_frame.grid(row=1, column=0, sticky="nsew")

        self.panels = {}
        for addr in range(MAX_BOARDS):
            row = addr // 2
            col = addr % 2
            panel = BoardPanel(boards_frame, addr, row, col,
                               log_func=self.log, interlock_mode_var=self.interlock_mode_var,
                               interlock_delay_entry=self.interlock_delay_entry)
            self.panels[addr] = panel

        bottom_frame = ttk.Frame(self.root, padding=10)
        bottom_frame.grid(row=2, column=0, sticky="ew")

        ttk.Label(bottom_frame, text="Board:").pack(side="left")
        self.cmd_board_var = tk.StringVar(value="0")
        cmd_board = ttk.Combobox(bottom_frame, textvariable=self.cmd_board_var,
                                 values=[str(i) for i in range(MAX_BOARDS)], width=3, state="readonly")
        cmd_board.pack(side="left", padx=5)

        ttk.Label(bottom_frame, text="Cmd:").pack(side="left")
        self.cmd_entry = ttk.Entry(bottom_frame, width=15)
        self.cmd_entry.pack(side="left", padx=5)
        self.cmd_entry.bind("<Return>", lambda e: self.send_manual())
        ttk.Button(bottom_frame, text="Send", command=self.send_manual).pack(side="left", padx=5)

        self.response_var = tk.StringVar()
        ttk.Label(bottom_frame, textvariable=self.response_var, width=30).pack(side="left", padx=10)

        log_frame = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        log_frame.grid(row=3, column=0, sticky="ew")
        self.log_text = tk.Text(log_frame, height=4, width=80, state="disabled")
        self.log_text.pack(fill="x")

        self.refresh_ports()
        self.load_config()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.mainloop()

    def log(self, msg):
        self.log_text.config(state="normal")
        self.log_text.insert("end", f"{msg}\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def reset_usb(self):
        self.disconnect_all()
        self.log("[Reset USB] Finding CH340 devices...")
        self.root.update()

        result = subprocess.run(
            ["powershell", "-Command",
             "Get-CimInstance Win32_PnPEntity | "
             "Where-Object { $_.DeviceID -match 'VID_1A86&PID_7523' } | "
             "Select-Object -ExpandProperty DeviceID"],
            capture_output=True, text=True, timeout=10
        )
        instance_ids = [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]

        if not instance_ids:
            self.log("[Reset USB] No CH340 devices found")
            return

        for iid in instance_ids:
            self.log(f"[Reset USB] Resetting {iid}...")
        self.root.update()

        ps_lines = []
        for iid in instance_ids:
            ps_lines.append(
                f"Disable-PnpDevice -InstanceId '{iid}' -Confirm:$false")
        ps_lines.append("Start-Sleep 5")
        for iid in instance_ids:
            ps_lines.append(
                f"Enable-PnpDevice -InstanceId '{iid}' -Confirm:$false")
        ps_script = "; ".join(ps_lines)

        try:
            subprocess.run(
                ["powershell", "-Command",
                 f"Start-Process powershell -Verb RunAs -ArgumentList "
                 f"'-Command','{ps_script}' -Wait"],
                capture_output=True, text=True, timeout=45
            )
        except subprocess.TimeoutExpired:
            self.log("[Reset USB] Timeout waiting for admin command")
            return

        self.log("[Reset USB] Waiting for re-enumeration...")
        self.root.update()
        time.sleep(5)
        self.refresh_ports()
        self.log("[Reset USB] Done. Click Auto Detect to reconnect.")

    def refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_combo["values"] = ports
        if ports:
            self.port_var.set(ports[0])

    def reconnect(self):
        port = self.port_var.get()
        if not port:
            self.log("[Reconnect] No port selected")
            return
        for panel in self.panels.values():
            if getattr(panel, "port", None) == port:
                panel.disconnect()
                self.log(f"[Reconnect] Disconnected board {panel.addr} from {port}")
                break
        self.log(f"[Reconnect] Opening {port}...")
        self.root.update()
        try:
            s = serial.Serial(port, 9600, timeout=2, write_timeout=1)
            time.sleep(2)
            s.reset_input_buffer()
            s.write(b"*IDN?\n")
            response = s.readline().decode().strip()
            if response.startswith("8Ch Relay Control"):
                parts = response.split(",")
                addr = int(parts[1].strip()) if len(parts) > 1 else 0
                if addr in self.panels:
                    self.panels[addr].connect(s, port)
                    self.log(f"[Reconnect] Board {addr} connected on {port}")
                    self.status_var.set(f"Reconnected board {addr} on {port}")
                else:
                    s.close()
                    self.log(f"[Reconnect] Unknown board address {addr}")
            else:
                s.close()
                self.log(f"[Reconnect] Not a relay device (got: {response or 'no response'})")
        except (serial.SerialException, OSError, ValueError) as e:
            self.log(f"[Reconnect] Failed: {e}")

    def _try_connect(self, port):
        s = serial.Serial(port, 9600, timeout=2, write_timeout=1)
        time.sleep(2)
        s.reset_input_buffer()
        s.write(b"*IDN?\n")
        response = s.readline().decode().strip()
        if response.startswith("8Ch Relay Control"):
            parts = response.split(",")
            addr = int(parts[1].strip()) if len(parts) > 1 else 0
            if addr in self.panels:
                self.panels[addr].connect(s, port)
                self.log(f"[Auto Detect] {port}: Board {addr} connected")
                return True
            else:
                s.close()
                self.log(f"[Auto Detect] {port}: unknown address {addr}")
        else:
            s.close()
            self.log(f"[Auto Detect] {port}: not a relay device (got: {response or 'no response'})")
        return False

    def auto_detect(self):
        self.disconnect_all()

        ports = [p.device for p in serial.tools.list_ports.comports()]
        if not ports:
            self.status_var.set("No COM ports found")
            return

        self.log(f"[Auto Detect] Scanning {len(ports)} port(s): {', '.join(ports)}")
        self.root.update()

        found = 0
        failed_ports = []
        for port in ports:
            try:
                if self._try_connect(port):
                    found += 1
            except (serial.SerialException, OSError, ValueError) as e:
                self.log(f"[Auto Detect] {port}: failed ({e})")
                failed_ports.append(port)
                continue

        for port in failed_ports:
            self.log(f"[Auto Detect] {port}: retrying...")
            self.root.update()
            try:
                if self._try_connect(port):
                    found += 1
            except (serial.SerialException, OSError, ValueError) as e:
                self.log(f"[Auto Detect] {port}: retry failed ({e})")
                continue

        self.status_var.set(f"Connected: {found} board(s)" if found else "No boards found")

    def disconnect_all(self):
        for panel in self.panels.values():
            panel.disconnect()
        self.status_var.set("Disconnected")

    def send_manual(self):
        cmd = self.cmd_entry.get().strip()
        if not cmd:
            return
        try:
            addr = int(self.cmd_board_var.get())
        except ValueError:
            return
        panel = self.panels.get(addr)
        if not panel or not panel.ser or not panel.ser.is_open:
            self.response_var.set(f"Board {addr} not connected")
            return
        panel.ser.reset_input_buffer()
        panel.ser.write(f"{cmd}\n".encode())
        time.sleep(0.1)
        response = ""
        while panel.ser.in_waiting:
            response += panel.ser.read(panel.ser.in_waiting).decode()
        self.response_var.set(response.strip() if response else "(no response)")
        self.cmd_entry.delete(0, "end")

    def load_config(self):
        if not os.path.exists(CONFIG_FILE):
            return
        with open(CONFIG_FILE, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows_by_board = {}
            for row in reader:
                board = int(row.get("board", -99))
                if board == -1:
                    self.interlock_mode_var.set(row.get("note", "block"))
                    self.interlock_delay_entry.delete(0, "end")
                    self.interlock_delay_entry.insert(0, row.get("delay_ms", "50"))
                    continue
                rows_by_board.setdefault(board, []).append(row)
            for addr, rows in rows_by_board.items():
                if addr in self.panels:
                    self.panels[addr].load_config(rows)

    def open_config(self):
        self.save_config()
        os.startfile(CONFIG_FILE)

    def save_and_log(self):
        self.save_config()
        self.log(f"[Save] Config saved to {os.path.basename(CONFIG_FILE)}")

    def save_config(self):
        with open(CONFIG_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["board", "pin", "note", "delay_ms", "interlock"])
            writer.writeheader()
            writer.writerow({
                "board": -1,
                "pin": 0,
                "note": self.interlock_mode_var.get(),
                "delay_ms": self.interlock_delay_entry.get(),
                "interlock": "",
            })
            for addr in range(MAX_BOARDS):
                for row in self.panels[addr].get_config():
                    writer.writerow(row)

    def on_close(self):
        self.save_config()
        for panel in self.panels.values():
            if panel.ser and panel.ser.is_open:
                panel.ser.close()
        self.root.destroy()


if __name__ == "__main__":
    RelayGUI()
