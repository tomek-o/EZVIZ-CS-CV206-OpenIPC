#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Build a complete 16 MiB flash image for the Ezviz CS-CV206 (to program with an SPI programmer, e.g. flashrom + CH341A) from YOUR OWN flash dump.

  make-spi-image.py make   --dump flash_dump.bin --sys SYS.bin --app APP.sqsh --out image.bin
  make-spi-image.py verify --image image.bin --dump flash_dump.bin

What `make` changes, and nothing else (all other bytes come unchanged from your dump):
  sys      (0x060000, 2816 KB): our kernel image (uImage) padded with 0xFF
  app      (0x5e0000, 4352 KB): our app image (squashfs) padded with 0xFF
  sys_bak  (0x320000, 2816 KB), app_bak (0xa20000, 4352 KB): slot B = a second copy of the same two images (the known-good fallback; the stock `loadk` repairs slot A from it).
                                The original Ezviz firmware that was there is then gone from the flash: it only exists in your dump.
  env      (0x040000,   64 KB): YOUR U-Boot environment with five variables set (a1 a2 a3 s1 bootcmd): boot slot A first, slot B as fallback; CRC recomputed
Never touched: bld (bootloader), enc (device identity), cfg (stock configuration, credentials), log.

The image contains your device's MAC address, serial number and credentials (they are in your dump): never publish it.
Standard library only.
"""
import argparse, hashlib, struct, sys, zlib

SIZE = 0x1000000
REGIONS = [  # name, offset, size
    ("bld", 0x000000, 0x040000), ("env", 0x040000, 0x010000), ("enc", 0x050000, 0x010000),
    ("sys", 0x060000, 0x2c0000), ("sys_bak", 0x320000, 0x2c0000), ("app", 0x5e0000, 0x440000),
    ("app_bak", 0xa20000, 0x440000), ("cfg", 0xe60000, 0x100000), ("log", 0xf60000, 0x0a0000),
]
R = {n: (o, s) for n, o, s in REGIONS}
BOOT = {  # the boot command of this project (REFERENCE.md "Flash layout and boot"): our kernel from slot A with a 35 MB OS, slot B (a copy of our images) as fallback
    "a1": "setenv bootargs mem=35M console=ttyAMA0,115200 panic=10",
    "a2": "sf probe 0",
    "a3": "sf read 0x82000000 0x60000 0x2c0000",
    "s1": "setenv bootargs mem=35M console=ttyAMA0,115200 panic=10",
    "bootcmd": "${a1};${a2};${a3};bootm 0x82000000;${s1};loadk;bootm 0x80007fc0",
}


def die(msg):
    sys.exit("error: " + msg)


def read(path, what):
    try:
        return open(path, "rb").read()
    except OSError as e:
        die(f"cannot read {what} {path}: {e}")


def parse_env(block):
    """U-Boot environment block: 4 bytes CRC32 (little endian) of the rest, then NUL separated NAME=VALUE entries, ended by an empty entry."""
    crc = struct.unpack("<I", block[:4])[0]
    if zlib.crc32(block[4:]) & 0xFFFFFFFF != crc:
        die("the environment block in the dump has a bad CRC: this does not look like a good dump of this camera")
    body = block[4:]
    end = body.find(b"\0\0")
    if end < 0:
        die("environment block has no terminator")
    pad = body[end + 2] if end + 2 < len(body) else 0
    items = []
    for e in body[:end].split(b"\0"):
        k, _, v = e.decode("latin-1").partition("=")
        items.append((k, v))
    return items, pad


def build_env(items, pad):
    d = dict(items)
    out = [(k, v) for k, v in items]
    for k, v in BOOT.items():
        if k in d:
            out = [(kk, v if kk == k else vv) for kk, vv in out]
        else:
            out.append((k, v))
    body = b"".join(f"{k}={v}".encode("latin-1") + b"\0" for k, v in out) + b"\0"
    if len(body) > 0x10000 - 4:
        die("environment too large")
    body += bytes([pad]) * (0x10000 - 4 - len(body))
    return struct.pack("<I", zlib.crc32(body) & 0xFFFFFFFF) + body


def check_dump(dump):
    if len(dump) != SIZE:
        die(f"the dump must be exactly {SIZE} bytes (16 MiB), it is {len(dump)}")
    if dump[0x060000:0x060004] != b"\x27\x05\x19\x56" or dump[0x320000:0x320004] != b"\x27\x05\x19\x56":
        die("sys and sys_bak in the dump do not start with a uImage header: wrong layout or a damaged dump")
    if dump[0xa20000:0xa20004] not in (b"hsqs", b"sqsh"):
        die("app_bak in the dump is not a squashfs: wrong layout or a damaged dump")
    if dump[0x050000:0x050010] == b"\xff" * 16:
        die("the enc (device identity) region of the dump is empty: damaged dump")


def sha(b):
    return hashlib.sha256(b).hexdigest()


def make(a):
    dump, ksys, app = read(a.dump, "dump"), read(a.sys, "kernel image"), read(a.app, "app image")
    check_dump(dump)
    if ksys[:4] != b"\x27\x05\x19\x56":
        die("--sys is not a uImage (bad magic)")
    if app[:4] != b"hsqs":
        die("--app is not a squashfs image")
    if len(ksys) > R["sys"][1]:
        die(f"kernel image is {len(ksys)} bytes, slot is {R['sys'][1]}")
    if len(app) > R["app"][1]:
        die(f"app image is {len(app)} bytes, slot is {R['app'][1]}")
    items, pad = parse_env(dump[0x040000:0x050000])
    img = bytearray(dump)
    img[0x040000:0x050000] = build_env(items, pad)
    img[0x060000:0x060000 + R["sys"][1]] = ksys + b"\xff" * (R["sys"][1] - len(ksys))
    img[0x5e0000:0x5e0000 + R["app"][1]] = app + b"\xff" * (R["app"][1] - len(app))
    img[0x320000:0x320000 + R["sys"][1]] = img[0x060000:0x060000 + R["sys"][1]]          # slot B: a copy of ours
    img[0xa20000:0xa20000 + R["app"][1]] = img[0x5e0000:0x5e0000 + R["app"][1]]
    open(a.out, "wb").write(img)
    print(f"wrote {a.out} ({len(img)} bytes), sha256 {sha(img)}")
    verify_report(bytes(img), dump)


def verify_report(img, dump):
    ok = True
    items, _ = parse_env(img[0x040000:0x050000])
    e = dict(items)
    print("\nregion        offset    size      state")
    for n, o, s in REGIONS:
        same = img[o:o + s] == dump[o:o + s] if dump else None
        state = "" if same is None else ("identical to the dump" if same else "CHANGED")
        want_changed = n in ("env", "sys", "app", "sys_bak", "app_bak")
        if same is not None and ((not same) != want_changed):
            state += "   <-- UNEXPECTED"; ok = False
        print(f"{n:<12}  0x{o:06x}  {s // 1024:>5} KB  {state}   sha256 {sha(img[o:o + s])[:16]}")
    for k, v in BOOT.items():
        if e.get(k) != v:
            print(f"environment variable {k} is not as expected"); ok = False
    print("environment CRC ok, bootcmd =", e.get("bootcmd"))
    print("sys: uImage magic", "ok" if img[0x060000:0x060004] == b"\x27\x05\x19\x56" else "BAD", "| app: squashfs magic", "ok" if img[0x5e0000:0x5e0004] == b"hsqs" else "BAD", "| slot B equals slot A:", "yes" if img[0x320000:0x320000 + R["sys"][1]] == img[0x060000:0x060000 + R["sys"][1]] and img[0xa20000:0xa20000 + R["app"][1]] == img[0x5e0000:0x5e0000 + R["app"][1]] else "NO")
    if dump:
        print("\nbootloader, device identity, stock config and logs are byte-identical to the dump; sys, app and slot B hold the new images" if ok else "\nVERIFICATION FAILED")
    if not ok:
        sys.exit(1)


def verify(a):
    img = read(a.image, "image")
    if len(img) != SIZE:
        die("image size is not 16 MiB")
    dump = read(a.dump, "dump") if a.dump else None
    if dump:
        check_dump(dump)
    verify_report(img, dump)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    s = p.add_subparsers(dest="cmd", required=True)
    m = s.add_parser("make"); m.add_argument("--dump", required=True); m.add_argument("--sys", required=True); m.add_argument("--app", required=True); m.add_argument("--out", required=True)
    v = s.add_parser("verify"); v.add_argument("--image", required=True); v.add_argument("--dump")
    a = p.parse_args()
    make(a) if a.cmd == "make" else verify(a)


if __name__ == "__main__":
    main()
