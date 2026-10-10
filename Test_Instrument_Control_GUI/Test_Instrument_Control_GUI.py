import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import pyvisa
import os
import sys
import subprocess
from datetime import datetime
import threading
import time

class InstrumentGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("ADTH APP Test Equipment Control Panel")
        self.root.geometry("900x800")
        self.root.withdraw()

        # Initialize VISA
        try:
            self.rm = pyvisa.ResourceManager()
            self.resources = self.rm.list_resources()
        except Exception as e:
            messagebox.showerror("VISA Error", str(e))
            self.resources = []

        self.detected_devices = self.auto_detect_devices()

        # Notebook (tabs)
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill='both', expand=True)

        self.create_n8734a_tab()
        self.create_power_supply_tab()
        self.create_waveform_generator_tab()
        self.create_oscilloscope_tab()
        self.create_electronic_load_tab()
        self.create_daq973a_tab()
        self.create_scpi_low_level_tab()

        self.apply_detected_devices()
        if self.daq_combo.get():
            self._daq_on_device_selected()
        self.root.deiconify()

    # =====================================================
    # Functions for Oscilloscope Tektronix MDO34
    # =====================================================
    def select_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.save_folder.set(folder)


    def open_folder(self):
        folder = self.save_folder.get()
        if os.path.exists(folder):
            if os.name == 'nt':  # Windows
                os.startfile(folder)
            elif os.name == 'posix':  # macOS/Linux
                subprocess.Popen(['open', folder])


    def save_waveform(self):
        resource = self.scope_combo.get()
        if not resource:
            self.save_status_label.config(text="Status: No oscilloscope selected")
            return

        global save_folder
        selected_device = resource
        
        rm = pyvisa.ResourceManager()
        try:
            instrument = rm.open_resource(selected_device)
            instrument.timeout = 5000  # Allow time for image transfer

            # Set screenshot format and capture image
            instrument.write("HARDCOPY:FORMAT PNG")
            instrument.write("HARDCOPY START")

            # Read image data from oscilloscope
            image_data = instrument.read_raw()

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            waveform_name = self.waveform_name_entry.get()
            if not waveform_name:
                self.save_status_label.config(text="Status: Enter waveform name")
                return
            file_path = os.path.join(self.save_folder.get(),f"{waveform_name}_{timestamp}.png")


            with open(file_path, "wb") as f:
                f.write(image_data)

            self.save_status_label.config(text=f"Status: Saved to {file_path}")
            instrument.close()
            print(f"Screenshot saved: {file_path}")
        except Exception as e:
            self.save_status_label.config(text=f"Error: {str(e)}")
            print("Screenshot Error:", e)
            

    def get_horizontal_scale(self, scope):
        try:
            scale = float(scope.query("HORIZONTAL:SCALE?"))
            self.h_scale_var.set(f"Current Scale: {scale} s/div")
            return scale
        except:
            self.h_scale_var.set("Current Scale: Error")
            return None


    def increase_horizontal_scale(self):
        resource = self.scope_combo.get()
        if not resource:
            self.h_scale_var.set("No oscilloscope selected")
            return

        try:
            with self.rm.open_resource(resource) as scope:
                scope.timeout = 3000
                current_scale = self.get_horizontal_scale(scope)

                if current_scale:
                    new_scale = current_scale * 2
                    scope.write(f"HORIZONTAL:SCALE {new_scale}")
                    self.h_scale_var.set(f"Current Scale: {new_scale} s/div")

        except Exception as e:
            self.h_scale_var.set(f"Error: {str(e)}")


    def decrease_horizontal_scale(self):
        resource = self.scope_combo.get()
        if not resource:
            self.h_scale_var.set("No oscilloscope selected")
            return

        try:
            with self.rm.open_resource(resource) as scope:
                scope.timeout = 3000
                current_scale = self.get_horizontal_scale(scope)

                if current_scale:
                    new_scale = current_scale / 2
                    scope.write(f"HORIZONTAL:SCALE {new_scale}")
                    self.h_scale_var.set(f"Current Scale: {new_scale} s/div")

        except Exception as e:
            self.h_scale_var.set(f"Error: {str(e)}")
    def run_mode(self):
        resource = self.scope_combo.get()
        if not resource:
            self.annotation_status.config(text="Status: No oscilloscope selected")
            return

        try:
            with self.rm.open_resource(resource) as scope:
                scope.timeout = 3000
                scope.write("ACQuire:STATE RUN")

            self.annotation_status.config(text="Status: Triggered Run Mode")

        except Exception as e:
            self.annotation_status.config(text=f"Error: {str(e)}")

    def stop_mode(self):
        resource = self.scope_combo.get()
        if not resource:
            self.annotation_status.config(text="Status: No oscilloscope selected")
            return

        try:
            with self.rm.open_resource(resource) as scope:
                scope.timeout = 3000
                scope.write("ACQuire:STATE STOP")

            self.annotation_status.config(text="Status: Triggered Stop Mode")

        except Exception as e:
            self.annotation_status.config(text=f"Error: {str(e)}")
    
    def single_mode(self):
        resource = self.scope_combo.get()
        if not resource:
            self.annotation_status.config(text="Status: No oscilloscope selected")
            return
        try:
            with self.rm.open_resource(resource) as scope:
                scope.timeout = 3000
                scope.write("ACQuire:STOPAfter SEQuence")

            self.annotation_status.config(text="Status: Triggered Single Acquisition")

        except Exception as e:
            self.annotation_status.config(text=f"Error: {str(e)}")

    def sequence_mode(self):
        resource = self.scope_combo.get()
        if not resource:
            self.annotation_status.config(text="Status: No oscilloscope selected")
            return
        try:
            with self.rm.open_resource(resource) as scope:
                scope.timeout = 3000
                scope.write("ACQuire:STOPAfter RUNSTop")

            self.annotation_status.config(text="Status: Triggered Sequence Acquisition")

        except Exception as e:
            self.annotation_status.config(text=f"Error: {str(e)}")

    def trigger_auto(self):
        resource = self.scope_combo.get()
        if not resource:
            self.annotation_status.config(text="Status: No oscilloscope selected")
            return
        try:
            with self.rm.open_resource(resource) as scope:
                scope.timeout = 3000
                scope.write("TRIG:A:MODE AUTO")

            self.annotation_status.config(text="Status: Set Trigger to Auto")
        except Exception as e:
            self.annotation_status.config(text=f"Error: {str(e)}")

    def trigger_normal(self):
        resource = self.scope_combo.get()
        if not resource:
            self.annotation_status.config(text="Status: No oscilloscope selected")
            return

        try:
            with self.rm.open_resource(resource) as scope:
                scope.timeout = 3000
                scope.write("TRIG:A:MODE NORM")

            self.annotation_status.config(text="Status: Set Trigger to Normal")

        except Exception as e:
            self.annotation_status.config(text=f"Error: {str(e)}")

    def save_waveform_to_reference(self, source, destination):
        resource = self.scope_combo.get()
        if not resource:
            self.annotation_status.config(text="Status: No oscilloscope selected")
            return

        try:
            with self.rm.open_resource(resource) as scope:
                scope.timeout = 3000
                scope.write(f"SAVE:WAVEFORM {source},{destination}")

            self.annotation_status.config(text="Status: Waveform saved to reference")

        except Exception as e:
            self.annotation_status.config(text=f"Error: {str(e)}")

    def send_annotation(self):
        resource = self.scope_combo.get()
        if not resource:
            self.annotation_status.config(text="Status: No oscilloscope selected")
            return

        text = self.annotation_entry.get()
        if not text:
            self.annotation_status.config(text="Status: Enter annotation text")
            return

        try:
            with self.rm.open_resource(resource) as scope:
                scope.timeout = 3000

                # Generic SCPI annotation (may vary by brand)
                scope.write(f'MESSage:SHOW "{text}"')
                # scope.write("DISPLAY:ANNOTATION ON")

            self.annotation_status.config(text="Status: Annotation Sent")

        except Exception as e:
            self.annotation_status.config(text=f"Error: {str(e)}")

    # =====================================================
    # Functions for Waveform Generator Keysight 33500B
    # =====================================================

    def send_high(self):
        resource = self.wg_combo.get()
        self.execute_scpi(resource, f":VOLT:HIGH {self.high_var.get()} mV")
        self.calc_voltage_var.set(self.high_var.get())
        self.calculate_load_current()

    def send_low(self):
        resource = self.wg_combo.get()
        self.execute_scpi(resource, f":VOLT:LOW {self.low_var.get()} mV")
        self.calc_voltage_var.set(self.low_var.get())
        self.calculate_load_current()


    def send_frequency(self):
        resource = self.wg_combo.get()
        self.execute_scpi(resource, f"FREQ {self.freq_var.get()} E3")

    def send_pulse_width(self):
        resource = self.wg_combo.get()
        self.execute_scpi(resource, f":PULS:WIDT {self.pulse_width_var.get()} E-6")

    def wg_output_on(self):
        resource = self.wg_combo.get()
        self.execute_scpi(resource, "OUTP ON")

    def wg_output_off(self):
        resource = self.wg_combo.get()
        self.execute_scpi(resource, "OUTP OFF")

    def toggle_output(self):
        try:
            delay = float(self.delay_var.get())
        except ValueError:
            messagebox.showerror("Invalid Input", "Delay must be numeric.")
            return

        threading.Thread(target=self._toggle_thread, args=(delay,), daemon=True).start()

    
    def _toggle_thread(self, delay: float):
        resource = self.wg_combo.get()
        if not resource:
            self.show_response("Status: No device selected")
            return

        try:
            with self.rm.open_resource(resource) as inst:
                # Adjust terminations if your instrument requires them
                # inst.write_termination = '\n'
                # inst.read_termination = '\n'
                inst.timeout = 3000

                inst.write("OUTP ON")
                time.sleep(delay)
                inst.write("OUTP OFF")

            # self.show_response("OUTP toggled successfully")
        except Exception as e:
            print(f"Toggle Error: {e}")
            # self.show_response(f"ERROR: {e}")

    def send_scpi(self, resource, var):
        cmd = var.get().strip()
        if cmd:
            self.execute_scpi(resource, cmd)
        else:
            self.show_response(text="Status:No SCPI command", box=self.scpi_response_text)

    def _scpi_query(self, resource, var):
        cmd = var.get().strip()
        if not cmd:
            self.show_response("Status: No SCPI command", box=self.scpi_response_text)
            return
        if "?" not in cmd:
            cmd += "?"
        self.execute_scpi(resource, cmd)

    def execute_scpi(self, resource, cmd: str):
        if not resource:
            self.show_response("Status: No device selected", box=self.scpi_response_text)
            return
        try:
            with self.rm.open_resource(resource) as inst:
                inst.timeout = 3000

        except Exception as e:
            self.show_response(f"Error: {str(e)}", box=self.scpi_response_text)

        try:
            with self.rm.open_resource(resource) as inst:
                inst.timeout = 3000

                if "?" in cmd:
                    resp = inst.query(cmd).strip()
                    self.show_response(f"> {cmd}\n{resp}", box=self.scpi_response_text)
                else:
                    inst.write(cmd)
                    self.show_response(f"> {cmd}\nOK", box=self.scpi_response_text)
        except Exception as e:
            self.show_response(f"ERROR: {e}", box=self.scpi_response_text)

    def show_response(self, text, box):
        box.config(state="normal")
        box.delete("1.0", tk.END)
        box.insert(tk.END, text)
        box.config(state="disabled")

    def clear_response(self, box):
        box.config(state="normal")
        box.delete("1.0", tk.END)
        box.config(state="disabled")

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
    
    def calculate_voltage_high(self):
        try:
            max_load_current = float(self.max_load_var.get())
            ratio = float(self.calc_ratio_var.get())
            if ratio == 0:
                raise ValueError
            voltage_high = max_load_current*ratio
            self.high_var.set(voltage_high) #
            self.load_current_var.set(f"Voltage High = {voltage_high:.6f} mV")
        except ValueError:
            messagebox.showerror("Invalid Input", "Enter valid numeric values.\n(Current Ratio ≠ 0)")

    
    # =====================================================
    # Functions for Electronic Load KIKUSUI PLZ664WA
    # =====================================================
    class ELoad:
        def measure_voltage(self) -> float:
            resource = self.eload_combo.get()
            if not resource:
                self.show_response(text="Status: No device selected", box=self.eload_response_text)
                return "NA"
            try:
                with self.rm.open_resource(resource) as inst:
                    inst.timeout = 3000
                    return float(inst.query(":MEAS:VOLT?"))
            except Exception as e:
                self.show_response(f"ERROR: {e}", box=self.eload_response_text)
                return "NA"

        def measure_current(self) -> float:
            resource = self.eload_combo.get()
            if not resource:
                self.show_response(text="Status: No device selected", box=self.eload_response_text)
                return "NA"

            try:
                with self.rm.open_resource(resource) as inst:
                    inst.timeout = 3000
                    return float(inst.query(":MEAS:CURR?"))
            except Exception as e:
                self.show_response(f"ERROR: {e}", box=self.eload_response_text)
                return "NA"

        def measure_power(self) -> float:
            resource = self.eload_combo.get()
            if not resource:
                self.show_response(text="Status: No device selected", box=self.eload_response_text)
                return "NA"

            try:
                with self.rm.open_resource(resource) as inst:
                    inst.timeout = 3000
                    return float(inst.query(":MEAS:POW?"))
            except Exception as e:
                self.show_response(f"ERROR: {e}", box=self.eload_response_text)
                return "NA"

        def set_current(self, amps: float):
            resource = self.eload_combo.get()
            if not amps:
                self.show_response("Status: No current value provided", box=self.eload_response_text)
                return "NA"
            if not resource:
                self.show_response("Status: No device selected", box=self.eload_response_text)
                return "NA"
            try:
                with self.rm.open_resource(resource) as inst:
                    inst.timeout = 3000
                    result = inst.write(f":CURR {amps}")
                    current_setting = inst.query(":CURR?")
                    self.eload_current_setting_label.config(text=f"Current Setting: {float(current_setting):.4f} A")
                    return result
            except Exception as e:
                self.show_response(f"ERROR: {e}", box=self.eload_response_text)
                return "NA"

        def read_current_setting(self):
            resource = self.eload_combo.get()
            if not resource:
                self.show_response("Status: No device selected", box=self.eload_response_text)
                return "NA"
            try:
                with self.rm.open_resource(resource) as inst:
                    inst.timeout = 3000
                    current_setting = inst.query(":CURR?")
                    self.eload_current_setting_label.config(text=f"Current Setting: {float(current_setting):.4f} A")
                    return current_setting
            except Exception as e:
                self.show_response(f"ERROR: {e}", box=self.eload_response_text)
                return "NA"

        def set_cv(self, volts: float):
            resource = self.eload_combo.get()
            if not resource:
                self.show_response("Status: No device selected", box=self.eload_response_text)
                return "NA"
            try:
                with self.rm.open_resource(resource) as inst:
                    inst.timeout = 3000
                    return inst.write(f":VOLT {volts}")
            except Exception as e:
                self.show_response(f"ERROR: {e}", box=self.eload_response_text)
                return "NA"

        def turn_on(self):
            resource = self.eload_combo.get()
            if not resource:
                self.show_response("Status: No device selected", box=self.eload_response_text)
                return "NA"
            try:
                threshold = float(self.eload_uv_threshold_var.get())
                with self.rm.open_resource(resource) as inst:
                    inst.timeout = 3000
                    voltage = float(inst.query(":MEAS:VOLT?"))
                    if voltage < threshold:
                        self.show_response(f"WARNING: Voltage too low ({voltage:.4f} V < {threshold} V threshold). E-Load not turned on.", box=self.eload_response_text)
                        return "NA"
                    return inst.write(":INP ON")
            except Exception as e:
                self.show_response(f"ERROR: {e}", box=self.eload_response_text)
                return "NA"

        def turn_off(self):
            resource = self.eload_combo.get()
            if not resource:
                self.show_response("Status: No device selected", box=self.eload_response_text)
                return "NA"
            try:
                with self.rm.open_resource(resource) as inst:
                    inst.timeout = 3000
                    return inst.write(":INP OFF")
            except Exception as e:
                self.show_response(f"ERROR: {e}", box=self.eload_response_text)
                return "NA"
        
        def toggle_output(self):
            try:
                delay = float(self.on_off_eload_delay_var.get())
            except ValueError:
                messagebox.showerror("Invalid Input", "Delay must be numeric.")
                return
            threading.Thread(target=self._eload_toggle_thread(delay = delay), daemon=True).start()
        
    def _eload_toggle_thread(self, delay: float):
        resource = self.eload_combo.get()
        if not resource:
            self.show_response("Status: No device selected",box=self.eload_response_text)
            return

        try:
            threshold = float(self.eload_uv_threshold_var.get())
            with self.rm.open_resource(resource) as inst:
                inst.timeout = 3000

                voltage = float(inst.query(":MEAS:VOLT?"))
                if voltage < threshold:
                    self.show_response(f"WARNING: Voltage too low ({voltage:.4f} V < {threshold} V threshold). E-Load not turned on.", box=self.eload_response_text)
                    return

                inst.write(":INP ON")
                time.sleep(delay)
                inst.write(":INP OFF")

            self.show_response("OUTP toggled successfully", box=self.eload_response_text)
        except Exception as e:
            self.show_response(f"ERROR: {e}",box=self.eload_response_text)


    # -------------------------
    # Common VISA Functions
    # -------------------------

    def _device_config_path(self):
        if getattr(sys, 'frozen', False):
            base_path = os.path.dirname(sys.executable)
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base_path, "device_config.txt")

    def load_device_config(self):
        config_path = self._device_config_path()
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

    def auto_detect_devices(self):
        config = self.load_device_config()
        if not config:
            messagebox.showinfo("Auto-Detect", "device_config.txt not found or empty.\nSkipping auto-detect.")
            return {}

        progress_win = tk.Toplevel(self.root)
        progress_win.title("Auto-Detecting Devices")
        progress_win.geometry("400x100")
        progress_win.resizable(False, False)
        progress_win.grab_set()
        ttk.Label(progress_win, text="Scanning connected instruments...").pack(pady=(15, 5))
        progress_label = ttk.Label(progress_win, text="")
        progress_label.pack()
        progress_bar = ttk.Progressbar(progress_win, length=350, mode="determinate", maximum=len(self.resources))
        progress_bar.pack(pady=10)
        progress_win.update()

        results = {}
        for i, resource in enumerate(self.resources):
            progress_label.config(text=f"Querying: {resource}")
            progress_bar["value"] = i + 1
            progress_win.update()
            try:
                with self.rm.open_resource(resource) as inst:
                    inst.timeout = 3000
                    idn = inst.query("*IDN?").strip()
                    idn_fields = [field.strip().upper() for field in idn.split(",")]
                    for tab_name, keyword in config.items():
                        if keyword and keyword.upper() in idn_fields:
                            results[tab_name] = (resource, idn)
            except Exception:
                continue

        progress_win.destroy()

        total = len(config)
        found_count = sum(1 for tab in config if tab in results)
        not_found_count = total - found_count

        summary_win = tk.Toplevel(self.root)
        summary_win.title("Auto-Detect Summary")
        summary_win.geometry("550x450")
        summary_win.resizable(False, False)
        summary_win.grab_set()

        ttk.Label(summary_win, text=f"Devices found: {found_count}/{total}", font=("Arial", 11, "bold")).pack(pady=(15, 10))

        # Scrollable device list
        list_container = ttk.Frame(summary_win)
        list_container.pack(padx=20, fill="both", expand=True)
        canvas = tk.Canvas(list_container, highlightthickness=0)
        vsb = ttk.Scrollbar(list_container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        summary_frame = tk.Frame(canvas)
        canvas.create_window((0, 0), window=summary_frame, anchor="nw")
        summary_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        for tab_name, keyword in config.items():
            row = tk.Frame(summary_frame)
            row.pack(fill="x", pady=2)
            if tab_name in results:
                resource, idn = results[tab_name]
                tk.Label(row, text="[PASS]", fg="green", font=("Arial", 10, "bold")).pack(side="left")
                tk.Label(row, text=f" {tab_name} ({keyword}) -> {resource}", font=("Arial", 10)).pack(side="left")
            else:
                tk.Label(row, text="[FAIL]", fg="red", font=("Arial", 10, "bold")).pack(side="left")
                tk.Label(row, text=f" {tab_name} ({keyword}) -> Not found", font=("Arial", 10)).pack(side="left")

        if not_found_count > 0:
            ttk.Label(summary_win, text="Please check device_config.txt and verify connections.", foreground="red").pack(pady=(10, 5))

        btn_frame = ttk.Frame(summary_win)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="Open device_config.txt",
                   command=lambda: os.startfile(self._device_config_path())).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="OK", command=summary_win.destroy).pack(side="left", padx=5)
        summary_win.wait_window()

        return results

    def apply_detected_devices(self):
        tab_map = {
            "power_supply": (self.psu_combo, self.psu_id_label),
            "waveform_generator": (self.wg_combo, self.wg_id_label),
            "oscilloscope": (self.scope_combo, self.scope_id_label),
            "electronic_load": (self.eload_combo, self.eload_id_label),
            "data_acquisition": (self.daq_combo, self.daq_id_label),
            "high_power_supply": (self.n8734a_combo, self.n8734a_id_label),
        }
        if not self.detected_devices:
            return
        for tab_name, (resource, idn) in self.detected_devices.items():
            if tab_name in tab_map:
                combo, id_label = tab_map[tab_name]
                combo.set(resource)
                id_label.config(text=f"ID: {idn}")

    def query_idn(self, resource_name, idn_label):
        try:
            with self.rm.open_resource(resource_name) as inst:
                inst.timeout = 3000
                idn = inst.query("*IDN?")
                idn_label.config(text=f"ID: {idn.strip()}")
        except Exception as e:
            idn_label.config(text=f"Error: {str(e)}")

    def refresh_devices(self, combobox):
        try:
            self.resources = self.rm.list_resources()
            combobox["values"] = self.resources
        except:
            combobox["values"] = []

    def _make_scrollable_tab(self, title: str):
        outer = ttk.Frame(self.notebook)
        self.notebook.add(outer, text=title)
        canvas = tk.Canvas(outer, highlightthickness=0)
        vsb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = ttk.Frame(canvas)
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        def _on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
        def _on_canvas_configure(event):
            canvas.itemconfig(win_id, width=event.width)
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        inner.bind("<Configure>", _on_frame_configure)
        canvas.bind("<Configure>", _on_canvas_configure)
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
        return inner

    # -------------------------
    # Power Supply Tab
    # -------------------------

    def create_power_supply_tab(self):
        tab = self._make_scrollable_tab("Power Supply")

        ttk.Label(tab, text="Select Device:").pack(pady=5)
        self.psu_combo = ttk.Combobox(tab, values=self.resources, width=50)
        self.psu_combo.pack()
        ttk.Button(tab, text="Refresh Devices",
                   command=lambda: self.refresh_devices(self.psu_combo)).pack(pady=5)
        self.psu_id_label = ttk.Label(tab, text="ID: ")
        self.psu_id_label.pack(pady=5)
        self.psu_combo.bind("<<ComboboxSelected>>",
                            lambda e: self.query_idn(self.psu_combo.get(), self.psu_id_label))

        # --- Keysight E36311A Section ---
        e36311a_frame = ttk.LabelFrame(tab, text="Keysight E36311A Control", padding=10)
        e36311a_frame.pack(padx=10, pady=10, fill="x")

        # Channel 1 Controls
        ch1_frame = ttk.LabelFrame(e36311a_frame, text="Channel 1: VREN = 3V")
        ch1_frame.pack(padx=10, pady=5, fill="x")
        self.e36311a_ch1_voltage_var = tk.StringVar()
        self.e36311a_ch1_current_var = tk.StringVar()
        ttk.Label(ch1_frame, text="Voltage (V):").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        ttk.Entry(ch1_frame, textvariable=self.e36311a_ch1_voltage_var, width=12).grid(row=0, column=1, padx=5, pady=5)
        ttk.Button(ch1_frame, text="Set Voltage", command=self.e36311a_set_channel_1_voltage).grid(row=0, column=2, padx=10, pady=5)
        ttk.Label(ch1_frame, text="Current Limit (A):").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        ttk.Entry(ch1_frame, textvariable=self.e36311a_ch1_current_var, width=12).grid(row=1, column=1, padx=5, pady=5)
        ttk.Button(ch1_frame, text="Set Current Limit", command=self.e36311a_set_channel_1_current).grid(row=1, column=2, padx=10, pady=5)
        ttk.Button(ch1_frame, text="Output ON", command=lambda: self.e36311a_set_output("1", True)).grid(row=2, column=1, padx=5, pady=5, sticky="e")
        ttk.Button(ch1_frame, text="Output OFF", command=lambda: self.e36311a_set_output("1", False)).grid(row=2, column=2, padx=5, pady=5, sticky="w")
        ttk.Label(ch1_frame, text="Readback Voltage (V):").grid(row=3, column=0, padx=5, pady=5, sticky="e")
        self.e36311a_ch1_read_voltage = ttk.Label(ch1_frame, text="N/A")
        self.e36311a_ch1_read_voltage.grid(row=3, column=1, padx=5, pady=5, sticky="w")
        ttk.Label(ch1_frame, text="Readback Current (A):").grid(row=4, column=0, padx=5, pady=5, sticky="e")
        self.e36311a_ch1_read_current = ttk.Label(ch1_frame, text="N/A")
        self.e36311a_ch1_read_current.grid(row=4, column=1, padx=5, pady=5, sticky="w")

        # Channel 2 Controls
        ch2_frame = ttk.LabelFrame(e36311a_frame, text="Channel 2: Vin = 12V")
        ch2_frame.pack(padx=10, pady=5, fill="x")
        self.e36311a_ch2_voltage_var = tk.StringVar()
        self.e36311a_ch2_current_var = tk.StringVar()
        ttk.Label(ch2_frame, text="Voltage (V):").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        ttk.Entry(ch2_frame, textvariable=self.e36311a_ch2_voltage_var, width=12).grid(row=0, column=1, padx=5, pady=5)
        ttk.Button(ch2_frame, text="Set Voltage", command=self.e36311a_set_channel_2_voltage).grid(row=0, column=2, padx=10, pady=5)
        ttk.Label(ch2_frame, text="Current Limit (A):").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        ttk.Entry(ch2_frame, textvariable=self.e36311a_ch2_current_var, width=12).grid(row=1, column=1, padx=5, pady=5)
        ttk.Button(ch2_frame, text="Set Current Limit", command=self.e36311a_set_channel_2_current).grid(row=1, column=2, padx=10, pady=5)
        ttk.Button(ch2_frame, text="Output ON", command=lambda: self.e36311a_set_output("2", True)).grid(row=2, column=1, padx=5, pady=5, sticky="e")
        ttk.Button(ch2_frame, text="Output OFF", command=lambda: self.e36311a_set_output("2", False)).grid(row=2, column=2, padx=5, pady=5, sticky="w")
        ttk.Label(ch2_frame, text="Readback Voltage (V):").grid(row=3, column=0, padx=5, pady=5, sticky="e")
        self.e36311a_ch2_read_voltage = ttk.Label(ch2_frame, text="N/A")
        self.e36311a_ch2_read_voltage.grid(row=3, column=1, padx=5, pady=5, sticky="w")
        ttk.Label(ch2_frame, text="Readback Current (A):").grid(row=4, column=0, padx=5, pady=5, sticky="e")
        self.e36311a_ch2_read_current = ttk.Label(ch2_frame, text="N/A")
        self.e36311a_ch2_read_current.grid(row=4, column=1, padx=5, pady=5, sticky="w")

        # Auto-readback controls
        auto_frame = ttk.Frame(e36311a_frame)
        auto_frame.pack(pady=5, fill="x", padx=10)
        self.e36311a_auto_readback_var = tk.BooleanVar(value=False)
        self.e36311a_auto_checkbox = ttk.Checkbutton(auto_frame, text="Enable Automatic Readback", variable=self.e36311a_auto_readback_var, command=self.e36311a_toggle_auto_readback)
        self.e36311a_auto_checkbox.pack(side="left")
        ttk.Label(auto_frame, text="Interval (ms):").pack(side="left", padx=(20, 5))
        self.e36311a_readback_interval_var = tk.StringVar(value="1000")
        self.e36311a_readback_interval_entry = ttk.Entry(auto_frame, textvariable=self.e36311a_readback_interval_var, width=8)
        self.e36311a_readback_interval_entry.pack(side="left")

    def e36311a_set_channel_1_voltage(self):
        self.e36311a_set_voltage("1", self.e36311a_ch1_voltage_var.get())
    def e36311a_set_channel_2_voltage(self):
        self.e36311a_set_voltage("2", self.e36311a_ch2_voltage_var.get())
    def e36311a_set_channel_1_current(self):
        self.e36311a_set_current("1", self.e36311a_ch1_current_var.get())
    def e36311a_set_channel_2_current(self):
        self.e36311a_set_current("2", self.e36311a_ch2_current_var.get())
    def e36311a_set_output(self, channel, state):
        device = self.psu_combo.get()
        if not device:
            messagebox.showerror("Error", "No device selected.")
            return
        # Query IDN to check device type
        try:
            with self.rm.open_resource(device, timeout=2000) as inst:
                idn = inst.query("*IDN?")
                if "E36311A" not in idn:
                    if not messagebox.askyesno("Warning", "Device does not appear to be Keysight E36311A. Try to send output command anyway?"):
                        return
        except Exception as e:
            messagebox.showerror("Communication Error", f"Failed to query IDN: {e}")
            return
        try:
            with self.rm.open_resource(device, timeout=2000) as inst:
                cmd = f"OUTP {'ON' if state else 'OFF'}, (@{channel})"
                inst.write(cmd)
                self.e36311a_update_readback()
        except Exception as e:
            messagebox.showerror("Communication Error", f"Failed to set output state:\n{e}")
    def e36311a_set_voltage(self, channel, voltage):
        device = self.psu_combo.get()
        if not device:
            messagebox.showerror("Error", "No device selected.")
            return
        try:
            with self.rm.open_resource(device, timeout=2000) as inst:
                idn = inst.query("*IDN?")
                if "E36311A" not in idn:
                    if not messagebox.askyesno("Warning", "Device does not appear to be Keysight E36311A. Try to send voltage command anyway?"):
                        return
        except Exception as e:
            messagebox.showerror("Communication Error", f"Failed to query IDN: {e}")
            return
        try:
            voltage_val = float(voltage)
        except ValueError:
            messagebox.showerror("Input Error", "Invalid voltage value.")
            return
        try:
            with self.rm.open_resource(device, timeout=2000) as inst:
                cmd = f"SOUR:VOLT:LEV {voltage_val}, (@{channel})"
                inst.write(cmd)
                self.e36311a_update_readback()
        except Exception as e:
            messagebox.showerror("Communication Error", f"Failed to set voltage:\n{e}")
    def e36311a_set_current(self, channel, current):
        device = self.psu_combo.get()
        if not device:
            messagebox.showerror("Error", "No device selected.")
            return
        try:
            with self.rm.open_resource(device, timeout=2000) as inst:
                idn = inst.query("*IDN?")
                if "E36311A" not in idn:
                    if not messagebox.askyesno("Warning", "Device does not appear to be Keysight E36311A. Try to send current command anyway?"):
                        return
        except Exception as e:
            messagebox.showerror("Communication Error", f"Failed to query IDN: {e}")
            return
        try:
            current_val = float(current)
        except ValueError:
            messagebox.showerror("Input Error", "Invalid current value.")
            return
        try:
            with self.rm.open_resource(device, timeout=2000) as inst:
                cmd = f"SOUR:CURR:LEV {current_val}, (@{channel})"
                inst.write(cmd)
                self.e36311a_update_readback()
        except Exception as e:
            messagebox.showerror("Communication Error", f"Failed to set current:\n{e}")
    def e36311a_update_readback(self):
        device = self.psu_combo.get()
        if not device:
            self.e36311a_ch1_read_voltage.config(text="N/A")
            self.e36311a_ch1_read_current.config(text="N/A")
            self.e36311a_ch2_read_voltage.config(text="N/A")
            self.e36311a_ch2_read_current.config(text="N/A")
            return
        try:
            with self.rm.open_resource(device, timeout=2000) as inst:
                v1 = inst.query("MEAS:VOLT? (@1)")
                i1 = inst.query("MEAS:CURR? (@1)")
                v2 = inst.query("MEAS:VOLT? (@2)")
                i2 = inst.query("MEAS:CURR? (@2)")
                self.e36311a_ch1_read_voltage.config(text=f"{float(v1):.3f} V")
                self.e36311a_ch1_read_current.config(text=f"{float(i1):.3f} A")
                self.e36311a_ch2_read_voltage.config(text=f"{float(v2):.3f} V")
                self.e36311a_ch2_read_current.config(text=f"{float(i2):.3f} A")
        except Exception as e:
            self.e36311a_ch1_read_voltage.config(text="N/A")
            self.e36311a_ch1_read_current.config(text="N/A")
            self.e36311a_ch2_read_voltage.config(text="N/A")
            self.e36311a_ch2_read_current.config(text="N/A")
    def e36311a_toggle_auto_readback(self):
        if self.e36311a_auto_readback_var.get():
            self.e36311a_start_auto_readback()
        else:
            self.e36311a_stop_auto_readback()
    def e36311a_start_auto_readback(self):
        try:
            interval = int(self.e36311a_readback_interval_var.get())
            if interval < 100:
                messagebox.showwarning("Warning", "Interval too short, setting to 100 ms minimum.")
                interval = 100
        except ValueError:
            messagebox.showerror("Input Error", "Invalid interval value.")
            self.e36311a_auto_readback_var.set(False)
            return
        self._e36311a_auto_readback_loop(interval)
    def _e36311a_auto_readback_loop(self, interval):
        if self.e36311a_auto_readback_var.get():
            self.e36311a_update_readback()
            self.root.after(interval, lambda: self._e36311a_auto_readback_loop(interval))
    def e36311a_stop_auto_readback(self):
        self.e36311a_auto_readback_var.set(False)

    # -------------------------
    # Waveform Generator Tab
    # -------------------------

    def create_waveform_generator_tab(self):
        tab = self._make_scrollable_tab("Waveform Generator")

        ttk.Label(tab, text="Select Device:").pack(pady=5)

        self.wg_combo = ttk.Combobox(tab, values=self.resources, width=50)
        self.wg_combo.pack()

        ttk.Button(tab, text="Refresh Devices",
                   command=lambda: self.refresh_devices(self.wg_combo)).pack(pady=5)

        self.wg_id_label = ttk.Label(tab, text="ID: ")
        self.wg_id_label.pack(pady=5)

        self.wg_combo.bind("<<ComboboxSelected>>",
                           lambda e: self.query_idn(self.wg_combo.get(), self.wg_id_label))
        
        # Voltage frame
        vframe = ttk.LabelFrame(tab, text="Parameters")
        vframe.pack(pady=8, fill="x", padx=10)

        ttk.Label(vframe, text="Voltage HIGH(mV):").grid(row=0, column=0, padx=5, pady=6, sticky="w")
        self.high_var = tk.StringVar()
        ttk.Entry(vframe, textvariable=self.high_var, width=15).grid(row=0, column=1)
        ttk.Button(vframe, text="Send HIGH", command=self.send_high).grid(row=0, column=2, padx=10)

        ttk.Label(vframe, text="Voltage LOW(mV):").grid(row=1, column=0, padx=5, pady=6, sticky="w")
        self.low_var = tk.StringVar()
        ttk.Entry(vframe, textvariable=self.low_var, width=15).grid(row=1, column=1)
        ttk.Button(vframe, text="Send LOW", command=self.send_low).grid(row=1, column=2, padx=10)

        ttk.Label(vframe, text="Frequency(kHz):").grid(row=2, column=0, padx=5, pady=6, sticky="w")
        self.freq_var = tk.StringVar()
        ttk.Entry(vframe, textvariable=self.freq_var, width=15).grid(row=2, column=1)
        ttk.Button(vframe, text="Send Freq", command=self.send_frequency).grid(row=2, column=2, padx=10)

        ttk.Label(vframe, text="Pulse Width(uS):").grid(row=3, column=0, padx=5, pady=6, sticky="w")
        self.pulse_width_var = tk.StringVar()
        ttk.Entry(vframe, textvariable=self.pulse_width_var, width=15).grid(row=3, column=1)
        ttk.Button(vframe, text="Send Pulse W", command=self.send_pulse_width).grid(row=3, column=2, padx=10)

        load_tool_frame = ttk.LabelFrame(tab, text="Load Tool Calculation")
        load_tool_frame.pack(pady=8, fill="x", padx=5)

        ttk.Label(load_tool_frame, text="Voltage (mV):").grid(row=5, column=0, padx=10, pady=10, sticky="w")
        self.calc_voltage_var = tk.StringVar()
        ttk.Entry(load_tool_frame, textvariable=self.calc_voltage_var, width=20).grid(row=5, column=1)

        ttk.Label(load_tool_frame, text="Max Load Current (A):").grid(row=5, column=4, padx=10, pady=10, sticky="w")
        self.max_load_var = tk.StringVar()
        ttk.Entry(load_tool_frame, textvariable=self.max_load_var, width=20).grid(row=5, column=5)

        ttk.Label(load_tool_frame, text="Current Ratio:").grid(row=6, column=0, padx=10, pady=10, sticky="w")
        self.calc_ratio_var = tk.StringVar(value = "2.5") # Default current 2.5mV/A
        ttk.Entry(load_tool_frame, textvariable=self.calc_ratio_var, width=20).grid(row=6, column=1)

        ttk.Button(
           load_tool_frame, text="Calculate Load Current", command=self.calculate_load_current
        ).grid(row=7, column=0, columnspan=2, pady=15)

        ttk.Button(
           load_tool_frame, text="Calculate Voltage High", command=self.calculate_voltage_high
        ).grid(row=7, column=5, columnspan=2, pady=15)

        result_frame = ttk.LabelFrame(tab, text="Result")
        result_frame.pack(padx=20, pady=10, fill="x")

        self.load_current_var = tk.StringVar(value="—")
        ttk.Label(
            result_frame,
            textvariable=self.load_current_var,
            font=("Arial", 12),
            foreground="green"
        ).pack(pady=15)

        # Output toggle frame
        oframe = ttk.LabelFrame(tab, text="Output Control")
        oframe.pack(pady=8, fill="x", padx=10)

        self.wg_on_btn = tk.Button(oframe, text="ON", bg="green", fg="white",
                                    font=("Arial", 10, "bold"), width=8,
                                    command=self.wg_output_on)
        self.wg_on_btn.grid(row=0, column=0, padx=5, pady=8)

        self.wg_off_btn = tk.Button(oframe, text="OFF", bg="red", fg="white",
                                    font=("Arial", 10, "bold"), width=8,
                                    command=self.wg_output_off)
        self.wg_off_btn.grid(row=0, column=1, padx=5, pady=8)

        ttk.Label(oframe, text="Delay Time (seconds):").grid(row=0, column=2, padx=5, pady=8, sticky="w")
        self.delay_var = tk.StringVar()
        ttk.Entry(oframe, textvariable=self.delay_var, width=15).grid(row=0, column=3)
        ttk.Button(oframe, text="Toggle Output", command=self.toggle_output).grid(row=0, column=4, padx=15)


    # -------------------------
    # Oscilloscope Tab
    # -------------------------

    def create_oscilloscope_tab(self):
        tab = self._make_scrollable_tab("Oscilloscope")

        # -------------------------
        # Device Selection
        # -------------------------
        ttk.Label(tab, text="Select Device:").pack(pady=5)

        self.scope_combo = ttk.Combobox(tab, values=self.resources, width=60)
        self.scope_combo.pack()

        ttk.Button(tab, text="Refresh Devices",
                command=lambda: self.refresh_devices(self.scope_combo)).pack(pady=5)

        self.scope_id_label = ttk.Label(tab, text="ID: ")
        self.scope_id_label.pack(pady=5)

        self.scope_combo.bind("<<ComboboxSelected>>",
                            lambda e: self.query_idn(self.scope_combo.get(), self.scope_id_label))

        ttk.Separator(tab, orient='horizontal').pack(fill='x', pady=10)

        # -------------------------
        # Save Waveform Section
        # -------------------------
        ttk.Label(tab, text="Save Waveform", font=("Arial", 12, "bold")).pack(pady=5)

        # Folder display
        self.save_folder = tk.StringVar()
        self.save_folder.set(os.getcwd())

        ttk.Label(tab, text="Save Folder:").pack()
        self.folder_label = ttk.Label(tab, textvariable=self.save_folder)
        self.folder_label.pack()

        folder_btn_frame = ttk.Frame(tab)
        folder_btn_frame.pack(pady=5)

        ttk.Button(folder_btn_frame, text="Select Folder",
                command=self.select_folder).grid(row=0, column=0, padx=5)

        ttk.Button(folder_btn_frame, text="Open Folder",
                command=self.open_folder).grid(row=0, column=1, padx=5)

        # Waveform name
        ttk.Label(tab, text="Waveform Name:").pack(pady=5)
        # Waveform name entry and Save Waveform button in the same row
        waveform_row = ttk.Frame(tab)
        waveform_row.pack(pady=5)
        self.waveform_name_entry = ttk.Entry(waveform_row, width=40)
        self.waveform_name_entry.pack(side="left", padx=(0, 8))
        ttk.Button(waveform_row, text="Save Waveform",
                command=self.save_waveform).pack(side="left")

        self.save_status_label = ttk.Label(tab, text="Status: ")
        self.save_status_label.pack(pady=5)

        # -------------------------
        # Oscilloscope Control Section
        # -------------------------
        ttk.Label(tab, text="Oscilloscope Control", 
                font=("Arial", 12, "bold")).pack(pady=5)

        self.h_scale_var = tk.StringVar()
        self.h_scale_var.set("Current Scale: Unknown")

        ttk.Label(tab, textvariable=self.h_scale_var).pack(pady=5)

        scale_btn_frame = ttk.Frame(tab)
        scale_btn_frame.pack(pady=5)

        # First row: Increase/Decrease Horizontal Scale
        row1 = ttk.Frame(scale_btn_frame)
        row1.pack()
        ttk.Button(row1, text="Increase Horizontal Scale",
                   command=self.increase_horizontal_scale).pack(side="left", padx=5)
        ttk.Button(row1, text="Decrease Horizontal Scale",
                   command=self.decrease_horizontal_scale).pack(side="left", padx=5)

        # Second row: RUN, STOP, SINGLE
        row2 = ttk.Frame(scale_btn_frame)
        row2.pack(pady=(5, 0))
        ttk.Button(row2, text="RUN",
                   command=self.run_mode).pack(side="left", padx=5)
        ttk.Button(row2, text="STOP",
                   command=self.stop_mode).pack(side="left", padx=5)
        ttk.Button(row2, text="SINGLE",
                   command=self.single_mode).pack(side="left", padx=5)
        ttk.Button(row2, text="Sequence",
                   command=self.sequence_mode).pack(side="left", padx=5)

        # Third row: Trigger Auto, Trigger Normal
        row3 = ttk.Frame(scale_btn_frame)
        row3.pack(pady=(5, 0))
        ttk.Button(row3, text="Trigger Auto",
                   command=self.trigger_auto).pack(side="left", padx=5)
        ttk.Button(row3, text="Trigger Normal",
                   command=self.trigger_normal).pack(side="left", padx=5)
        
        # -------------------------
        # Save Waveform to Reference Section
        # -------------------------
        ttk.Label(tab, text="Save Waveform to Reference", 
                font=("Arial", 12, "bold")).pack(pady=5)

        # Dropdowns for channel and reference selection in the same row
        select_row = ttk.Frame(tab)
        select_row.pack(pady=5)
        ttk.Label(select_row, text="Source:").pack(side="left", padx=(0, 8))
        self.channel_var = tk.StringVar(value="CH1")
        self.channel_combo = ttk.Combobox(select_row, textvariable=self.channel_var, values=["CH1", "CH2", "CH3", "CH4"], state="readonly", width=10)
        self.channel_combo.pack(side="left", padx=(0, 16))
        ttk.Label(select_row, text="Destination:").pack(side="left", padx=(0, 8))
        self.ref_var = tk.StringVar(value="REF1")
        self.ref_combo = ttk.Combobox(select_row, textvariable=self.ref_var, values=["REF1", "REF2", "REF3", "REF4"], state="readonly", width=10)
        self.ref_combo.pack(side="left")
        ttk.Button(select_row, text="Save to Reference",
                command=lambda: self.save_waveform_to_reference(self.channel_var.get(), self.ref_var.get())).pack(side="left")



        # -------------------------
        # Screen Annotation Section
        # -------------------------
        ttk.Label(tab, text="Screen Annotation",
                font=("Arial", 12, "bold")).pack(pady=5)

        ttk.Label(tab, text="Annotation Text:").pack()

        # Annotation entry and button in the same row
        annotation_row = ttk.Frame(tab)
        annotation_row.pack(pady=5)
        self.annotation_entry = ttk.Entry(annotation_row, width=50)
        self.annotation_entry.pack(side="left", padx=(0, 8))
        ttk.Button(annotation_row, text="Send Annotation",
                command=self.send_annotation).pack(side="left")

        self.annotation_status = ttk.Label(tab, text="Status: ")
        self.annotation_status.pack(pady=5)

        ttk.Separator(tab, orient='horizontal').pack(fill='x', pady=10)
    
    # -------------------------
    # Electronic Load Tab
    # -------------------------

    def create_electronic_load_tab(self):
        tab = self._make_scrollable_tab("Electronic Load")

        # -------------------------
        # Device Selection
        # -------------------------
        ttk.Label(tab, text="Select Device:").pack(pady=5)

        self.eload_combo = ttk.Combobox(tab, values=self.resources, width=60)
        self.eload_combo.pack()

        ttk.Button(tab, text="Refresh Devices",
                command=lambda: self.refresh_devices(self.eload_combo)).pack(pady=5)

        self.eload_id_label = ttk.Label(tab, text="ID: ")
        self.eload_id_label.pack(pady=5)
        self.eload_combo.bind("<<ComboboxSelected>>",
                            lambda e: self.query_idn(self.eload_combo.get(), self.eload_id_label))

        ttk.Separator(tab, orient='horizontal').pack(fill='x', pady=10)

        # --- ELoad Control ---
        eload_frame = ttk.LabelFrame(tab, text="E-Load Control", padding=10)
        eload_frame.pack(padx=10, pady=10, fill="x")

        # Channel 1 Controls
        ch1_frame = ttk.LabelFrame(eload_frame, text="E-Load")
        ch1_frame.pack(padx=10, pady=5, fill="x")
        self.eload_ch1_voltage_var = tk.StringVar()
        self.eload_ch1_current_var = tk.StringVar()
    
        ttk.Label(ch1_frame, text="Set Load Current(A):").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        ttk.Entry(ch1_frame, textvariable=self.eload_ch1_current_var, width=12).grid(row=1, column=1, padx=5, pady=5)
        ttk.Button(ch1_frame, text="Set Load Current", command=lambda: self.ELoad.set_current(self,self.eload_ch1_current_var.get())).grid(row=1, column=2, padx=10, pady=5)
        self.eload_current_setting_label = ttk.Label(ch1_frame, text="Current Setting: N/A")
        self.eload_current_setting_label.grid(row=1, column=3, padx=10, pady=5, sticky="w")
        ttk.Button(ch1_frame, text="Read", command=lambda: self.ELoad.read_current_setting(self)).grid(row=1, column=4, padx=5, pady=5)
        ttk.Button(ch1_frame, text="ON", command=lambda: self.ELoad.turn_on(self)).grid(row=2, column=1, padx=5, pady=5, sticky="e")
        ttk.Button(ch1_frame, text="OFF", command=lambda: self.ELoad.turn_off(self)).grid(row=2, column=2, padx=5, pady=5, sticky="w")
        ttk.Label(ch1_frame, text="Readback Voltage (V):").grid(row=3, column=0, padx=5, pady=5, sticky="e")
        self.eload_voltage_label = ttk.Label(ch1_frame, text="N/A")
        self.eload_voltage_label.grid(row=3, column=1, padx=5, pady=5, sticky="w")
        ttk.Label(ch1_frame, text="Readback Current (A):").grid(row=4, column=0, padx=5, pady=5, sticky="e")
        self.eload_current_label = ttk.Label(ch1_frame, text="N/A")
        self.eload_current_label.grid(row=4, column=1, padx=5, pady=5, sticky="w")

        # Auto-readback controls
        auto_frame = ttk.Frame(eload_frame)
        auto_frame.pack(pady=5, fill="x", padx=10)
        self.eload_auto_readback_var = tk.BooleanVar(value=False)
        self.eload_auto_checkbox = ttk.Checkbutton(auto_frame, text="Enable Automatic Readback", variable=self.eload_auto_readback_var, command=self.eload_toggle_auto_readback)
        self.eload_auto_checkbox.pack(side="left")
        ttk.Label(auto_frame, text="Interval (ms):").pack(side="left", padx=(20, 5))
        self.eload_readback_interval_var = tk.StringVar(value="1000")
        self.eload_readback_interval_entry = ttk.Entry(auto_frame, textvariable=self.eload_readback_interval_var, width=8)
        self.eload_readback_interval_entry.pack(side="left")

        # Undervoltage threshold
        uv_frame = ttk.Frame(eload_frame)
        uv_frame.pack(pady=5, fill="x", padx=10)
        ttk.Label(uv_frame, text="E-Load Undervoltage Threshold (V):").pack(side="left")
        self.eload_uv_threshold_var = tk.StringVar(value="0.1")
        ttk.Entry(uv_frame, textvariable=self.eload_uv_threshold_var, width=8).pack(side="left", padx=(5, 0))

        # Output toggle frame
        oframe = ttk.LabelFrame(tab, text="Toggle Load Current")
        oframe.pack(pady=8, fill="x", padx=10)

        ttk.Label(oframe, text="Delay Time (seconds):").grid(row=0, column=0, padx=5, pady=8, sticky="w")
        self.on_off_eload_delay_var = tk.StringVar()
        ttk.Entry(oframe, textvariable=self.on_off_eload_delay_var, width=15).grid(row=0, column=1)
        ttk.Button(oframe, text="Toggle", command=lambda: self.ELoad.toggle_output(self)).grid(row=0, column=2, padx=15)
        
        # Response box
        ttk.Label(tab, text="Response:").pack(pady=(5, 2))
        self.eload_response_text = tk.Text(tab, height=5, wrap="word", state="disabled")
        self.eload_response_text.pack(fill="x", padx=10)

        ttk.Button(tab, text="Clear Response", command=lambda: self.clear_response(self.eload_response_text)).pack(pady=6)

    def eload_update_readback(self):
        device = self.eload_combo.get()
        if not device:
            self.show_response("Status: No device selected", box=self.eload_response_text)
            self.eload_voltage_label.config(text="N/A")
            self.eload_current_label.config(text="N/A")
            return
        try:
            with self.rm.open_resource(device, timeout=2000) as inst:
                v1 = self.ELoad.measure_voltage(self)
                i1 = self.ELoad.measure_current(self)
                self.eload_voltage_label.config(text=f"{float(v1):.3f} V")
                self.eload_current_label.config(text=f"{float(i1):.3f} A")
        except Exception as e:
            self.show_response(f"Error: {e}", box=self.eload_response_text)
            self.eload_voltage_label.config(text="Error")
            self.eload_current_label.config(text="Error")
    def eload_toggle_auto_readback(self):
        if self.eload_auto_readback_var.get():
            self.eload_start_auto_readback()
        else:
            self.eload_stop_auto_readback()
    def eload_start_auto_readback(self):
        try:
            interval = int(self.eload_readback_interval_var.get())
            if interval < 100:
                messagebox.showwarning("Warning", "Interval too short, setting to 100 ms minimum.")
                interval = 100
        except ValueError:
            messagebox.showerror("Input Error", "Invalid interval value.")
            self.eload_auto_readback_var.set(False)
            return
        self._eload_auto_readback_loop(interval)
    def _eload_auto_readback_loop(self, interval):
        if self.eload_auto_readback_var.get():
            self.eload_update_readback()
            self.root.after(interval, lambda: self._eload_auto_readback_loop(interval))
    def eload_stop_auto_readback(self):
        self.eload_auto_readback_var.set(False)
        self.eload_voltage_label.config(text="N/A")
        self.eload_current_label.config(text="N/A")


    # -------------------------
    # DAQ973A + DAQM909A Tab
    # -------------------------

    _DAQ_RANGES      = ["300mV", "1V", "3V", "18V"]
    _DAQ_INPUT_TYPES = ["DIFF", "SEND", "IEPE"]
    _DAQ_COUPLINGS   = ["DC", "AC"]
    _DAQ_MODES       = ["TIME", "FREQ"]
    _DAQ_RATES       = ["1562.5", "3125", "6250", "12500", "25000", "50000", "100000", "200000", "400000", "800000"]

    def create_daq973a_tab(self):
        tab = self._make_scrollable_tab("Data Acq")

        ttk.Label(tab, text="Select Device:").pack(pady=5)
        self.daq_combo = ttk.Combobox(tab, values=self.resources, width=60)
        self.daq_combo.pack()
        ttk.Button(tab, text="Refresh Devices",
                   command=lambda: self.refresh_devices(self.daq_combo)).pack(pady=5)
        ttk.Button(tab, text="Check Connected Modules",
                   command=self._daq_on_device_selected).pack(pady=2)
        self.daq_id_label = ttk.Label(tab, text="ID: ")
        self.daq_id_label.pack(pady=5)
        self.daq_combo.bind("<<ComboboxSelected>>", self._daq_on_device_selected)

        ttk.Separator(tab, orient="horizontal").pack(fill="x", pady=8)

        # --- Channel config + results ---
        self.daq_ch_range      = {}
        self.daq_ch_input_type = {}
        self.daq_ch_coupling   = {}
        self.daq_ch_mode       = {}
        self.daq_ch_rate       = {}
        self.daq_ch_samp_count = {}
        self.daq_ch_results    = {}   # {ch: {"avg": Label, "std": Label, "min": Label, "max": Label}}

        channels_frame = ttk.Frame(tab)
        channels_frame.pack(fill="x", padx=10)

        # Header row
        for col, text in enumerate(["Ch", "Range", "Input Type", "Coupling", "Mode", "Rate (Sa/s)", "Samp Count", "Avg (V)", "Std Dev", "Min (V)", "Max (V)", ""]):
            ttk.Label(channels_frame, text=text, font=("Arial", 9, "bold")).grid(
                row=0, column=col, padx=4, pady=4, sticky="w")

        ttk.Label(channels_frame, text="Slot 1", font=("Arial", 9, "bold")).grid(
            row=1, column=0, columnspan=3, sticky="w", padx=4, pady=(4, 2))
        self.daq_slot1_status_label = ttk.Label(channels_frame, text="(select device to check)", foreground="gray")
        self.daq_slot1_status_label.grid(row=1, column=3, columnspan=9, sticky="w", padx=4, pady=(4, 2))

        for row_idx, ch in enumerate([101, 102, 103, 104], start=2):
            ttk.Label(channels_frame, text=str(ch)).grid(row=row_idx, column=0, padx=4, pady=4)

            rng = tk.StringVar(value="18V")
            self.daq_ch_range[ch] = rng
            ttk.Combobox(channels_frame, textvariable=rng, values=self._DAQ_RANGES,
                         state="readonly", width=6).grid(row=row_idx, column=1, padx=4)

            itype = tk.StringVar(value="DIFF")
            self.daq_ch_input_type[ch] = itype
            ttk.Combobox(channels_frame, textvariable=itype, values=self._DAQ_INPUT_TYPES,
                         state="readonly", width=6).grid(row=row_idx, column=2, padx=4)

            coup = tk.StringVar(value="DC")
            self.daq_ch_coupling[ch] = coup
            ttk.Combobox(channels_frame, textvariable=coup, values=self._DAQ_COUPLINGS,
                         state="readonly", width=5).grid(row=row_idx, column=3, padx=4)

            mode = tk.StringVar(value="TIME")
            self.daq_ch_mode[ch] = mode
            ttk.Combobox(channels_frame, textvariable=mode, values=self._DAQ_MODES,
                         state="readonly", width=5).grid(row=row_idx, column=4, padx=4)

            rate = tk.StringVar(value="100000")
            self.daq_ch_rate[ch] = rate
            ttk.Combobox(channels_frame, textvariable=rate, values=self._DAQ_RATES,
                         state="readonly", width=9).grid(row=row_idx, column=5, padx=4)

            samp_count = tk.StringVar(value="512")
            self.daq_ch_samp_count[ch] = samp_count
            ttk.Entry(channels_frame, textvariable=samp_count, width=8).grid(row=row_idx, column=6, padx=4)

            result_labels = {}
            for col_offset, key in enumerate(["avg", "std", "min", "max"]):
                lbl = ttk.Label(channels_frame, text="--", width=10, anchor="w")
                lbl.grid(row=row_idx, column=7 + col_offset, padx=4)
                result_labels[key] = lbl
            self.daq_ch_results[ch] = result_labels

            ttk.Button(channels_frame, text="Acquire",
                       command=lambda c=ch: self._daq_acquire_channel(c)).grid(
                row=row_idx, column=11, padx=6)

        # Slot 2 separator label + availability status
        ttk.Label(channels_frame, text="Slot 2", font=("Arial", 9, "bold")).grid(
            row=6, column=0, columnspan=3, sticky="w", padx=4, pady=(8, 2))
        self.daq_slot2_status_label = ttk.Label(channels_frame, text="(select device to check)", foreground="gray")
        self.daq_slot2_status_label.grid(row=6, column=3, columnspan=9, sticky="w", padx=4, pady=(8, 2))

        self.daq_slot2_widgets = []
        self._daq_slot2_avail  = False

        for row_idx, ch in enumerate([201, 202, 203, 204], start=7):
            ttk.Label(channels_frame, text=str(ch)).grid(row=row_idx, column=0, padx=4, pady=4)

            rng = tk.StringVar(value="18V")
            self.daq_ch_range[ch] = rng
            w = ttk.Combobox(channels_frame, textvariable=rng, values=self._DAQ_RANGES,
                             state="readonly", width=6)
            w.grid(row=row_idx, column=1, padx=4)
            self.daq_slot2_widgets.append(w)

            itype = tk.StringVar(value="DIFF")
            self.daq_ch_input_type[ch] = itype
            w = ttk.Combobox(channels_frame, textvariable=itype, values=self._DAQ_INPUT_TYPES,
                             state="readonly", width=6)
            w.grid(row=row_idx, column=2, padx=4)
            self.daq_slot2_widgets.append(w)

            coup = tk.StringVar(value="DC")
            self.daq_ch_coupling[ch] = coup
            w = ttk.Combobox(channels_frame, textvariable=coup, values=self._DAQ_COUPLINGS,
                             state="readonly", width=5)
            w.grid(row=row_idx, column=3, padx=4)
            self.daq_slot2_widgets.append(w)

            mode = tk.StringVar(value="TIME")
            self.daq_ch_mode[ch] = mode
            w = ttk.Combobox(channels_frame, textvariable=mode, values=self._DAQ_MODES,
                             state="readonly", width=5)
            w.grid(row=row_idx, column=4, padx=4)
            self.daq_slot2_widgets.append(w)

            rate = tk.StringVar(value="100000")
            self.daq_ch_rate[ch] = rate
            w = ttk.Combobox(channels_frame, textvariable=rate, values=self._DAQ_RATES,
                             state="readonly", width=9)
            w.grid(row=row_idx, column=5, padx=4)
            self.daq_slot2_widgets.append(w)

            samp_count = tk.StringVar(value="512")
            self.daq_ch_samp_count[ch] = samp_count
            w = ttk.Entry(channels_frame, textvariable=samp_count, width=8)
            w.grid(row=row_idx, column=6, padx=4)
            self.daq_slot2_widgets.append(w)

            result_labels = {}
            for col_offset, key in enumerate(["avg", "std", "min", "max"]):
                lbl = ttk.Label(channels_frame, text="--", width=10, anchor="w")
                lbl.grid(row=row_idx, column=7 + col_offset, padx=4)
                result_labels[key] = lbl
            self.daq_ch_results[ch] = result_labels

            btn = ttk.Button(channels_frame, text="Acquire",
                             command=lambda c=ch: self._daq_acquire_channel(c))
            btn.grid(row=row_idx, column=11, padx=6)
            self.daq_slot2_widgets.append(btn)

        # Slot 3 separator label + availability status
        ttk.Label(channels_frame, text="Slot 3", font=("Arial", 9, "bold")).grid(
            row=11, column=0, columnspan=3, sticky="w", padx=4, pady=(8, 2))
        self.daq_slot3_status_label = ttk.Label(channels_frame, text="(select device to check)", foreground="gray")
        self.daq_slot3_status_label.grid(row=11, column=3, columnspan=9, sticky="w", padx=4, pady=(8, 2))

        self.daq_slot3_widgets = []
        self._daq_slot3_avail  = False

        for row_idx, ch in enumerate([301, 302, 303, 304], start=12):
            ttk.Label(channels_frame, text=str(ch)).grid(row=row_idx, column=0, padx=4, pady=4)

            rng = tk.StringVar(value="18V")
            self.daq_ch_range[ch] = rng
            w = ttk.Combobox(channels_frame, textvariable=rng, values=self._DAQ_RANGES,
                             state="readonly", width=6)
            w.grid(row=row_idx, column=1, padx=4)
            self.daq_slot3_widgets.append(w)

            itype = tk.StringVar(value="DIFF")
            self.daq_ch_input_type[ch] = itype
            w = ttk.Combobox(channels_frame, textvariable=itype, values=self._DAQ_INPUT_TYPES,
                             state="readonly", width=6)
            w.grid(row=row_idx, column=2, padx=4)
            self.daq_slot3_widgets.append(w)

            coup = tk.StringVar(value="DC")
            self.daq_ch_coupling[ch] = coup
            w = ttk.Combobox(channels_frame, textvariable=coup, values=self._DAQ_COUPLINGS,
                             state="readonly", width=5)
            w.grid(row=row_idx, column=3, padx=4)
            self.daq_slot3_widgets.append(w)

            mode = tk.StringVar(value="TIME")
            self.daq_ch_mode[ch] = mode
            w = ttk.Combobox(channels_frame, textvariable=mode, values=self._DAQ_MODES,
                             state="readonly", width=5)
            w.grid(row=row_idx, column=4, padx=4)
            self.daq_slot3_widgets.append(w)

            rate = tk.StringVar(value="100000")
            self.daq_ch_rate[ch] = rate
            w = ttk.Combobox(channels_frame, textvariable=rate, values=self._DAQ_RATES,
                             state="readonly", width=9)
            w.grid(row=row_idx, column=5, padx=4)
            self.daq_slot3_widgets.append(w)

            samp_count = tk.StringVar(value="512")
            self.daq_ch_samp_count[ch] = samp_count
            w = ttk.Entry(channels_frame, textvariable=samp_count, width=8)
            w.grid(row=row_idx, column=6, padx=4)
            self.daq_slot3_widgets.append(w)

            result_labels = {}
            for col_offset, key in enumerate(["avg", "std", "min", "max"]):
                lbl = ttk.Label(channels_frame, text="--", width=10, anchor="w")
                lbl.grid(row=row_idx, column=7 + col_offset, padx=4)
                result_labels[key] = lbl
            self.daq_ch_results[ch] = result_labels

            btn = ttk.Button(channels_frame, text="Acquire",
                             command=lambda c=ch: self._daq_acquire_channel(c))
            btn.grid(row=row_idx, column=11, padx=6)
            self.daq_slot3_widgets.append(btn)

        ttk.Separator(tab, orient="horizontal").pack(fill="x", pady=8)

        bottom_frame = ttk.Frame(tab)
        bottom_frame.pack(fill="x", padx=10, pady=4)
        ttk.Button(bottom_frame, text="Acquire All Slot1",
                   command=self._daq_acquire_all).pack(side="left", padx=5)
        ttk.Button(bottom_frame, text="Initialize Slot1",
                   command=self._daq_init3_all).pack(side="left", padx=5)
        self.daq_slot2_acquire_btn = ttk.Button(bottom_frame, text="Acquire All Slot2",
                                                command=self._daq_acquire_all_slot2)
        self.daq_slot2_acquire_btn.pack(side="left", padx=5)
        self.daq_slot2_init_btn = ttk.Button(bottom_frame, text="Initialize Slot2",
                                             command=self._daq_init3_slot2)
        self.daq_slot2_init_btn.pack(side="left", padx=5)
        self.daq_slot2_widgets.append(self.daq_slot2_acquire_btn)
        self.daq_slot2_widgets.append(self.daq_slot2_init_btn)
        self.daq_slot3_acquire_btn = ttk.Button(bottom_frame, text="Acquire All Slot3",
                                                command=self._daq_acquire_all_slot3)
        self.daq_slot3_acquire_btn.pack(side="left", padx=5)
        self.daq_slot3_init_btn = ttk.Button(bottom_frame, text="Initialize Slot3",
                                             command=self._daq_init3_slot3)
        self.daq_slot3_init_btn.pack(side="left", padx=5)
        self.daq_slot3_widgets.append(self.daq_slot3_acquire_btn)
        self.daq_slot3_widgets.append(self.daq_slot3_init_btn)
        ttk.Button(bottom_frame, text="Clear Error (*CLS)",
                   command=self._daq_clear_error).pack(side="left", padx=5)
        ttk.Button(bottom_frame, text="Query Error (SYST:ERR?)",
                   command=self._daq_query_error).pack(side="left", padx=5)

        auto_frame = ttk.Frame(tab)
        auto_frame.pack(pady=5, fill="x", padx=10)
        self.daq_auto_acquire_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(auto_frame, text="Enable Automatic Acquire",
                        variable=self.daq_auto_acquire_var,
                        command=self._daq_toggle_auto_acquire).pack(side="left")
        ttk.Label(auto_frame, text="Interval (ms):").pack(side="left", padx=(20, 5))
        self.daq_auto_interval_var = tk.StringVar(value="500")
        ttk.Entry(auto_frame, textvariable=self.daq_auto_interval_var, width=8).pack(side="left")

        ttk.Label(tab, text="Status:").pack(anchor="w", padx=10, pady=(8, 2))
        self.daq_status_text = tk.Text(tab, height=4, wrap="word", state="disabled")
        self.daq_status_text.pack(fill="x", padx=10)
        ttk.Button(tab, text="Clear",
                   command=lambda: self.clear_response(self.daq_status_text)).pack(pady=4)

    def _daq_toggle_auto_acquire(self):
        if self.daq_auto_acquire_var.get():
            try:
                interval = int(self.daq_auto_interval_var.get())
                if interval < 100:
                    messagebox.showwarning("Warning", "Interval too short, setting to 100 ms minimum.")
                    interval = 100
                    self.daq_auto_interval_var.set("100")
            except ValueError:
                messagebox.showerror("Input Error", "Invalid interval value.")
                self.daq_auto_acquire_var.set(False)
                return
            self._daq_auto_acquire_loop(interval)

    def _daq_auto_acquire_loop(self, interval):
        if not self.daq_auto_acquire_var.get():
            return
        resource = self.daq_combo.get()
        if resource:
            threading.Thread(target=self._daq_auto_acquire_thread, args=(resource, interval), daemon=True).start()
        else:
            self.root.after(interval, lambda: self._daq_auto_acquire_loop(interval))

    def _daq_auto_acquire_thread(self, resource, interval):
        try:
            with self.rm.open_resource(resource) as inst:
                inst.timeout = 30000
                active_slots = [1]
                if self._daq_slot2_avail:
                    active_slots.append(2)
                if self._daq_slot3_avail:
                    active_slots.append(3)
                lines = []
                for slot in active_slots:
                    channels = [slot * 100 + i for i in range(1, 5)]
                    try:
                        results = self._daq_configure_and_acquire_slot(inst, channels)
                        for ch, stats in results.items():
                            self.root.after(0, lambda c=ch, s=stats: self._daq_update_result_labels(c, s))
                            lines.append(f"Ch{ch}: avg={stats['avg']:.6f} std={stats['std']:.6f} min={stats['min']:.6f} max={stats['max']:.6f}")
                    except Exception as e:
                        lines.append(f"Slot{slot} ERROR: {e}")
                self.root.after(0, lambda: self.show_response("\n".join(lines), box=self.daq_status_text))
        except Exception as e:
            self.root.after(0, lambda: self.show_response(f"Auto-acquire ERROR: {e}", box=self.daq_status_text))
        finally:
            self.root.after(interval, lambda: self._daq_auto_acquire_loop(interval))

    def _daq_on_device_selected(self, event=None):
        resource = self.daq_combo.get()
        self.query_idn(resource, self.daq_id_label)
        self.daq_slot2_status_label.config(text="Checking...", foreground="gray")
        threading.Thread(target=self._daq_check_slot2_thread, args=(resource,), daemon=True).start()

    def _daq_check_slot2_thread(self, resource):
        try:
            with self.rm.open_resource(resource) as inst:
                inst.timeout = 3000
                ctype1 = inst.query("SYSTem:CTYPe? 1").strip()
                ctype2 = inst.query("SYSTem:CTYPe? 2").strip()
                ctype3 = inst.query("SYSTem:CTYPe? 3").strip()
            avail2 = self._daq_parse_ctype_model(ctype2).upper() == "DAQM909A"
            avail3 = self._daq_parse_ctype_model(ctype3).upper() == "DAQM909A"
            self.root.after(0, lambda: self._daq_apply_slot_states(avail2, avail3, ctype1, ctype2, ctype3))
        except Exception as e:
            err = f"Error: {e}"
            self.root.after(0, lambda: self._daq_apply_slot_states(False, False, err, err, err))

    def _daq_parse_ctype_model(self, ctype: str) -> str:
        # Response format: "Manufacturer,Model,Serial,FW" — extract model field
        parts = [p.strip() for p in ctype.split(",")]
        return parts[1] if len(parts) >= 2 else ctype

    def _daq_slot_label_config(self, label, ctype: str, slot: int):
        model = self._daq_parse_ctype_model(ctype)
        if model == "0" or model == "":
            label.config(text="No module found", foreground="red")
        elif model.upper() == "DAQM909A":
            label.config(text=f"Model {model} is connected", foreground="green")
        else:
            label.config(text=f"Model {model} is connected but not supported", foreground="red")

    def _daq_apply_slot_widget_state(self, widgets, available: bool):
        for w in widgets:
            try:
                w.config(state="readonly" if (available and isinstance(w, ttk.Combobox)) else ("normal" if available else "disabled"))
            except Exception:
                pass

    def _daq_apply_slot_states(self, avail2: bool, avail3: bool, ctype1: str, ctype2: str, ctype3: str):
        self._daq_slot2_avail = avail2
        self._daq_slot3_avail = avail3
        self._daq_slot_label_config(self.daq_slot1_status_label, ctype1, 1)
        self._daq_slot_label_config(self.daq_slot2_status_label, ctype2, 2)
        self._daq_slot_label_config(self.daq_slot3_status_label, ctype3, 3)
        self._daq_apply_slot_widget_state(self.daq_slot2_widgets, avail2)
        self._daq_apply_slot_widget_state(self.daq_slot3_widgets, avail3)

    def _daq_init3_all(self):
        resource = self.daq_combo.get()
        if not resource:
            self.show_response("Status: No device selected", box=self.daq_status_text)
            return
        try:
            with self.rm.open_resource(resource) as inst:
                inst.timeout = 30000
                inst.write("INIT3 (@101,102,103,104)")
            self.show_response("INIT3 (@101,102,103,104) sent", box=self.daq_status_text)
        except Exception as e:
            self.show_response(f"INIT3 ERROR: {e}", box=self.daq_status_text)

    def _daq_init3_slot2(self):
        resource = self.daq_combo.get()
        if not resource:
            self.show_response("Status: No device selected", box=self.daq_status_text)
            return
        try:
            with self.rm.open_resource(resource) as inst:
                inst.timeout = 30000
                inst.write("INIT3 (@201,202,203,204)")
            self.show_response("INIT3 (@201,202,203,204) sent", box=self.daq_status_text)
        except Exception as e:
            self.show_response(f"INIT3 ERROR: {e}", box=self.daq_status_text)

    def _daq_acquire_all_slot2(self):
        resource = self.daq_combo.get()
        if not resource:
            self.show_response("Status: No device selected", box=self.daq_status_text)
            return
        threading.Thread(target=self._daq_acquire_all_slot2_thread, daemon=True).start()

    def _daq_acquire_all_slot2_thread(self):
        resource = self.daq_combo.get()
        lines = []
        try:
            with self.rm.open_resource(resource) as inst:
                inst.timeout = 30000
                results = self._daq_configure_and_acquire_slot(inst, [201, 202, 203, 204])
                for ch, stats in results.items():
                    self.root.after(0, lambda c=ch, s=stats: self._daq_update_result_labels(c, s))
                    lines.append(f"Ch{ch}: avg={stats['avg']:.6f} std={stats['std']:.6f} min={stats['min']:.6f} max={stats['max']:.6f}")
        except Exception as e:
            lines.append(f"Connection ERROR: {e}")
        msg = "\n".join(lines)
        self.root.after(0, lambda: self.show_response(msg, box=self.daq_status_text))

    def _daq_init3_slot3(self):
        resource = self.daq_combo.get()
        if not resource:
            self.show_response("Status: No device selected", box=self.daq_status_text)
            return
        try:
            with self.rm.open_resource(resource) as inst:
                inst.timeout = 30000
                inst.write("INIT3 (@301,302,303,304)")
            self.show_response("INIT3 (@301,302,303,304) sent", box=self.daq_status_text)
        except Exception as e:
            self.show_response(f"INIT3 ERROR: {e}", box=self.daq_status_text)

    def _daq_acquire_all_slot3(self):
        resource = self.daq_combo.get()
        if not resource:
            self.show_response("Status: No device selected", box=self.daq_status_text)
            return
        threading.Thread(target=self._daq_acquire_all_slot3_thread, daemon=True).start()

    def _daq_acquire_all_slot3_thread(self):
        resource = self.daq_combo.get()
        lines = []
        try:
            with self.rm.open_resource(resource) as inst:
                inst.timeout = 30000
                results = self._daq_configure_and_acquire_slot(inst, [301, 302, 303, 304])
                for ch, stats in results.items():
                    self.root.after(0, lambda c=ch, s=stats: self._daq_update_result_labels(c, s))
                    lines.append(f"Ch{ch}: avg={stats['avg']:.6f} std={stats['std']:.6f} min={stats['min']:.6f} max={stats['max']:.6f}")
        except Exception as e:
            lines.append(f"Connection ERROR: {e}")
        msg = "\n".join(lines)
        self.root.after(0, lambda: self.show_response(msg, box=self.daq_status_text))

    def _daq_configure_and_acquire_slot(self, inst, channels: list) -> dict:
        inst.write("ABOR3")
        inst.write("*CLS")
        for ch in channels:
            rng        = self.daq_ch_range[ch].get()
            itype      = self.daq_ch_input_type[ch].get()
            coup       = self.daq_ch_coupling[ch].get()
            mode       = self.daq_ch_mode[ch].get()
            rate       = self.daq_ch_rate[ch].get()
            samp_count = self.daq_ch_samp_count[ch].get().strip() or "DEF"
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

    def _daq_configure_and_acquire(self, inst, ch: int):
        rng        = self.daq_ch_range[ch].get()
        itype      = self.daq_ch_input_type[ch].get()
        coup       = self.daq_ch_coupling[ch].get()
        mode       = self.daq_ch_mode[ch].get()
        rate       = self.daq_ch_rate[ch].get()
        samp_count = self.daq_ch_samp_count[ch].get().strip() or "DEF"

        inst.write("ABOR3")
        inst.write("*CLS")
        inst.write(f"ACQ3:VOLT {rng},{itype},{coup},{mode},{samp_count},{rate},(@{ch})")
        inst.write(f"INIT3 (@{ch})")
        inst.query("*OPC?")
        # FETCh3:STATistics? record, first_pt, last_pt, (@ch)
        # record=1: first acquisition record; first_pt=1, last_pt=256: sample range for stats
        # returns avg, std_dev, min, max computed on instrument side
        raw = inst.query(f"FETCh3:STATistics? 1,1,256,(@{ch})").strip()
        # Returns: avg,std_dev,min,max
        parts = [float(x) for x in raw.split(",")]
        return {"avg": parts[0], "std": parts[1], "min": parts[2], "max": parts[3]}

    def _daq_update_result_labels(self, ch: int, stats: dict):
        labels = self.daq_ch_results[ch]
        labels["avg"].config(text=f"{stats['avg']:.6f}")
        labels["std"].config(text=f"{stats['std']:.6f}")
        labels["min"].config(text=f"{stats['min']:.6f}")
        labels["max"].config(text=f"{stats['max']:.6f}")

    def _daq_acquire_channel(self, ch: int):
        resource = self.daq_combo.get()
        if not resource:
            self.show_response("Status: No device selected", box=self.daq_status_text)
            return
        threading.Thread(target=self._daq_acquire_channel_thread, args=(ch,), daemon=True).start()

    def _daq_acquire_channel_thread(self, ch: int):
        resource = self.daq_combo.get()
        try:
            with self.rm.open_resource(resource) as inst:
                inst.timeout = 30000
                stats = self._daq_configure_and_acquire(inst, ch)
            self.root.after(0, lambda: self._daq_update_result_labels(ch, stats))
            self.root.after(0, lambda: self.show_response(
                f"Ch{ch}: avg={stats['avg']:.6f} std={stats['std']:.6f} min={stats['min']:.6f} max={stats['max']:.6f}",
                box=self.daq_status_text))
        except Exception as e:
            self.root.after(0, lambda: self.show_response(f"Ch{ch} ERROR: {e}", box=self.daq_status_text))

    def _daq_acquire_all(self):
        resource = self.daq_combo.get()
        if not resource:
            self.show_response("Status: No device selected", box=self.daq_status_text)
            return
        threading.Thread(target=self._daq_acquire_all_thread, daemon=True).start()

    def _daq_acquire_all_thread(self):
        resource = self.daq_combo.get()
        lines = []
        try:
            with self.rm.open_resource(resource) as inst:
                inst.timeout = 30000
                results = self._daq_configure_and_acquire_slot(inst, [101, 102, 103, 104])
                for ch, stats in results.items():
                    self.root.after(0, lambda c=ch, s=stats: self._daq_update_result_labels(c, s))
                    lines.append(f"Ch{ch}: avg={stats['avg']:.6f} std={stats['std']:.6f} min={stats['min']:.6f} max={stats['max']:.6f}")
        except Exception as e:
            lines.append(f"Connection ERROR: {e}")
        msg = "\n".join(lines)
        self.root.after(0, lambda: self.show_response(msg, box=self.daq_status_text))

    def _daq_clear_error(self):
        resource = self.daq_combo.get()
        if not resource:
            self.show_response("Status: No device selected", box=self.daq_status_text)
            return
        try:
            with self.rm.open_resource(resource) as inst:
                inst.timeout = 3000
                inst.write("*CLS")
            self.show_response("*CLS sent", box=self.daq_status_text)
        except Exception as e:
            self.show_response(f"*CLS ERROR: {e}", box=self.daq_status_text)

    def _daq_query_error(self):
        resource = self.daq_combo.get()
        if not resource:
            self.show_response("Status: No device selected", box=self.daq_status_text)
            return
        try:
            with self.rm.open_resource(resource) as inst:
                inst.timeout = 3000
                resp = inst.query("SYST:ERR?").strip()
            self.show_response(f"SYST:ERR? -> {resp}", box=self.daq_status_text)
        except Exception as e:
            self.show_response(f"SYST:ERR? ERROR: {e}", box=self.daq_status_text)

    # -------------------------
    # N8734A Power Supply Tab
    # -------------------------

    def create_n8734a_tab(self):
        tab = self._make_scrollable_tab("High Power Supply")
        self.n8734a_inst = None
        self._n8734a_auto_read_id = None

        vcmd = (self.root.register(self._n8734a_validate_float), '%P')

        # Device selection
        ttk.Label(tab, text="Select Device:").pack(pady=5)
        self.n8734a_combo = ttk.Combobox(tab, values=self.resources, width=50)
        self.n8734a_combo.pack()
        ttk.Button(tab, text="Refresh Devices",
                   command=lambda: self.refresh_devices(self.n8734a_combo)).pack(pady=5)
        self.n8734a_id_label = ttk.Label(tab, text="ID: ")
        self.n8734a_id_label.pack(pady=5)
        self.n8734a_combo.bind("<<ComboboxSelected>>",
                               lambda e: self.query_idn(self.n8734a_combo.get(), self.n8734a_id_label))

        # Connect / Disconnect
        conn_frame = ttk.Frame(tab)
        conn_frame.pack(pady=5)
        self.n8734a_connect_btn = ttk.Button(conn_frame, text="Connect", command=self.n8734a_connect)
        self.n8734a_connect_btn.pack(side="left", padx=5)
        self.n8734a_disconnect_btn = ttk.Button(conn_frame, text="Disconnect", command=self.n8734a_disconnect, state="disabled")
        self.n8734a_disconnect_btn.pack(side="left", padx=5)

        ttk.Separator(tab, orient='horizontal').pack(fill='x', pady=10)

        # Control frame
        ctrl_frame = ttk.LabelFrame(tab, text="N8734A Control", padding=10)
        ctrl_frame.pack(padx=10, pady=5, fill="x")

        # Voltage
        ttk.Label(ctrl_frame, text="Voltage (V):").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        self.n8734a_volt_var = tk.StringVar(value="0.000")
        ttk.Entry(ctrl_frame, textvariable=self.n8734a_volt_var, width=10, validate="key", validatecommand=vcmd).grid(row=0, column=1, padx=5, pady=5)
        ttk.Button(ctrl_frame, text="Set V", command=self.n8734a_set_voltage).grid(row=0, column=2, padx=10, pady=5)

        # Current
        ttk.Label(ctrl_frame, text="Current (A):").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        self.n8734a_curr_var = tk.StringVar(value="0.000")
        ttk.Entry(ctrl_frame, textvariable=self.n8734a_curr_var, width=10, validate="key", validatecommand=vcmd).grid(row=1, column=1, padx=5, pady=5)
        ttk.Button(ctrl_frame, text="Set I", command=self.n8734a_set_current).grid(row=1, column=2, padx=10, pady=5)

        # OVP
        ttk.Label(ctrl_frame, text="OVP (V):").grid(row=2, column=0, padx=5, pady=5, sticky="e")
        self.n8734a_ovp_var = tk.StringVar(value="0.000")
        ttk.Entry(ctrl_frame, textvariable=self.n8734a_ovp_var, width=10, validate="key", validatecommand=vcmd).grid(row=2, column=1, padx=5, pady=5)
        ttk.Button(ctrl_frame, text="Set OVP", command=self.n8734a_set_ovp).grid(row=2, column=2, padx=10, pady=5)

        # UVL
        ttk.Label(ctrl_frame, text="UVL (V):").grid(row=3, column=0, padx=5, pady=5, sticky="e")
        self.n8734a_uvl_var = tk.StringVar(value="0.000")
        ttk.Entry(ctrl_frame, textvariable=self.n8734a_uvl_var, width=10, validate="key", validatecommand=vcmd).grid(row=3, column=1, padx=5, pady=5)
        ttk.Button(ctrl_frame, text="Set UVL", command=self.n8734a_set_uvl).grid(row=3, column=2, padx=10, pady=5)

        # Output ON/OFF + LEDs
        btn_frame = ttk.Frame(ctrl_frame)
        btn_frame.grid(row=4, column=0, columnspan=3, padx=5, pady=10)
        self.n8734a_on_btn = tk.Button(btn_frame, text="ON", command=self.n8734a_output_on,
                                       bg="green", fg="white", width=5, font=("Arial", 9, "bold"))
        self.n8734a_on_btn.pack(side="left", padx=5)
        self.n8734a_off_btn = tk.Button(btn_frame, text="OFF", command=self.n8734a_output_off,
                                        bg="red", fg="white", width=5, font=("Arial", 9, "bold"))
        self.n8734a_off_btn.pack(side="left", padx=5)

        self.n8734a_output_led = tk.Canvas(btn_frame, width=16, height=16, highlightthickness=0)
        self.n8734a_output_led.pack(side="left", padx=5)
        self.n8734a_output_indicator = self.n8734a_output_led.create_oval(2, 2, 14, 14, fill="gray")
        ttk.Label(btn_frame, text="OUT").pack(side="left")

        self.n8734a_cv_led = tk.Canvas(btn_frame, width=16, height=16, highlightthickness=0)
        self.n8734a_cv_led.pack(side="left", padx=(15, 2))
        self.n8734a_cv_indicator = self.n8734a_cv_led.create_oval(2, 2, 14, 14, fill="gray")
        ttk.Label(btn_frame, text="CV").pack(side="left")

        self.n8734a_cc_led = tk.Canvas(btn_frame, width=16, height=16, highlightthickness=0)
        self.n8734a_cc_led.pack(side="left", padx=(10, 2))
        self.n8734a_cc_indicator = self.n8734a_cc_led.create_oval(2, 2, 14, 14, fill="gray")
        ttk.Label(btn_frame, text="CC").pack(side="left")

        ttk.Button(btn_frame, text="Check Limits", command=self.n8734a_check_limits).pack(side="left", padx=10)

        # OCP
        ocp_frame = ttk.Frame(ctrl_frame)
        ocp_frame.grid(row=5, column=0, columnspan=3, padx=5, pady=5)
        ttk.Button(ocp_frame, text="OCP ON", command=self.n8734a_ocp_on).pack(side="left", padx=5)
        ttk.Button(ocp_frame, text="OCP OFF", command=self.n8734a_ocp_off).pack(side="left", padx=5)
        self.n8734a_ocp_led = tk.Canvas(ocp_frame, width=16, height=16, highlightthickness=0)
        self.n8734a_ocp_led.pack(side="left", padx=5)
        self.n8734a_ocp_indicator = self.n8734a_ocp_led.create_oval(2, 2, 14, 14, fill="gray")
        ttk.Label(ocp_frame, text="OCP").pack(side="left")

        # Fault LEDs
        fault_frame = ttk.LabelFrame(ctrl_frame, text="Faults")
        fault_frame.grid(row=6, column=0, columnspan=3, padx=5, pady=5, sticky="ew")
        self.n8734a_fault_bits = [
            ("OV",  1),
            ("OC",  2),
            ("PF",  4),
            ("OT",  16),
            ("INH", 512),
            ("UNR", 1024),
        ]
        self.n8734a_fault_leds = {}
        for name, _ in self.n8734a_fault_bits:
            f = ttk.Frame(fault_frame)
            f.pack(side="left", padx=8, pady=5)
            canvas = tk.Canvas(f, width=16, height=16, highlightthickness=0)
            canvas.pack()
            indicator = canvas.create_oval(2, 2, 14, 14, fill="gray")
            ttk.Label(f, text=name, font=("Consolas", 8)).pack()
            self.n8734a_fault_leds[name] = (canvas, indicator)
        ttk.Button(fault_frame, text="Clear and OFF", command=self.n8734a_clear_protection).pack(side="right", padx=8, pady=5)

        # Auto-read toggle
        self.n8734a_auto_read_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(ctrl_frame, text="Auto Read Status",
                        variable=self.n8734a_auto_read_var,
                        command=self.n8734a_on_auto_read_toggle).grid(row=7, column=0, columnspan=3, pady=(5, 0))

        # Readback
        self.n8734a_meas_label = ttk.Label(ctrl_frame, text="Meas:  -- V  /  -- A", font=("Consolas", 10))
        self.n8734a_meas_label.grid(row=8, column=0, columnspan=3, pady=(0, 0))
        self.n8734a_power_label = ttk.Label(ctrl_frame, text="Power: -- W", font=("Consolas", 10))
        self.n8734a_power_label.grid(row=9, column=0, columnspan=3, pady=(0, 5))

    def _n8734a_validate_float(self, value):
        if value == "":
            return True
        try:
            float(value)
            return True
        except ValueError:
            return False

    def n8734a_connect(self):
        resource = self.n8734a_combo.get()
        if not resource:
            messagebox.showwarning("N8734A", "No resource selected.")
            return
        try:
            self.n8734a_inst = self.rm.open_resource(resource)
            self.n8734a_inst.timeout = 5000
            self.n8734a_inst.write_termination = '\n'
            self.n8734a_inst.read_termination = '\n'
            idn = self.n8734a_inst.query("*IDN?").strip()
            self.n8734a_id_label.config(text=f"ID: {idn}")
            self.n8734a_connect_btn.config(state="disabled")
            self.n8734a_disconnect_btn.config(state="normal")
            self._n8734a_read_initial_values()
            self.n8734a_update_readback()
        except Exception as e:
            messagebox.showerror("N8734A", f"Failed to connect:\n{e}")
            self.n8734a_inst = None

    def n8734a_disconnect(self):
        if self._n8734a_auto_read_id is not None:
            self.root.after_cancel(self._n8734a_auto_read_id)
            self._n8734a_auto_read_id = None
        if self.n8734a_inst:
            try:
                self.n8734a_inst.close()
            except Exception:
                pass
            self.n8734a_inst = None
        self.n8734a_id_label.config(text="ID: ")
        self.n8734a_connect_btn.config(state="normal")
        self.n8734a_disconnect_btn.config(state="disabled")
        self.n8734a_meas_label.config(text="Meas:  -- V  /  -- A")
        self.n8734a_power_label.config(text="Power: -- W")

    def _n8734a_read_initial_values(self):
        try:
            self.n8734a_volt_var.set(f"{float(self.n8734a_inst.query('VOLT?').strip()):.3f}")
            self.n8734a_curr_var.set(f"{float(self.n8734a_inst.query('CURR?').strip()):.3f}")
            self.n8734a_ovp_var.set(f"{float(self.n8734a_inst.query('VOLT:PROT:LEV?').strip()):.3f}")
            self.n8734a_uvl_var.set(f"{float(self.n8734a_inst.query('VOLT:LIM:LOW?').strip()):.3f}")
        except Exception:
            pass

    def n8734a_set_voltage(self):
        if self.n8734a_inst:
            self.n8734a_inst.write(f"VOLT {self.n8734a_volt_var.get()}")

    def n8734a_set_current(self):
        if self.n8734a_inst:
            self.n8734a_inst.write(f"CURR {self.n8734a_curr_var.get()}")

    def n8734a_set_ovp(self):
        if self.n8734a_inst:
            self.n8734a_inst.write(f"VOLT:PROT:LEV {self.n8734a_ovp_var.get()}")

    def n8734a_set_uvl(self):
        if self.n8734a_inst:
            self.n8734a_inst.write(f"VOLT:LIM:LOW {self.n8734a_uvl_var.get()}")

    def n8734a_output_on(self):
        if self.n8734a_inst:
            self.n8734a_inst.write("OUTP ON")

    def n8734a_output_off(self):
        if self.n8734a_inst:
            self.n8734a_inst.write("OUTP OFF")

    def n8734a_ocp_on(self):
        if self.n8734a_inst:
            self.n8734a_inst.write("CURR:PROT:STAT ON")

    def n8734a_ocp_off(self):
        if self.n8734a_inst:
            self.n8734a_inst.write("CURR:PROT:STAT OFF")

    def n8734a_clear_protection(self):
        if self.n8734a_inst:
            self.n8734a_inst.write("OUTP:PROT:CLE")
            self.n8734a_inst.write("OUTP OFF")

    def n8734a_check_limits(self):
        if not self.n8734a_inst:
            return
        try:
            ovp = float(self.n8734a_inst.query("VOLT:PROT:LEV?").strip())
            vlow = float(self.n8734a_inst.query("VOLT:LIM:LOW?").strip())
            ocp = self.n8734a_inst.query("CURR:PROT:STAT?").strip()
            curr_max = float(self.n8734a_inst.query("CURR? MAX").strip())
            volt_max = float(self.n8734a_inst.query("VOLT? MAX").strip())
            info = (
                f"OVP:       {ovp:.3f} V\n"
                f"V Low Lim: {vlow:.3f} V\n"
                f"V Max:     {volt_max:.3f} V\n"
                f"I Max:     {curr_max:.3f} A\n"
                f"OCP:       {'ON' if ocp == '1' else 'OFF'}"
            )
            top = tk.Toplevel()
            top.title("N8734A Limits")
            top.resizable(False, False)
            ttk.Label(top, text=info, font=("Consolas", 10), justify="left").pack(padx=15, pady=15)
        except Exception as e:
            messagebox.showerror("N8734A", f"Failed to query limits:\n{e}")

    def n8734a_on_auto_read_toggle(self):
        if self.n8734a_auto_read_var.get():
            self.n8734a_update_readback()
        else:
            if self._n8734a_auto_read_id is not None:
                self.root.after_cancel(self._n8734a_auto_read_id)
                self._n8734a_auto_read_id = None

    def n8734a_update_readback(self):
        if not self.n8734a_inst:
            if self.n8734a_auto_read_var.get():
                self._n8734a_auto_read_id = self.root.after(1000, self.n8734a_update_readback)
            return
        try:
            v = float(self.n8734a_inst.query("MEAS:VOLT?").strip())
            i = float(self.n8734a_inst.query("MEAS:CURR?").strip())
            self.n8734a_meas_label.config(text=f"Meas:  {v:.3f} V  /  {i:.3f} A")
            self.n8734a_power_label.config(text=f"Power: {v * i:.3f} W")
        except Exception:
            self.n8734a_meas_label.config(text="Meas:  -- V  /  -- A")
            self.n8734a_power_label.config(text="Power: -- W")
        self._n8734a_update_output_led()
        self._n8734a_update_cv_cc_leds()
        self._n8734a_update_ocp_led()
        self._n8734a_update_fault_leds()
        if self.n8734a_auto_read_var.get():
            self._n8734a_auto_read_id = self.root.after(1000, self.n8734a_update_readback)
        else:
            self._n8734a_auto_read_id = None

    def _n8734a_update_output_led(self):
        try:
            out = self.n8734a_inst.query("OUTP?").strip()
            color = "green" if out == "1" else "gray"
        except Exception:
            color = "yellow"
        self.n8734a_output_led.itemconfig(self.n8734a_output_indicator, fill=color)

    def _n8734a_update_cv_cc_leds(self):
        try:
            status = int(self.n8734a_inst.query("STAT:OPER:COND?").strip())
            cv = bool(status & 256)
            cc = bool(status & 1024)
        except Exception:
            cv = cc = False
        self.n8734a_cv_led.itemconfig(self.n8734a_cv_indicator, fill="green" if cv else "gray")
        self.n8734a_cc_led.itemconfig(self.n8734a_cc_indicator, fill="orange" if cc else "gray")

    def _n8734a_update_ocp_led(self):
        try:
            ocp = self.n8734a_inst.query("CURR:PROT:STAT?").strip()
            color = "green" if ocp == "1" else "gray"
        except Exception:
            color = "red"
        self.n8734a_ocp_led.itemconfig(self.n8734a_ocp_indicator, fill=color)

    def _n8734a_update_fault_leds(self):
        try:
            status = int(self.n8734a_inst.query("STAT:QUES:COND?").strip())
            for name, mask in self.n8734a_fault_bits:
                canvas, indicator = self.n8734a_fault_leds[name]
                faulted = bool(status & mask)
                canvas.itemconfig(indicator, fill="red" if faulted else "gray")
        except Exception:
            for name, _ in self.n8734a_fault_bits:
                canvas, indicator = self.n8734a_fault_leds[name]
                canvas.itemconfig(indicator, fill="yellow")

    # -------------------------
    # SCPI Low Level Tab
    # -------------------------

    def create_scpi_low_level_tab(self):
        tab = self._make_scrollable_tab("SCPI Low Level")

        # -------------------------
        # Device Selection
        # -------------------------
        ttk.Label(tab, text="Select Device:").pack(pady=5)

        self.device_combo = ttk.Combobox(tab, values=self.resources, width=60)
        self.device_combo.pack()

        ttk.Button(tab, text="Refresh Devices",
                command=lambda: self.refresh_devices(self.device_combo)).pack(pady=5)

        self.device_id_label = ttk.Label(tab, text="ID: ")
        self.device_id_label.pack(pady=5)

        self.device_combo.bind("<<ComboboxSelected>>",
                            lambda e: self.query_idn(self.device_combo.get(), self.device_id_label))

        ttk.Separator(tab, orient='horizontal').pack(fill='x', pady=10)

        # SCPI commands
        scpi_frame = ttk.LabelFrame(tab, text="Custom SCPI Commands")
        scpi_frame.pack(pady=10, fill="x", padx=10)

        self.scpi_vars = []
        for i in range(4):
            ttk.Label(scpi_frame, text=f"SCPI Command {i + 1}:").grid(
                row=i, column=0, padx=5, pady=6, sticky="w"
            )
            var = tk.StringVar()
            self.scpi_vars.append(var)
            ttk.Entry(scpi_frame, textvariable=var, width=60).grid(row=i, column=1, padx=5)
            ttk.Button(
                scpi_frame, text="Send", command=lambda v=var: self.send_scpi(self.device_combo.get(), v)
            ).grid(row=i, column=2, padx=5)
            ttk.Button(
                scpi_frame, text="Query", command=lambda v=var: self._scpi_query(self.device_combo.get(), v)
            ).grid(row=i, column=3, padx=5)

        # Response box
        ttk.Label(tab, text="SCPI Response:").pack(pady=(10, 2))
        self.scpi_response_text = tk.Text(tab, height=7, wrap="word", state="disabled")
        self.scpi_response_text.pack(fill="x", padx=10)

        ttk.Button(tab, text="Clear Response", command=lambda: self.clear_response(self.scpi_response_text)).pack(pady=6)

if __name__ == "__main__":
    root = tk.Tk()
    app = InstrumentGUI(root)
    root.mainloop()