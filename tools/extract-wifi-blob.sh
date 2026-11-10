#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Extract the Marvell SD8801 Wi-Fi firmware from YOUR OWN flash dump (it is proprietary and must not be redistributed).
# usage: extract-wifi-blob.sh flash_dump.bin OUT_FILE      (needs unsquashfs from squashfs-tools)
set -e
D=$1; O=$2; [ -f "$D" ] && [ -n "$O" ] || { echo "usage: $0 flash_dump.bin OUT_FILE"; exit 2; }
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
dd if="$D" of="$T/app_bak.sqsh" bs=4096 skip=$((0xa20000 / 4096)) count=$((0x440000 / 4096)) status=none     # stock app slot B
unsquashfs -q -d "$T/x" "$T/app_bak.sqsh" sd8801_uapsta.bin >/dev/null 2>&1 || true     # it sits at the root of the squashfs (the stock system mounts it at /dav)
F=$(find "$T/x" -name 'sd8801_uapsta.bin' | head -1)
[ -n "$F" ] || { echo "sd8801_uapsta.bin not found in the stock app image of this dump"; exit 1; }
cp "$F" "$O"; echo "wrote $O ($(stat -c %s "$O") bytes, sha256 $(sha256sum "$O" | cut -c1-16)...)"
