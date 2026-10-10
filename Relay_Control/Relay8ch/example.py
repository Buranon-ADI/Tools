import time
import serial
import serial.tools.list_ports


def find_devices():
    """Scan COM ports and return dict {addr: serial.Serial}."""
    devices = {}
    for port in serial.tools.list_ports.comports():
        try:
            s = serial.Serial(port.device, 9600, timeout=2)
            time.sleep(2)
            s.reset_input_buffer()
            s.write(b"*IDN?\n")
            response = s.readline().decode().strip()
            if response.startswith("8Ch Relay Control"):
                parts = response.split(",")
                addr = int(parts[1].strip()) if len(parts) > 1 else 0
                devices[addr] = s
                print(f"  Found board {addr} on {port.device}")
            else:
                s.close()
        except (serial.SerialException, OSError, ValueError):
            continue
    return devices


def send(ser, cmd):
    ser.reset_input_buffer()
    ser.write(f"{cmd}\n".encode())
    time.sleep(0.1)
    response = ser.read(ser.in_waiting).decode().strip()
    return response


print("Scanning for relay boards...")
devices = find_devices()
if not devices:
    print("No devices found")
    raise SystemExit

print(f"\n{len(devices)} board(s) connected: {list(devices.keys())}")
print("Commands: <board>:<pin>_<L|H>  e.g. 0:D2_L, 1:D5_H")
print("          Or without board prefix (uses board 0): D2_L, D3_H")
print("          quit to exit")

while True:
    cmd = input("\n> ").strip()
    if cmd.lower() == "quit":
        break

    if ":" in cmd:
        try:
            addr_str, pin_cmd = cmd.split(":", 1)
            addr = int(addr_str)
        except ValueError:
            print("Invalid board address")
            continue
    else:
        addr = 0
        pin_cmd = cmd

    if addr not in devices:
        print(f"Board {addr} not connected. Available: {list(devices.keys())}")
        continue

    if len(pin_cmd) == 4 and pin_cmd[0] == "D" and pin_cmd[2] == "_" and pin_cmd[3] in "LH":
        send(devices[addr], pin_cmd)
        state = "ON" if pin_cmd[3] == "L" else "OFF"
        print(f"Board {addr} Relay {pin_cmd[:2]} {state}")
    else:
        print("Invalid. Use: [board:]D2_L, D2_H, ... D9_L, D9_H, quit")

for s in devices.values():
    s.close()
print("Done")
