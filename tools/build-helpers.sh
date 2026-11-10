#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Build the small target helper programs from tools/src and gather the prebuilt pieces for the app image into app/
# (those binaries are not committed). Needs the OpenIPC build output (toolchain, staging, target).
# usage: build-helpers.sh [OPENIPC_OUTPUT]   (default: $OPENIPC_OUT, see tools/common.sh)
set -e
. "$(dirname "${BASH_SOURCE[0]}")/common.sh"; O=${1:-$OPENIPC_OUT}
export PATH=$O/host/bin:$PATH; CC=arm-openipc-linux-musleabi-gcc; V=$H/app
mkdir -p $V/bin $V/sbin $V/lib $V/usr/share/udhcpc $V/etc/ssl
for t in jget jcfg; do $CC -Os -I$O/staging/usr/include -o $V/bin/$t $H/tools/src/$t.c -L$O/staging/usr/lib -ljson-c; done
for t in httpget i2cwr i2cprobe addentropy acodecctl; do $CC -Os -I$H/tools/src -o $V/bin/$t $H/tools/src/$t.c; done
cp $O/target/usr/sbin/wpa_supplicant $O/target/sbin/iwconfig $V/sbin/; arm-openipc-linux-musleabi-strip $V/sbin/wpa_supplicant; ln -sf iwconfig $V/sbin/iwlist
cp -L $O/target/usr/lib/libnl-3.so.200 $O/target/usr/lib/libnl-genl-3.so.200 $V/lib/
cp $O/target/usr/share/udhcpc/default.script $V/usr/share/udhcpc/
mkdir -p $V/usr/share/fonts/truetype; cp $O/target/usr/share/fonts/truetype/UbuntuMono-Regular.ttf $O/target/usr/share/fonts/truetype/UbuntuMono-Regular.LICENSE $V/usr/share/fonts/truetype/   # for the on-screen display (the font licence must travel with the font)
cp /etc/ssl/certs/ca-certificates.crt $V/etc/ssl/ca-certificates.crt
echo "helpers ready in $V (the app base tree with modules, majestic and libraries comes from the OpenIPC target, see tools/mkapp.sh)"
