import tkinter as tk
from tkinter import ttk, filedialog
import pyvisa
import os
from datetime import datetime
import numpy as np

# Globals
save_folder = ""
screenshot_file_name = ""
rising_threshold = 1.0
falling_threshold = 0.5

def search_visa_devices():
    rm = pyvisa.ResourceManager()
    try:
        devices = rm.list_resources()
        device_dropdown['values'] = devices
        if devices:
            device_dropdown.current(0)
            query_device_id()
        else:
            device_dropdown.set("No devices found")
            id_label.config(text="")
    except Exception as e:
        device_dropdown.set("Error")
        id_label.config(text=f"Error: {e}")
        print("VISA Error:", e)

def query_device_id(event=None):
    selected_device = device_dropdown.get()
    if not selected_device or "No devices" in selected_device:
        id_label.config(text="")
        return

    rm = pyvisa.ResourceManager()
    try:
        instrument = rm.open_resource(selected_device)
        idn = instrument.query("*IDN?")
        id_label.config(text=f"Device ID: {idn.strip()}")
        instrument.close()
    except Exception as e:
        id_label.config(text=f"Error querying *IDN?: {e}")
        print("Query Error:", e)

def send_command():
    selected_device = device_dropdown.get()
    command = command_entry.get().strip()

    if not selected_device or "No devices" in selected_device:
        response_label.config(text="No device selected.")
        return

    if not command:
        response_label.config(text="Enter a command.")
        return

    rm = pyvisa.ResourceManager()
    try:
        instrument = rm.open_resource(selected_device)

        if command.endswith("?"):
            response = instrument.query(command)
            response_label.config(text=f"Response: {response.strip()}")
            print(response)
        else:
            instrument.write(command)
            response_label.config(text=f"Command sent: {command}")
        
        instrument.close()
    except Exception as e:
        response_label.config(text=f"Error: {e}")
        print("Command Error:", e)

def control_scope():
    selected_device = device_dropdown.get()

    if not selected_device or "No devices" in selected_device:
        response_label.config(text="No device selected for scope control.")
        return

    rm = pyvisa.ResourceManager()
    try:
        # instrument = rm.open_resource(selected_device)
        scope = rm.open_resource(selected_device)  # Update VISA address!

        # Step 1: Setup waveform read on CH2 (binary data)
        # scope.write("DATA:SOURCE CH2")
        # scope.write("DATA:ENCdg BIN")     # Binary format
        # scope.write("DATA:WIDth 1")       # 1 byte per sample
        # scope.write("DATA:START 1")
        # scope.write("DATA:STOP 1000000")  # As per your preamble points

        # Step 2: Get waveform preamble info
        preamble_raw = scope.query("WFMPRE?")
        fields = preamble_raw.split(';')

        # Parse preamble (same as previous parsing)
        num_points = int(fields[6])
        x_increment = float(fields[9])
        x_origin = float(fields[10])
        y_multiplier = float(fields[13])
        y_offset = float(fields[14])
        y_zero = float(fields[15])

        # Step 3: Read waveform binary data
        scope.write("CURVE?")
        raw_waveform = scope.read_raw()

        # Tektronix binary data header parsing: first byte is '#', then a digit N telling how many digits to read for data length
        # Example: b'#41024' means next 1024 bytes are data
        # Parse accordingly:

        header_len = int(raw_waveform[1:2])  # N digits count
        data_len = int(raw_waveform[2:2+header_len])
        data_start = 2 + header_len
        data_end = data_start + data_len

        waveform_bytes = raw_waveform[data_start:data_end]
        waveform_raw = np.frombuffer(waveform_bytes, dtype=np.uint8)

        # Step 4: Convert raw data to voltage
        voltages = (waveform_raw - y_offset) * y_multiplier + y_zero

        # Step 5: Create time axis
        times = np.arange(len(voltages)) * x_increment + x_origin

        # Step 6: Find first rising edge crossing threshold (adjust threshold as needed)
        threshold = float(rising_threshold.get())
        print(f"Rising Threshold(V) = {threshold}")

        rising_edges = np.where((voltages[:-1] < threshold) & (voltages[1:] >= threshold))[0]

        if rising_edges.size == 0:
            print("No rising edge found.")
            scope.close()
            rm.close()
            exit()

        first_edge_index = rising_edges[0]
        first_edge_time = times[first_edge_index]

        print(f"First rising edge at time: {first_edge_time:.9f} seconds")

        # Step 7: Move Cursor A to rising edge time
        scope.write("CURSor1:STATe ON")
        scope.write("CURSor1:TYPE VERTical")
        scope.write(f"CURSor:VBARs:POSITION1 {first_edge_time}")

        print("Cursor A moved to first rising edge.")


        # Find falling edge after rising edge
        # threshold = 1.0  # Adjust this to your signal level

        # Find rising edge
        rising_edges = np.where((voltages[:-1] < threshold) & (voltages[1:] >= threshold))[0]
        # print(f"voltages = {voltages} \n voltages[:-1] {voltages[:-1]} \n voltages[1:] {voltages[1:]}")

        if rising_edges.size == 0:
            print("No rising edge found.")
            scope.close()
            rm.close()
            exit()
        threshold = float(falling_threshold.get())
        print(f"Falling Threshold(V) = {threshold}")
        rising_index = rising_edges[0]
        rising_time = times[rising_index]
        falling_edges = np.where(
            (voltages[rising_index:-1] > threshold) & (voltages[rising_index+1:] <= threshold)
        )[0]

        # print(f"falling_edges = {falling_edges}")

        if falling_edges.size == 0:
            print("No falling edge found.")
            scope.close()
            rm.close()
            exit()

        falling_index = falling_edges[0] + rising_index  # offset index
        falling_time = times[falling_index]
        print(f"Falling edge at {falling_time:.9f} s")
        scope.write(f"CURSor:VBARs:POSITION2 {falling_time}")


        # Read Cursor A and B time positions
        cursor_a_time = float(scope.query("CURSor:VBARs:POSITION1?"))
        cursor_b_time = float(scope.query("CURSor:VBARs:POSITION2?"))

        delta_time = abs(cursor_b_time - cursor_a_time)*1e6
        print(f"Δ Time: {delta_time:.2f} µs")

        # cursor_a_volt = float(scope.query("CURSor:HBARs:POSITION1?"))
        # cursor_b_volt = float(scope.query("CURSor:HBARs:POSITION2?"))
    
        delta_volt = abs(float(scope.query("CURSor:VBArs:VDELTa?")))*1e3
        print(f"Δ Voltage: {delta_volt:.2f}  mV")

        slew_rate = delta_volt/delta_time

        print(f"Slew Rate = {slew_rate:.2f} mV/us")


        # Cleanup
        scope.close()
        rm.close()
    except Exception as e:
        response_label.config(text=f"Scope control error: {e}")
        print("Scope Error:", e)

