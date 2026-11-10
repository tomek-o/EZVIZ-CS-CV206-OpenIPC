#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Fast file transfer from the host to the RUNNING Linux shell of the camera over UART.

The camera's console tty is switched to a higher speed (default 921600), the file is
streamed raw into RAM (`head -c`), its SHA-256 is checked there, and optionally it is
copied to the SD card. Nothing is written to flash. Standard library only.

Measured on this camera: about 90 KB/s at 921600 (XMODEM via busybox `rx` manages
only about 17 KB/s because it reads the port byte by byte).

usage: rawput.py [-p PORT] [--rate 921600] FILE [--to-card NAME]
  FILE            file to send (lands in /tmp/rawput.bin on the camera)
  --to-card NAME  then copy it to /mnt/sd/cv206/NAME (card must be mounted at /mnt/sd)
The camera must be at its shell prompt ('~ #'), console at 115200.
"""
import argparse, hashlib, os, select, sys, termios, time

SPEEDS = {115200: termios.B115200, 230400: termios.B230400, 460800: termios.B460800,
          576000: termios.B576000, 921600: termios.B921600, 1000000: termios.B1000000}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file")
    ap.add_argument("-p", "--port", default="/dev/ttyUSB0")
    ap.add_argument("--rate", type=int, default=921600, choices=sorted(SPEEDS))
    ap.add_argument("--to-card", metavar="NAME")
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--tty", default="/dev/ttyAMA0", help="camera-side console tty")
    args = ap.parse_args()

    data = open(args.file, "rb").read()
    n = len(data)
    sha = hashlib.sha256(data).hexdigest()
    log = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "rawput.log"), "ab", buffering=0)

    def say(m):
        line = "%s %s\n" % (time.strftime("%H:%M:%S"), m)
        log.write(line.encode()); print(line, end="", flush=True)

    fd = os.open(args.port, os.O_RDWR | os.O_NOCTTY)   # blocking writes; reads via select

    def setspeed(sp):
        a = termios.tcgetattr(fd)
        a[0] = 0; a[1] = 0; a[3] = 0
        a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        a[4] = a[5] = sp
        a[6][termios.VMIN] = 0; a[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, a)

    def read_for(secs, stop=None):
        buf = b""; end = time.time() + secs
        while time.time() < end:
            r, _, _ = select.select([fd], [], [], 0.1)
            if r:
                buf += os.read(fd, 65536)
                if stop and stop in buf: break
        log.write(buf)
        return buf

    def run(c, secs=3.0, stop=b"# "):
        read_for(0.2)
        os.write(fd, c.encode() + b"\r")
        return read_for(secs, stop).decode(errors="replace")

    def restore():
        # try to get the camera back to 115200, whatever state we are in
        for sp in (args.rate, 115200):
            setspeed(SPEEDS[sp]); os.write(fd, b"\r"); r = read_for(1.0)
            if b"#" in r:
                if sp != 115200:
                    os.write(fd, ("stty -F %s 115200\r" % args.tty).encode()); time.sleep(0.4)
                    setspeed(SPEEDS[115200]); os.write(fd, b"\r"); read_for(1.0)
                return True
        return False

    say("file %s: %d bytes, sha256 %s" % (args.file, n, sha[:16]))
    setspeed(SPEEDS[115200])
    os.write(fd, b"\r")
    if b"#" not in read_for(1.5):
        say("ABORT: no shell prompt at 115200"); sys.exit(1)
    os.write(fd, ("stty -F %s %d; echo SPEEDSET\r" % (args.tty, args.rate)).encode())
    time.sleep(0.5)
    setspeed(SPEEDS[args.rate])
    if b"#" not in (read_for(1.0) + (os.write(fd, b"\r") and b"" or b"") + read_for(1.0)):
        say("no answer at %d; recovering" % args.rate)
        say("recovered: %s" % restore()); sys.exit(2)
    say("camera console now at %d" % args.rate)

    ok = False
    for attempt in range(1, args.retries + 1):
        read_for(0.3)
        os.write(fd, ("rm -f /tmp/rawput.bin; stty -F %s raw -echo; head -c %d > /tmp/rawput.bin; "
                      "stty -F %s cooked echo; echo RAWDONE\r" % (args.tty, n, args.tty)).encode())
        time.sleep(1.0)
        t0 = time.time()
        for i in range(0, n, 4096):
            os.write(fd, data[i:i + 4096])
        termios.tcdrain(fd)
        dt = time.time() - t0
        got = read_for(8.0, b"RAWDONE")
        if b"RAWDONE" not in got:
            say("attempt %d: no RAWDONE (bytes lost?); padding" % attempt)
            os.write(fd, b"\0" * 70000); read_for(6.0, b"RAWDONE")
        out = run("sha256sum /tmp/rawput.bin", 6.0, b"rawput.bin")
        good = sha in out
        say("attempt %d: %d bytes in %.1f s (%.1f KB/s) sha256 %s" % (attempt, n, dt, n / 1024 / dt, "MATCH" if good else "MISMATCH"))
        if good:
            ok = True; break
    if ok and args.to_card:
        dst = "/mnt/sd/cv206/" + args.to_card
        run("mkdir -p /mnt/sd/cv206; cp /tmp/rawput.bin %s; sync" % dst, 30.0, b"# ")
        out = run("sha256sum %s" % dst, 8.0, b"cv206")
        card_ok = sha in out
        say("copied to card %s: sha256 %s" % (dst, "MATCH" if card_ok else "MISMATCH"))
        ok = ok and card_ok
    run("rm -f /tmp/rawput.bin", 1.0)
    say("restoring console to 115200: %s" % restore())
    os.close(fd)
    say("OK" if ok else "FAILED")
    sys.exit(0 if ok else 3)


if __name__ == "__main__":
    main()
