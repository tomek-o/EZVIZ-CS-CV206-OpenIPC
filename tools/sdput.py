# SPDX-License-Identifier: GPL-2.0-or-later
"""Copy one file onto the camera's SD card (FAT boot partition) via the running
Linux shell: busybox `rx` (XMODEM) on the camera, lrzsz `sx` on the host.
usage: sdput.py <host_file> <name_on_card>   (stored in /mnt/sd/cv206/)"""
import os, sys, time, termios, select, subprocess, hashlib

PORT = os.environ.get("CV206_SERIAL", "/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0")
src, name = sys.argv[1], sys.argv[2]
data = open(src, "rb").read()
size = len(data)
sha = hashlib.sha256(data).hexdigest()
LOG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sdput_session.log")
log = open(LOG, "ab", buffering=0)

def say(m):
    line = "%s %s\n" % (time.strftime("%H:%M:%S"), m)
    log.write(line.encode()); print(line, end="", flush=True)

def setraw(fd, nonblock):
    a = termios.tcgetattr(fd)
    a[0] = 0; a[1] = 0; a[3] = 0
    a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    a[4] = a[5] = termios.B115200
    a[6][termios.VMIN] = 0 if nonblock else 1
    a[6][termios.VTIME] = 0
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

SHELL = b"~ # "
def cmd(fd, c, timeout=30):
    # flush
    end = time.time() + 0.2
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.05)
        if r: os.read(fd, 65536); end = time.time() + 0.2
    os.write(fd, c.encode() + b"\r")
    return read_until(fd, lambda b: b.rstrip().endswith(b"#") and b.count(b"\n") >= 1, timeout).decode(errors="replace")

say("file %s: %d bytes, sha256 %s" % (src, size, sha))
fd = opennb()
os.write(fd, b"\r")
b = read_until(fd, lambda b: b.rstrip().endswith(b"#"), 4)
if not b.rstrip().endswith(b"#"):
    say("ABORT: no shell prompt"); sys.exit(1)
say("shell prompt OK")
for c in ("mount -t proc proc /proc 2>/dev/null; mount -t devtmpfs devtmpfs /dev 2>/dev/null; mkdir -p /mnt/sd; mountpoint -q /mnt/sd || mount -t vfat /dev/mmcblk0p1 /mnt/sd; mount -o remount,rw /mnt/sd", "mkdir -p /mnt/sd/cv206", "rm -f /mnt/sd/cv206/%s" % name,
          "df -k /mnt/sd | tail -1"):
    out = cmd(fd, c); say("%s -> %r" % (c, out[-120:]))

dst = "/mnt/sd/cv206/%s" % name
os.write(fd, ("rx %s\r" % dst).encode())
time.sleep(1.5)
os.close(fd)

bfd = os.open(PORT, os.O_RDWR | os.O_NOCTTY); setraw(bfd, False)
t0 = time.time()
say("starting sx --xmodem ...")
with open(LOG + ".sx", "ab") as sl:
    p = subprocess.run(["sx", "--xmodem", src], stdin=bfd, stdout=bfd, stderr=sl)
dt = time.time() - t0
os.close(bfd)
say("sx exit code %d after %.0f s (%.1f KB/s)" % (p.returncode, dt, size / 1024 / dt))

fd = opennb()
time.sleep(1)
os.write(fd, b"\r")
read_until(fd, lambda b: b.rstrip().endswith(b"#"), 5)
# trim XMODEM padding to the exact size, then checksum
cmd(fd, "cd /mnt/sd/cv206; ls -l %s" % name)
out = cmd(fd, "head -c %d %s > %s.trim && mv %s.trim %s && ls -l %s && sha256sum %s" % (size, name, name, name, name, name, name), 60)
say("on card: %r" % out[-300:])
cmd(fd, "sync; cd /")
ok = sha in out
say("sha256 match: %s" % ok)
if not ok:
    sys.exit(2)
say("OK")
os.close(fd)
