# SPDX-License-Identifier: GPL-2.0-or-later
"""One Wi-Fi bring-up trial on the camera (RAM image kept across a warm reset).
usage: wifitrial.py NAME PARTS...
PARTS (combine): mux_sdio1  gpio15  pad  other_mux  gpios_other
Reboots the camera (reboot -f), boots the kernel still in RAM at 0x82000000,
applies the chosen register changes from the shell, rescans mmc1 and reports.
Nothing is flashed."""
import os, re, sys, time, termios, select

PORT = os.environ.get("CV206_SERIAL", "/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0")
SIZE_HEX, CRC = "0x2c79e4", "f3c22e89"
NAME = sys.argv[1]; PARTS = sys.argv[2:]
LOG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "wifitrial.log")
log = open(LOG, "ab", buffering=0)
BOOTARGS = 'mem=64M console=ttyAMA0,115200 panic=10 rdinit=/bin/sh dyndbg="module mmc_core +p"'

FRAG = {
 "mux_sdio1": "for r in 10 1c 20 24 28 34; do devmem 0x200f00$r 32 4; done",
 "gpio15": "devmem 0x200f0098 32 0; devmem 0x20150400 32 0x80; devmem $((0x20150000+(0x80<<2))) 32 0x80",
 "mux18": "devmem 0x200f0018 32 0",
 "mux40_58": "for r in 40 44 48 50 54 58; do devmem 0x200f00$r 32 1; done",
 "gpio18": "devmem 0x20160400 32 0x04; devmem $((0x20160000+(4<<2))) 32 4",
 "pad": "i=0; for v in 0x40 0x90 0 0 0xd0 0xa0 0xa0 0xa0 0xa0 0xa0 0xa0 0xb0 0xa0 0xd0 0x90 0xa0; do devmem $((0x200f0800+i*4)) 32 $v; i=$((i+1)); done",
 "other_mux": "devmem 0x200f0018 32 0; for r in 40 44 48 50 54 58; do devmem 0x200f00$r 32 1; done",
 "gpios_other": "w() { devmem $(($1+0x400)) 32 $2; devmem $(($1+($2<<2))) 32 $3; }; w 0x20140000 0x08 0x08; w 0x20160000 0x04 0x04; w 0x20170000 0x40 0; w 0x20180000 0x04 0",
}

def say(m):
    line = "%s [%s] %s\n" % (time.strftime("%H:%M:%S"), NAME, m)
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
        r, _, _ = select.select([fd], [], [], 0.1)
        if r:
            buf += os.read(fd, 65536)
            if stop and stop in buf: break
    log.write(buf); return buf

def shell(c, secs=3.0, stop=b"~ # "):
    read_for(0.2)
    os.write(fd, c.encode() + b"\r")
    return read_for(secs, stop).decode(errors="replace")

# ---- 1. get to the U-Boot prompt
os.write(fd, b"\r"); r = read_for(1.0)
if b"HKVS #" not in r:
    if b"#" in r:
        say("rebooting from Linux shell (reboot -f)")
        os.write(fd, b"reboot -f\r")
    else:
        say("no prompt; assuming camera is booting/powering up")
    t0 = time.time(); got = b""; ok = False
    while time.time() - t0 < 60:
        d = read_for(0.2)
        got += d
        if b"Hit Ctrl" in got: os.write(fd, b"\x15")
        if b"Hit Ctrl" in got and got.rstrip().endswith(b"HKVS #"): ok = True; break
    if not ok:
        say("ABORT: never reached U-Boot prompt"); sys.exit(1)
os.write(fd, b"\r"); read_for(0.5)
say("at U-Boot prompt")

# ---- 2. image still in RAM?
read_for(0.3); os.write(fd, ("crc32 0x82000000 %s\r" % SIZE_HEX).encode())
out = read_for(8.0, b"HKVS #").decode(errors="replace")
m = re.search(r"==> ([0-9a-f]{8})", out)
if not m or m.group(1) != CRC:
    say("ABORT: RAM image not intact (crc %s); needs re-upload" % (m.group(1) if m else None)); sys.exit(2)
say("RAM image intact")
read_for(0.3); os.write(fd, ("setenv bootargs %s\r" % BOOTARGS).encode()); read_for(1.0, b"HKVS #")
os.write(fd, b"bootm 0x82000000\r")
# ---- 3. wait for the shell
t0 = time.time(); got = b""
while time.time() - t0 < 60:
    got += read_for(0.5)
    if b"Freeing unused kernel memory" in got and got.rstrip().endswith(b"#"): break
else:
    say("ABORT: no shell after boot"); sys.exit(3)
say("Linux shell up")
time.sleep(1.0); os.write(fd, b"\r"); read_for(0.5)
shell("mount -t proc proc /proc; mount -t sysfs sysfs /sys; mount -t devtmpfs devtmpfs /dev", 2.0)

# ---- 4. apply the variant and rescan
body = "\n".join(FRAG[p] for p in PARTS)
script = "cat > /tmp/t.sh <<'EOF'\n%s\ndmesg -c >/dev/null\necho 1 > /sys/class/mmc_host/mmc1/rescan\nsleep 12\necho TRIAL_DONE\nEOF" % body
shell(script, 2.0)
shell("sh /tmp/t.sh > /tmp/t.out 2>&1 &", 1.0)
time.sleep(16)
out = shell("echo R_NEW=$(dmesg | grep -c 'mmc1: new'); echo R_TO=$(dmesg | grep -c 'mmc1: req done.*-110'); echo R_ENODEV=$(dmesg | grep -c 'mmc1: req done.*-19'); echo R_FW=$(dmesg | grep -c 'WLAN FW is active'); echo R_DONE=$(grep -c TRIAL_DONE /tmp/t.out)", 3.0)
vals = dict(re.findall(r"R_(\w+)=(\d+)", out))
verdict = "CHIP ANSWERS, firmware active" if vals.get("FW", "0") != "0" else ("card found" if vals.get("NEW", "0") != "0" else "no answer")
say("parts=%s -> new_card=%s timeouts=%s enodev=%s fw_active=%s done=%s => %s" % (
    "+".join(PARTS) or "(none)", vals.get("NEW"), vals.get("TO"), vals.get("ENODEV"), vals.get("FW"), vals.get("DONE"), verdict))
os.close(fd)
