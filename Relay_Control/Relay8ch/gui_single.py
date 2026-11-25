import csv
import os
import subprocess
import time
import customtkinter as ctk
import serial
import serial.tools.list_ports

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "channels_single.csv")

PINS            = list(range(2, 10))
INTERLOCK_NONE  = "-"
INTERLOCK_OPTS  = [INTERLOCK_NONE] + [str(i) for i in range(1, 9)]

GREEN       = "#2fa572"
GREEN_HOVER = "#268a5f"
GRAY        = "#3a3d42"
GRAY_HOVER  = "#4a4e54"
RED         = "#c0392b"
ROW_BG      = ("#e8eaed", "#24272b")
MUTED       = ("#5f6368", "#9aa0a6")

ctk.ThemeManager.theme["CTkFont"]["size"] = 11
ctk.set_widget_scaling(0.8)


COLUMNS = [("Pin", 26), ("", 14), ("", 40), ("", 40), ("", 52), ("ms", 46), ("Note", 0), ("Lock", 50)]


def column_padx(i):
    if i == 0:
        return (6, 2)
    if i == len(COLUMNS) - 1:
        return (2, 6)
    return 2


class RelayRow(ctk.CTkFrame):
    def __init__(self, parent, pin, app):
        super().__init__(parent, corner_radius=6, fg_color=ROW_BG)
        self.pin = pin
        self.app = app
        self.is_on = False
        self.grid_columnconfigure(6, weight=1)

        ctk.CTkLabel(self, text=f"D{pin}", width=26, anchor="w", font=ctk.CTkFont(size=12, weight="bold")).grid(
            row=0, column=0, padx=column_padx(0), pady=3)
        self.dot = ctk.CTkLabel(self, text="●", width=14, font=ctk.CTkFont(size=13), text_color=GRAY)
        self.dot.grid(row=0, column=1)

        self.on_btn = ctk.CTkButton(self, text="ON", width=40, height=22, fg_color=GREEN,
                                    hover_color=GREEN_HOVER, command=lambda: app.relay_on(pin), state="disabled")
        self.on_btn.grid(row=0, column=2, padx=2)
        self.off_btn = ctk.CTkButton(self, text="OFF", width=40, height=22, fg_color=GRAY,
                                     hover_color=GRAY_HOVER, command=lambda: app.relay_off(pin), state="disabled")
        self.off_btn.grid(row=0, column=3, padx=2)
        self.toggle_btn = ctk.CTkButton(self, text="Toggle", width=52, height=22, fg_color="transparent",
                                        border_width=1, command=self.on_toggle, state="disabled")
        self.toggle_btn.grid(row=0, column=4, padx=2)

        self.delay = ctk.CTkEntry(self, width=46, height=22, justify="right")
        self.delay.insert(0, "500")
        self.delay.grid(row=0, column=5, padx=2)

        self.note = ctk.CTkEntry(self, placeholder_text="Note", width=110, height=22)
        self.note.grid(row=0, column=6, padx=2, sticky="ew")

        self.interlock = ctk.CTkOptionMenu(self, values=INTERLOCK_OPTS, width=50, height=22)
        self.interlock.set(INTERLOCK_NONE)
        self.interlock.grid(row=0, column=7, padx=column_padx(7))

    @property
    def name(self):
        note = self.note.get().strip()
        return f"D{self.pin}" + (f" ({note})" if note else "")

    @property
    def group(self):
        g = self.interlock.get()
        return "" if g == INTERLOCK_NONE else g

    def set_enabled(self, enabled):
        state = "normal" if enabled else "disabled"
        self.on_btn.configure(state=state)
        self.off_btn.configure(state=state)
        self.toggle_btn.configure(state=state)

    def show_state(self, on):
        self.is_on = on
        self.dot.configure(text_color=GREEN if on else GRAY)
        self.configure(border_width=1 if on else 0, border_color=GREEN)

    def on_toggle(self):
        try:
            delay_ms = int(self.delay.get())
        except ValueError:
            self.app.log(f"Invalid toggle delay for {self.name}")
            return
        self.app.relay_pulse(self.pin, delay_ms)


class RelayApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.title("Relay 8ch Control")
        self.resizable(False, False)

        self.ser = None
        self.port = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._build_header()
        self._build_toolbar()
        self._build_cards()
        self._build_footer()

        self.refresh_ports()
        self.load_config()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_header(self):
        bar = ctk.CTkFrame(self, corner_radius=0, fg_color=("#d6d9de", "#1b1d20"))
        bar.grid(row=0, column=0, sticky="ew")
        bar.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(bar, text="Relay 8ch", font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=0, column=0, padx=8, pady=6, sticky="w")

        conn = ctk.CTkFrame(bar, fg_color="transparent")
        conn.grid(row=0, column=1, sticky="e", padx=4)
        self.port_menu = ctk.CTkOptionMenu(conn, values=[""], width=72, height=22)
        self.port_menu.pack(side="left", padx=2)
        ctk.CTkButton(conn, text="↻", width=22, height=22, command=self.refresh_ports).pack(side="left", padx=2)
        self.connect_btn = ctk.CTkButton(conn, text="Connect", width=64, height=22, command=self.toggle_connection)
        self.connect_btn.pack(side="left", padx=2)
        ctk.CTkButton(conn, text="Auto", width=44, height=22, fg_color="transparent", border_width=1,
                      command=self.auto_detect).pack(side="left", padx=2)

        self.status = ctk.CTkLabel(bar, text="  Disconnected  ", height=20, corner_radius=8,
                                   fg_color=GRAY, text_color="white")
        self.status.grid(row=0, column=2, padx=(2, 8))

    def _build_toolbar(self):
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=1, column=0, sticky="ew", padx=8, pady=(6, 2))

        ctk.CTkLabel(bar, text="Interlock", text_color=MUTED).pack(side="left", padx=(0, 4))
        self.mode = ctk.CTkSegmentedButton(bar, values=["Block", "Auto-off"], height=22)
        self.mode.set("Block")
        self.mode.pack(side="left")
        ctk.CTkLabel(bar, text="Delay", text_color=MUTED).pack(side="left", padx=(8, 4))
        self.interlock_delay = ctk.CTkEntry(bar, width=40, height=22, justify="right")
        self.interlock_delay.insert(0, "50")
        self.interlock_delay.pack(side="left")
        ctk.CTkLabel(bar, text="ms", text_color=MUTED).pack(side="left", padx=2)

        ctk.CTkButton(bar, text="Settings", width=56, height=22, fg_color="transparent", border_width=1,
                      command=self.open_config).pack(side="right")
        ctk.CTkButton(bar, text="Save", width=44, height=22, fg_color="transparent", border_width=1,
                      command=self.save_and_log).pack(side="right", padx=4)

    def _build_cards(self):
        table = ctk.CTkFrame(self, fg_color="transparent")
        table.grid(row=2, column=0, sticky="nsew", padx=8, pady=2)
        table.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(table, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(6, weight=1)
        for i, (text, width) in enumerate(COLUMNS):
            ctk.CTkLabel(header, text=text, width=width, height=16, anchor="w", text_color=MUTED).grid(
                row=0, column=i, padx=column_padx(i), sticky="ew")

        self.cards = {}
        for i, pin in enumerate(PINS):
            row = RelayRow(table, pin, self)
            row.grid(row=i + 1, column=0, sticky="ew", pady=1)
            self.cards[pin] = row

    def _build_footer(self):
        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.grid(row=3, column=0, sticky="ew", padx=8, pady=(4, 8))
        foot.grid_columnconfigure(0, weight=1)

        cmd = ctk.CTkFrame(foot, fg_color="transparent")
        cmd.grid(row=0, column=0, sticky="ew")
        cmd.grid_columnconfigure(0, weight=1)
        self.cmd_entry = ctk.CTkEntry(cmd, placeholder_text="Cmd, e.g. D2_L or *IDN?", height=22)
        self.cmd_entry.grid(row=0, column=0, sticky="ew")
        self.cmd_entry.bind("<Return>", lambda _: self.send_manual())
        ctk.CTkButton(cmd, text="Send", width=44, height=22, command=self.send_manual).grid(row=0, column=1, padx=4)
        ctk.CTkButton(cmd, text="Dev Mgr", width=56, height=22, fg_color="transparent", border_width=1,
                      command=lambda: os.startfile("devmgmt.msc")).grid(row=0, column=2, padx=(0, 4))
        ctk.CTkButton(cmd, text="Reset USB", width=64, height=22, fg_color="transparent", border_width=1,
                      command=self.reset_usb).grid(row=0, column=3)

        self.log_box = ctk.CTkTextbox(foot, height=60, font=ctk.CTkFont(family="Consolas", size=10),
                                      state="disabled")
        self.log_box.grid(row=1, column=0, sticky="ew", pady=(4, 0))

    def log(self, msg):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"{time.strftime('%H:%M:%S')}  {msg}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def set_status(self, text, color):
        self.status.configure(text=f"  {text}  ", fg_color=color)

    def refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_menu.configure(values=ports or [""])
        self.port_menu.set(ports[0] if ports else "")

    def _open(self, port):
        s = serial.Serial(port, 9600, timeout=2, write_timeout=1)
        time.sleep(2)
        s.reset_input_buffer()
        s.write(b"*IDN?\n")
        response = s.readline().decode().strip()
        if not response.startswith("8Ch Relay Control"):
            s.close()
            self.log(f"{port}: not a relay device (got: {response or 'no response'})")
            return False
        parts = response.split(",")
        addr = parts[1].strip() if len(parts) > 1 else "0"
        self.ser = s
        self.port = port
        self.port_menu.set(port)
        self.connect_btn.configure(text="Disconnect")
        for card in self.cards.values():
            card.set_enabled(True)
            card.show_state(False)
        self.set_status(f"{port}  |  addr {addr}", GREEN)
        self.log(f"{port}: connected (addr {addr})")
        return True

    def toggle_connection(self):
        if self.ser:
            self.disconnect()
            return
        port = self.port_menu.get()
        if not port:
            self.log("No port selected")
            return
        self.set_status("Connecting...", GRAY)
        self.update()
        try:
            if not self._open(port):
                self.set_status("Disconnected", GRAY)
        except (serial.SerialException, OSError, ValueError) as e:
            self.log(f"{port}: failed ({e})")
            self.set_status("Disconnected", GRAY)

    def auto_detect(self):
        self.disconnect()
        ports = [p.device for p in serial.tools.list_ports.comports()]
        if not ports:
            self.log("No COM ports found")
            return
        self.log(f"Scanning {len(ports)} port(s): {', '.join(ports)}")
        self.set_status("Scanning...", GRAY)
        self.update()
        for _ in range(2):
            for port in ports:
                try:
                    if self._open(port):
                        return
                except (serial.SerialException, OSError, ValueError) as e:
                    self.log(f"{port}: failed ({e})")
                self.update()
        self.set_status("No device found", RED)

    def disconnect(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
            self.log(f"{self.port}: disconnected")
        self.ser = None
        self.port = None
        self.connect_btn.configure(text="Connect")
        for card in self.cards.values():
            card.set_enabled(False)
            card.show_state(False)
        self.set_status("Disconnected", GRAY)

    def send(self, cmd):
        if not (self.ser and self.ser.is_open):
            return False
        try:
            self.ser.write(f"{cmd}\n".encode())
            return True
        except serial.SerialException as e:
            self.log(f"Write failed: {e}")
            self.disconnect()
            return False

    def conflicts(self, pin):
        group = self.cards[pin].group
        if not group:
            return []
        return [p for p, c in self.cards.items() if p != pin and c.group == group and c.is_on]

    def interlock_delay_ms(self):
        try:
            return int(self.interlock_delay.get())
        except ValueError:
            return 50

    def relay_on(self, pin, after_on=None):
        conflicts = self.conflicts(pin)
        if conflicts:
            group = self.cards[pin].group
            if self.mode.get() == "Block":
                for cp in conflicts:
                    self.log(f"BLOCKED: D{pin} -- {self.cards[cp].name} is ON (interlock {group})")
                return
            for cp in conflicts:
                self.relay_off(cp)
                self.log(f"Auto-off {self.cards[cp].name} (interlock {group})")
            self.after(self.interlock_delay_ms(), lambda: self._do_on(pin, after_on))
            return
        self._do_on(pin, after_on)

    def _do_on(self, pin, after_on=None):
        if self.send(f"D{pin}_L"):
            self.cards[pin].show_state(True)
            self.log(f"{self.cards[pin].name} ON")
            if after_on:
                after_on()

    def relay_off(self, pin):
        if self.send(f"D{pin}_H"):
            self.cards[pin].show_state(False)
            self.log(f"{self.cards[pin].name} OFF")

    def relay_pulse(self, pin, delay_ms):
        self.relay_on(pin, after_on=lambda: self.after(delay_ms, lambda: self.relay_off(pin)))

    def send_manual(self):
        cmd = self.cmd_entry.get().strip()
        if not cmd:
            return
        if not (self.ser and self.ser.is_open):
            self.log("Not connected")
            return
        self.ser.reset_input_buffer()
        self.ser.write(f"{cmd}\n".encode())
        time.sleep(0.1)
        response = ""
        while self.ser.in_waiting:
            response += self.ser.read(self.ser.in_waiting).decode()
        self.log(f"> {cmd}  ->  {response.strip() or '(no response)'}")
        self.cmd_entry.delete(0, "end")

    def reset_usb(self):
        self.disconnect()
        self.log("[Reset USB] Finding CH340 devices...")
        self.update()

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
        self.update()

        ps_lines = [f"Disable-PnpDevice -InstanceId '{iid}' -Confirm:$false" for iid in instance_ids]
        ps_lines.append("Start-Sleep 5")
        ps_lines += [f"Enable-PnpDevice -InstanceId '{iid}' -Confirm:$false" for iid in instance_ids]
        ps_script = "; ".join(ps_lines)
        try:
            subprocess.run(
                ["powershell", "-Command",
                 f"Start-Process powershell -Verb RunAs -ArgumentList '-Command','{ps_script}' -Wait"],
                capture_output=True, text=True, timeout=45
            )
        except subprocess.TimeoutExpired:
            self.log("[Reset USB] Timeout waiting for admin command")
            return

        self.log("[Reset USB] Waiting for re-enumeration...")
        self.update()
        time.sleep(5)
        self.refresh_ports()
        self.log("[Reset USB] Done. Click Auto Detect to reconnect.")

    def load_config(self):
        if not os.path.exists(CONFIG_FILE):
            return
        with open(CONFIG_FILE, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                pin = int(row["pin"])
                if pin == 0:
                    self.mode.set("Auto-off" if row.get("note") == "auto_off" else "Block")
                    self.interlock_delay.delete(0, "end")
                    self.interlock_delay.insert(0, row.get("delay_ms") or "50")
                    continue
                card = self.cards.get(pin)
                if not card:
                    continue
                card.note.delete(0, "end")
                if row.get("note"):
                    card.note.insert(0, row["note"])
                if row.get("delay_ms"):
                    card.delay.delete(0, "end")
                    card.delay.insert(0, row["delay_ms"])
                card.interlock.set(row.get("interlock") or INTERLOCK_NONE)

    def save_config(self):
        with open(CONFIG_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["pin", "note", "delay_ms", "interlock"])
            writer.writeheader()
            writer.writerow({
                "pin": 0,
                "note": "auto_off" if self.mode.get() == "Auto-off" else "block",
                "delay_ms": self.interlock_delay.get(),
                "interlock": "",
            })
            for pin, card in self.cards.items():
                writer.writerow({
                    "pin": pin,
                    "note": card.note.get(),
                    "delay_ms": card.delay.get(),
                    "interlock": card.group,
                })

    def save_and_log(self):
        self.save_config()
        self.log(f"Config saved to {os.path.basename(CONFIG_FILE)}")

    def open_config(self):
        self.save_config()
        os.startfile(CONFIG_FILE)

    def on_close(self):
        self.save_config()
        if self.ser and self.ser.is_open:
            self.ser.close()
        self.destroy()


if __name__ == "__main__":
    RelayApp().mainloop()
