"""Windows laptop remote + serial monitor for the river-cleaning robot over HC-06 Bluetooth.

This version keeps all serial I/O off the Tkinter UI thread so the interface does
not freeze when the Bluetooth COM port is slow or disconnected.

IMPORTANT:
- For COMMANDS, HC-06 TXD -> Arduino RX pin is enough.
- To SEE Arduino status/debug messages in this app, Arduino TX pin -> HC-06 RXD
  must also be connected (through a voltage divider if Arduino is 5 V logic).

Setup:
  1. Pair HC-06 in Windows.
  2. Find its Bluetooth serial COM port in Device Manager.
  3. Install pyserial:  py -m pip install pyserial
  4. Change COM_PORT below.

Controls: (Capital is required)
  W / Up Arrow      Forward
  S / Down Arrow    Backward
  A / Left Arrow    Turn left
  D / Right Arrow   Turn right
  Q / E             Rotate left / right
  Space             Stop propulsion
  C                 Conveyor up
  V                 Conveyor down
  X                 Stop conveyor
  U                 Autonomous mode
  I                 Idle
  Esc               Stop + close
"""

import tkinter as tk
from tkinter.scrolledtext import ScrolledText
import serial
import threading
import queue
import time

COM_PORT = "COM4"      # Change to the HC-06 Bluetooth COM port.
BAUD = 9600
CONNECT_TIMEOUT = 2.0
WRITE_TIMEOUT = 0.75

# UI -> worker command queue
send_queue = queue.Queue()
stop_event = threading.Event()
ser = None
serial_lock = threading.Lock()

active_motion_key = None

MOTION_COMMANDS = {
    "w": "F", "Up": "F",
    "s": "B", "Down": "B",
    "a": "L", "Left": "L",
    "d": "R", "Right": "R",
    "q": "Q",
    "e": "E",
}

SINGLE_COMMANDS = {
    "space": "S",
    "c": "C",
    "v": "V",
    "x": "X",
    "u": "U",
    "i": "I",
}


def ui_status(text):
    """Safely schedule a status update on the Tkinter thread."""
    try:
        root.after(0, status_var.set, text)
    except tk.TclError:
        pass


def ui_connection(text):
    try:
        root.after(0, connection_var.set, text)
    except tk.TclError:
        pass


def ui_monitor_append(text):
    """Append received serial text to the monitor box."""
    try:
        root.after(0, _monitor_append_now, text)
    except tk.TclError:
        pass


def _monitor_append_now(text):
    try:
        serial_monitor.configure(state="normal")
        serial_monitor.insert("end", text)
        serial_monitor.see("end")
        serial_monitor.configure(state="disabled")
    except tk.TclError:
        pass


def connect_serial():
    """Open the Bluetooth COM port in the worker thread."""
    global ser
    with serial_lock:
        try:
            if ser is not None and ser.is_open:
                return True

            ui_connection(f"Connecting to {COM_PORT}...")
            ser = serial.Serial(
                COM_PORT,
                BAUD,
                timeout=0.05,
                write_timeout=WRITE_TIMEOUT,
            )
            ui_connection(f"CONNECTED: {COM_PORT} @ {BAUD} baud")
            ui_monitor_append(f"\n--- Connected to {COM_PORT} @ {BAUD} baud ---\n")
            return True
        except Exception as exc:
            ser = None
            ui_connection(f"NOT CONNECTED: {exc}")
            return False


def close_serial():
    global ser
    with serial_lock:
        try:
            if ser is not None and ser.is_open:
                ser.close()
        except Exception:
            pass
        ser = None


def serial_worker():
    """Background serial worker for both TX and RX."""
    connect_serial()
    rx_buffer = ""

    while not stop_event.is_set():
        # Reconnect automatically if needed.
        if ser is None or not getattr(ser, "is_open", False):
            connect_serial()
            time.sleep(0.25)
            continue

        # ---- Read incoming Arduino/HC-06 text ----
        try:
            with serial_lock:
                waiting = getattr(ser, "in_waiting", 0)
                data = ser.read(waiting if waiting > 0 else 1)

            if data:
                decoded = data.decode("utf-8", errors="replace")
                ui_monitor_append(decoded)

        except Exception as exc:
            ui_connection(f"READ DISCONNECTED: {exc}")
            close_serial()
            time.sleep(0.25)
            continue

        # ---- Send queued command if one exists ----
        try:
            command = send_queue.get_nowait()
        except queue.Empty:
            command = None

        if command is None:
            time.sleep(0.01)
            continue

        if command == "__QUIT__":
            break

        payload = command.encode("ascii")
        started = time.perf_counter()

        try:
            with serial_lock:
                written = ser.write(payload)
                ser.flush()
                pending = getattr(ser, "out_waiting", 0)

            elapsed_ms = (time.perf_counter() - started) * 1000.0

            if written == len(payload) and pending == 0:
                ui_status(
                    f"SEND OK: '{command}' | {written} byte | "
                    f"driver queue empty | {elapsed_ms:.0f} ms"
                )
            elif written == len(payload):
                ui_status(
                    f"QUEUED: '{command}' | {written} byte | "
                    f"{pending} byte(s) still pending"
                )
            else:
                ui_status(
                    f"PARTIAL SEND: '{command}' | {written}/{len(payload)} byte"
                )

        except serial.SerialTimeoutException:
            ui_status(f"TIMEOUT: '{command}' was not accepted by Bluetooth COM port")
            ui_connection(f"Connection problem on {COM_PORT}")
            close_serial()
        except Exception as exc:
            ui_status(f"SEND ERROR: '{command}' | {exc}")
            ui_connection(f"DISCONNECTED: {exc}")
            close_serial()

    close_serial()


