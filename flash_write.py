#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Write ONE flash partition (or, with --both, a slot and its slot B twin) of an Ezviz CS-CV206 over UART, from the U-Boot prompt.

Standard library only, plus `sz` (lrzsz) on the host. The camera must be stopped
at the U-Boot prompt ("HKVS # "): press Ctrl+U during boot; close other terminals.

Safety rails (by design):
  * only these partitions can be written: sys, sys_bak, app, app_bak
    (never bld, env, enc, cfg, log)
  * a verified backup must exist: dump/flash_dump.bin with a matching
    dump/flash_dump.bin.sha256
  * before erasing, the CURRENT flash content of the partition is read back and
    must be the backup, an image written earlier by this tool, the backup of the sibling slot, or
    (relaxed check) an intact image of the right kind (uImage with good CRCs, squashfs 4.x that fits),
    for example after an update from the web page; anything else stops the write.
    This check is skipped for --restore, which exists to undo a custom write
  * the image is CRC32-checked in RAM against the host file before anything is erased
  * after writing, the partition is read back and its CRC32 compared
  * nothing is ever saved to the U-Boot environment (no saveenv)
  * one attempt only: on any mismatch it stops and tells you; it does not guess

Usage:
  flash_write.py -p /dev/ttyUSB0 --partition sys sys.bin --both --yes
      writes sys.bin to slot A (sys), then the same file to slot B (sys_bak), each one checked and read back
  flash_write.py -p /dev/ttyUSB0 --partition app app.sqsh --dry-run
      every check and the upload to RAM, nothing erased or written
  flash_write.py -p /dev/ttyUSB0 --partition sys --restore --yes
      writes the partition's own backup content back (restore test)
  flash_write.py -p /dev/ttyUSB0 --partition app new_rootfs.squashfs --yes
      writes a new image (padded with 0xff to the partition size)
