# SPDX-License-Identifier: GPL-2.0-or-later
"""Upload a kernel image over the U-Boot serial link (loady/ymodem), verify, then boot it.
usage: ramboot3.py IMAGE [--gpio NAME ...] [--extra BOOTARGS] [--capture SECONDS]
  --gpio wifi_pwr   GPIO 15 high  (group 1 bit 7, 0x20150000)  'sdio_card_power_en'
  --gpio wifi_rst   GPIO 38 high  (group 4 bit 6, 0x20180000)
Nothing is flashed or saved."""
import os, re, sys, time, termios, select, zlib, subprocess

PORT = os.environ.get("CV206_SERIAL", "/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0")
ADDR = 0x82000000
PROMPT = b"HKVS # "
IMG = sys.argv[1]
gp = [sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == "--gpio"]
extra = sys.argv[sys.argv.index("--extra") + 1] if "--extra" in sys.argv else ""
cap = int(sys.argv[sys.argv.index("--capture") + 1]) if "--capture" in sys.argv else 60
BOOTARGS = ("mem=64M console=ttyAMA0,115200 panic=10 rdinit=/bin/sh " + extra).strip()
GPIOS = {"wifi_pwr": (0x20150000, 0x80), "wifi_rst": (0x20180000, 0x40)}
LOG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ramboot3_session.log")
data = open(IMG, "rb").read(); size = len(data); crc = zlib.crc32(data) & 0xffffffff
log = open(LOG, "ab", buffering=0)

def say(m):
    line = "%s %s\n" % (time.strftime("%H:%M:%S"), m)
    log.write(line.encode()); print(line, end="", flush=True)

def setraw(fd, nb):
    a = termios.tcgetattr(fd)
    a[0] = 0; a[1] = 0; a[3] = 0
    a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    a[4] = a[5] = termios.B115200
    a[6][termios.VMIN] = 0 if nb else 1; a[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, a)

def opennb():
    fd = os.open(PORT, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK); setraw(fd, True); return fd

def read_until(fd, pred, timeout):
    buf = b""; start = time.time()
    while time.time() - start < timeout:
        r, _, _ = select.select([fd], [], [], 0.1)
        if r:
            d = os.read(fd, 65536)
            if d: buf += d; log.write(d)
        if pred(buf): break
    return buf

def cmd(fd, c, timeout=30):
    end = time.time() + 0.2
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.05)
        if r: log.write(os.read(fd, 65536)); end = time.time() + 0.2
    os.write(fd, c.encode() + b"\r")
    return read_until(fd, lambda b: b.endswith(PROMPT), timeout).decode(errors="replace")

say("image %s: %d bytes crc32 %08x" % (os.path.basename(IMG), size, crc))
fd = opennb(); os.write(fd, b"\r")
if not read_until(fd, lambda b: b.endswith(PROMPT), 4).endswith(PROMPT):
    say("ABORT: no U-Boot prompt"); sys.exit(1)
os.write(fd, ("loady 0x%x\r" % ADDR).encode())
b = read_until(fd, lambda b: b"ymodem" in b.lower() and b"download" in b.lower(), 6)
if b"ymodem" not in b.lower():
    say("ABORT: loady did not start"); sys.exit(2)
os.close(fd)
bfd = os.open(PORT, os.O_RDWR | os.O_NOCTTY); setraw(bfd, False)
t0 = time.time(); say("sz --ymodem ...")
with open(LOG + ".sz", "ab") as sl:
    p = subprocess.run(["sz", "--ymodem", IMG], stdin=bfd, stdout=bfd, stderr=sl)
os.close(bfd)
say("sz exit %d after %.0f s" % (p.returncode, time.time() - t0))
fd = opennb()
b = read_until(fd, lambda b: b.endswith(PROMPT), 15)
m = re.search(rb"Total Size\s*=\s*(0x[0-9a-fA-F]+)\s*=\s*(\d+)", b)
if p.returncode != 0 or not m or int(m.group(2)) != size:
    say("ABORT: upload not confirmed"); sys.exit(3)
out = cmd(fd, "crc32 0x%x 0x%x" % (ADDR, size), 30)
mm = re.search(r"==> ([0-9a-f]{8})", out)
say("RAM crc32 %s (file %08x)" % (mm.group(1) if mm else None, crc))
if not mm or int(mm.group(1), 16) != crc:
    say("ABORT: CRC mismatch"); sys.exit(4)
cmd(fd, "setenv bootargs " + BOOTARGS)
for g in gp:
    base, bit = GPIOS[g]
    cmd(fd, "mw.l 0x%x 0x%x" % (base + 0x400, bit)); cmd(fd, "mw.l 0x%x 0x%x" % (base + (bit << 2), bit))
    out = cmd(fd, "md.l 0x%x 1" % (base + 0x3fc)); say("%s: data reg %r" % (g, out[-36:]))
say("bootargs: %s" % BOOTARGS); say("bootm")
os.write(fd, ("bootm 0x%x\r" % ADDR).encode())
end = time.time() + cap
while time.time() < end:
    r, _, _ = select.select([fd], [], [], 0.2)
    if r:
        d = os.read(fd, 65536)
        if d: log.write(d)
say("capture finished"); os.close(fd)
