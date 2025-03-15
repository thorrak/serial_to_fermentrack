import serial.tools.list_ports
import time

def get_usb_devices():
    devices = []
    for port in serial.tools.list_ports.comports():
        devices.append({
            "Device": port.device,  # e.g., /dev/ttyUSB0 or COM3
            "VID:PID": f"{port.vid:04X}:{port.pid:04X}" if port.vid and port.pid else "Unknown",
            "Serial Number": port.serial_number or "Unknown",
            "Manufacturer": port.manufacturer or "Unknown",
            "Description": port.description or "Unknown",
            "Location": port.location or "Unknown",  # Only available on some OSes
            "HWID": port.hwid or "Unknown"  # Contains VID, PID, and serial (Windows)
        })
    return devices

def print_devices(devices):
    print("\nDetected USB Serial Devices:")
    print("=" * 80)
    for device in devices:
        for key, value in device.items():
            print(f"{key}: {value}")
        print("-" * 80)
    if not devices:
        print("No USB serial devices detected.")
    print("\nWaiting for changes... (Ctrl+C to exit)")

def monitor_usb_changes(interval=2):
    """Continuously monitors USB devices and prints changes."""
    previous_devices = get_usb_devices()
    print_devices(previous_devices)

    try:
        while True:
            time.sleep(interval)
            current_devices = get_usb_devices()
            if current_devices != previous_devices:
                print("\n[Device list updated]")
                print_devices(current_devices)
                previous_devices = current_devices
    except KeyboardInterrupt:
        print("\nExiting...")

if __name__ == "__main__":
    monitor_usb_changes()