"""
import argparse, hashlib, os, re, select, subprocess, sys, termios, time, zlib

PARTS = {  # name: (offset, size)
    "sys":     (0x060000, 0x2c0000),
    "sys_bak": (0x320000, 0x2c0000),
    "app":     (0x5e0000, 0x440000),
    "app_bak": (0xa20000, 0x440000),
}
SIBLING = {"sys": "sys_bak", "app": "app_bak", "sys_bak": "sys", "app_bak": "app"}   # the stock U-Boot `loadk` copies B over A
KNOWN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dump", "flashed_crcs.txt")   # "partition crc32hex" per successful write
RAM_IMG, RAM_READ = 0x82000000, 0x83000000
PROMPT = b"HKVS # "
HERE = os.path.dirname(os.path.abspath(__file__))


def write_one(args, part, log):
    """write (or, with --dry-run, only check) one partition; stops the program on any problem"""

    def say(m):
        line = "%s %s\n" % (time.strftime("%H:%M:%S"), m)
        log.write(line.encode()); print(line, end="", flush=True)

    def die(m, code=1):
        say("STOP: " + m); sys.exit(code)

    off, psize = PARTS[part]
    # ---- backup must exist and be intact
    dump = os.path.join(args.dump_dir, "flash_dump.bin")
    shaf = dump + ".sha256"
    if not (os.path.exists(dump) and os.path.exists(shaf)):
        die("no verified backup (dump/flash_dump.bin + .sha256)")
    want_sha = open(shaf).read().split()[0]
    dd = open(dump, "rb").read()
    if hashlib.sha256(dd).hexdigest() != want_sha or len(dd) != 0x1000000:
        die("backup does not match its SHA-256 / has wrong size")
    backup_region = dd[off:off + psize]
    backup_crc = zlib.crc32(backup_region) & 0xFFFFFFFF
    known = set()
    if os.path.exists(KNOWN_FILE):
        for ln in open(KNOWN_FILE):
            f = ln.split()
            if len(f) == 2 and f[0] == part: known.add(int(f[1], 16))
    soff, ssize = PARTS[SIBLING[part]]
    sibling_crc = zlib.crc32(dd[soff:soff + ssize]) & 0xFFFFFFFF
    say("backup OK; partition %s backup crc32 %08x" % (part, backup_crc))

    # ---- image
    if args.restore:
        data = backup_region
    else:
        if not args.image:
            die("give an image file or --restore")
        data = open(args.image, "rb").read()
    if len(data) > psize:
        die("image is %d bytes, partition holds %d" % (len(data), psize))
    img = data + b"\xff" * (psize - len(data))      # always write the whole partition
    size = len(img)
    crc = zlib.crc32(img) & 0xFFFFFFFF
    say("image %d bytes (padded to %d), crc32 %08x" % (len(data), size, crc))
    if not args.yes and not args.dry_run:
        die("add --yes to confirm writing flash partition '%s' (0x%06x-0x%06x)" % (part, off, off + psize))
    tmp = os.path.join(args.dump_dir, ".flash_write_image.bin")
    open(tmp, "wb").write(img)

    # ---- serial helpers
    def setraw(fd, nonblock):
        a = termios.tcgetattr(fd)
        a[0] = 0; a[1] = 0; a[3] = 0
        a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        a[4] = a[5] = termios.B115200
        a[6][termios.VMIN] = 0 if nonblock else 1
        a[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, a)

    def opennb():
        fd = os.open(args.port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK); setraw(fd, True); return fd

    def read_until(fd, pred, timeout):
        buf = b""; start = time.time()
        while time.time() - start < timeout:
            r, _, _ = select.select([fd], [], [], 0.1)
            if r:
                d = os.read(fd, 65536)
                if d: buf += d; log.write(d)
            if pred(buf): break
        return buf

    def cmd(fd, c, timeout=60):
        end = time.time() + 0.2
        while time.time() < end:
            r, _, _ = select.select([fd], [], [], 0.05)
            if r: log.write(os.read(fd, 65536)); end = time.time() + 0.2
        os.write(fd, c.encode() + b"\r")
        b = read_until(fd, lambda b: b.endswith(PROMPT), timeout)
        if not b.endswith(PROMPT):
            die("no prompt after: " + c)
        return b.decode(errors="replace")

    def crc_of(fd, addr, n):
        m = re.search(r"==> ([0-9a-f]{8})", cmd(fd, "crc32 0x%x 0x%x" % (addr, n), 120))
        return int(m.group(1), 16) if m else None

    def head_bytes(fd, addr, n):
        """the first n bytes at addr, from U-Boot's `md.b` (16 per line)"""
        out = cmd(fd, "md.b 0x%x 0x%x" % (addr, n), 30)
        got = []
        for ln in out.splitlines():
            m = re.match(r"\s*[0-9a-f]{8}:((?: [0-9a-f]{2}){1,16})", ln)
            if m: got += [int(x, 16) for x in m.group(1).split()]
        return bytes(got[:n]) if len(got) >= n else None

    def looks_valid(fd, part, psize):
        """Relaxed check: the flash (just read to RAM_READ) holds an intact image of the right kind although it is not the backup,
        for example after an update from the web page. sys/sys_bak: uImage with a good header CRC and a good data CRC (checked by U-Boot);
        app/app_bak: a squashfs 4.x superblock whose size fits the partition (squashfs has no checksum: this is a structure check only)."""
        if part.startswith("sys"):
            h = head_bytes(fd, RAM_READ, 64)
            if not h or h[:4] != b"\x27\x05\x19\x56":
                return False
            hcrc = int.from_bytes(h[4:8], "big")
            if zlib.crc32(h[:4] + b"\0\0\0\0" + h[8:]) & 0xFFFFFFFF != hcrc:
                return False
            dsize, dcrc = int.from_bytes(h[12:16], "big"), int.from_bytes(h[24:28], "big")
            if dsize < 1 or dsize + 64 > psize or crc_of(fd, RAM_READ + 64, dsize) != dcrc:
                return False
            say("live content is an intact uImage (header and data CRC ok, %d bytes): accepted" % dsize)
            return True
        h = head_bytes(fd, RAM_READ, 48)
        if not h or h[:4] != b"hsqs" or int.from_bytes(h[28:30], "little") != 4:
            return False
        used = int.from_bytes(h[40:48], "little")
        if used < 4096 or used > psize:
            return False
        say("live content is a squashfs 4.x image of %d bytes (structure check only): accepted" % used)
        return True

    fd = opennb()
    os.write(fd, b"\r")
    if not read_until(fd, lambda b: b.endswith(PROMPT), 4).endswith(PROMPT):
        die("no U-Boot prompt ('HKVS # ') on %s" % args.port)
    out = cmd(fd, "sf probe 0")
    if "16384 KiB" not in out:
        die("unexpected flash: %r" % out[-100:])
    usage = cmd(fd, "sf")
    if "erase" not in usage or "write" not in usage:
        die("this U-Boot's 'sf' has no erase/write: %r" % usage[-200:])
    say("U-Boot ready; flash 16384 KiB; sf erase/write available")

    # ---- 1. current flash content must equal the backup (proves the backup is good
    #         for this partition). Not required for --restore: there the whole point is
    #         to overwrite a partition that no longer holds the backup's content.
    cmd(fd, "sf read 0x%x 0x%x 0x%x" % (RAM_READ, off, psize), 300)
    cur = crc_of(fd, RAM_READ, psize)
    say("current flash crc32 %s (backup %08x)" % ("%08x" % cur if cur is not None else None, backup_crc))
    if cur != backup_crc and cur in known and not args.restore:
        say("live content equals an image written earlier by this tool (%08x); accepted" % cur)
    elif cur != backup_crc and cur == sibling_crc and not args.restore:
        say("live content equals the backup of the sibling slot %s (stock `loadk` synced it); accepted" % SIBLING[part])
    elif cur != backup_crc and not args.restore and looks_valid(fd, part, psize):
        pass        # an intact image of the right kind (the message is printed by looks_valid)
    elif cur != backup_crc:
        if args.restore:
            say("restore mode: live content differs from the backup (expected after a custom write); continuing")
        else:
            die("current flash content does not match the backup for this partition; not writing "
                "(if you are putting the original content back, use --restore)")

    # ---- 2. upload to RAM and verify
    wsize = size
    if args.from_sd:
        # fast route: the image is already on the microSD card (first FAT partition, folder cv206/); U-Boot reads it in seconds
        n = len(data)
        out = cmd(fd, "fatload mmc 0:1 0x%x cv206/%s" % (RAM_IMG, args.from_sd), 120)
        if ("%d bytes read" % n) not in out:
            die("fatload did not read %d bytes: %r" % (n, out[-160:]))
        ram = crc_of(fd, RAM_IMG, n); dcrc = zlib.crc32(data) & 0xFFFFFFFF
        say("RAM crc32 %s (file %08x), loaded from the SD card" % ("%08x" % ram if ram is not None else None, dcrc))
        if ram != dcrc:
            die("RAM CRC mismatch; flash untouched")
        wsize = n          # only the data is written; the erased remainder (0xff) equals the padded image
    else:
        os.write(fd, ("loady 0x%x\r" % RAM_IMG).encode())
        b = read_until(fd, lambda b: b"ymodem" in b.lower() and b"download" in b.lower(), 6)
        if b"ymodem" not in b.lower():
            die("loady did not start")
        os.close(fd)
        bfd = os.open(args.port, os.O_RDWR | os.O_NOCTTY); setraw(bfd, False)
        t0 = time.time()
        say("uploading %d bytes with sz --ymodem ..." % size)
        with open(args.log + ".sz", "ab") as szlog:
            p = subprocess.run(["sz", "--ymodem", tmp], stdin=bfd, stdout=bfd, stderr=szlog)
        os.close(bfd)
        say("sz exit %d after %.0f s (%.1f KB/s)" % (p.returncode, time.time() - t0, size / 1024 / (time.time() - t0)))
        fd = opennb()
        b = read_until(fd, lambda b: b.endswith(PROMPT), 15)
        m = re.search(rb"Total Size\s*=\s*(0x[0-9a-fA-F]+)\s*=\s*(\d+)", b)
        if p.returncode != 0 or not m or int(m.group(2)) != size:
            die("upload not confirmed")
        ram = crc_of(fd, RAM_IMG, size)
        say("RAM crc32 %s (file %08x)" % ("%08x" % ram if ram is not None else None, crc))
        if ram != crc:
            die("RAM CRC mismatch; flash untouched")

    if args.dry_run:
        os.remove(tmp)
        say("DRY RUN: all checks passed for partition '%s'; nothing was erased or written" % part)
        os.close(fd)
        return

    # ---- 3. erase + write
    say("erasing 0x%06x-0x%06x ..." % (off, off + psize))
    cmd(fd, "sf erase 0x%x 0x%x" % (off, psize), 300)
    say("writing ...")
    cmd(fd, "sf write 0x%x 0x%x 0x%x" % (RAM_IMG, off, wsize), 600)

    # ---- 4. read back and verify
    cmd(fd, "sf read 0x%x 0x%x 0x%x" % (RAM_READ, off, psize), 300)
    back = crc_of(fd, RAM_READ, psize)
    say("read-back crc32 %s (expected %08x)" % ("%08x" % back if back is not None else None, crc))
    os.remove(tmp)
    if back != crc:
        die("VERIFY FAILED: partition '%s' does not match. Other partitions are untouched. "
            "Restore it from the backup (--restore) before rebooting." % part, 2)
    with open(KNOWN_FILE, "a") as kf: kf.write("%s %08x\n" % (part, crc))
    say("OK: partition '%s' written and verified" % part)
    os.close(fd)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", nargs="?", help="image file (omit with --restore)")
    ap.add_argument("-p", "--port", default="/dev/ttyUSB0")
    ap.add_argument("--partition", required=True, choices=sorted(PARTS))
    ap.add_argument("--both", action="store_true", help="after SYS or APP also write its slot B twin (SYS_BAK or APP_BAK) with the same image, one after the other (slot A first)")
    ap.add_argument("--dry-run", action="store_true", help="do every check and the upload to RAM (CRC compared), but erase and write nothing")
    ap.add_argument("--restore", action="store_true", help="use the backup's own content for the partition")
    ap.add_argument("--dump-dir", default=os.path.join(HERE, "dump"))
    ap.add_argument("--from-sd", metavar="NAME", help="read the image from cv206/NAME on the camera's microSD card (FAT p1) instead of uploading it over UART; the local image file must be the same file (its CRC is checked)")
    ap.add_argument("--yes", action="store_true", help="confirm that you really want to write flash")
    ap.add_argument("--log", default=os.path.join(HERE, "flash_write.log"))
    args = ap.parse_args()
    log = open(args.log, "ab", buffering=0)
    if args.both:
        if args.partition not in ("sys", "app"):
            sys.exit("--both goes with --partition sys or app (it then also writes sys_bak or app_bak)")
        parts = [args.partition, SIBLING[args.partition]]
    else:
        parts = [args.partition]
    for part in parts:
        write_one(args, part, log)


if __name__ == "__main__":
    main()
