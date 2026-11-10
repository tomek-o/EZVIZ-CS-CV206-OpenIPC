# SPDX-License-Identifier: GPL-2.0-or-later
"""From the U-Boot prompt: load cv206/NAME from the microSD (FAT p1), verify CRC against the local copy, boot it.
usage: sdkernel.py LOCALFILE NAME "BOOTARGS" "WAITSTRING"   Nothing is written to flash."""
import os, re, sys, time, termios, select, zlib
PORT = os.environ.get("CV206_SERIAL", "/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0")
P = b"HKVS # "
local, name, bargs, wait = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4].encode()
data = open(local, "rb").read(); crc = zlib.crc32(data) & 0xffffffff
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
def cmd(c, t=30):
    rd(lambda b: False, 0.2); os.write(fd, c.encode()+b"\r")
    return rd(lambda b: b.endswith(P), t).decode(errors="replace")
os.write(fd, b"\r"); rd(lambda b: b.endswith(P), 3)
out = cmd("fatload mmc 0:1 0x82000000 cv206/%s" % name, 60)
if ("%d bytes read" % len(data)) not in out: print("ABORT fatload:", out[-200:]); sys.exit(2)
out = cmd("crc32 0x82000000 0x%x" % len(data), 20)
m = re.search(r"==> ([0-9a-f]{8})", out)
print("crc in RAM", m and m.group(1), "want %08x" % crc, flush=True)
if not m or int(m.group(1),16) != crc: sys.exit(3)
cmd("setenv bootargs " + bargs)
os.write(fd, b"bootm 0x82000000\r")
b = rd(lambda b: wait in b and b.rstrip().endswith(b"#") and b"Starting kernel" in b, 90)
open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ramkernel_boot.log"),"wb").write(b)
print("booted" if wait in b else "NO SHELL", flush=True)
