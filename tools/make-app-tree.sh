#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Collect the base tree of the app image (majestic, HiSilicon media modules and libraries, sensor/IQ files) from a built OpenIPC tree.
# The list of files is tools/app-tree.manifest (paths relative to OpenIPC's output/target). usage: make-app-tree.sh [DEST]   (default $APP_TREE = build/app-tree)
set -e
. "$(dirname "${BASH_SOURCE[0]}")/common.sh"
D=${1:-$APP_TREE}; T=$OPENIPC_OUT/target
[ -d "$T" ] || { echo "no OpenIPC build output at $T (see BUILDING.md; set OPENIPC_DIR)"; exit 1; }
rm -rf "$D"; mkdir -p "$D"
while read -r f; do
    [ -e "$T/$f" ] || [ -L "$T/$f" ] || { echo "missing in the OpenIPC output: $f"; exit 1; }
    mkdir -p "$D/$(dirname "$f")"; cp -a "$T/$f" "$D/$f"
done < "$H/tools/app-tree.manifest"
echo "app tree: $(wc -l < "$H/tools/app-tree.manifest") files, $(du -sh "$D" | cut -f1) in $D"
