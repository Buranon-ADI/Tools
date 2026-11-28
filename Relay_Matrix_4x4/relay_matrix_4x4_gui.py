import csv
import os
import re
import math
import time
import tkinter as tk
from datetime import datetime
import customtkinter as ctk
import serial
import serial.tools.list_ports

LABEL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "relay_labels.csv")

FW_ID        = "relay_matrix_v1.0"
BAUD         = 115200
MCP_COUNT    = 8
SHARED_DEV   = -1
ARDUINO_VID  = 0x2341
NANO_USB_IDS = {(0x1A86, 0x7523), (0x0403, 0x6001)}
BOOT_WAIT    = 2000
REPLY_WAIT   = 1.0
STARTUP_WAIT = 0.3
PULSE_MS     = "500"
PULSE_MAX    = 60000
COLOR_ON     = "#2E8B57"
COLOR_OFF    = "#4A4A4A"
FONT_SIZE    = 11
WIDGET_H     = 22

NETS_DARK  = ["#E08A2E", "#3CCB7F", "#4A90E2", "#B07CD8", "#E0C040", "#A8D86E", "#40C8C8", "#9DA8FF"]
NETS_LIGHT = ["#C46A10", "#1E8F4A", "#1F5FBF", "#7B3FA8", "#9A7B00", "#5E8C1E", "#0F8C8C", "#4A55C8"]
THEMES     = {
    "dark":   dict(mode="dark",  window="#242424", panel="#2B2B2B", canvas="#2B2B2B", wire="#555555",
                   off="#8A8A8A", sep="#3A3A3A", sel="#F0C040", short="#FF4040", nets=NETS_DARK),
    "black":  dict(mode="dark",  window="#0E0E0E", panel="#181818", canvas="#111111", wire="#3C3C3C",
                   off="#7A7A7A", sep="#2A2A2A", sel="#F0C040", short="#FF4040", nets=NETS_DARK),
    "navy":   dict(mode="dark",  window="#0B1626", panel="#122238", canvas="#0E1D31", wire="#34507A",
                   off="#8FA6C8", sep="#22395A", sel="#F0C040", short="#FF5050", nets=NETS_DARK),
    "light":  dict(mode="light", window="#E6E6E6", panel="#F4F4F4", canvas="#FFFFFF", wire="#BDBDBD",
                   off="#6E6E6E", sep="#D6D6D6", sel="#C08000", short="#D32F2F", nets=NETS_LIGHT),
    "paper":  dict(mode="light", window="#EAE5D8", panel="#F6F2E7", canvas="#FFFDF6", wire="#B5AE98",
                   off="#6E6A5E", sep="#DDD6C2", sel="#B07000", short="#C62828", nets=NETS_LIGHT),
}
THEME = "paper"
T     = THEMES[THEME]

MX_WIRE      = T["wire"]
MX_OFF       = T["off"]
MX_SEL       = T["sel"]
MX_SEP       = T["sep"]
MX_SHORT     = T["short"]
MX_NETS      = T["nets"]
MX_ENTRY_X   = 66
MX_WIRE_X0   = 140
MX_CELL_W    = 84
MX_CELL_H    = 52
MX_BLADE     = 28
MX_BUS_OFF   = 56
MX_ROW_OFF   = 14
MX_DOT       = 3
MX_HOP       = 6
MX_OPEN      = math.radians(65)
MX_BLOCK_H   = 4 * MX_CELL_H
MX_TOP       = 2
MX_W         = MX_WIRE_X0 + 4 * MX_CELL_W + 8

RE_OK   = re.compile(r"^OK (\d) ([0-9A-F]{4})$")
RE_GET  = re.compile(r"Dev (\d) \(0x[0-9A-F]{2}\)\s+OLAT: ([0-9A-F]{4})\s+GPIO: ([0-9A-F]{4})")
RE_SCAN = re.compile(r"^\| (\d)\s+\| 0x[0-9A-F]{2} \| (.+?)\s*\|$")
RE_K17  = re.compile(r"K17:? (OPEN|CLOSED)")


