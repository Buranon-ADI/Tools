import tkinter as tk
from tkinter import ttk, messagebox
import pyvisa

class VisaDeviceFinderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("VISA Device Finder")
        self.root.geometry("500x700")  # slightly taller for new widgets
        self.style = ttk.Style()

        self.rm = pyvisa.ResourceManager()
        self.auto_readback_job = None  # to track scheduled job

        # Device selection dropdown
        ttk.Label(root, text="Select VISA Device:").pack(pady=5)
        self.device_var = tk.StringVar()
        self.device_combo = ttk.Combobox(root, textvariable=self.device_var, state="readonly", width=70)
        self.device_combo.pack()

        # IDN display
        ttk.Label(root, text="Selected Device ID:").pack(pady=(15, 0))
        self.idn_text = tk.Text(root, height=3, width=80, wrap="word")
        self.idn_text.pack(pady=5)
        self.idn_text.config(state="disabled")

        # --- Channel 1 Controls ---
        # self.frame_ch1 = ttk.LabelFrame(root, text="Channel 1 Controls")
        # self.frame_ch1.pack(padx=10, pady=10, fill="x")
        # Configure a new style for the LabelFrame label
        self.style.configure("RedBold.TLabelframe.Label", 
                        foreground="red",      # Text color red
                        font=("Arial", 16, "bold"))  # Bold and bigger font size 16

        # Create the LabelFrame and apply the new style
        self.frame_ch1 = ttk.LabelFrame(root, text="Channel 1: VREN = 3V", style="RedBold.TLabelframe")
        self.frame_ch1.pack(padx=20, pady=20)

        self.ch1_voltage_var = tk.StringVar()
        self.ch1_current_var = tk.StringVar()
        self.ch1_set_voltage_btn = ttk.Button(self.frame_ch1, text="Set Voltage", command=self.set_channel_1_voltage)
        self.ch1_set_current_btn = ttk.Button(self.frame_ch1, text="Set Current Limit", command=self.set_channel_1_current)
        self.ch1_on_btn = ttk.Button(self.frame_ch1, text="Output ON", command=lambda: self.set_output(self.device_var.get(), "1", True))
        self.ch1_off_btn = ttk.Button(self.frame_ch1, text="Output OFF", command=lambda: self.set_output(self.device_var.get(), "1", False))

        ttk.Label(self.frame_ch1, text="Voltage (V):").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        self.ch1_voltage_entry = ttk.Entry(self.frame_ch1, textvariable=self.ch1_voltage_var, width=12)
        self.ch1_voltage_entry.grid(row=0, column=1, padx=5, pady=5)
        self.ch1_set_voltage_btn.grid(row=0, column=2, padx=10, pady=5)

        ttk.Label(self.frame_ch1, text="Current Limit (A):").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        self.ch1_current_entry = ttk.Entry(self.frame_ch1, textvariable=self.ch1_current_var, width=12)
        self.ch1_current_entry.grid(row=1, column=1, padx=5, pady=5)
        self.ch1_set_current_btn.grid(row=1, column=2, padx=10, pady=5)

        self.ch1_on_btn.grid(row=2, column=1, padx=5, pady=5, sticky="e")
        self.ch1_off_btn.grid(row=2, column=2, padx=5, pady=5, sticky="w")

        ttk.Label(self.frame_ch1, text="Readback Voltage (V):").grid(row=3, column=0, padx=5, pady=5, sticky="e")
        self.ch1_read_voltage = ttk.Label(self.frame_ch1, text="N/A")
        self.ch1_read_voltage.grid(row=3, column=1, padx=5, pady=5, sticky="w")

        ttk.Label(self.frame_ch1, text="Readback Current (A):").grid(row=4, column=0, padx=5, pady=5, sticky="e")
        self.ch1_read_current = ttk.Label(self.frame_ch1, text="N/A")
        self.ch1_read_current.grid(row=4, column=1, padx=5, pady=5, sticky="w")

        # --- Channel 2 Controls ---
        # self.frame_ch2 = ttk.LabelFrame(root, text="Channel 2 Controls")
        # self.frame_ch2.pack(padx=10, pady=10, fill="x")
        self.style.configure("RedBold.TLabelframe.Label", 
                        foreground="red",      # Text color red
                        font=("Arial", 16, "bold"))  # Bold and bigger font size 16

        # Create the LabelFrame and apply the new style
        self.frame_ch2 = ttk.LabelFrame(root, text="Channel 2: Vin = 12V ", style="RedBold.TLabelframe")
        self.frame_ch2.pack(padx=20, pady=20)

        self.ch2_voltage_var = tk.StringVar()
        self.ch2_current_var = tk.StringVar()
        self.ch2_set_voltage_btn = ttk.Button(self.frame_ch2, text="Set Voltage", command=self.set_channel_2_voltage)
        self.ch2_set_current_btn = ttk.Button(self.frame_ch2, text="Set Current Limit", command=self.set_channel_2_current)
        self.ch2_on_btn = ttk.Button(self.frame_ch2, text="Output ON", command=lambda: self.set_output(self.device_var.get(), "2", True))
        self.ch2_off_btn = ttk.Button(self.frame_ch2, text="Output OFF", command=lambda: self.set_output(self.device_var.get(), "2", False))

        ttk.Label(self.frame_ch2, text="Voltage (V):").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        self.ch2_voltage_entry = ttk.Entry(self.frame_ch2, textvariable=self.ch2_voltage_var, width=12)
        self.ch2_voltage_entry.grid(row=0, column=1, padx=5, pady=5)
        self.ch2_set_voltage_btn.grid(row=0, column=2, padx=10, pady=5)

        ttk.Label(self.frame_ch2, text="Current Limit (A):").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        self.ch2_current_entry = ttk.Entry(self.frame_ch2, textvariable=self.ch2_current_var, width=12)
        self.ch2_current_entry.grid(row=1, column=1, padx=5, pady=5)
        self.ch2_set_current_btn.grid(row=1, column=2, padx=10, pady=5)

        self.ch2_on_btn.grid(row=2, column=1, padx=5, pady=5, sticky="e")
        self.ch2_off_btn.grid(row=2, column=2, padx=5, pady=5, sticky="w")

        ttk.Label(self.frame_ch2, text="Readback Voltage (V):").grid(row=3, column=0, padx=5, pady=5, sticky="e")
        self.ch2_read_voltage = ttk.Label(self.frame_ch2, text="N/A")
        self.ch2_read_voltage.grid(row=3, column=1, padx=5, pady=5, sticky="w")

        ttk.Label(self.frame_ch2, text="Readback Current (A):").grid(row=4, column=0, padx=5, pady=5, sticky="e")
        self.ch2_read_current = ttk.Label(self.frame_ch2, text="N/A")
        self.ch2_read_current.grid(row=4, column=1, padx=5, pady=5, sticky="w")

        # --- Auto-readback controls ---
        auto_frame = ttk.Frame(root)
        auto_frame.pack(pady=10, fill="x", padx=10)

        self.auto_readback_var = tk.BooleanVar(value=False)
        self.auto_checkbox = ttk.Checkbutton(auto_frame, text="Enable Automatic Readback", variable=self.auto_readback_var, command=self.toggle_auto_readback)
        self.auto_checkbox.pack(side="left")

        ttk.Label(auto_frame, text="Interval (ms):").pack(side="left", padx=(20, 5))
        self.readback_interval_var = tk.StringVar(value="1000")
        self.readback_interval_entry = ttk.Entry(auto_frame, textvariable=self.readback_interval_var, width=8)
        self.readback_interval_entry.pack(side="left")

        # Refresh button
        self.refresh_button = ttk.Button(root, text="Refresh Devices", command=self.load_devices)
        self.refresh_button.pack(pady=10)

        # Bind selection event
        self.device_combo.bind("<<ComboboxSelected>>", self.device_selected)

        # Initial load
        self.load_devices()

    def load_devices(self):
        try:
            devices = self.rm.list_resources()
            if devices:
                self.device_combo['values'] = devices
                self.device_combo.current(0)
                self.show_device_idn(devices[0])
                self.update_readback(devices[0])
            else:
                self.device_combo['values'] = []
                self.clear_idn_text()
                self.clear_readbacks()
                messagebox.showinfo("Info", "No VISA devices found.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to list devices:\n{e}")

    def device_selected(self, event):
        selected = self.device_var.get()
        self.show_device_idn(selected)
        self.update_readback(selected)

    def show_device_idn(self, resource_name):
        self.clear_idn_text()
        try:
            with self.rm.open_resource(resource_name, timeout=2000) as instr:
                idn = instr.query("*IDN?")
                self.idn_text.config(state="normal")
                self.idn_text.delete("1.0", tk.END)
                self.idn_text.insert("1.0", idn.strip())
                self.idn_text.config(state="disabled")
        except Exception as e:
            self.idn_text.config(state="normal")
            self.idn_text.delete("1.0", tk.END)
            self.idn_text.insert("1.0", f"Could not query *IDN?: {e}")
            self.idn_text.config(state="disabled")

    def clear_idn_text(self):
        self.idn_text.config(state="normal")
        self.idn_text.delete("1.0", tk.END)
        self.idn_text.config(state="disabled")

    def clear_readbacks(self):
        self.ch1_read_voltage.config(text="N/A")
        self.ch1_read_current.config(text="N/A")
        self.ch2_read_voltage.config(text="N/A")
        self.ch2_read_current.config(text="N/A")

    def update_readback(self, device):
        try:
            with self.rm.open_resource(device, timeout=2000) as instr:
                v1 = instr.query("MEAS:VOLT? (@1)")
                i1 = instr.query("MEAS:CURR? (@1)")
                v2 = instr.query("MEAS:VOLT? (@2)")
                i2 = instr.query("MEAS:CURR? (@2)")

                self.ch1_read_voltage.config(text=f"{float(v1):.3f} V")
                self.ch1_read_current.config(text=f"{float(i1):.3f} A")
                self.ch2_read_voltage.config(text=f"{float(v2):.3f} V")
                self.ch2_read_current.config(text=f"{float(i2):.3f} A")
        except Exception as e:
            self.clear_readbacks()
            print(f"Warning: Could not read back measurements: {e}")

    def set_voltage(self, device, channel, voltage):
        if not device:
            messagebox.showerror("Error", "No device selected.")
            return

        if "E36311A" not in self.idn_text.get("1.0", tk.END):
            if not messagebox.askyesno("Warning", "Device does not appear to be Keysight E36311A.\nTry to send voltage command anyway?"):
                return

        try:
            voltage_val = float(voltage)
        except ValueError:
            messagebox.showerror("Input Error", "Invalid voltage value.")
            return

        try:
            with self.rm.open_resource(device, timeout=2000) as instr:
                cmd = f"SOUR:VOLT:LEV {voltage_val}, (@{channel})"
                instr.write(cmd)
                # messagebox.showinfo("Success", f"Voltage for Channel {channel} set to {voltage_val} V")
                self.update_readback(device)
        except Exception as e:
            messagebox.showerror("Communication Error", f"Failed to set voltage:\n{e}")

    def set_current(self, device, channel, current):
        if not device:
            messagebox.showerror("Error", "No device selected.")
            return

        if "E36311A" not in self.idn_text.get("1.0", tk.END):
            if not messagebox.askyesno("Warning", "Device does not appear to be Keysight E36311A.\nTry to send current command anyway?"):
                return

        try:
            current_val = float(current)
        except ValueError:
            messagebox.showerror("Input Error", "Invalid current value.")
            return

        try:
            with self.rm.open_resource(device, timeout=2000) as instr:
                cmd = f"SOUR:CURR:LEV {current_val}, (@{channel})"
                instr.write(cmd)
                # messagebox.showinfo("Success", f"Current limit for Channel {channel} set to {current_val} A")
                self.update_readback(device)
        except Exception as e:
            messagebox.showerror("Communication Error", f"Failed to set current:\n{e}")

    def set_output(self, device, channel, state):
        if not device:
            messagebox.showerror("Error", "No device selected.")
            return

        if "E36311A" not in self.idn_text.get("1.0", tk.END):
            if not messagebox.askyesno("Warning", "Device does not appear to be Keysight E36311A.\nTry to send output command anyway?"):
                return

        try:
            with self.rm.open_resource(device, timeout=2000) as instr:
                cmd = f"OUTP {'ON' if state else 'OFF'}, (@{channel})"
                instr.write(cmd)
                # messagebox.showinfo("Success", f"Output on Channel {channel} turned {'ON' if state else 'OFF'}")
                self.update_readback(device)
        except Exception as e:
            messagebox.showerror("Communication Error", f"Failed to set output state:\n{e}")

    def set_channel_1_voltage(self):
        self.set_voltage(self.device_var.get(), "1", self.ch1_voltage_var.get())

    def set_channel_2_voltage(self):
        self.set_voltage(self.device_var.get(), "2", self.ch2_voltage_var.get())

    def set_channel_1_current(self):
        self.set_current(self.device_var.get(), "1", self.ch1_current_var.get())

    def set_channel_2_current(self):
        self.set_current(self.device_var.get(), "2", self.ch2_current_var.get())

    def toggle_auto_readback(self):
        if self.auto_readback_var.get():
            self.start_auto_readback()
        else:
            self.stop_auto_readback()

    def start_auto_readback(self):
        interval_ms = self.readback_interval_var.get()
        try:
            interval = int(interval_ms)
            if interval < 100:
                messagebox.showwarning("Warning", "Interval too short, setting to 100 ms minimum.")
                interval = 100
        except ValueError:
            messagebox.showerror("Input Error", "Invalid interval value.")
            self.auto_readback_var.set(False)
            return

        self._auto_readback_loop(interval)

    def _auto_readback_loop(self, interval):
        device = self.device_var.get()
        if self.auto_readback_var.get() and device:
            self.update_readback(device)
            # schedule next call
            self.auto_readback_job = self.root.after(interval, lambda: self._auto_readback_loop(interval))
        else:
            self.auto_readback_job = None

    def stop_auto_readback(self):
        if self.auto_readback_job:
            self.root.after_cancel(self.auto_readback_job)
            self.auto_readback_job = None


if __name__ == "__main__":
    root = tk.Tk()
    app = VisaDeviceFinderApp(root)
    root.mainloop()
