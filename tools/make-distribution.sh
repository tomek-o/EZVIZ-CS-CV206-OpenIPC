#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Build the release package of the finished images, into _release/ (not in git; these files are what gets attached to a release):
#   cv206-open-firmware-VERSION.tar.xz         the two images, checksums, license texts, notices, install guide
#   cv206-open-firmware-VERSION-source.tar.xz  the corresponding source of the GPL parts (kernel, BusyBox, wireless tools, this repository, the OpenIPC build tree snapshot)
# usage: tools/make-distribution.sh [SYS_IMAGE] [APP_IMAGE]      (defaults: _release/sys-VERSION.uImage and _release/app-VERSION.sqsh)
# It refuses to continue when the privacy scan (tools/scan-images.py) finds anything, or when the app image is a development build.
set -e
. "$(dirname "${BASH_SOURCE[0]}")/common.sh"
V=$(cat "$H/VERSION"); NAME=cv206-open-firmware-$V
SYS=${1:-$H/_release/sys-$V.uImage}; APP=${2:-$H/_release/app-$V.sqsh}
DL=$OPENIPC_OUT/buildroot-2024.02.10/dl
die() { echo "ERROR: $*" >&2; exit 1; }
[ -f "$SYS" ] && [ -f "$APP" ] || die "image files not found ($SYS, $APP)"
[ "$(od -An -tx1 -N4 "$SYS" | tr -d ' ')" = 27051956 ] || die "$SYS is not a uImage"
BT=$(unsquashfs -cat "$APP" etc/build.txt 2>/dev/null) || die "cannot read the build stamp of $APP"
case "$BT" in *-dev*) die "the app image is a development build ($BT): build it with RELEASE=1";; esac
echo "app build stamp: $BT"
echo "--- privacy scan"; python3 "$H/tools/scan-images.py" "$SYS" "$APP" || die "the privacy scan found something: look at it first"

