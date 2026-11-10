# SPDX-License-Identifier: GPL-2.0-or-later
"""Boot the OpenIPC test kernel from the SD card (FAT p1, cv206/<name>) via U-Boot.
usage: cardboot.py <name_on_card> <crc32_hex_of_file> <size_dec> [mw=ADDR:VAL ...] [--capture SECONDS]
GPIO 38 (Wi-Fi power) is always driven high before bootm. Nothing is flashed or saved."""
import os, re, sys, time, termios, select

PORT = os.environ.get("CV206_SERIAL", "/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0")
PROMPT = b"HKVS # "
name, crc_hex, size = sys.argv[1], sys.argv[2].lower(), int(sys.argv[3])
mws = [a[3:] for a in sys.argv[4:] if a.startswith("mw=")]
cap = 120
if "--capture" in sys.argv:
    cap = int(sys.argv[sys.argv.index("--capture") + 1])
BOOTARGS = "mem=64M console=ttyAMA0,115200 panic=10 rdinit=/bin/sh"
if "--extra" in sys.argv:
    BOOTARGS += " " + sys.argv[sys.argv.index("--extra") + 1]
LOG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cardboot_session.log")
log = open(LOG, "ab", buffering=0)

def say(m):
    line = "%s %s\n" % (time.strftime("%H:%M:%S"), m)
    log.write(line.encode()); print(line, end="", flush=True)

fd = os.open(PORT, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
a = termios.tcgetattr(fd)
a[0] = 0; a[1] = 0; a[3] = 0
a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
a[4] = a[5] = termios.B115200
a[6][termios.VMIN] = 0; a[6][termios.VTIME] = 0
termios.tcsetattr(fd, termios.TCSANOW, a)

def drain(t=0.3):
    end = time.time() + t
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.05)
        if r:
            log.write(os.read(fd, 65536)); end = time.time() + t

def read_until(pred, timeout):
    buf = b""; start = time.time()
    while time.time() - start < timeout:
        r, _, _ = select.select([fd], [], [], 0.1)
        if r:
            d = os.read(fd, 65536)
            if d: buf += d; log.write(d)
        if pred(buf): break
    return buf

def cmd(c, timeout=30):
    drain(0.2)
    os.write(fd, c.encode() + b"\r")
    return read_until(lambda b: b.endswith(PROMPT), timeout).decode(errors="replace")

os.write(fd, b"\r")
if not read_until(lambda b: b.endswith(PROMPT), 4).endswith(PROMPT):
    say("ABORT: no U-Boot prompt"); sys.exit(1)
say("=== card boot of cv206/%s; mw trials: %s; bootargs: %s ===" % (name, mws or "none", BOOTARGS))
out = cmd("fatload mmc 0:1 0x82000000 cv206/%s" % name)
if ("%d bytes read" % size) not in out:
    say("ABORT: fatload: %r" % out[-150:]); sys.exit(2)
out = cmd("crc32 0x82000000 0x%x" % size)
m = re.search(r"==> ([0-9a-f]{8})", out)
say("crc32 in RAM %s (expected %s)" % (m.group(1) if m else None, crc_hex))
if not m or m.group(1) != crc_hex:
    say("ABORT: crc mismatch"); sys.exit(3)
cmd("setenv bootargs " + BOOTARGS)
# Wi-Fi power: GPIO 38 = group 4 (0x20180000) bit 6
cmd("mw.l 0x20180400 0x40"); cmd("mw.l 0x20180100 0x40")
out = cmd("md.l 0x201803fc 1"); say("GPIO group4 data: %r" % out[-40:])
for t in mws:
    addr, val = t.split(":")
    cmd("mw.l %s %s" % (addr, val)); out = cmd("md.l %s 1" % addr); say("mw %s=%s -> %r" % (addr, val, out[-34:]))
say("bootm 0x82000000")
drain(0.2)
os.write(fd, b"bootm 0x82000000\r")
end = time.time() + cap
while time.time() < end:
    r, _, _ = select.select([fd], [], [], 0.2)
    if r:
        d = os.read(fd, 65536)
        if d: log.write(d)
say("capture finished (%d s)" % cap)
os.close(fd)