def select_folder():
    global save_folder
    folder = filedialog.askdirectory()
    if folder:
        save_folder = folder
        folder_label.config(text=f"Save Folder: {save_folder}", fg="black")

def save_scope_screenshot():
    global save_folder
    selected_device = device_dropdown.get()

    if not selected_device or "No devices" in selected_device:
        response_label.config(text="No device selected for screenshot.")
        return

    if not save_folder:
        response_label.config(text="No save folder selected.")
        return

    rm = pyvisa.ResourceManager()
    try:
        instrument = rm.open_resource(selected_device)
        instrument.timeout = 5000  # Allow time for image transfer

        # Adjust command for your oscilloscope model
        # image_data = instrument.query_binary_values("DISP:DATA? PNG", datatype='B', container=bytes)
        # Set the oscilloscope to output the screenshot in PNG format
        instrument.write("HARDCOPY:FORMAT PNG")
        instrument.write("HARDCOPY START")  # Capture screenshot
 
        # Read image data from the oscilloscope
        image_data = instrument.read_raw()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(save_folder, f"{screenshot_file_name.get()}_{timestamp}.png")
        with open(filepath, "wb") as f:
            f.write(image_data)

        response_label.config(text=f"Screenshot saved: {filepath}")
        instrument.close()
    except Exception as e:
        response_label.config(text=f"Screenshot error: {e}")
        print("Screenshot Error:", e)

# GUI Setup
root = tk.Tk()
root.title("VISA Device Communicator")
root.geometry("650x220")

# Device dropdown
tk.Label(root, text="Connected VISA Devices:", font=("Arial", 12)).pack(pady=10)

device_dropdown = ttk.Combobox(root, state="readonly", width=75)
device_dropdown.pack(pady=5)
device_dropdown.bind("<<ComboboxSelected>>", query_device_id)

# Device ID display
id_label = tk.Label(root, text="", font=("Arial", 11), fg="blue")
id_label.pack(pady=10)

# Command input frame
command_frame = tk.Frame(root)
command_frame.pack(pady=5)

tk.Label(command_frame, text="Enter Command:").pack(side=tk.LEFT)
command_entry = tk.Entry(command_frame, width=45)
command_entry.pack(side=tk.LEFT, padx=5)

send_button = tk.Button(command_frame, text="Send Command", command=send_command)
send_button.pack(side=tk.LEFT)

# # Control Scope button
# scope_button = tk.Button(root, text="Control Scope", command=control_scope)
# scope_button.pack(pady=10)

# # Folder selection
# folder_frame = tk.Frame(root)
# folder_frame.pack(pady=5)

# select_folder_button = tk.Button(folder_frame, text="Select Save Folder", command=select_folder)
# select_folder_button.pack(side=tk.LEFT)

# folder_label = tk.Label(folder_frame, text="No folder selected", fg="gray", wraplength=500)
# folder_label.pack(side=tk.LEFT, padx=10)

# # screenshot file name
# text_frame = tk.Frame(root)
# text_frame.pack(pady=5)

# tk.Label(text_frame, text="Enter File name:").pack(side=tk.LEFT)
# screenshot_file_name = tk.Entry(text_frame, width=20)
# screenshot_file_name.pack(side=tk.LEFT, padx=5)

# # Rising Threshold
# rising_threshold_frame = tk.Frame(root)
# rising_threshold_frame.pack(pady=5)

# tk.Label(rising_threshold_frame, text="Rising Threshold(V):").pack(side=tk.LEFT)
# rising_threshold = tk.Entry(rising_threshold_frame, width=20)
# rising_threshold.insert(0, "1.0")  # Default value set here
# rising_threshold.pack(side=tk.LEFT, padx=10)

# # Fallinf Threshold
# falling_threshold_frame = tk.Frame(root)
# falling_threshold_frame.pack(pady=5)

# tk.Label(falling_threshold_frame, text="Falling Threshold(V):").pack(side=tk.LEFT)
# falling_threshold = tk.Entry(falling_threshold_frame, width=20)
# falling_threshold.insert(0, "0.5")  # Default value set here
# falling_threshold.pack(side=tk.LEFT, padx=10)



# Screenshot button
# screenshot_button = tk.Button(root, text="Save Screenshot", command=save_scope_screenshot)
# screenshot_button.pack(pady=10)

# Response label
response_label = tk.Label(root, text="", font=("Arial", 11), fg="green", wraplength=600, justify="left")
response_label.pack(pady=10)

# Search for VISA devices on startup
root.after(100, search_visa_devices)

# Run GUI
root.mainloop()
