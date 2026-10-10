import tkinter as tk
from tkinter import ttk, messagebox
import pyvisa
import threading
import time


class VisaDeviceFinder:
    def __init__(self, root):
        self.root = root
        self.root.title("VISA Device Controller")
        self.root.geometry("760x700")

        try:
            self.rm = pyvisa.ResourceManager()
        except Exception as e:
            messagebox.showerror("VISA Error", str(e))
            self.root.destroy()
            return

        self.inst = None

        # ================= Notebook (Tabs) =================
        notebook = ttk.Notebook(root)
        notebook.pack(fill="both", expand=True)

        self.control_tab = ttk.Frame(notebook)
        self.calc_tab = ttk.Frame(notebook)

        # # Set background colors
        # self.control_tab.configure(background="#E3FFDD")   # Light blue
        # self.calc_tab.configure(background="#FFEEDD")      # Light peach/orange

        notebook.add(self.control_tab, text="Instrument Control")
        notebook.add(self.calc_tab, text="Load Tool Calculation")

        self.build_control_tab()
        self.build_calc_tab()

    # =====================================================
    # Instrument Control Tab
    # =====================================================
    def build_control_tab(self):
        frame = self.control_tab

        ttk.Label(frame, text="Available VISA Devices:").pack(pady=6)

        self.device_var = tk.StringVar()
        self.device_dropdown = ttk.Combobox(
            frame, textvariable=self.device_var, state="readonly", width=85
        )
        self.device_dropdown.pack()
        self.device_dropdown.bind("<<ComboboxSelected>>", self.on_device_selected)

        ttk.Button(frame, text="Search Devices", command=self.search_devices).pack(pady=4)

        ttk.Label(frame, text="Device ID:").pack(pady=(8, 2))
        self.idn_text = tk.StringVar(value="No device selected")
        ttk.Label(
            frame, textvariable=self.idn_text, wraplength=700, foreground="blue"
        ).pack()

        # Voltage frame
        vframe = ttk.LabelFrame(frame, text="Voltage Levels (mV)")
        vframe.pack(pady=8, fill="x", padx=10)

        ttk.Label(vframe, text="Voltage HIGH:").grid(row=0, column=0, padx=5, pady=6, sticky="w")
        self.high_var = tk.StringVar()
        ttk.Entry(vframe, textvariable=self.high_var, width=15).grid(row=0, column=1)
        ttk.Button(vframe, text="Send HIGH", command=self.send_high).grid(row=0, column=2, padx=10)

        ttk.Label(vframe, text="Voltage LOW:").grid(row=1, column=0, padx=5, pady=6, sticky="w")
        self.low_var = tk.StringVar()
        ttk.Entry(vframe, textvariable=self.low_var, width=15).grid(row=1, column=1)
        ttk.Button(vframe, text="Send LOW", command=self.send_low).grid(row=1, column=2, padx=10)

        # Output toggle frame
        oframe = ttk.LabelFrame(frame, text="Output Control")
        oframe.pack(pady=8, fill="x", padx=10)

        ttk.Label(oframe, text="Delay Time (seconds):").grid(row=0, column=0, padx=5, pady=8, sticky="w")
        self.delay_var = tk.StringVar()
        ttk.Entry(oframe, textvariable=self.delay_var, width=15).grid(row=0, column=1)
        ttk.Button(oframe, text="Toggle Output", command=self.toggle_output).grid(row=0, column=2, padx=15)

        # SCPI commands
        scpi_frame = ttk.LabelFrame(frame, text="Custom SCPI Commands")
        scpi_frame.pack(pady=10, fill="x", padx=10)

        self.scpi_vars = []
        for i in range(3):
            ttk.Label(scpi_frame, text=f"SCPI Command {i + 1}:").grid(
                row=i, column=0, padx=5, pady=6, sticky="w"
            )
            var = tk.StringVar()
            self.scpi_vars.append(var)
            ttk.Entry(scpi_frame, textvariable=var, width=60).grid(row=i, column=1, padx=5)
            ttk.Button(
                scpi_frame, text="Send", command=lambda v=var: self.send_scpi(v)
            ).grid(row=i, column=2, padx=10)

        # Response box
        ttk.Label(frame, text="SCPI Response:").pack(pady=(10, 2))
        self.response_text = tk.Text(frame, height=7, wrap="word", state="disabled")
        self.response_text.pack(fill="x", padx=10)

        ttk.Button(frame, text="Clear Response", command=self.clear_response).pack(pady=6)

    # =====================================================
    # Load Tool Calculation Tab
    # =====================================================
    def build_calc_tab(self):
        frame = self.calc_tab

        ttk.Label(frame, text="Load Tool Calculation", font=("Arial", 14, "bold"), background= "#DDEEFF").pack(pady=15)

        calc_frame = ttk.LabelFrame(frame, text="Inputs")
        calc_frame.pack(padx=20, pady=10, fill="x")

        ttk.Label(calc_frame, text="Voltage (mV):").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        self.calc_voltage_var = tk.StringVar()
        ttk.Entry(calc_frame, textvariable=self.calc_voltage_var, width=20).grid(row=0, column=1)

        ttk.Label(calc_frame, text="Current Ratio:").grid(row=1, column=0, padx=10, pady=10, sticky="w")
        self.calc_ratio_var = tk.StringVar()
        ttk.Entry(calc_frame, textvariable=self.calc_ratio_var, width=20).grid(row=1, column=1)

        ttk.Button(
            calc_frame, text="Calculate Load Current", command=self.calculate_load_current
        ).grid(row=2, column=0, columnspan=2, pady=15)

        result_frame = ttk.LabelFrame(frame, text="Result")
        result_frame.pack(padx=20, pady=10, fill="x")

        self.load_current_var = tk.StringVar(value="—")
        ttk.Label(
            result_frame,
            textvariable=self.load_current_var,
            font=("Arial", 12),
            foreground="green"
        ).pack(pady=15)

    # =====================================================
    # Functions
    # =====================================================
    def search_devices(self):
        try:
            devices = self.rm.list_resources()
            if devices:
                self.device_dropdown["values"] = devices
                self.device_var.set(devices[0])
                self.on_device_selected()
            else:
                self.device_dropdown["values"] = []
                self.device_var.set("")
                self.idn_text.set("No VISA devices found")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def on_device_selected(self, event=None):
        device = self.device_var.get()
        if not device:
            return
        try:
            if self.inst:
                self.inst.close()
            self.inst = self.rm.open_resource(device)
            self.inst.timeout = 3000
            self.idn_text.set(self.inst.query("*IDN?").strip())
        except Exception as e:
            self.idn_text.set(f"Could not read ID: {e}")
            self.inst = None

    def send_high(self):
        self.execute_scpi(f":VOLT:HIGH {self.high_var.get()} mV")

    def send_low(self):
        self.execute_scpi(f":VOLT:LOW {self.low_var.get()} mV")

    def toggle_output(self):
        try:
            delay = float(self.delay_var.get())
        except ValueError:
            messagebox.showerror("Invalid Input", "Delay must be numeric.")
            return

        threading.Thread(target=self._toggle_thread, args=(delay,), daemon=True).start()

    def _toggle_thread(self, delay):
        try:
            self.inst.write("OUTP ON")
            time.sleep(delay)
            self.inst.write("OUTP OFF")
            self.show_response("OUTP toggled successfully")
        except Exception as e:
            self.show_response(str(e))

    def send_scpi(self, var):
        cmd = var.get().strip()
        if cmd:
            self.execute_scpi(cmd)

    def execute_scpi(self, cmd):
        try:
            if cmd.endswith("?"):
                resp = self.inst.query(cmd).strip()
                self.show_response(f"> {cmd}\n{resp}")
            else:
                self.inst.write(cmd)
                self.show_response(f"> {cmd}\nOK")
        except Exception as e:
            self.show_response(f"ERROR: {e}")

    def show_response(self, text):
        self.response_text.config(state="normal")
        self.response_text.delete("1.0", tk.END)
        self.response_text.insert(tk.END, text)
        self.response_text.config(state="disabled")

    def clear_response(self):
        self.response_text.config(state="normal")
        self.response_text.delete("1.0", tk.END)
        self.response_text.config(state="disabled")

    def calculate_load_current(self):
        try:
            voltage = float(self.calc_voltage_var.get())
            ratio = float(self.calc_ratio_var.get())
            if ratio == 0:
                raise ValueError
            load_current = voltage / ratio
            self.load_current_var.set(f"Load Current = {load_current:.6f} A")
        except ValueError:
            messagebox.showerror("Invalid Input", "Enter valid numeric values.\n(Current Ratio ≠ 0)")


if __name__ == "__main__":
    root = tk.Tk()
    app = VisaDeviceFinder(root)
    root.mainloop()
