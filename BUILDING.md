# Building the firmware images

You build two images yourself: **`sys`** (the kernel image, a uImage of at most 2,883,584 bytes) and **`app`** (a squashfs of at most 4,456,448 bytes).
They contain proprietary parts (the Marvell Wi-Fi firmware, `majestic`, the HiSilicon media modules) that this repository does not include and that you must not redistribute;
the Wi-Fi firmware comes from your own camera's dump. Installation of the result: [INSTALL.md](INSTALL.md).

Everything below uses paths relative to this repository. The location of the OpenIPC tree goes into `local.env` (not in git; read by the shell build scripts, see `tools/common.sh`):

```
OPENIPC_DIR=$HOME/openipc-cv206        # contains firmware/ (the OpenIPC clone) and later firmware/output/
```
The UART adapter for the Python flashing tools is set in your shell: `export CV206_SERIAL=/dev/serial/by-id/...`.

## Host requirements

Linux PC, Python 3, `git`, `curl`, `make`, `gcc`, `bc`, `bison`, `flex`, `libssl-dev` (a normal Buildroot/kernel build host), `squashfs-tools` (`mksquashfs`, `unsquashfs`),
`lrzsz` (`sz`, for UART uploads), optionally `flashrom` (SPI route) and `node` (only to syntax-check the web page). The first OpenIPC build takes a few hours and several GB.

## 1. Your flash dump

You need `dump/flash_dump.bin` (INSTALL.md, step 0): it is the source of the Wi-Fi firmware, of the stock firmware (kept only in your backup), and of your device identity.
```
tools/extract-wifi-blob.sh dump/flash_dump.bin build/sd8801_uapsta.bin      # 237,120 bytes
```

## 2. The OpenIPC tree (toolchain, BusyBox, `wpa_supplicant`, `majestic`, media modules)

```
git clone https://github.com/OpenIPC/firmware.git $OPENIPC_DIR/firmware
cd $OPENIPC_DIR/firmware && git checkout ba8647a            # the commit this project was built and tested with (2026-11-06)
echo 'BR2_PACKAGE_WPA_SUPPLICANT_AP_SUPPORT=y' >> br-ext-chip-hisilicon/configs/hi3518ev200_lite_defconfig    # our single Buildroot change: access point mode
make BOARD=hi3518ev200_lite                                  # output/ = toolchain, target, staging, images
```
Everything else is OpenIPC's stock `hi3518ev200_lite` configuration (it already contains `wpa_supplicant`, wireless tools, BusyBox with `httpd`/`udhcpd`/`ntpd`).
Without the AP option the setup access point does not work (`wpa_supplicant` answers "AP mode support not included in the build").

## 3. The kernel image (`sys`)

Details and the reasons for each change are in [kernel/README.md](kernel/README.md). In short:
```
cd $OPENIPC_DIR/firmware/output/build/linux-custom
patch -p1 < <repo>/kernel/patches/0001-himci-nonremovable-and-rescan.patch
patch -p1 < <repo>/kernel/patches/0002-cv206-device-tree.patch
cp <repo>/kernel/config.cv206-final .config                       # then set CONFIG_INITRAMFS_SOURCE to the list made next
<repo>/kernel/initramfs/prepare.sh WORKDIR $OPENIPC_DIR/firmware/output <repo>/build/sd8801_uapsta.bin
<repo>/tools/kbuild.sh                                           # make all + make uImage; do NOT use Buildroot's linux-rebuild (it re-merges the config)
```
The result is `arch/arm/boot/uImage`. **`CONFIG_FS_POSIX_ACL=y` must stay on** (the binary vendor media modules read `struct inode` at fixed offsets). Before flashing, the kernel must pass the vendor ioctl test:
`tools/src/chipid.c` (cross-compile it, run it on the camera from a RAM-booted test image) must print `0x3518e200`.

## 4. The app image (`app`)

```
tools/build-helpers.sh                    # cross-compiles tools/src/* (settings tool, helpers) with OpenIPC's toolchain into app/
tools/make-app-tree.sh                    # build/app-tree: 82 files (majestic, media modules, libraries) copied from OPENIPC output/target, listed in tools/app-tree.manifest
RELEASE=1 tools/mkapp.sh app.sqsh         # the release image: no baked-in Wi-Fi network or password (first start = setup access point)
```
`tools/mkapp.sh` without `RELEASE=1` makes a development image that bakes in the test Wi-Fi network and password from `.hotspot.private` (a private file with `SSID=`, `PASS=`, `RTSPPASS=`; not in git).
The version (`VERSION`) is stamped into `/app/etc/build.txt` and shown on the page.

## 5. Flash

INSTALL.md: UART, SD card, (untested: SPI programmer with `tools/make-spi-image.py`), or (once the camera runs this firmware and has a password) over Wi-Fi: upload the file on the page (System, Firmware update) or `tools/wupdate.sh app app.sqsh`.

## What was verified, and what was not

Verified on the real camera and the real dump (2026-11-10):
- the app tree built by `tools/make-app-tree.sh` from the OpenIPC output equals the hand-made tree that runs on the camera (apart from two unused sensor files and one IQ file that is a symlink instead of a copy), and an image built from it has the same file list;
- `tools/make-spi-image.py` on the real dump: the environment block rebuilt without changes is byte-identical to the original, the generated `sys` region has the CRC recorded when the same image was flashed over UART, and all regions except `env`/`sys`/`app` are identical to the dump;
- `tools/extract-wifi-blob.sh` extracts the 237,120-byte firmware from the dump.

**Not verified from a clean machine:** a full OpenIPC rebuild from scratch (the OpenIPC tree here was built once and extended), `kernel/initramfs/prepare.sh` from a clean checkout, and the upstream kernel source:
Buildroot downloads a **branch** archive (`openipc/linux`, branch `hisilicon-hi3516cv200`) that can change over time, so a rebuild later may differ from ours (kernel 4.9.37 on 2026-11-06).
If you rebuild and something differs, compare with `kernel/config.openipc-orig` and the patches.
