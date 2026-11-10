# Installing the firmware on an Ezviz CS-CV206

This replaces the Ezviz firmware with the open firmware of this project. **You do this at your own risk**: a wrong write can leave the camera unbootable
(it can then only be recovered with an SPI programmer). The procedure is built so that you always hold a verified backup first. It writes our images to both firmware slots,
so the original Ezviz firmware is **no longer in the flash afterwards**: it exists only in your backup (see "Going back to the stock firmware").

The firmware needs three ingredients that this repository deliberately does **not** contain, because they are proprietary or personal:
the Marvell Wi-Fi firmware, the closed `majestic` streamer with the HiSilicon media modules, and your device's own data (MAC address, serial number, credentials).
You either use the images from a release package of this project (next section) or build them yourself from your own flash dump and the OpenIPC build tree: see [BUILDING.md](BUILDING.md).

## What you need

- the camera (model `CS-CV206-C0-3B2WFR-Pro`, Hi3518EV200, 16 MB SPI flash, Marvell SD8801 Wi-Fi) and a way to power it
- a 3.3 V USB-UART adapter (CP2102 or similar) on the camera's UART pads, 115200 8N1 (pads: https://www.tomeko.net/reviews/Ezviz_CS-CV206_camera);
- a Linux PC with Python 3, `lrzsz` (`sz`), `squashfs-tools` (this repository's tools)
- this repository and the two images (`sys` kernel image, `app` squashfs): from a release package or built by you

## The images: release package or your own build

A release consists of these files (non-commercial use only, see `THIRD-PARTY.md`):

| File | What |
|---|---|
| `cv206-open-firmware-1.0.0.tar.xz` | the package you need: the two images, `README.txt`, `INSTALL.md`, `THIRD-PARTY.md`, `LICENSE`, `licenses/` and `SHA256SUMS` |
| `cv206-open-firmware-1.0.0-source.tar.xz` | the matching source of the GPL parts (kernel, BusyBox, wireless tools, this project, the OpenIPC build system); you do not need it to install |
| `cv206-open-firmware-1.0.0.SHA256SUMS` | checksums of the two archives |

```
sha256sum -c cv206-open-firmware-1.0.0.SHA256SUMS --ignore-missing      # the downloaded archive(s) must say OK
tar -xJf cv206-open-firmware-1.0.0.tar.xz                              # makes the folder cv206-open-firmware-1.0.0/
(cd cv206-open-firmware-1.0.0 && sha256sum -c SHA256SUMS)              # sys-1.0.0.uImage and app-1.0.0.sqsh: OK
```

Use `sys-1.0.0.uImage` and `app-1.0.0.sqsh` from that folder wherever this guide says `sys.bin` and `app.sqsh`. They are release images: no Wi-Fi network and no password yet (see "First start").
The images contain proprietary parts (Marvell Wi-Fi firmware, `majestic`, HiSilicon libraries) that this repository does not: keep the license files that come with them. If you prefer to build everything yourself, follow [BUILDING.md](BUILDING.md).

Never write the regions `bld` (bootloader), `enc` (device identity: model, serial, MAC) or `cfg` (stock configuration, credentials). The tools here refuse to.

## Step 0: make and verify a backup (always)

Connect the UART, stop the camera at the U-Boot prompt (`HKVS #`: press Ctrl+U within 2 seconds of power-on), close any terminal program, then:

```
./flash_dump.py -p /dev/ttyUSB0 --include-cfg all        # reads every 64 KB chunk twice-checked against U-Boot's CRC; resumable; read-only
./flash_dump.py --assemble                               # dump/flash_dump.bin (16 MiB) + .sha256
```

Keep `dump/` private (mode 0700): it contains your MAC, serial number and the stock credentials. With an SPI programmer (untested): `flashrom -p ch341a_spi -r a.bin; flashrom -p ch341a_spi -r b.bin; cmp a.bin b.bin`
(read twice, the two reads must be identical).

Set the serial port for the other tools once: `export CV206_SERIAL=/dev/ttyUSB0` (or a `/dev/serial/by-id/...` path; the number behind `ttyUSB` can change at every power-cycle).

## Route A: UART (slow, about 15 minutes per region)

1. Have the two images ready (release package or BUILDING.md): `sys.bin` (uImage, at most 2,883,584 bytes) and `app.sqsh`.
2. Stop at U-Boot. Write the kernel and the app image to slot A, then the same two files to slot B, one region at a time. Each write is CRC-checked in RAM before anything is erased and read back afterwards:
   ```
   ./flash_write.py -p $CV206_SERIAL --partition sys sys.bin --yes
   ./flash_write.py -p $CV206_SERIAL --partition app app.sqsh --yes
   ./flash_write.py -p $CV206_SERIAL --partition sys_bak sys.bin --yes
   ./flash_write.py -p $CV206_SERIAL --partition app_bak app.sqsh --yes
   ```
   (They refuse to run without a matching backup, and they only touch `sys`, `app` and the two slot B regions.) Slot B is the copy that the boot command falls back to; leaving the stock firmware there would start the Ezviz cloud firmware if ours ever fails to boot.
3. Change the boot command (a one-time U-Boot environment change). Type slowly, the console drops fast input;
   `tools/ubcmd.py` does it for you:
   ```
   tools/ubcmd.py "setenv a1 'setenv bootargs mem=35M console=ttyAMA0,115200 panic=10'" "setenv a2 'sf probe 0'" \
      "setenv a3 'sf read 0x82000000 0x60000 0x2c0000'" "setenv s1 'setenv bootargs mem=35M console=ttyAMA0,115200 panic=10'" \
      "setenv bootcmd '\${a1};\${a2};\${a3};bootm 0x82000000;\${s1};loadk;bootm 0x80007fc0'" "saveenv"
   ```
   This U-Boot has no `run` and a 128-character input line, hence the short variables. Slot A is tried first; if its kernel fails to start, the bootloader copies slot B over slot A (`loadk`) and boots that.
4. `reset`, or power-cycle. Continue at "First start".

## Route B: SD card (fast: about 20 seconds per region)

Copy `sys.bin` and `app.sqsh` into a folder named `cv206` on a FAT32 card (first partition), put the card into the camera, stop at U-Boot, and write from the card.
The local file is still given: the tool compares its CRC with what U-Boot read from the card, and only then erases and writes (slot A, then the same files into slot B):
```
./flash_write.py -p $CV206_SERIAL --partition sys sys.bin --from-sd sys.bin --yes
./flash_write.py -p $CV206_SERIAL --partition app app.sqsh --from-sd app.sqsh --yes
./flash_write.py -p $CV206_SERIAL --partition sys_bak sys.bin --from-sd sys.bin --yes
./flash_write.py -p $CV206_SERIAL --partition app_bak app.sqsh --from-sd app.sqsh --yes
```
Then change the boot command as in Route A, step 3.

## Another possibility: an SPI programmer (not tested)

Programming the flash chip directly (for example a CH341A with `flashrom`) should also work, and `tools/make-spi-image.py` can build a complete 16 MiB image from your own dump
(`make --dump dump/flash_dump.bin --sys sys.bin --app app.sqsh --out image.bin`, then `verify`; it changes only `sys`, `app`, slot B and the boot command, everything else is byte-for-byte your dump).
**None of this was tried on a real camera**: the image tool was only run on the PC. In-circuit programming with a clip often fails on boards like this one, so the chip may have to be desoldered. `image.bin` contains your MAC, serial number and credentials: never share it.

## First start

The first start takes about a minute. (Later updates need no cable: set a password, then use System, Firmware update on the page.) With the release image there is no Wi-Fi network and no password yet, so the camera makes its own network:

1. Join the Wi-Fi network `cv206-XXXX` (the last digits of the camera's MAC), password `cv206setup`.
2. Open `http://192.168.4.1`. The page is open (a yellow banner warns that no password is set). Set a **password** (device and security) and your **Wi-Fi network** (Wi-Fi), then Save.
3. The camera joins your network; find it by its name (`cv206.local`, `openipc.local`) or in your router. Sign in as user `root` with your password.
   The video is at `rtsp://IP/stream=0` (the page lists all addresses).

Status LED (blue): short double flash every 2 s = connected; 1 s on/off = access point mode; fast blinking = no network. Reset button: hold 5 s = delete the settings and start over
(LED flashing, three beeps, reboot). Details: REFERENCE.md.

## Going back to the stock firmware

The original firmware is only in your backup (`dump/flash_dump.bin`), because slot B holds our images too. Going back means writing the backup's regions again:

- With an SPI programmer (untested): write the original `dump/flash_dump.bin` back with `flashrom -w`.
- Over the UART: restore each of `sys`, `sys_bak`, `app` and `app_bak` from the backup with `flash_write.py --partition NAME --restore --yes` (**not tested** with stock content), then restore the original boot command at the U-Boot prompt:
  `setenv bootcmd 'loadk;bootm 0x80007fc0'` and `saveenv` (and the original `a1` and `s1` values from your saved `env`). Restore slot B before changing the boot command: the stock `loadk` copies slot B over slot A at every boot.

## If something does not work

- No Wi-Fi network appears after a few minutes: connect the UART (115200 8N1) and read the boot messages; the kernel messages end with `cv206 init` and the `rc` output.
- The camera restarts in a loop: it falls back to nothing by itself yet (boot-loop protection is not implemented): stop at U-Boot (Ctrl+U) and restore the boot command as above.
- Anything else: REFERENCE.md has the technical notes and the list of pitfalls we hit.