def queue_command(command):
    """Never write serial data directly from the UI thread."""
    send_queue.put(command)
    status_var.set(f"Queued: '{command}'")


def reconnect():
    """Request a reconnect without blocking the GUI."""
    close_serial()
    ui_connection("Reconnect requested...")
    ui_monitor_append("\n--- Reconnect requested ---\n")


def clear_monitor():
    try:
        serial_monitor.configure(state="normal")
        serial_monitor.delete("1.0", "end")
        serial_monitor.configure(state="disabled")
    except tk.TclError:
        pass


def on_key_press(event):
    global active_motion_key
    key = event.keysym
    key_lower = key.lower()

    if key == "Escape":
        queue_command("S")
        root.after(150, on_close)
        return

    command = MOTION_COMMANDS.get(key, MOTION_COMMANDS.get(key_lower))
    if command is not None:
        if active_motion_key != key:
            active_motion_key = key
            queue_command(command)
        return

    command = SINGLE_COMMANDS.get(key_lower)
    if command is not None:
        queue_command(command)


def on_key_release(event):
    global active_motion_key
    key = event.keysym
    key_lower = key.lower()

    if key in MOTION_COMMANDS or key_lower in MOTION_COMMANDS:
        if active_motion_key == key:
            active_motion_key = None
            queue_command("S")


def on_close():
    stop_event.set()
    send_queue.put("__QUIT__")
    try:
        root.destroy()
    except tk.TclError:
        pass


root = tk.Tk()
root.title("Boat HC-06 Bluetooth Remote + Serial Monitor")
root.geometry("760x700")
root.resizable(False, False)

connection_var = tk.StringVar(value=f"Starting connection to {COM_PORT}...")
status_var = tk.StringVar(value="No command sent yet")

instructions = (
    "W / ↑  Forward       S / ↓  Backward\n"
    "A / ←  Left          D / →  Right\n"
    "Q / E  Rotate        Space  Stop\n\n"
    "C  Conveyor up       V  Conveyor down\n"
    "X  Conveyor stop\n"
    "U  Autonomous        I  Idle\n\n"
    "Release a movement key to send STOP."
)

tk.Label(root, text="River Cleaning Robot - HC-06", font=("Segoe UI", 16, "bold")).pack(pady=(12, 6))
tk.Label(root, text=instructions, font=("Segoe UI", 11), justify="left").pack()

tk.Label(root, textvariable=connection_var, font=("Segoe UI", 10, "bold"), wraplength=700).pack(pady=(10, 3))
tk.Label(root, textvariable=status_var, font=("Consolas", 10), wraplength=700).pack(pady=(3, 6))

button_frame = tk.Frame(root)
button_frame.pack(pady=4)

tk.Button(button_frame, text="Reconnect HC-06", command=reconnect, width=20).pack(side="left", padx=5)
tk.Button(button_frame, text="Clear Monitor", command=clear_monitor, width=16).pack(side="left", padx=5)

tk.Label(root, text="Bluetooth Serial Monitor", font=("Segoe UI", 11, "bold")).pack(pady=(8, 4))

serial_monitor = ScrolledText(
    root,
    width=88,
    height=19,
    font=("Consolas", 10),
    wrap="word",
    state="disabled",
)
serial_monitor.pack(padx=10, pady=(0, 8))

tk.Label(
    root,
    text=(
        "To see Arduino messages here, Arduino TX -> HC-06 RXD must be connected.\n"
        "This monitor shows data received through the HC-06 COM port, similar to Arduino Serial Monitor."
    ),
    font=("Segoe UI", 9),
    justify="center",
    wraplength=700,
).pack(pady=(2, 0))

root.bind("<KeyPress>", on_key_press)
root.bind("<KeyRelease>", on_key_release)
root.protocol("WM_DELETE_WINDOW", on_close)
root.focus_force()

worker = threading.Thread(target=serial_worker, daemon=True)
worker.start()

root.mainloop()
