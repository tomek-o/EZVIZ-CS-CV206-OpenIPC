# Kernel and initramfs

Our kernel is the OpenIPC Linux 4.9.37 for the Hi3518EV200 with three small changes, built **outside** this repository
(the OpenIPC build tree is several GB).

## Base

| What | Value |
|---|---|
| OpenIPC firmware repository | https://github.com/OpenIPC/firmware, commit `ba8647a` (2026-11-06), build `make BOARD=hi3518ev200_lite` |
| Kernel source | the tarball Buildroot downloads: `https://github.com/openipc/linux/archive/hisilicon-hi3516cv200.tar.gz` (a **branch** archive: it can change; version 4.9.37; we built it on 2026-11-06) |
| Toolchain | OpenIPC's prebuilt `arm-openipc-linux-musleabi` (downloaded by the first OpenIPC build) |
| Our changes | `patches/` (apply with `patch -p1` in the kernel tree), `config.cv206-final` |
| OpenIPC's own config (for diffs) | `config.openipc-orig` |

## Changes

1. `patches/0001-himci-nonremovable-and-rescan.patch`: `himci` driver: report "card present" for non-removable hosts (the SDIO Wi-Fi
   chip has no card-detect line) and a `rescan` sysfs attribute.
2. `patches/0002-cv206-device-tree.patch`: `&mmc1_sd` non-removable + SDIO1 pad mux state (function 4) + GPIO 18 hog (Wi-Fi enable).
3. `config.cv206-final`: trimmed, **`CONFIG_FS_POSIX_ACL=y` is mandatory** (the binary vendor media modules read `struct inode` at fixed
   offsets, see the top-level README), XZ-compressed kernel, `CONFIG_IP_PNP` off, USB gadget, Wi-Fi (`CONFIG_MWIFIEX_SDIO`) built in,
   `CONFIG_INITRAMFS_SOURCE` points at the generated list (see below).

## Build

```
# once: build OpenIPC as usual so that output/ (toolchain, target, host) exists, then in output/build/linux-custom:
patch -p1 < kernel/patches/0001-himci-nonremovable-and-rescan.patch
patch -p1 < kernel/patches/0002-cv206-device-tree.patch
cp kernel/config.cv206-final .config            # then set CONFIG_INITRAMFS_SOURCE to the list made below
kernel/initramfs/prepare.sh WORKDIR OPENIPC_OUTPUT SD8801_BLOB   # creates WORKDIR/min-final.list and WORKDIR/min-files/
tools/kbuild.sh                                  # make all + make uImage with the OpenIPC toolchain (not Buildroot linux-rebuild!)
```

The result (`arch/arm/boot/uImage`) must be smaller than the `sys` slot (2,883,584 bytes) and must pass the vendor ioctl test
(`tools/src/chipid.c` prints `0x3518e200`) before it is flashed.

## Initramfs

`initramfs/min-final.list` (gen_init_cpio list, `@INITRAMFS@` is replaced by the work directory) and `initramfs/min-files/init-final`
(`/init`) are ours. Not committed, copied in by `initramfs/prepare.sh`:

- `busybox`, `libc.so` (musl), `libgcc_s.so.1`: from the OpenIPC build output;
- `fw/sd8801_uapsta.bin`: the Marvell Wi-Fi firmware, **not redistributable**: extract it from your own firmware dump
  (the `app_bak` squashfs, file `sd8801_uapsta.bin`).
