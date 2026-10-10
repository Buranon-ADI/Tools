import tkinter as tk
from tkinter import ttk, filedialog
import pyvisa
import os
import platform
import subprocess
from datetime import datetime

# Global variable to hold save folder path
save_folder = ""

def get_visa_devices():
    try:
        rm = pyvisa.ResourceManager()
        return rm.list_resources()
    except Exception as e:
        print(f"VISA Error: {e}")
        return []

def on_device_selected(event=None):
    selected = device_dropdown.get()
    try:
        rm = pyvisa.ResourceManager()
        inst = rm.open_resource(selected)
        idn = inst.query("*IDN?")
        id_label.config(text=f"IDN: {idn.strip()}")
        print(f"Selected Device: {selected}")
        print(f"IDN Response: {idn.strip()}")
    except Exception as e:
        id_label.config(text=f"Query Error: {e}")
        print(f"Query Error: {e}")

def select_folder():
    global save_folder
    folder = filedialog.askdirectory()
    if folder:
        save_folder = folder
        folder_label.config(text=f"Selected folder: {folder}")
        print(f"Selected folder: {folder}")

def open_save_folder():
    global save_folder
    if not save_folder:
        response_label.config(text="No folder selected to open.")
        return

    try:
        if platform.system() == "Windows":
            os.startfile(save_folder)
        elif platform.system() == "Darwin":  # macOS
            subprocess.Popen(["open", save_folder])
        else:  # Linux and others
            subprocess.Popen(["xdg-open", save_folder])
        response_label.config(text=f"Opened folder: {save_folder}")
    except Exception as e:
        response_label.config(text=f"Failed to open folder: {e}")
        print(f"Open Folder Error: {e}")

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

        # Set screenshot format and capture image
        instrument.write("HARDCOPY:FORMAT PNG")
        instrument.write("HARDCOPY START")

        # Read image data from oscilloscope
        image_data = instrument.read_raw()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Use the filename entered by user or default
        filename = screenshot_file_name.get().strip()
        if not filename:
            filename = "oscilloscope_screenshot"
        filepath = os.path.join(save_folder, f"{filename}_{timestamp}.png")

        with open(filepath, "wb") as f:
            f.write(image_data)

        response_label.config(text=f"Screenshot saved: {filepath}")
        instrument.close()
        print(f"Screenshot saved: {filepath}")
    except Exception as e:
        response_label.config(text=f"Screenshot error: {e}")
        print("Screenshot Error:", e)

# --- Pre-scan devices ---
devices = get_visa_devices()

# --- GUI Setup ---
root = tk.Tk()
root.title("VISA Device Selector & Screenshot")

device_dropdown = ttk.Combobox(root, width=50, state="readonly")
device_dropdown['values'] = devices
device_dropdown.set(devices[0] if devices else "No devices found")
device_dropdown.pack(pady=10)
device_dropdown.bind("<<ComboboxSelected>>", on_device_selected)

id_label = tk.Label(root, text="Select a device to view its IDN")
id_label.pack(pady=5)

folder_button = tk.Button(root, text="Select Save Folder", command=select_folder)
folder_button.pack(pady=10)

folder_open_button = tk.Button(root, text="Open Save Folder", command=open_save_folder)
folder_open_button.pack(pady=5)

folder_label = tk.Label(root, text="No folder selected")
folder_label.pack(pady=5)

tk.Label(root, text="Screenshot File Name:").pack(pady=(10, 0))
screenshot_file_name = tk.Entry(root, width=40)
screenshot_file_name.pack(pady=5)
screenshot_file_name.insert(0, "oscilloscope_screenshot")

save_button = tk.Button(root, text="Save Screenshot", command=save_scope_screenshot)
save_button.pack(pady=10)

response_label = tk.Label(root, text="")
response_label.pack(pady=5)

# Auto-query IDN on start if devices exist
if devices:
    on_device_selected()

root.mainloop()
