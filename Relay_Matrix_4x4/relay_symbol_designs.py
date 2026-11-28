import math
import tkinter as tk
import customtkinter as ctk

BG       = "#2B2B2B"
WIRE     = "#555555"
OFF      = "#8A8A8A"
ON       = "#3CCB7F"
ON_FILL  = "#2E8B57"
TILE_OFF = "#3A3A3A"
LBL_W    = 48
HDR_H    = 18
CELL_W   = 46
CELL_H   = 34
COLS     = 4
SMALL    = ("Segoe UI", 7)
TEXT     = ("Segoe UI", 8)
MONO     = ("Consolas", 9)


def k_label(cv, cx, y, k, on):
    cv.create_text(cx, y, text=f"K{k}", font=SMALL, fill=ON if on else OFF)


def d_switch_h(cv, cx, cy, k, on):
    col = ON if on else OFF
    k_label(cv, cx, cy - 10, k, on)
    cv.create_line(cx - 12, cy + 5, cx + 12, cy + 5 if on else cy - 4, fill=col, width=2)
    for x in (cx - 12, cx + 12):
        cv.create_oval(x - 2, cy + 3, x + 2, cy + 7, fill=col, outline=col)


def d_cross_dot(cv, cx, cy, k, on, live=False):
    if on:
        cv.create_oval(cx - 6, cy - 6, cx + 6, cy + 6, fill=ON, outline=ON)
    elif live:
        cv.create_oval(cx - 3, cy - 3, cx + 3, cy + 3, fill=ON, outline=ON)
    else:
        cv.create_oval(cx - 3, cy - 3, cx + 3, cy + 3, fill=BG, outline=OFF)
    cv.create_text(cx + 12, cy - 9, text=f"{k}", font=SMALL, fill=ON if on else OFF)


