# SPDX-License-Identifier: GPL-2.0-or-later
import os, sys
root = sys.argv[1]          # extracted rootfs (read only)
out = sys.argv[2]
keep_files = {"bin/busybox", "lib/libc.so", "lib/libgcc_s.so.1"}
lines = []
for dp, dn, fn in os.walk(root):
    rel = os.path.relpath(dp, root)
    rel = "" if rel == "." else rel
    # skip big app trees; keep only what a bring-up shell needs
    if rel.split("/")[0] in ("var", "usr", "mnt", "home", "root", "tmp", "lib") and rel.startswith(("var", "usr/lib", "usr/share", "mnt", "home", "root", "tmp", "lib/modules", "lib/firmware", "lib/mdev")):
        dn[:] = []
        if rel not in ("tmp", "home", "root", "mnt"): continue
    lines.append("dir /%s 755 0 0" % rel if rel else "dir / 755 0 0")
    for n in sorted(dn + fn):
        p = os.path.join(dp, n); r = (rel + "/" + n) if rel else n
        if os.path.islink(p):
            if r.startswith(("usr/lib", "usr/share", "lib/modules", "lib/firmware", "var")): continue
            lines.append("slink /%s %s 777 0 0" % (r, os.readlink(p)))
        elif os.path.isfile(p) and r in keep_files:
            lines.append("file /%s %s 755 0 0" % (r, p))
lines.append("dir /dev 755 0 0")
lines.append("nod /dev/console 600 0 0 c 5 1")
lines.append("nod /dev/null 666 0 0 c 1 3")
seen = set(); res = []
for l in lines:
    k = l.split()[1]
    if k in seen: continue
    seen.add(k); res.append(l)
open(out, "w").write("\n".join(res) + "\n")
print(len(res), "entries")
