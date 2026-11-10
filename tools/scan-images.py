#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Scan finished firmware images for personal or private data before they are shared.

  scan-images.py IMAGE [IMAGE ...]

Unpacks what it can (squashfs via unsquashfs, every XZ stream inside a kernel image, recursively, which includes the initramfs) and looks for:
  * the owner's secrets from .hotspot.private (SSID, passwords) and the camera's identifiers found in dump/ (environment MAC, printable strings of the `enc` region)
  * MAC-address-like strings, e-mail addresses, home directory paths, the build user/host in the kernel version string
Exit status 0 = nothing found that needs a decision, 1 = findings (printed with the secret part masked). Findings of the generic kind (MAC-like, paths)
need a human look: some are harmless (for example documentation examples, `00:00:00:00:00:00`).
"""
import lzma, os, re, shutil, subprocess, sys, tempfile

H = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XZ_MAGIC = b"\xfd7zXZ\x00"
MAC = re.compile(rb"(?<![0-9A-Fa-f:])(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}(?![0-9A-Fa-f:])")
BENIGN_MAC = {b"00:00:00:00:00:00", b"ff:ff:ff:ff:ff:ff", b"FF:FF:FF:FF:FF:FF"}
MAIL = re.compile(rb"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
HOME = re.compile(rb"/home/[A-Za-z0-9._-]+")
VERS = re.compile(rb"Linux version [^\n\x00]{0,160}")


# strings reviewed on 2026-11-10 and found harmless; anything else that matches the generic patterns is reported
BENIGN_MAIL = {b"1001@pbx.local", b"camera@pbx.local",                                    # placeholder text of the SIP page
               b"j@w1.fi",                                                              # wpa_supplicant author
               b"sk-ecdsa-sha2-nistp256@openssh.com", b"sk-ssh-ed25519@openssh.com",    # OpenSSH algorithm names (mbed TLS/dropbear data)
               b"th@Tt.Cx"}                                                             # data inside the kernel image
BENIGN_HOME = {b"/home/pub"}                                                           # a default path inside majestic


def mask(b, keep=2):
    s = b.decode("latin-1")
    return s[:keep] + "*" * max(0, len(s) - keep) if len(s) > 4 else "*" * len(s)


def secrets():
    out = {}
    try:
        for line in open(os.path.join(H, ".hotspot.private")):
            k, _, v = line.strip().partition("=")
            v = v.strip().strip('"').strip("'")
            if k in ("SSID", "PASS", "RTSPPASS") and len(v) >= 4:
                out["secret " + k] = v.encode()
    except OSError:
        pass
    dump = os.path.join(H, "dump", "flash_dump.bin")
    if os.path.exists(dump):
        d = open(dump, "rb").read()
        env = d[0x40000:0x50000]
        m = re.search(rb"ethaddr=([0-9A-Fa-f:]{17})", env)
        if m:
            out["camera MAC (env)"] = m.group(1)
            out["camera MAC (env, lower)"] = m.group(1).lower()
            out["camera MAC (env, upper)"] = m.group(1).upper()
        for i, s in enumerate(re.findall(rb"[ -~]{8,}", d[0x50000:0x60000])[:20]):   # identity region: model, serial, MAC strings
            if not re.fullmatch(rb"[A-Za-z ._-]+", s):
                out["identity string %d" % i] = s
    return out


def unpack(data, depth=0, found=None):
    """yield byte blobs: the data itself and everything XZ-compressed inside it (recursively)"""
    yield data
    if depth >= 3:
        return
    pos = 0
    while True:
        i = data.find(XZ_MAGIC, pos)
        if i < 0:
            return
        pos = i + 6
        try:
            dec = lzma.LZMADecompressor(format=lzma.FORMAT_XZ)
            out = dec.decompress(data[i:], max_length=64 * 1024 * 1024)
        except (lzma.LZMAError, EOFError, ValueError):
            continue
        if len(out) > 4096:
            yield from unpack(out, depth + 1)


def blobs_of(path):
    data = open(path, "rb").read()
    if data[:4] == b"hsqs":
        tmp = tempfile.mkdtemp(prefix="scan-")
        try:
            subprocess.run(["unsquashfs", "-q", "-f", "-d", os.path.join(tmp, "x"), path], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            n = 0
            for root, _, files in os.walk(os.path.join(tmp, "x")):
                for f in files:
                    p = os.path.join(root, f)
                    if os.path.islink(p) or not os.path.isfile(p):
                        continue
                    n += 1
                    yield from unpack(open(p, "rb").read())
            print("  unpacked %d files from the squashfs" % n)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    else:
        yield from unpack(data)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    sec = secrets()
    print("looking for %d secrets/identifiers and generic patterns" % len(sec))
    bad = 0
    for path in sys.argv[1:]:
        print("\n== %s (%d bytes)" % (path, os.path.getsize(path)))
        macs, mails, homes, vers, hits = set(), set(), set(), set(), []
        blobs = 0
        for b in blobs_of(path):
            blobs += 1
            for name, v in sec.items():
                if v in b:
                    hits.append(name)
            macs |= {m for m in MAC.findall(b) if m not in BENIGN_MAC}
            mails |= set(MAIL.findall(b)) - BENIGN_MAIL
            homes |= set(HOME.findall(b)) - BENIGN_HOME
            vers |= set(VERS.findall(b))
        print("  scanned %d unpacked parts" % blobs)
        for name in sorted(set(hits)):
            print("  FOUND %s" % name); bad += 1
        for m in sorted(macs)[:12]:
            print("  MAC-like string: %s" % mask(m, 8)); bad += 1
        for m in sorted(mails)[:12]:
            print("  e-mail-like string: %s" % mask(m, 3)); bad += 1
        for m in sorted(homes)[:12]:
            print("  home path: %s" % m.decode("latin-1")); bad += 1
        for v in sorted(vers)[:3]:
            print("  kernel version string: %s" % v.decode("latin-1"))
            m = re.search(rb"\(([^)@\s]+@[^)\s]+)\)", v)
            if m and m.group(1) != b"cv206@build":       # the neutral build identity set in tools/kbuild.sh is fine
                bad += 1; print("    -> contains the builder's user@host (rebuild with tools/kbuild.sh)")
    print("\nRESULT:", "findings above need a decision" if bad else "nothing found")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