def d_cross_switch(cv, cx, cy, k, on):
    col = ON if on else OFF
    if on:
        cv.create_line(cx, cy - CELL_H // 2, cx, cy, fill=ON, width=2)
        cv.create_line(cx - CELL_W // 2, cy, cx + CELL_W // 2, cy, fill=ON, width=2)
        cv.create_oval(cx - 3, cy - 3, cx + 3, cy + 3, fill=ON, outline=ON)
    else:
        cv.create_line(cx, cy - 7, cx + 6, cy - 2, fill=OFF, width=2)
    cv.create_text(cx + 13, cy - 9, text=f"{k}", font=SMALL, fill=col)


def d_tile_icon(cv, cx, cy, k, on):
    cv.create_rectangle(cx - 20, cy - 13, cx + 20, cy + 13, fill=ON_FILL if on else TILE_OFF, outline="")
    cv.create_text(cx - 10, cy, text=f"K{k}", font=SMALL, fill="white")
    cv.create_line(cx + 2, cy + 4, cx + 16, cy + 4 if on else cy - 4, fill="white", width=2)
    for x in (cx + 2, cx + 16):
        cv.create_oval(x - 2, cy + 2, x + 2, cy + 6, fill="white", outline="white")


def d_led(cv, cx, cy, k, on):
    cv.create_oval(cx - 16, cy - 5, cx - 6, cy + 5, fill=ON if on else TILE_OFF, outline=ON if on else OFF)
    cv.create_text(cx + 6, cy, text=f"K{k}", font=TEXT, fill="white" if on else OFF)


def d_pill(cv, cx, cy, k, on):
    k_label(cv, cx, cy - 10, k, on)
    x0, y0, x1, y1 = cx - 11, cy, cx + 11, cy + 11
    fill = ON_FILL if on else TILE_OFF
    cv.create_oval(x0, y0, x0 + 11, y1, fill=fill, outline="")
    cv.create_oval(x1 - 11, y0, x1, y1, fill=fill, outline="")
    cv.create_rectangle(x0 + 5, y0, x1 - 5, y1, fill=fill, outline="")
    kx = x1 - 6 if on else x0 + 6
    cv.create_oval(kx - 4, cy + 1.5, kx + 4, cy + 9.5, fill="white", outline="")


def d_glyph(cv, cx, cy, k, on):
    k_label(cv, cx, cy - 9, k, on)
    cv.create_text(cx, cy + 5, text="-o--o-" if on else "-o/ o-", font=MONO, fill=ON if on else OFF)


def d_checkbox(cv, cx, cy, k, on):
    cv.create_rectangle(cx - 16, cy - 5, cx - 6, cy + 5, fill=ON_FILL if on else BG, outline=ON if on else OFF)
    if on:
        cv.create_line(cx - 14, cy, cx - 12, cy + 3, cx - 8, cy - 3, fill="white", width=2)
    cv.create_text(cx + 6, cy, text=f"K{k}", font=TEXT, fill="white" if on else OFF)


def d_switch_v(cv, cx, cy, k, on):
    col = ON if on else OFF
    cv.create_text(cx - 13, cy, text=f"K{k}", font=SMALL, fill=col)
    cv.create_line(cx + 4, cy + 10, cx + 4 if on else cx + 12, cy - 9 if on else cy - 7, fill=col, width=2)
    for y in (cy - 10, cy + 10):
        cv.create_oval(cx + 2, y - 2, cx + 6, y + 2, fill=col, outline=col)


def d_tile_min(cv, cx, cy, k, on):
    cv.create_rectangle(cx - 17, cy - 12, cx + 17, cy + 12,
                        fill=ON_FILL if on else BG, outline=ON if on else WIRE, width=1)
    cv.create_text(cx, cy, text=f"K{k}", font=TEXT, fill="white" if on else OFF)


DESIGNS = [
    ("1. Switch (horizontal)",       d_switch_h,     False),
    ("2. Crosspoint dot",            d_cross_dot,    True),
    ("3. Crosspoint switch",         d_cross_switch, True),
    ("4. Tile + switch icon",        d_tile_icon,    False),
    ("5. LED + label",               d_led,          False),
    ("6. Pill toggle",               d_pill,         False),
    ("7. Text glyph -o/ o-",         d_glyph,        False),
    ("8. Checkbox",                  d_checkbox,     False),
    ("9. Switch (vertical)",         d_switch_v,     False),
    ("10. Minimal tile",             d_tile_min,     False),
    ("11. Crosspoint dot + path",    d_cross_dot,    "path"),
]


class MatrixDemo(ctk.CTkFrame):
    def __init__(self, master, title, draw, wires):
        super().__init__(master)
        self.draw  = draw
        self.wires = wires
        self.state = {1, 6, 11, 16}
        ctk.CTkLabel(self, text=title, font=ctk.CTkFont(size=12, weight="bold"), height=20).pack(anchor="w", padx=6, pady=(4, 0))
        self.cv = tk.Canvas(self, width=LBL_W + COLS * CELL_W + 4, height=HDR_H + 4 * CELL_H + 4,
                            bg=BG, highlightthickness=0)
        self.cv.pack(padx=6, pady=(2, 6))
        self.cv.bind("<Button-1>", self.click)
        self.redraw()

    def centre(self, r, c):
        return LBL_W + c * CELL_W + CELL_W // 2, HDR_H + r * CELL_H + CELL_H // 2

    def redraw(self):
        cv = self.cv
        cv.delete("all")
        path     = self.wires == "path"
        on_rows  = {(k - 1) // 4 for k in self.state} if path else set()
        on_cols  = {(k - 1) % 4 for k in self.state} if path else set()
        for c in range(COLS):
            cv.create_text(LBL_W + c * CELL_W + CELL_W // 2, HDR_H // 2, text=f"OUT{c + 1}", font=SMALL,
                           fill=ON if c in on_cols else OFF)
        for r in range(4):
            cv.create_text(4, HDR_H + r * CELL_H + CELL_H // 2, text=f"IN{r + 1}", font=SMALL,
                           fill=ON if r in on_rows else OFF, anchor="w")
        if self.wires:
            for r in range(4):
                y = self.centre(r, 0)[1]
                cv.create_line(LBL_W - 18, y, LBL_W + COLS * CELL_W, y, fill=WIRE)
            for c in range(COLS):
                x = self.centre(0, c)[0]
                cv.create_line(x, HDR_H, x, HDR_H + 4 * CELL_H, fill=WIRE)
        if path:
            for k in self.state:
                x, y = self.centre((k - 1) // 4, (k - 1) % 4)
                cv.create_line(LBL_W - 18, y, x, y, fill=ON, width=2)
                cv.create_line(x, HDR_H, x, y, fill=ON, width=2)
        row_end = {}
        col_end = {}
        for k in self.state:
            r, c       = (k - 1) // 4, (k - 1) % 4
            row_end[r] = max(row_end.get(r, -1), c)
            col_end[c] = max(col_end.get(c, -1), r)
        for r in range(4):
            for c in range(COLS):
                k = r * 4 + c + 1
                if path:
                    live = c <= row_end.get(r, -1) or r <= col_end.get(c, -1)
                    self.draw(cv, *self.centre(r, c), k, k in self.state, live)
                else:
                    self.draw(cv, *self.centre(r, c), k, k in self.state)

    def click(self, e):
        c = (e.x - LBL_W) // CELL_W
        r = (e.y - HDR_H) // CELL_H
        if 0 <= c < COLS and 0 <= r < 4:
            self.state ^= {r * 4 + c + 1}
            self.redraw()


NET_COLORS = ["#E08A2E", "#3CCB7F", "#4A90E2", "#B07CD8", "#E0C040", "#A8D86E", "#40C8C8", "#9DA8FF"]
SHORT      = "#FF4040"
# Relay output node -> column bus 0R link, from Schematic_relay_matrix_2026-11-03.pdf sheet "Relays"
OUT_R      = {1: "R11", 2: "R13", 3: "R19", 4: "R23", 5: "R12", 6: "R16", 7: "R20", 8: "R24",
              9: "R14", 10: "R17", 11: "R21", 12: "R25", 13: "R37", 14: "R18", 15: "R22", 16: "R26"}
BUS_NAMES  = ["VOUT_A", "VOUT_B", "VOUT_C", "VOUT_D", "", "", "", ""]
BUS_DEVS   = 2
B_LBL_W    = 112
B_HDR_H    = 18


class BusDemo(ctk.CTkFrame):
    TITLE  = "12. Net colours + shared bus (hover for nets)"
    CELL_W = 60
    CELL_H = 30
    SHOW_R = True

    def __init__(self, master):
        super().__init__(master)
        self.state = {(0, 7), (0, 10)}
        ctk.CTkLabel(self, text=self.TITLE,
                     font=ctk.CTkFont(size=12, weight="bold"), height=20).pack(anchor="w", padx=6, pady=(4, 0))
        self.cv = tk.Canvas(self, width=B_LBL_W + 4 * self.CELL_W + 10, height=B_HDR_H + BUS_DEVS * 4 * self.CELL_H + 4,
                            bg=BG, highlightthickness=0, cursor="hand2")
        self.cv.pack(anchor="w", padx=6, pady=2)
        self.tip = ctk.CTkLabel(self, text="", font=ctk.CTkFont(family="Consolas", size=11), height=64,
                                anchor="w", justify="left")
        self.tip.pack(fill="x", padx=6, pady=(0, 6))
        self.cv.bind("<Button-1>", self.click)
        self.cv.bind("<Motion>", self.hover)
        self.cv.bind("<Leave>", lambda _: self.tip.configure(text=""))
        self.redraw()

    def x(self, c):
        return B_LBL_W + c * self.CELL_W + self.CELL_W // 2

    def y(self, g):
        return B_HDR_H + g * self.CELL_H + self.CELL_H // 2

    def hit(self, e):
        c = (e.x - B_LBL_W) // self.CELL_W
        g = (e.y - B_HDR_H) // self.CELL_H
        if 0 <= c < 4 and 0 <= g < BUS_DEVS * 4:
            return g // 4, (g % 4) * 4 + c + 1
        return None

    def analyse(self):
        row_end = {}
        drivers = {}
        for dev, k in self.state:
            g, c       = dev * 4 + (k - 1) // 4, (k - 1) % 4
            row_end[g] = max(row_end.get(g, -1), c)
            drivers.setdefault(c, []).append(g)
        col_end = {c: max(gs) for c, gs in drivers.items()}
        col_net = {c: NET_COLORS[gs[0] % 8] if len(gs) == 1 else SHORT for c, gs in drivers.items()}
        return row_end, drivers, col_end, col_net

    def redraw(self):
        cv = self.cv
        cv.delete("all")
        row_end, _, col_end, col_net = self.analyse()
        rows  = BUS_DEVS * 4
        x_end = B_LBL_W + 4 * self.CELL_W
        for c in range(4):
            cv.create_text(self.x(c), B_HDR_H // 2, text=f"SIG_OUT{c + 1}", font=SMALL, fill=col_net.get(c, OFF))
            cv.create_line(self.x(c), B_HDR_H, self.x(c), self.y(rows - 1) + self.CELL_H // 2, fill=WIRE)
        for g in range(rows):
            y   = self.y(g)
            net = NET_COLORS[g % 8]
            if g and g % 4 == 0:
                cv.create_line(0, y - self.CELL_H // 2, B_LBL_W - 10, y - self.CELL_H // 2, fill="#444444", dash=(3, 3))
            cv.create_text(4, y, text=f"SIG_IN{g + 1}", font=TEXT, anchor="w", fill=net if g in row_end else OFF)
            cv.create_text(62, y, text=BUS_NAMES[g], font=SMALL, anchor="w", fill=net if g in row_end else OFF)
            cv.create_line(B_LBL_W - 8, y, x_end, y, fill=WIRE)
        for g, c in row_end.items():
            cv.create_line(B_LBL_W - 8, self.y(g), self.x(c), self.y(g), fill=NET_COLORS[g % 8], width=2)
        for c, g in col_end.items():
            cv.create_line(self.x(c), B_HDR_H, self.x(c), self.y(g), fill=col_net[c], width=2)
        for g in range(rows):
            dev, r = divmod(g, 4)
            for c in range(4):
                k    = r * 4 + c + 1
                x, y = self.x(c), self.y(g)
                if (dev, k) in self.state:
                    cv.create_oval(x - 6, y - 6, x + 6, y + 6, fill=NET_COLORS[g % 8], outline="")
                elif c in col_end:
                    cv.create_oval(x - 4, y - 4, x + 4, y + 4, fill=BG, outline=SHORT, width=2)
                elif c <= row_end.get(g, -1):
                    cv.create_oval(x - 3, y - 3, x + 3, y + 3, fill=NET_COLORS[g % 8], outline="")
                else:
                    cv.create_oval(x - 3, y - 3, x + 3, y + 3, fill=BG, outline=OFF)
                cv.create_text(x + 13, y - 9, text=str(k), font=SMALL, fill=OFF)

    def click(self, e):
        key = self.hit(e)
        if key:
            self.state ^= {key}
            self.redraw()
            self.hover(e)

    def hover(self, e):
        key = self.hit(e)
        if not key:
            self.tip.configure(text="")
            return
        dev, k = key
        r, c   = (k - 1) // 4, (k - 1) % 4
        g      = dev * 4 + r
        in_net  = f"sig_in_{r + 1}" if c == 0 else f"sig_in_k{k}"
        out_net = f"sig_out_{c + 1}" if r == 0 else f"sig_out_k{k}"
        mcp     = f"GPA{k - 1}" if k <= 8 else f"GPB{k - 9}"
        uln     = f"U5 ch{k}" if k <= 8 else f"U6 ch{k - 8}"
        lines   = [f"Dev {dev} K{k}: SIG_IN{g + 1} -> SIG_OUT{c + 1}",
                   f"{in_net} -> {out_net} -> " + (f"{OUT_R[k]} -> " if self.SHOW_R else "") + f"bus {c + 1}",
                   f"coil IO_{c + 1}{r + 1}  {mcp}  {uln}"]
        _, drivers, _, _ = self.analyse()
        others = [d for d in drivers.get(c, []) if d != g]
        if others and (dev, k) not in self.state:
            lines.append(f"!! closing shorts SIG_IN{g + 1} to " + ", ".join(f"SIG_IN{d + 1}" for d in others))
        elif len(drivers.get(c, [])) > 1:
            lines.append("!! SHORT: " + ", ".join(f"SIG_IN{d + 1}" for d in drivers[c]))
        self.tip.configure(text="\n".join(lines))


# Layout follows relay_matrix_diagram.html (0R links omitted): each relay switches its row node up to an
# output node, and the output node is hard-wired to the column bus, so it always carries the bus net
class SchematicDemo(BusDemo):
    TITLE  = "13. Schematic style (hover for nets)"
    CELL_W = 84
    CELL_H = 52
    SHOW_R = False

    def node_x(self, c):
        return B_LBL_W + c * self.CELL_W + 24

    def bus_x(self, c):
        return B_LBL_W + c * self.CELL_W + 66

    def top_y(self, g):
        return B_HDR_H + g * self.CELL_H + 12

    def row_y(self, g):
        return B_HDR_H + g * self.CELL_H + self.CELL_H - 12

    def redraw(self):
        cv = self.cv
        cv.delete("all")
        row_end, _, col_end, col_net = self.analyse()
        rows   = BUS_DEVS * 4
        bottom = B_HDR_H + rows * self.CELL_H - 4
        for g in range(rows):
            y   = self.row_y(g)
            net = NET_COLORS[g % 8]
            if g and g % 4 == 0:
                sy = B_HDR_H + g * self.CELL_H
                cv.create_line(0, sy, B_LBL_W - 10, sy, fill="#444444", dash=(3, 3))
            cv.create_text(4, y, text=f"SIG_IN{g + 1}", font=TEXT, anchor="w", fill=net if g in row_end else OFF)
            cv.create_text(62, y, text=BUS_NAMES[g], font=SMALL, anchor="w", fill=net if g in row_end else OFF)
            cv.create_line(B_LBL_W - 8, y, self.node_x(3), y, fill=WIRE, width=2)
            if g in row_end:
                cv.create_line(B_LBL_W - 8, y, self.node_x(row_end[g]), y, fill=net, width=3)
            for c in range(3):
                x    = self.bus_x(c)
                live = row_end.get(g, -1) > c
                cv.create_rectangle(x - 6, y - 3, x + 6, y + 3, fill=BG, outline="")
                cv.create_arc(x - 6, y - 6, x + 6, y + 6, start=0, extent=180, style="arc",
                              outline=net if live else WIRE, width=3 if live else 2)
        for c in range(4):
            x = self.bus_x(c)
            cv.create_text(x, B_HDR_H // 2, text=f"SIG_OUT{c + 1}", font=SMALL, fill=col_net.get(c, OFF))
            cv.create_line(x, B_HDR_H, x, bottom, fill=WIRE, width=2)
            if c in col_end:
                cv.create_line(x, B_HDR_H, x, bottom, fill=col_net[c], width=3)
        for g in range(rows):
            dev, r = divmod(g, 4)
            for c in range(4):
                k      = r * 4 + c + 1
                nx, bx = self.node_x(c), self.bus_x(c)
                ty, ry = self.top_y(g), self.row_y(g)
                on     = (dev, k) in self.state
                rnet   = NET_COLORS[g % 8] if c <= row_end.get(g, -1) else OFF
                onet   = col_net.get(c, OFF)
                danger = not on and c in col_end
                cv.create_line(nx, ty, bx, ty, fill=onet if c in col_end else WIRE, width=2)
                cv.create_line(nx, ty, nx, ty + 8, fill=onet if c in col_end else WIRE, width=2)
                cv.create_line(nx, ry, nx, ry - 8, fill=rnet if rnet != OFF else WIRE, width=2)
                if on:
                    cv.create_line(nx, ry - 8, nx, ty + 8, fill=NET_COLORS[g % 8], width=3)
                else:
                    cv.create_line(nx, ry - 8, nx + 11, ty + 10, fill=SHORT if danger else OFF, width=2)
                for px, py, col in ((nx, ty, onet), (bx, ty, onet), (nx, ry, rnet)):
                    cv.create_oval(px - 3, py - 3, px + 3, py + 3, fill=col, outline="")
                cv.create_text(nx + 16, (ty + ry) // 2, text=f"K{k}", font=SMALL, anchor="w",
                               fill=NET_COLORS[g % 8] if on else SHORT if danger else OFF)


OPEN_ANGLE = math.radians(65)


# Fixed contact sits on the column bus, pivot on the row: closed blade is a 45 deg line from row to bus
class BladeDemo(SchematicDemo):
    TITLE  = "14. 45 deg blade (hover for nets)"
    # Small version: CELL 48x30, BLADE 16, BUS_OFF 32, ROW_OFF 8, DOT 2, HOP 4
    CELL_W  = 84
    CELL_H  = 52
    BLADE   = 28
    BUS_OFF = 56
    ROW_OFF = 14
    DOT     = 3
    HOP     = 6

    def bus_x(self, c):
        return B_LBL_W + c * self.CELL_W + self.BUS_OFF

    def pivot_x(self, c):
        return self.bus_x(c) - self.BLADE

    def row_y(self, g):
        return B_HDR_H + g * self.CELL_H + self.CELL_H - self.ROW_OFF

    def redraw(self):
        cv = self.cv
        cv.delete("all")
        row_end, _, col_end, col_net = self.analyse()
        rows   = BUS_DEVS * 4
        bottom = B_HDR_H + rows * self.CELL_H - 4
        for g in range(rows):
            y   = self.row_y(g)
            net = NET_COLORS[g % 8]
            if g and g % 4 == 0:
                sy = B_HDR_H + g * self.CELL_H
                cv.create_line(0, sy, B_LBL_W - 10, sy, fill="#444444", dash=(3, 3))
            cv.create_text(4, y, text=f"SIG_IN{g + 1}", font=TEXT, anchor="w", fill=net if g in row_end else OFF)
            cv.create_text(62, y, text=BUS_NAMES[g], font=SMALL, anchor="w", fill=net if g in row_end else OFF)
            cv.create_line(B_LBL_W - 8, y, self.pivot_x(3), y, fill=WIRE, width=2)
            if g in row_end:
                cv.create_line(B_LBL_W - 8, y, self.pivot_x(row_end[g]), y, fill=net, width=3)
            for c in range(3):
                x    = self.bus_x(c)
                live = row_end.get(g, -1) > c
                hp = self.HOP
                cv.create_rectangle(x - hp, y - 3, x + hp, y + 3, fill=BG, outline="")
                cv.create_arc(x - hp, y - hp, x + hp, y + hp, start=0, extent=180, style="arc",
                              outline=net if live else WIRE, width=2)
        for c in range(4):
            x = self.bus_x(c)
            cv.create_text(x, B_HDR_H // 2, text=f"SIG_OUT{c + 1}", font=SMALL, fill=col_net.get(c, OFF))
            cv.create_line(x, B_HDR_H, x, bottom, fill=col_net.get(c, WIRE), width=3 if c in col_end else 2)
        for g in range(rows):
            dev, r = divmod(g, 4)
            for c in range(4):
                k      = r * 4 + c + 1
                px, bx = self.pivot_x(c), self.bus_x(c)
                ry     = self.row_y(g)
                cy     = ry - self.BLADE
                on     = (dev, k) in self.state
                rnet   = NET_COLORS[g % 8] if c <= row_end.get(g, -1) else OFF
                danger = not on and c in col_end
                if on:
                    cv.create_line(px, ry, bx, cy, fill=NET_COLORS[g % 8], width=3)
                else:
                    tx = px + self.BLADE * math.sqrt(2) * math.cos(OPEN_ANGLE)
                    ty = ry - self.BLADE * math.sqrt(2) * math.sin(OPEN_ANGLE)
                    cv.create_line(px, ry, tx, ty, fill=SHORT if danger else OFF, width=2)
                d = self.DOT
                cv.create_oval(px - d, ry - d, px + d, ry + d, fill=rnet, outline="")
                cv.create_oval(bx - d, cy - d, bx + d, cy + d, fill=col_net.get(c, OFF), outline="")
                cv.create_text(px - 4, ry - self.BLADE // 2, text=f"K{k}", font=SMALL, anchor="e",
                               fill=NET_COLORS[g % 8] if on else SHORT if danger else OFF)


if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    app = ctk.CTk()
    app.title("Relay symbol designs -- click relays to toggle")
    for i, (title, draw, wires) in enumerate(DESIGNS):
        MatrixDemo(app, title, draw, wires).grid(row=i // 4, column=i % 4, padx=4, pady=4, sticky="n")
    BusDemo(app).grid(row=0, column=4, rowspan=3, padx=4, pady=4, sticky="n")
    SchematicDemo(app).grid(row=0, column=5, rowspan=3, padx=4, pady=4, sticky="n")
    BladeDemo(app).grid(row=0, column=6, rowspan=3, padx=4, pady=4, sticky="n")
    app.mainloop()
