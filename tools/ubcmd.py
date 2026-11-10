# SPDX-License-Identifier: GPL-2.0-or-later
"""Send U-Boot commands one at a time, waiting for the prompt after each (slow typing: the console drops/garbles fast input).
usage: ubcmd.py "cmd1" "cmd2" ...   Prints each command's output."""
import os, sys, time, termios, select
PORT = os.environ.get("CV206_SERIAL", "/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0")
P = b"HKVS # "
fd = os.open(PORT, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
a = termios.tcgetattr(fd); a[0]=0; a[1]=0; a[3]=0
a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL; a[4] = a[5] = termios.B115200
a[6][termios.VMIN]=0; a[6][termios.VTIME]=0; termios.tcsetattr(fd, termios.TCSANOW, a)
def rd(pred, t):
    b=b""; s=time.time()
    while time.time()-s<t:
        if select.select([fd],[],[],0.1)[0]:
            try: b+=os.read(fd,65536)
            except BlockingIOError: pass
        if pred(b): break
    return b
os.write(fd, b"\r"); rd(lambda b: b.endswith(P), 3)
for c in sys.argv[1:]:
    rd(lambda b: False, 0.3)
    for ch in c.encode():            # type slowly
        os.write(fd, bytes([ch])); time.sleep(0.004)
    os.write(fd, b"\r")
    out = rd(lambda b: b.endswith(P), 120).decode(errors="replace")
    print(out.replace("\r", "").strip(), flush=True)
