#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
# usage: prepare.sh WORKDIR OPENIPC_OUTPUT SD8801_BLOB
#   WORKDIR         where to create min-files/ and min-final.list (the kernel's CONFIG_INITRAMFS_SOURCE then points to WORKDIR/min-final.list)
#   OPENIPC_OUTPUT  OpenIPC build output directory (contains target/ and host/)
#   SD8801_BLOB     sd8801_uapsta.bin taken from your own firmware dump (not redistributable)
set -e
W=$(realpath -m "$1"); O=$(realpath "$2"); FW=$(realpath "$3"); H=$(dirname "$(realpath "$0")")
mkdir -p $W/min-files/fw
cp $H/min-files/init-final $H/min-files/ld-musl-arm.path $W/min-files/
cp $O/target/bin/busybox $W/min-files/busybox
cp $(find $O/host -name libc.so -path "*musl*" | head -1) $W/min-files/libc.so 2>/dev/null || cp $O/target/lib/libc.so $W/min-files/libc.so
cp $(find $O/host -name libgcc_s.so.1 | head -1) $W/min-files/libgcc_s.so.1 2>/dev/null || cp $O/target/lib/libgcc_s.so.1 $W/min-files/libgcc_s.so.1
cp "$FW" $W/min-files/fw/sd8801_uapsta.bin
sed "s#@INITRAMFS@#$W#g" $H/min-final.list > $W/min-final.list
echo "ready: set CONFIG_INITRAMFS_SOURCE=\"$W/min-final.list\""
