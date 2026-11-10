# SPDX-License-Identifier: GPL-2.0-or-later
"""Wait for a power-cycle, stop U-Boot, then boot OUR kernel from flash slot A (sys) by hand.
Nothing is written to flash or to the U-Boot environment."""
import os, re, sys, time, termios, select

PORT = os.environ.get("CV206_SERIAL", "/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0")
WAIT = 1500
SIZE_HEX, CRC = "0x29ee59", "015dc5c6"
LOG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bootflash.log")
log = open(LOG, "ab", buffering=0)
ARGS = "mem=35M console=ttyAMA0,115200 panic=10"

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

def read_for(secs, stop=None):
    buf = b""; end = time.time() + secs
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.05)
        if r:
            buf += os.read(fd, 65536)
            if stop and stop in buf: break
    log.write(buf); return buf

def cmd(c, secs=20):
    read_for(0.2); os.write(fd, c.encode() + b"\r")
    return read_for(secs, b"HKVS # ").decode(errors="replace")

say("waiting for a power-cycle (up to %d s) ..." % WAIT)
t0 = time.time(); got = b""; ok = False
while time.time() - t0 < WAIT:
    d = read_for(0.1); got = (got + d)[-4000:]
    if b"Hit Ctrl" in got:
        os.write(fd, b"\x15")
        if got.rstrip().endswith(b"HKVS #"): ok = True; break
if not ok:
    say("gave up: no U-Boot prompt"); sys.exit(1)
say("U-Boot prompt caught")
os.write(fd, b"\r"); read_for(0.5)
cmd("sf probe 0")
cmd("sf read 0x82000000 0x60000 0x2c0000", 40)
out = cmd("crc32 0x82000000 %s" % SIZE_HEX, 20)
m = re.search(r"==> ([0-9a-f]{8})", out)
say("flash kernel crc32 %s (expected %s)" % (m.group(1) if m else None, CRC))
if not m or m.group(1) != CRC:
    say("ABORT: kernel in flash is not the expected image"); sys.exit(2)
cmd("setenv bootargs " + ARGS)
os.write(fd, b"bootm 0x82000000\r")
t0 = time.time(); buf = b""
while time.time() - t0 < 60:
    buf += read_for(0.3)
    if b"first stage" in buf and buf.rstrip().endswith(b"#"): break
else:
    say("no shell after boot"); sys.exit(3)
say("our kernel is running from flash; shell is up (%.0f s)" % (time.time() - t0))
