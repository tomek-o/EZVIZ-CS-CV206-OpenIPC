# SPDX-License-Identifier: GPL-2.0-or-later
# Sourced by the build scripts: where things are. Override in the environment or in ./local.env (not in git), e.g.
#   OPENIPC_DIR=/data/openipc-cv206        # contains firmware/ (OpenIPC clone, built: firmware/output/)
H=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
[ -f "$H/local.env" ] && . "$H/local.env"
OPENIPC_DIR=${OPENIPC_DIR:-$HOME/openipc-cv206}
OPENIPC_OUT=${OPENIPC_OUT:-$OPENIPC_DIR/firmware/output}
APP_TREE=${APP_TREE:-$H/build/app-tree}
