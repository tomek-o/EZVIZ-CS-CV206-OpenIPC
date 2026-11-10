# SPDX-License-Identifier: GPL-2.0-or-later
import os, sys, time, termios, select

PORT = os.environ.get("CV206_SERIAL", "/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0")
fd = os.open(PORT, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
a = termios.tcgetattr(fd)
a[0] = 0; a[1] = 0; a[3] = 0
a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
a[4] = a[5] = termios.B115200
a[6][termios.VMIN] = 0; a[6][termios.VTIME] = 0
termios.tcsetattr(fd, termios.TCSANOW, a)
log = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uart_session.log"), "ab", buffering=0)

def rd(idle=1.0, maxt=20):
    out = b""; last = time.time(); start = last
    while time.time() - start < maxt:
        r, _, _ = select.select([fd], [], [], 0.1)
        if r:
            try: d = os.read(fd, 4096)
            except BlockingIOError: d = b""
            if d:
                out += d; last = time.time(); log.write(d)
        elif time.time() - last > idle:
            break
    return out.decode(errors="replace")

rd(0.3, 2)
for c in sys.argv[1:]:
    os.write(fd, c.encode() + b"\r")
    print(rd(), end="", flush=True)
os.close(fd)