OUT=$H/_release; STAGE=$H/build/dist-stage; P=$STAGE/$NAME; S=$STAGE/$NAME-source     # the working folders live in build/, only the finished archives go to _release/
rm -rf "$STAGE"; mkdir -p "$P/licenses" "$S"
cp "$SYS" "$P/sys-$V.uImage"; cp "$APP" "$P/app-$V.sqsh"
cp "$H/INSTALL.md" "$H/THIRD-PARTY.md" "$H/LICENSE" "$P/"; cp "$H"/licenses/* "$P/licenses/"
cat > "$P/README.txt" <<EOF
cv206 open firmware $V  -  replacement firmware for the Ezviz CS-CV206-C0-3B2WFR-Pro ("ezCubePro")
==========================================================================================

What this is: a local-only firmware (no Ezviz cloud) built on OpenIPC: RTSP/ONVIF video, web page, audio, SIP, SD-card recording. Project sources and documents: see the source package.
Files: sys-$V.uImage (kernel image, flash slot "sys") and app-$V.sqsh (app image, flash slot "app"); SHA256SUMS. How to install: INSTALL.md (use these two files instead of building them).

READ THIS FIRST
  * USE AT YOUR OWN RISK. Flashing can leave a device unusable. Make a verified backup of your camera's flash first (INSTALL.md, step 0). There is NO WARRANTY of any kind.
  * Only for the model named above. Other variants of the CS-CV206 have different hardware.
  * NON-COMMERCIAL USE ONLY. The package contains the "majestic" streamer by OpenIPC, licensed under the Prosperity Public License 3.0.0 (licenses/Prosperity-3.0.0-majestic-LICENSE.md;
    contributor: OpenIPC (c) 2025; source: https://github.com/OpenIPC/majestic): free for non-commercial use and sharing, commercial use only as a 30-day trial. Do not sell this firmware, ship it on
    devices for sale, or run it in a commercial service. OpenIPC offers commercial terms through its partner program (https://openipc.org/partners).
  * Everyone who passes this package on must keep the license texts and notices in it (licenses/, THIRD-PARTY.md).
  * Not affiliated with or endorsed by Ezviz, Hikvision, OpenIPC, HiSilicon or Marvell. Product names belong to their owners.
  * The redistribution status of some parts (HiSilicon vendor libraries and kernel modules, the Marvell Wi-Fi firmware build) is not fully clear: see THIRD-PARTY.md. They are included as they come from the
    OpenIPC build and the Ezviz firmware, on the distributor's own responsibility, and will be removed on a justified request of the rights holder.
  * Free software parts (Linux, BusyBox, ...) are under their own licenses; their corresponding source is in the separate source package $NAME-source.tar.xz.
  * No personal data is included: the images were scanned for the builder's secrets, the camera's identifiers, MAC-like strings and build-machine names before packaging.
  * Marvell Wi-Fi firmware inside sys: Marvell's licence text for this firmware family is licenses/LICENCE.Marvell (use only with Marvell silicon, no reverse engineering).

Version: $V   Build stamp of the app image: $BT
Kernel: $(strings -a "$SYS" | grep -m1 'Linux version' || true)
EOF
( cd "$P" && sha256sum "sys-$V.uImage" "app-$V.sqsh" > SHA256SUMS )

echo "--- source package"
[ -d "$DL" ] || die "no OpenIPC download cache at $DL"
mkdir -p "$S/third-party-sources"
cp "$DL/linux/hisilicon-hi3516cv200.tar.gz" "$DL/busybox/busybox-1.36.1.tar.bz2" "$DL/wireless_tools/wireless_tools.30.pre9.tar.gz" "$S/third-party-sources/"
git -C "$H" archive --format=tar.gz --prefix=cv206-project-$V/ -o "$S/cv206-project-$V.tar.gz" HEAD
if git -C "$OPENIPC_DIR/firmware" rev-parse --verify -q ba8647a >/dev/null; then git -C "$OPENIPC_DIR/firmware" archive --format=tar.gz --prefix=openipc-firmware-ba8647a/ -o "$S/openipc-firmware-ba8647a.tar.gz" ba8647a; fi
cp "$H/THIRD-PARTY.md" "$H/BUILDING.md" "$H/LICENSE" "$S/"
cat > "$S/README.txt" <<EOF
Corresponding source for cv206 open firmware $V (GPL-2.0 parts and build scripts)
==========================================================================

third-party-sources/hisilicon-hi3516cv200.tar.gz   Linux 4.9.37, OpenIPC branch hisilicon-hi3516cv200 (https://github.com/openipc/linux), exactly the archive the kernel was built from (2026-11-06)
third-party-sources/busybox-1.36.1.tar.bz2         BusyBox 1.36.1 (https://busybox.net)
third-party-sources/wireless_tools.30.pre9.tar.gz  wireless tools (iwconfig, iwlist)
cv206-project-$V.tar.gz                            this project: kernel patches (kernel/patches), kernel config, initramfs lists, scripts, web page, documents (BUILDING.md describes the build)
openipc-firmware-ba8647a.tar.gz                    the OpenIPC build system snapshot (https://github.com/OpenIPC/firmware, commit ba8647a; MIT) used to build everything else
Not included: the proprietary binaries (majestic, HiSilicon libraries and modules, Marvell firmware): they have no source here.
Build instructions: BUILDING.md. Licenses: THIRD-PARTY.md, LICENSE.
EOF
( cd "$S" && find . -type f ! -name SHA256SUMS -print0 | xargs -0 sha256sum > SHA256SUMS )

echo "--- archives"
( cd "$STAGE" && tar -cJf "$OUT/$NAME.tar.xz" "$NAME" && tar -cJf "$OUT/$NAME-source.tar.xz" "$NAME-source" )
( cd "$OUT" && sha256sum "$NAME.tar.xz" "$NAME-source.tar.xz" > "$NAME.SHA256SUMS" )
rm -rf "$STAGE"
ls -l "$OUT"/*.tar.xz | awk '{printf "%10d  %s\n", $5, $9}'; cat "$OUT/$NAME.SHA256SUMS" | cut -c1-20,65-
echo "package ready in $OUT (nothing was published)"
