# SPDX-License-Identifier: GPL-2.0-or-later
import os, sys, time, termios, select

PORT = os.environ.get("CV206_SERIAL", "/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0")
LOG = sys.argv[1]
DEADLINE = time.time() + 900

def openport():
    while True:
        try:
            fd = os.open(PORT, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
            a = termios.tcgetattr(fd)
            a[0] = 0; a[1] = 0; a[3] = 0
            a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
            a[4] = a[5] = termios.B115200
            a[6][termios.VMIN] = 0; a[6][termios.VTIME] = 0
            termios.tcsetattr(fd, termios.TCSANOW, a)
            return fd
        except OSError:
            time.sleep(0.2)   # adapter re-enumerates when the camera is power-cycled
fd = openport()

buf = b""
spam = False
last_rx = time.time()
log = open(LOG, "ab", buffering=0)
print("listening...", flush=True)
while time.time() < DEADLINE:
    try:
        r, _, _ = select.select([fd], [], [], 0.05)
    except (OSError, ValueError):
        r = []; fd = openport(); continue
    if r:
        try: d = os.read(fd, 4096)
        except BlockingIOError: d = b""
        except OSError: fd = openport(); continue
        if d:
            buf += d; log.write(d); last_rx = time.time()
            if b"Hit Ctrl" in buf:
                spam = True
    if spam:
        os.write(fd, b"\x15")
        time.sleep(0.05)
        tail = buf[-300:]
        if b"Starting kernel" in tail:
            print("missed window: kernel started", flush=True); break
        if time.time() - last_rx > 1.5 and tail.rstrip().endswith((b"#", b">")):
            print("PROMPT REACHED", flush=True); break
print("tail:", buf[-300:].decode(errors="replace"), flush=True)
os.close(fd)
