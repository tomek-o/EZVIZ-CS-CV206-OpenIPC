#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Build the app squashfs: base tree + app, inject private settings (Wi-Fi test network, root password) from .hotspot.private.
# RELEASE=1 tools/mkapp.sh OUT.sqsh : no injected network/password (the image any user would get; first start = setup access point, no password).
set -e
. "$(dirname "${BASH_SOURCE[0]}")/common.sh"; B=$APP_TREE; W=${TMPDIR:-/tmp}/app-build
[ -d "$B" ] || "$H/tools/make-app-tree.sh" "$B"
rm -rf $W; cp -a $B $W; cp -a $H/app/. $W/
V=$(cat $H/VERSION)
# release image: "cv206 1.0.0 (app 2026-11-10_12:30)"; development image (test network and password baked in): "cv206 1.0.0-dev (app ...)"
if [ -n "$RELEASE" ]; then VS=$V; else VS=$V-dev; fi
echo "cv206 $VS (app $(date +%Y-%m-%d_%H:%M))" > $W/etc/build.txt
if [ -z "$RELEASE" ]; then
. $H/.hotspot.private
python3 - <<PY
import json
p="$W/etc/camera.json"; c=json.load(open(p))
c["wifi"]["networks"]=[{"ssid":"$SSID","psk":"$PASS"}]
c["users"]["root_password"]="$RTSPPASS"
json.dump(c,open(p,"w"),indent=2)
PY
fi
# minify the web page (strip comments, indentation and blank lines): the camera's CPU is slow and the page should be small
python3 - <<PY
import re
f="$W/www/index.html"; t=open(f).read()
t=re.sub(r'/\*.*?\*/','',t,flags=re.S)                       # CSS/JS block comments
t=re.sub(r'(?m)^[ \t]+','',t); t=re.sub(r'(?m)\s+$','',t); t=re.sub(r'\n{2,}','\n',t)
open(f,'w').write(t)
PY
mksquashfs $W ${1:-$H/analysis/video/app_v2.sqsh} -comp xz -b 256K -noappend -all-root -quiet
ls -l ${1:-$H/analysis/video/app_v2.sqsh}
