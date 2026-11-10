#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Send small files to /tmp on the RUNNING Linux shell of the camera (XMODEM, checksummed).

BusyBox `rx` on the camera + lrzsz `sx` on the host, at the console's current speed
(115200, about 9.7 KB/s). Trims the XMODEM padding and compares SHA-256.
Nothing is written to flash or to the SD card.

usage: xput.py [-p PORT] FILE [FILE ...]      (files land in /tmp/<basename>, mode 755)
"""
import argparse, hashlib, os, select, subprocess, sys, termios, time


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("-p", "--port", default="/dev/ttyUSB0")
    args = ap.parse_args()
    log = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "xput.log"), "ab", buffering=0)

    def say(m):
        line = "%s %s\n" % (time.strftime("%H:%M:%S"), m)
        log.write(line.encode()); print(line, end="", flush=True)

    def setraw(fd, nonblock):
        a = termios.tcgetattr(fd)
        a[0] = 0; a[1] = 0; a[3] = 0
        a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        a[4] = a[5] = termios.B115200
        a[6][termios.VMIN] = 0 if nonblock else 1; a[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, a)

    def opennb():
        fd = os.open(args.port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK); setraw(fd, True); return fd

    def read_for(fd, secs, stop=None):
        buf = b""; end = time.time() + secs
        while time.time() < end:
            r, _, _ = select.select([fd], [], [], 0.1)
            if r:
                buf += os.read(fd, 65536)
                if stop and stop in buf: break
        log.write(buf); return buf

    ok_all = True
    for path in args.files:
        name = os.path.basename(path)
        data = open(path, "rb").read(); size = len(data); sha = hashlib.sha256(data).hexdigest()
        fd = opennb(); os.write(fd, b"\r")
        if b"#" not in read_for(fd, 1.5):
            say("ABORT: no shell prompt"); sys.exit(1)
        os.write(fd, ("rm -f /tmp/%s; rx /tmp/%s\r" % (name, name)).encode())
        time.sleep(1.5); os.close(fd)
        bfd = os.open(args.port, os.O_RDWR | os.O_NOCTTY); setraw(bfd, False)
        t0 = time.time()
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "xput.log.sx"), "ab") as sl:
            p = subprocess.run(["sx", "--xmodem", path], stdin=bfd, stdout=bfd, stderr=sl)
        os.close(bfd)
        fd = opennb(); time.sleep(1.0); os.write(fd, b"\r"); read_for(fd, 1.0)
        os.write(fd, ("cd /tmp; head -c %d %s > %s.t && mv %s.t %s && chmod 755 %s && sha256sum %s\r"
                      % (size, name, name, name, name, name, name)).encode())
        out = read_for(fd, 5.0, name.encode() + b"\r\n~").decode(errors="replace")
        good = p.returncode == 0 and sha in out
        say("%s: %d bytes in %.0f s, sx exit %d, sha256 %s" % (name, size, time.time() - t0, p.returncode, "MATCH" if good else "MISMATCH"))
        ok_all = ok_all and good
        os.write(fd, b"cd /\r"); read_for(fd, 0.5); os.close(fd)
    sys.exit(0 if ok_all else 2)


if __name__ == "__main__":
    main()
