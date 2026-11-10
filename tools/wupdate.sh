#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Update the camera's flash over Wi-Fi: wupdate.sh app|sys IMAGE   (developer tool; needs the camera running our system and the PC hotspot)
# Serves IMAGE from the PC web server (analysis/video, port 8000), tells the camera (login from .hotspot.private) to download, verify,
# flash and reboot, then waits until the camera answers again and prints its build stamp.
set -e
KIND=$1; IMG=$2; [ -n "$KIND" ] && [ -f "$IMG" ] || { echo "usage: wupdate.sh app|sys IMAGE"; exit 2; }
H=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd); . $H/.hotspot.private
CAM=${CAM:-10.42.0.24}; PC=${PC:-10.42.0.1}
NAME=upd-$(basename "$IMG"); mkdir -p $H/analysis/video; cp "$IMG" $H/analysis/video/$NAME
SHA=$(sha256sum "$IMG" | cut -d' ' -f1)
curl -s -m 2 -o /dev/null -r 0-0 http://$PC:8000/$NAME || { echo "PC web server on :8000 (analysis/video) is not running"; exit 1; }
echo "image $(stat -c %s "$IMG") bytes, sha256 ${SHA:0:12}..."
[ -n "$DRY" ] && EXTRA="&dry=1"
R=$(curl -s -m 120 -u root:$RTSPPASS -X POST "http://$CAM/cgi-bin/update?kind=$KIND&sha256=$SHA&url=http://$PC:8000/$NAME$EXTRA")
echo "camera: $R"
echo "$R" | grep -q '"ok":true' || exit 1
[ -n "$DRY" ] && exit 0
POLL=${POLL:-$CAM}
echo -n "flashing and rebooting "; T0=$(date +%s)
sleep 20
for i in $(seq 1 60); do
  S=$(curl -s -m 4 -u root:$RTSPPASS http://$POLL/cgi-bin/status) && echo "$S" | grep -q uptime && break
  echo -n "."; sleep 3
done; echo
echo "camera back after $(( $(date +%s) - T0 )) s: $S"
rm -f $H/analysis/video/$NAME
