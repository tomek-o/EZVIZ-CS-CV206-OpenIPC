#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -e
. "$(dirname "${BASH_SOURCE[0]}")/common.sh"; O=$OPENIPC_OUT
export PATH=$O/per-package/linux/host/bin:$O/per-package/linux/host/sbin:$O/host/bin:$PATH
# neutral build identity: the kernel version string (uname -a) must not carry the builder's user and host name in a shared image
export KBUILD_BUILD_USER=${KBUILD_BUILD_USER:-cv206} KBUILD_BUILD_HOST=${KBUILD_BUILD_HOST:-build}
cd $O/build/linux-custom
V="ARCH=arm CROSS_COMPILE=arm-openipc-linux-musleabi- WERROR=0 REGENERATE_PARSERS=1"
make $V -j4 all
make $V uImage
echo KBUILD_DONE