# All devices share one canvas because SIG_OUT1-4 are a common bus across every MCP on the board
class MatrixView(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=T["panel"])
        self.app     = app
        self.s       = ctk.ScalingTracker.get_widget_scaling(app)
        self.devs    = []
        self.sel     = None
        self.gpio    = {}
        self.widgets = []

        f = app.font
        h = WIDGET_H
        s = self.s
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)
        self.cv = tk.Canvas(body, width=int(MX_W * s), bg=T["canvas"],
                            highlightthickness=0, cursor="hand2", yscrollincrement=int(MX_CELL_H * s))
        self.cv.pack(side="left", fill="y", padx=(4, 0), pady=(4, 2))
        bar = ctk.CTkScrollbar(body, command=self.cv.yview)
        bar.pack(side="left", fill="y", pady=(4, 2))
        self.cv.configure(yscrollcommand=bar.set)
        self.cv.bind("<Button-1>", lambda e: self.click(e, app.toggle_relay))
        self.cv.bind("<Button-3>", lambda e: self.click(e, self.select))
        app.bind_all("<MouseWheel>", self.wheel, add="+")

        sel = ctk.CTkFrame(self, fg_color="transparent")
        sel.pack(fill="x", padx=6, pady=(0, 4))
        self.sel_label = ctk.CTkLabel(sel, text="--", width=80, height=h, font=f, text_color=MX_SEL, anchor="w")
        self.sel_label.pack(side="left")
        ctk.CTkButton(sel, text="Pulse", width=40, height=h, font=f, command=self.pulse_sel).pack(side="left", padx=2)
        self.delay_entry = ctk.CTkEntry(sel, width=42, height=h, font=f)
        self.delay_entry.pack(side="left", padx=(2, 1))
        ctk.CTkLabel(sel, text="ms", height=h, font=f).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(sel, text="Mask", height=h, font=f).pack(side="left")
        self.mask_entry = ctk.CTkEntry(sel, width=50, height=h, font=f)
        self.mask_entry.pack(side="left", padx=2)
        ctk.CTkButton(sel, text="SET", width=40, height=h, font=f, command=self.set_mask).pack(side="left", padx=2)
        ctk.CTkButton(sel, text="Dev OFF", width=56, height=h, font=f, command=self.dev_off).pack(side="left", padx=2)
        self.state_label = ctk.CTkLabel(sel, text="", height=h, font=f)
        self.state_label.pack(side="left", padx=8)
        self.tip = ctk.CTkLabel(self, text="", height=30, font=ctk.CTkFont(family="Consolas", size=10),
                                anchor="w", justify="left")
        self.tip.pack(fill="x", padx=6, pady=(0, 2))
        self.cv.bind("<Motion>", self.hover)
        self.cv.bind("<Leave>", lambda _: self.tip.configure(text=""))

    @staticmethod
    def col_x(c):
        return MX_WIRE_X0 + c * MX_CELL_W + MX_BUS_OFF

    @staticmethod
    def pivot_x(c):
        return MX_WIRE_X0 + c * MX_CELL_W + MX_BUS_OFF - MX_BLADE

    @staticmethod
    def block_y(i):
        return MX_TOP + i * MX_BLOCK_H

    @staticmethod
    def row_y(i, r):
        return MX_TOP + i * MX_BLOCK_H + r * MX_CELL_H + MX_CELL_H - MX_ROW_OFF

    def put(self, x, y, widget):
        self.cv.create_window(x * self.s, y * self.s, anchor="w", window=widget)
        self.widgets.append(widget)

    def rebuild(self, devs):
        app, f, h, s = self.app, self.app.font, WIDGET_H, self.s
        for w in self.widgets:
            w.destroy()
        self.widgets = []
        self.cv.delete("all")
        self.devs = list(devs)
        for i, dev in enumerate(self.devs):
            for r in range(4):
                y = self.row_y(i, r)
                self.put(MX_ENTRY_X, y, ctk.CTkEntry(self.cv, width=70, height=h, font=f, bg_color=T["canvas"],
                                                       textvariable=app.labels[(dev, f"SIG_IN{r + 1}")]))
        self.cv.configure(scrollregion=(0, 0, MX_W * s, (MX_TOP + len(self.devs) * MX_BLOCK_H + 4) * s))
        if self.sel and self.sel[0] in self.devs:
            self.redraw()
        elif self.devs:
            self.select(self.devs[0], 1)
        else:
            self.sel = None
            self.sel_label.configure(text="--")
            self.state_label.configure(text="")

    def hit(self, e):
        x  = e.x / self.s
        y  = self.cv.canvasy(e.y) / self.s
        i  = int((y - MX_TOP) // MX_BLOCK_H)
        yy = y - self.block_y(i)
        c  = int((x - MX_WIRE_X0) // MX_CELL_W)
        r  = int(yy // MX_CELL_H)
        if 0 <= i < len(self.devs) and yy >= 0 and 0 <= c < 4 and 0 <= r < 4:
            return self.devs[i], r * 4 + c + 1
        return None

    def click(self, e, action):
        key = self.hit(e)
        if key:
            action(*key)
            self.hover(e)

    def nets(self):
        closed  = set()
        row_end = {}
        drivers = {}
        for i, dev in enumerate(self.devs):
            olat = self.app.relay_state[dev]
            for k in range(1, 17):
                if olat >> (k - 1) & 1:
                    r, c = (k - 1) // 4, (k - 1) % 4
                    closed.add((i, k))
                    row_end[(i, r)] = max(row_end.get((i, r), -1), c)
                    drivers.setdefault(c, []).append((i, r))
        col_net = {c: self.net_color(*ds[0]) if len(ds) == 1 else MX_SHORT for c, ds in drivers.items()}
        return closed, row_end, drivers, col_net

    def net_color(self, i, r):
        return MX_NETS[(self.devs[i] * 4 + r) % len(MX_NETS)]

    def sig_in(self, i, r):
        return f"SIG_IN{self.devs[i] * 4 + r + 1}"

    def hover(self, e):
        key = self.hit(e)
        if not key:
            self.tip.configure(text="")
            return
        dev, k  = key
        i       = self.devs.index(dev)
        r, c    = (k - 1) // 4, (k - 1) % 4
        in_net  = f"sig_in_{r + 1}" if c == 0 else f"sig_in_k{k}"
        out_net = f"sig_out_{c + 1}" if r == 0 else f"sig_out_k{k}"
        mcp     = f"GPA{k - 1}" if k <= 8 else f"GPB{k - 9}"
        uln     = f"U5 ch{k}" if k <= 8 else f"U6 ch{k - 8}"
        line1   = (f"Dev {dev} K{k}: {self.sig_in(i, r)} -> SIG_OUT{c + 1}   "
                   f"{in_net} -> {out_net} -> bus {c + 1}   coil IO_{c + 1}{r + 1} {mcp} {uln}")
        closed, _, drivers, _ = self.nets()
        srcs  = drivers.get(c, [])
        other = [d for d in srcs if d != (i, r)]
        line2 = ""
        if len(srcs) > 1:
            line2 = "!! SHORT on SIG_OUT{}: {}".format(c + 1, ", ".join(self.sig_in(*d) for d in srcs))
        elif other and (i, k) not in closed:
            line2 = f"!! closing shorts {self.sig_in(i, r)} to " + ", ".join(self.sig_in(*d) for d in other)
        self.tip.configure(text=f"{line1}\n{line2}", text_color=MX_SHORT if line2 else MX_OFF)

    def wheel(self, e):
        if str(e.widget).startswith(str(self.cv)):
            self.cv.yview_scroll(int(-e.delta / 120), "units")

    def select(self, dev, k):
        self.sel = (dev, k)
        self.sel_label.configure(text=f"Dev {dev}  K{k}")
        self.delay_entry.configure(textvariable=self.app.delays[(dev, f"K{k}")])
        self.show_olat()
        self.redraw()

    def show_olat(self):
        dev  = self.sel[0]
        olat = self.app.relay_state[dev]
        gpio = self.gpio.get(dev)
        self.state_label.configure(text=f"OLAT {olat:04X}" if gpio is None else f"OLAT {olat:04X}  GPIO {gpio:04X}")

    def update_state(self, dev, gpio):
        self.gpio[dev] = gpio
        if self.sel and self.sel[0] == dev:
            self.show_olat()
        self.redraw()

    def pulse_sel(self):
        if self.sel:
            self.app.pulse_relay(*self.sel)

    def dev_off(self):
        if self.sel:
            self.app.send(f"ALLOFF {self.sel[0]}")

    def set_mask(self):
        if not self.sel:
            self.app.log("ERR: no device selected", "err")
            return
        text = self.mask_entry.get().strip()
        try:
            mask = int(text, 16)
        except ValueError:
            self.app.log(f"ERR: invalid hex mask '{text}'", "err")
            return
        if not 0 <= mask <= 0xFFFF:
            self.app.log(f"ERR: mask {text} out of range (0000-FFFF)", "err")
            return
        self.app.set_relays(self.sel[0], mask)

    def redraw(self):
        cv, s = self.cv, self.s
        cv.delete("mx")
        if not self.devs:
            return
        bg     = cv["bg"]
        small  = ("Segoe UI", -int(9 * s))
        text   = ("Segoe UI", -int(FONT_SIZE * s))
        closed, row_end, _, col_net = self.nets()
        bottom = self.block_y(len(self.devs)) - 2
        for i, dev in enumerate(self.devs):
            if i:
                y = self.block_y(i) * s
                cv.create_line(0, y, (MX_WIRE_X0 - 8) * s, y, fill=MX_SEP, tags="mx")
            for r in range(4):
                y   = self.row_y(i, r)
                net = self.net_color(i, r)
                cv.create_text(4 * s, y * s, text=self.sig_in(i, r), font=text, anchor="w", tags="mx",
                               fill=net if (i, r) in row_end else MX_OFF)
                cv.create_line((MX_WIRE_X0 - 4) * s, y * s, self.pivot_x(3) * s, y * s, fill=MX_WIRE,
                               width=2 * s, tags="mx")
                if (i, r) in row_end:
                    cv.create_line((MX_WIRE_X0 - 4) * s, y * s, self.pivot_x(row_end[(i, r)]) * s, y * s,
                                   fill=net, width=3 * s, tags="mx")
                # Row passes under buses 1-3 with a hop: crossing is not a connection
                for c in range(3):
                    x    = self.col_x(c)
                    live = row_end.get((i, r), -1) > c
                    hp   = MX_HOP
                    cv.create_rectangle((x - hp) * s, (y - 3) * s, (x + hp) * s, (y + 3) * s, fill=bg, outline="",
                                        tags="mx")
                    cv.create_arc((x - hp) * s, (y - hp) * s, (x + hp) * s, (y + hp) * s, start=0, extent=180,
                                  style="arc", outline=net if live else MX_WIRE, width=2 * s, tags="mx")
        # Every relay output is hard-wired to its column bus, so a driven bus is live over its full length
        for c in range(4):
            x = self.col_x(c) * s
            cv.create_line(x, 0, x, bottom * s, fill=col_net.get(c, MX_WIRE), width=(3 if c in col_net else 2) * s,
                           tags="mx")
        for i, dev in enumerate(self.devs):
            for r in range(4):
                for c in range(4):
                    k      = r * 4 + c + 1
                    px, bx = self.pivot_x(c), self.col_x(c)
                    ry     = self.row_y(i, r)
                    cy     = ry - MX_BLADE
                    on     = (i, k) in closed
                    net    = self.net_color(i, r)
                    rnet   = net if c <= row_end.get((i, r), -1) else MX_OFF
                    danger = not on and c in col_net
                    if on:
                        cv.create_line(px * s, ry * s, bx * s, cy * s, fill=net, width=3 * s, tags="mx")
                    else:
                        tx = px + MX_BLADE * math.sqrt(2) * math.cos(MX_OPEN)
                        ty = ry - MX_BLADE * math.sqrt(2) * math.sin(MX_OPEN)
                        cv.create_line(px * s, ry * s, tx * s, ty * s, fill=MX_SHORT if danger else MX_OFF,
                                       width=2 * s, tags="mx")
                    d = MX_DOT * s
                    cv.create_oval(px * s - d, ry * s - d, px * s + d, ry * s + d, fill=rnet, outline="", tags="mx")
                    cv.create_oval(bx * s - d, cy * s - d, bx * s + d, cy * s + d, fill=col_net.get(c, MX_OFF),
                                   outline="", tags="mx")
                    cv.create_text((px - 4) * s, (ry - MX_BLADE / 2) * s, text=f"K{k}", font=small, anchor="e",
                                   tags="mx", fill=net if on else MX_SHORT if danger else MX_OFF)
                    if self.sel == (dev, k):
                        mx, my, d = (px + bx) / 2 * s, (ry + cy) / 2 * s, MX_BLADE * 0.85 * s
                        cv.create_oval(mx - d, my - d, mx + d, my + d, outline=MX_SEL, tags="mx")


class App(ctk.CTk):
    def __init__(self):
        ctk.set_appearance_mode(T["mode"])
        super().__init__(fg_color=T["window"])
        self.title("Relay Matrix 4x4")
        self.geometry("560x900")
        self.font = ctk.CTkFont(size=FONT_SIZE)

        self.ser         = None
        self.relay_state = [0] * MCP_COUNT
        self.present     = []
        self.k17         = False
        self.labels      = {(d, f"SIG_IN{n}"): ctk.StringVar() for d in range(MCP_COUNT) for n in range(1, 5)}
        self.delays      = {(d, f"K{k}"): ctk.StringVar(value=PULSE_MS) for d in range(MCP_COUNT) for k in range(1, 17)}
        for n in range(1, 5):
            self.labels[(SHARED_DEV, f"SIG_OUT{n}")] = ctk.StringVar()
        self.labels[(SHARED_DEV, "K17")] = ctk.StringVar()
        self.delays[(SHARED_DEV, "K17")] = ctk.StringVar(value=PULSE_MS)
        self.load_labels()

        f = self.font
        h = WIDGET_H
        top = ctk.CTkFrame(self, fg_color=T["panel"])
        top.pack(fill="x", padx=4, pady=(4, 2))
        ctk.CTkLabel(top, text="Port", height=h, font=f).pack(side="left", padx=(6, 2))
        self.port_combo = ctk.CTkComboBox(top, width=90, height=h, font=f, dropdown_font=f, values=[])
        self.port_combo.pack(side="left", padx=2, pady=3)
        ctk.CTkButton(top, text="Refresh", width=56, height=h, font=f, command=self.refresh_ports).pack(side="left", padx=2)
        self.connect_btn = ctk.CTkButton(top, text="Connect", width=76, height=h, font=f, command=self.toggle_connect)
        self.connect_btn.pack(side="left", padx=2)
        self.detect_btn = ctk.CTkButton(top, text="Auto Detect", width=76, height=h, font=f, command=self.auto_detect)
        self.detect_btn.pack(side="left", padx=2)
        self.status_label = ctk.CTkLabel(top, text="Disconnected", height=h, font=f)
        self.status_label.pack(side="left", padx=8)

        cmds = ctk.CTkFrame(self, fg_color=T["panel"])
        cmds.pack(fill="x", padx=4, pady=2)
        for text, cmd in (("SCAN", "SCAN"), ("INIT", "INIT"), ("GET", "GET"), ("ALL OFF", "ALLOFF")):
            ctk.CTkButton(cmds, text=text, width=60, height=h, font=f,
                          command=lambda c=cmd: self.send(c)).pack(side="left", padx=2, pady=3)
        ctk.CTkButton(cmds, text="Save Labels", width=76, height=h, font=f, command=self.save_labels).pack(side="right", padx=2)
        self.col_lock = ctk.BooleanVar(value=True)
        self.row_lock = ctk.BooleanVar(value=True)
        for name, var in (("Column", self.col_lock), ("Row", self.row_lock)):
            ctk.CTkSwitch(cmds, text=f"{name} lock", variable=var, font=f, height=h, width=0,
                          switch_width=32, switch_height=16,
                          command=lambda n=name, v=var: self.toggle_interlock(n, v)).pack(side="left", padx=(8, 0))

        k17 = ctk.CTkFrame(self, fg_color=T["panel"])
        k17.pack(fill="x", padx=4, pady=2)
        ctk.CTkLabel(k17, text="K17 (DAC1 -> sig_in_4)", height=h, font=f).pack(side="left", padx=6, pady=3)
        self.k17_btn = ctk.CTkButton(k17, text="OPEN", width=70, height=h, font=f, fg_color=COLOR_OFF, command=self.toggle_k17)
        self.k17_btn.pack(side="left", padx=2)
        ctk.CTkEntry(k17, width=140, height=h, font=f, textvariable=self.labels[(SHARED_DEV, "K17")]).pack(side="left", padx=4)
        ctk.CTkButton(k17, text="Pulse", width=40, height=h, font=f, command=self.pulse_k17).pack(side="left", padx=2)
        ctk.CTkEntry(k17, width=42, height=h, font=f, textvariable=self.delays[(SHARED_DEV, "K17")]).pack(side="left", padx=(2, 1))
        ctk.CTkLabel(k17, text="ms", height=h, font=f).pack(side="left")

        self.out_header = ctk.CTkFrame(self, height=2 * h + 8, fg_color=T["panel"])
        self.out_header.pack(fill="x", padx=4, pady=(2, 0))
        self.out_cells = []
        for n in range(1, 5):
            name = f"SIG_OUT{n}"
            cell = ctk.CTkFrame(self.out_header, fg_color="transparent")
            ctk.CTkLabel(cell, text=name, height=h - 4, font=f).pack()
            ctk.CTkEntry(cell, width=70, height=h, font=f, textvariable=self.labels[(SHARED_DEV, name)]).pack()
            self.out_cells.append(cell)
        self.out_header.bind("<Configure>", self.align_header, add="+")

        self.matrix = MatrixView(self, self)
        self.matrix.pack(fill="both", expand=True, padx=4, pady=(0, 2))
        self.matrix.cv.bind("<Configure>", self.align_header, add="+")

        self.log_box = ctk.CTkTextbox(self, height=120, font=ctk.CTkFont(family="Consolas", size=10), fg_color=T["canvas"])
        self.log_box.pack(fill="x", padx=4, pady=(2, 4))
        self.log_box.tag_config("tx", foreground="#5DADE2")
        self.log_box.tag_config("err", foreground="#FF5555")
        self.log_box.tag_config("info", foreground="#AAAAAA")

        self.refresh_ports()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(200, self.auto_detect)

    def log(self, text, tag=None):
        self.log_box.insert("end", f"{datetime.now():%H:%M:%S.%f}"[:-3] + f"  {text}\n", tag)
        self.log_box.see("end")

    def refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_combo.configure(values=ports)
        if ports and self.port_combo.get() not in ports:
            self.port_combo.set(ports[0])

    def toggle_connect(self):
        if self.ser:
            self.disconnect()
            return
        self.connect(self.port_combo.get(), False)

    def auto_detect(self):
        if self.ser:
            self.disconnect()
        ports  = list(serial.tools.list_ports.comports())
        nanos  = [p.device for p in ports if (p.vid, p.pid) in NANO_USB_IDS or p.vid == ARDUINO_VID]
        others = [p.device for p in ports if p.device not in nanos]
        if not ports:
            self.log("ERR: auto-detect -- no COM ports found", "err")
            return
        self.refresh_ports()
        self.probe_queue  = nanos + others
        self.probe_failed = []
        self.probe_retry  = False
        self.log(f"Auto-detect: probing {', '.join(self.probe_queue)}", "info")
        self.probe_next()

    def connect(self, port, probing):
        try:
            self.ser = serial.Serial(port, BAUD, timeout=0.1)
        except serial.SerialException as e:
            self.log(f"ERR: {e}", "err")
            if probing:
                if not self.probe_retry:
                    self.probe_failed.append(port)
                self.probe_next()
            return
        self.detect_btn.configure(state="disabled")
        self.connect_btn.configure(text="Disconnect")
        self.status_label.configure(text=f"{port} -- waiting for Nano boot")
        self.log(f"Opened {port}, waiting for Nano boot", "info")
        # Opening the port toggles DTR, which resets the Nano; the bootloader must finish first
        self.after(BOOT_WAIT, lambda: self.after_boot(probing))

    def probe_next(self):
        if not self.probe_queue and self.probe_failed and not self.probe_retry:
            self.log(f"Auto-detect: retrying {', '.join(self.probe_failed)}", "info")
            self.probe_queue = self.probe_failed
            self.probe_retry = True
        if self.probe_queue:
            self.connect(self.probe_queue.pop(0), True)
        else:
            self.log(f"ERR: auto-detect -- no {FW_ID} found", "err")

    def after_boot(self, probing):
        if not self.ser:
            return
        self.handle(self.read_reply(STARTUP_WAIT))
        lines = self.send("*IDN?")
        if not self.ser:
            return
        if not lines or FW_ID not in lines:
            self.log(f"ERR: {self.ser.port} is not a relay matrix (expected '{FW_ID}')", "err")
            self.disconnect()
            if probing:
                self.probe_next()
            return
        self.port_combo.set(self.ser.port)
        self.detect_btn.configure(state="normal")
        self.log(f"Found {FW_ID} on {self.ser.port}", "info")
        # Startup scan table is missed if the Nano did not reset on port open
        if not self.present:
            self.send("SCAN")
        self.send("GET")

    def disconnect(self):
        self.ser.close()
        self.ser = None
        self.present = []
        self.rebuild_matrix()
        self.detect_btn.configure(state="normal")
        self.connect_btn.configure(text="Connect")
        self.status_label.configure(text="Disconnected")
        self.log("Disconnected", "info")

    def read_reply(self, wait=REPLY_WAIT):
        lines = []
        start = time.time()
        while True:
            raw = self.ser.readline()
            if raw:
                line = raw.decode(errors="replace").strip()
                if line:
                    lines.append(line)
                    self.log(f"RX  {line}", "err" if line.startswith("ERR") else None)
                continue
            if lines or time.time() - start > wait:
                break
        return lines

    def send(self, cmd, wait=REPLY_WAIT):
        if not self.ser:
            self.log("ERR: not connected", "err")
            return
        self.log(f"TX  {cmd}", "tx")
        self.update_idletasks()
        try:
            self.ser.write(f"{cmd}\n".encode())
            lines = self.read_reply(wait)
        except serial.SerialException as e:
            self.log(f"ERR: {e}", "err")
            self.disconnect()
            return
        if not lines:
            self.log(f"ERR: no reply to '{cmd}'", "err")
        self.handle(lines)
        return lines

    def handle(self, lines):
        scanned = {}
        for line in lines:
            if m := RE_OK.match(line):
                self.set_state(int(m[1]), int(m[2], 16))
            elif m := RE_GET.search(line):
                dev, olat, gpio = int(m[1]), int(m[2], 16), int(m[3], 16)
                if olat != gpio:
                    self.log(f"WARN: dev {dev} OLAT {olat:04X} != GPIO {gpio:04X}", "err")
                self.set_state(dev, olat, gpio)
            elif m := RE_SCAN.match(line):
                scanned[int(m[1])] = m[2]
            elif m := RE_K17.search(line):
                self.set_k17(m[1] == "CLOSED")
        if scanned:
            for dev, status in scanned.items():
                if status == "INIT":
                    self.relay_state[dev] = 0
            self.present = [d for d, s in scanned.items() if s in ("INIT", "OK")]
            self.rebuild_matrix()

    def rebuild_matrix(self):
        self.matrix.rebuild(self.present)
        if self.ser:
            devs = ",".join(str(d) for d in self.present) or "none"
            self.status_label.configure(text=f"{self.ser.port} -- devices: {devs}")

    # Header lives outside the scrolling canvas, so each SIG_OUT cell is centred over its matrix column
    def align_header(self, _=None):
        cv = self.matrix.cv
        if cv.winfo_width() <= 1:
            return
        scale = ctk.ScalingTracker.get_widget_scaling(self)
        for c, cell in enumerate(self.out_cells):
            x = (cv.winfo_rootx() - self.out_header.winfo_rootx()) / scale + MatrixView.col_x(c)
            cell.place(x=x, rely=0.5, anchor="center")

    def set_state(self, dev, olat, gpio=None):
        self.relay_state[dev] = olat
        self.matrix.update_state(dev, gpio)

    def set_k17(self, closed):
        self.k17 = closed
        self.k17_btn.configure(text="CLOSED" if closed else "OPEN", fg_color=COLOR_ON if closed else COLOR_OFF)

    # SIG_OUT columns are a shared bus across all devices; two closed relays in one column tie two SIG_IN sources together.
    # A SIG_IN row closed onto two columns ties two SIG_OUT buses together.
    def interlock_conflict(self, dev, mask):
        states      = {d: self.relay_state[d] for d in self.present}
        added       = mask & ~states.get(dev, 0)
        states[dev] = mask
        if self.col_lock.get():
            for c in range(4):
                if not added & (0x1111 << c):
                    continue
                hits = [(d, r * 4 + c + 1) for d, st in states.items() for r in range(4) if st >> (r * 4 + c) & 1]
                if len(hits) > 1:
                    who = ", ".join(f"Dev {d} K{k} (SIG_IN{d * 4 + (k - 1) // 4 + 1})" for d, k in hits)
                    self.log(f"BLOCKED: column interlock -- SIG_OUT{c + 1} would connect {who}", "err")
                    return True
        if self.row_lock.get():
            for r in range(4):
                if not added & (0xF << (r * 4)):
                    continue
                hits = [r * 4 + c + 1 for c in range(4) if mask >> (r * 4 + c) & 1]
                if len(hits) > 1:
                    who = ", ".join(f"Dev {dev} K{k} (SIG_OUT{(k - 1) % 4 + 1})" for k in hits)
                    self.log(f"BLOCKED: row interlock -- SIG_IN{dev * 4 + r + 1} would connect {who}", "err")
                    return True
        return False

    def set_relays(self, dev, mask):
        if not self.interlock_conflict(dev, mask):
            self.send(f"SET {mask:04X} {dev}")

    def toggle_interlock(self, name, var):
        self.log(f"{name} interlock {'ON' if var.get() else 'OFF'}", "info")

    def toggle_relay(self, dev, k):
        self.set_relays(dev, self.relay_state[dev] ^ (1 << (k - 1)))


    def toggle_k17(self):
        self.send(f"K17 {0 if self.k17 else 1}")

    def pulse_delay(self, key):
        text = self.delays[key].get().strip()
        try:
            delay = int(text)
        except ValueError:
            delay = -1
        if not 1 <= delay <= PULSE_MAX:
            self.log(f"ERR: pulse delay '{text}' must be 1-{PULSE_MAX} ms", "err")
            return None
        return delay

    # Nano times the pulse and only replies when it ends, so the reply wait must cover the delay
    def pulse_relay(self, dev, k):
        delay = self.pulse_delay((dev, f"K{k}"))
        if delay is not None and not self.interlock_conflict(dev, self.relay_state[dev] | 1 << (k - 1)):
            self.send(f"PULSE {k} {delay} {dev}", wait=delay / 1000 + REPLY_WAIT)

    def pulse_k17(self):
        delay = self.pulse_delay((SHARED_DEV, "K17"))
        if delay is not None:
            self.send(f"PULSE 17 {delay}", wait=delay / 1000 + REPLY_WAIT)

    def load_labels(self):
        if not os.path.exists(LABEL_FILE):
            return
        with open(LABEL_FILE, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                key = (int(row["dev"]), row.get("item"))
                if key in self.labels:
                    self.labels[key].set(row["label"])
                elif key[1].startswith("SIG_OUT"):
                    shared = self.labels[(SHARED_DEV, key[1])]
                    if not shared.get():
                        shared.set(row["label"])
                if key in self.delays:
                    self.delays[key].set(row["delay_ms"] or PULSE_MS)

    def save_labels(self):
        with open(LABEL_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["dev", "item", "label", "delay_ms"])
            writer.writeheader()
            for key in sorted(self.labels.keys() | self.delays.keys()):
                label = self.labels[key].get().strip() if key in self.labels else ""
                delay = self.delays[key].get().strip() if key in self.delays else ""
                if label or delay not in ("", PULSE_MS):
                    writer.writerow({"dev": key[0], "item": key[1], "label": label, "delay_ms": delay})
        self.log(f"Labels saved to {os.path.basename(LABEL_FILE)}", "info")

    def on_close(self):
        self.save_labels()
        if self.ser:
            self.ser.close()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
