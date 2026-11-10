#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Dump SPI flash of an Ezviz CS-CV206 (Hi3518EV200, HKVS U-Boot) over UART.

Needs only the Python standard library. The camera must be stopped at the
U-Boot prompt ("HKVS # ") - press Ctrl+U during boot. Close any terminal
program (picocom/minicom) on the port first.

How it works: for each 64 KB chunk it runs `sf read` into RAM, `crc32` on RAM
and `md.b`, parses the hex dump and checks it against U-Boot's CRC. Verified
chunks are saved as chunk_NNN.bin, so an interrupted run resumes where it
stopped. Read-only: nothing is ever written to the flash.

Examples:
  ./flash_dump.py --list
  ./flash_dump.py -p /dev/ttyUSB2 sys app              # chosen partitions
  ./flash_dump.py -p /dev/ttyUSB2 sys_bak app_bak
  ./flash_dump.py -p /dev/ttyUSB2 all                  # everything except cfg
  ./flash_dump.py -p /dev/ttyUSB2 --include-cfg all    # cfg holds credentials
  ./flash_dump.py --assemble                           # build flash_dump.bin
"""
import argparse
import os
import re
import select
import sys
import termios
import time
import zlib

CHUNK = 0x10000          # 64 KB = one erase block
FLASH_SIZE = 0x1000000   # 16 MB
RAM = 0x82000000         # scratch area in DRAM (outside U-Boot)
PROMPT = b"HKVS # "

# name -> (start, end); from the kernel command line mtdparts
PARTS = {
    "bld":     (0x000000, 0x040000),
    "env":     (0x040000, 0x050000),
    "enc":     (0x050000, 0x060000),
    "sys":     (0x060000, 0x320000),
    "sys_bak": (0x320000, 0x5e0000),
    "app":     (0x5e0000, 0xa20000),
    "app_bak": (0xa20000, 0xe60000),
    "cfg":     (0xe60000, 0xf60000),
    "log":     (0xf60000, 0x1000000),
}
# default order for "all": most useful first
ALL_ORDER = ["bld", "env", "enc", "sys", "app", "sys_bak", "app_bak", "log", "cfg"]


class Uart:
    def __init__(self, port):
        self.fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        a = termios.tcgetattr(self.fd)
        a[0] = 0
        a[1] = 0
        a[3] = 0
        a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        a[4] = a[5] = termios.B115200
        a[6][termios.VMIN] = 0
        a[6][termios.VTIME] = 0
        termios.tcsetattr(self.fd, termios.TCSANOW, a)

    def drain(self, t=0.3):
        end = time.time() + t
        while time.time() < end:
            r, _, _ = select.select([self.fd], [], [], 0.05)
            if r:
                os.read(self.fd, 65536)
                end = time.time() + t

    def cmd(self, c, timeout=120):
        """Send a U-Boot command, return its output once the prompt is back."""
        self.drain(0.2)
        os.write(self.fd, c.encode() + b"\r")
        buf = b""
        start = last = time.time()
        while time.time() - start < timeout:
            r, _, _ = select.select([self.fd], [], [], 0.2)
            if r:
                d = os.read(self.fd, 65536)
                if d:
                    buf += d
                    last = time.time()
            if buf.endswith(PROMPT):
                return buf.decode(errors="replace")
            if time.time() - last > 15:
                break
        raise RuntimeError("timeout on: " + c)


LINE_RE = re.compile(r"^([0-9a-f]{8}): ((?:[0-9a-f]{2} ){16})", re.M)
CRC_RE = re.compile(r"==> ([0-9a-f]{8})")


def get_chunk(u, off):
    u.cmd("sf read 0x%x 0x%x 0x%x" % (RAM, off, CHUNK))
    m = CRC_RE.search(u.cmd("crc32 0x%x 0x%x" % (RAM, CHUNK)))
    if not m:
        raise RuntimeError("no crc in crc32 output")
    want = int(m.group(1), 16)
    txt = u.cmd("md.b 0x%x 0x%x" % (RAM, CHUNK), timeout=200)
    data = bytearray()
    exp = RAM
    for mm in LINE_RE.finditer(txt):
        if int(mm.group(1), 16) != exp:
            raise RuntimeError("address gap at %08x" % exp)
        data += bytes.fromhex(mm.group(2).replace(" ", ""))
        exp += 16
    if len(data) != CHUNK:
        raise RuntimeError("short chunk: %d bytes" % len(data))
    got = zlib.crc32(bytes(data)) & 0xFFFFFFFF
    if got != want:
        raise RuntimeError("crc mismatch got %08x want %08x" % (got, want))
    return bytes(data)


def chunk_path(outdir, off):
    return "%s/chunk_%03d.bin" % (outdir, off // CHUNK)


def assemble(outdir):
    missing = [o for o in range(0, FLASH_SIZE, CHUNK)
               if not os.path.exists(chunk_path(outdir, o))]
    if missing:
        print("not all chunks present; missing %d (first: 0x%06x). "
              "Assembling with 0xff fill for gaps." % (len(missing), missing[0]))
    dst = os.path.join(outdir, "flash_dump.bin")
    with open(dst, "wb") as f:
        for o in range(0, FLASH_SIZE, CHUNK):
            p = chunk_path(outdir, o)
            f.write(open(p, "rb").read() if os.path.exists(p) else b"\xff" * CHUNK)
    print("wrote", dst)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("partitions", nargs="*",
                    help="partition names (see --list) or 'all'")
    ap.add_argument("-p", "--port", default="/dev/ttyUSB0")
    ap.add_argument("-o", "--outdir", default=os.path.join(os.path.dirname(
        os.path.abspath(__file__)), "dump"))
    ap.add_argument("--include-cfg", action="store_true",
                    help="with 'all', also dump cfg (credentials!)")
    ap.add_argument("--retries", type=int, default=4)
    ap.add_argument("--list", action="store_true", help="show partitions and exit")
    ap.add_argument("--assemble", action="store_true",
                    help="join existing chunks into flash_dump.bin and exit")
    args = ap.parse_args()

    if args.list:
        for n, (a, b) in PARTS.items():
            print("%-8s 0x%06x-0x%06x  %5d KB  %3d chunks" %
                  (n, a, b, (b - a) // 1024, (b - a) // CHUNK))
        return
    os.makedirs(args.outdir, exist_ok=True)
    if args.assemble:
        assemble(args.outdir)
        return

    names = []
    for n in args.partitions:
        if n == "all":
            names += [x for x in ALL_ORDER if x != "cfg" or args.include_cfg]
        elif n in PARTS:
            names.append(n)
        else:
            sys.exit("unknown partition %r (see --list)" % n)
    if not names:
        sys.exit("no partitions given (see --help)")
    if "cfg" in names and not args.include_cfg and "all" not in args.partitions:
        print("note: cfg contains Wi-Fi/cloud credentials; keep the dump private")

    offsets = []
    for n in names:
        a, b = PARTS[n]
        offsets += [o for o in range(a, b, CHUNK) if o not in offsets]

    logf = open(os.path.join(args.outdir, "progress.log"), "a")

    def log(m):
        line = "%s %s" % (time.strftime("%H:%M:%S"), m)
        print(line, flush=True)
        logf.write(line + "\n")
        logf.flush()

    u = Uart(args.port)
    os.write(u.fd, b"\r")
    time.sleep(0.5)
    try:
        u.cmd("")
    except RuntimeError:
        sys.exit("no U-Boot prompt ('HKVS # ') on %s - interrupt boot with Ctrl+U "
                 "and close other terminal programs" % args.port)
    todo = [o for o in offsets if not os.path.exists(chunk_path(args.outdir, o))]
    log("synced; %d chunks to dump (%d already present)" %
        (len(todo), len(offsets) - len(todo)))

    for i, off in enumerate(todo, 1):
        for attempt in range(args.retries):
            try:
                data = get_chunk(u, off)
                with open(chunk_path(args.outdir, off), "wb") as f:
                    f.write(data)
                log("ok 0x%06x (%d/%d)" % (off, i, len(todo)))
                break
            except Exception as e:
                log("retry 0x%06x attempt %d: %s" % (off, attempt + 1, e))
                time.sleep(1)
                os.write(u.fd, b"\r")
                u.drain(1.0)
        else:
            log("FAILED at 0x%06x, aborting" % off)
            sys.exit(1)
    log("DONE")
    if all(os.path.exists(chunk_path(args.outdir, o))
           for o in range(0, FLASH_SIZE, CHUNK)):
        assemble(args.outdir)


if __name__ == "__main__":
    main()
