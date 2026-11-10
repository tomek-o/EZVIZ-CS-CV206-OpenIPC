# SPDX-License-Identifier: GPL-2.0-or-later
"""From the U-Boot prompt: boot OUR kernel from flash slot A (sys) by hand. Writes nothing and changes no environment.
usage: flashboot.py LOCALKERNEL "BOOTARGS" "WAITSTRING"   (LOCALKERNEL is only used to verify the CRC of what is in flash)"""
import os, re, sys, time, termios, select, zlib
PORT = os.environ.get("CV206_SERIAL", "/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0")
P = b"HKVS # "
local, bargs, wait = sys.argv[1], sys.argv[2], sys.argv[3].encode()
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
cmd("sf probe 0")
cmd("sf read 0x82000000 0x60000 0x2c0000", 60)
out = cmd("crc32 0x82000000 0x%x" % len(data), 20)
m = re.search(r"==> ([0-9a-f]{8})", out)
print("flash kernel crc", m and m.group(1), "want %08x" % crc, flush=True)
if not m or int(m.group(1),16) != crc: sys.exit(2)
cmd("setenv bootargs " + bargs)
os.write(fd, b"bootm 0x82000000\r")
b = rd(lambda b: wait in b and b.rstrip().endswith(b"#") and b"Starting kernel" in b, 120)
open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs/flashboot_boot.log"),"wb").write(b)
print("booted" if wait in b else "NO SHELL", flush=True)
