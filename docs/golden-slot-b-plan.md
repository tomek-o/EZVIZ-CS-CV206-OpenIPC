# Plan: a known-good image of our own in slot B (first step of removing the stock firmware)

Status: **plan only, nothing has been done.** Every flash write below needs the owner's explicit OK for that step; `bld` (bootloader) and `enc` (device identity) are never touched.

## Why

Today slot B (`sys_bak`, `app_bak`) holds the stock Ezviz firmware and our boot command ends with the stock path:
`bootcmd=${a1};${a2};${a3};bootm 0x82000000;${s1};loadk;bootm 0x80007fc0`.
If our kernel in slot A cannot be started (`bootm` fails), `loadk` runs: it **copies slot B over slot A** (observed on 2026-11-06: it replaced our `sys` and `app` with the stock ones) and then boots the **Ezviz cloud firmware**.
We want that fallback to be a known-good build of *our* firmware instead, so a bad update is repaired by code from this project and the stock cloud firmware never runs. Only afterwards does erasing the stock `cfg` make sense (it holds the stock Wi-Fi and cloud credentials; the stock system could not run without it anyway).

## What we know and what we assume

| Fact | Source |
|---|---|
| `loadk` copies B over A when they differ ("Erasing [app] ... Writing [app]"), then loads B's kernel at `0x80007fc0` | observed 2026-11-06 |
| Slot B's kernel can be booted without `loadk`: `sf read 0x80007fc0 0x320000 0x2c0000` then `bootm 0x80007fc0` | used on 2026-11-06 |
| `bootm` of a bad image returns to the prompt only for header problems (bad magic or header CRC); the environment has `verify=n`, so a damaged **data** part is probably **not** detected (inferred from the variable, not tested) | env dump, README |
| `flash_write.py` can write `sys_bak`/`app_bak` (CRC-checked in RAM, read-back verified, refuses without a verified backup, never `saveenv`) | tool |
| The stock path boots with `${s1}`: `mem=38M console=ttyAMA0,115200` (no `panic=10`) until 2026-11-10, now `mem=36M ... panic=10` like slot A | env |
| **Assumed, not yet tested:** our kernel and app work with `mem=38M` (the media memory then starts at `0x82600000` and is 26 MB instead of 28 MB; 1080p might need 28) | to test in stage 2 |
| **Assumed, not yet tested:** `loadk` repairs A from B when A's header is bad and B holds our image | to test in stage 5 |

Sizes: our kernel 2,731,665 bytes (slot 2,883,584), our app 3,047,424 bytes (slot 4,456,448): both fit slot B.

## The result we aim for

- Slot A = the current release (updated normally, also from the page). Slot B = a proven release (the "golden" copy), identical files at first.
- Normal boot: slot A. If its header is bad: `loadk` repairs A from B and boots B's kernel with the same app. The stock firmware is gone from the boot path.
- Not covered (needs boot-loop protection, `TODO.md` item 2): a kernel that starts and then panics, or an app that does not start. Those loop or hang; the SD-card override (`cv206/app.sqsh`) and the UART still recover them.
- Variant 2 (only if we do not want `loadk`'s repair copy): replace `loadk;bootm 0x80007fc0` in `bootcmd` by `sf read 0x80007fc0 0x320000 0x2c0000;bootm 0x80007fc0`. That needs an `env` change (`saveenv`) and is a separate decision.

## Before anything (stage 0, no camera involved)

1. The full backup is good and kept in a second place offline: `sha256sum -c dump/flash_dump.bin.sha256`; copy `dump/` (private) to another disk. After this plan it is the only copy of the stock firmware.
2. The release images are what we think: `cd _release && sha256sum -c SHA256SUMS`.
3. Make the deliberately broken kernel for stage 5 (first byte changed, so `bootm` reports "Bad Magic Number"): in `build/` (not in git)
   `python3 -c "d=bytearray(open('_release/sys-1.0.0.uImage','rb').read()); d[0]^=0xFF; open('build/bad-magic.uImage','wb').write(d)"`
4. Have the UART adapter connected and `export CV206_SERIAL=...`. Choose the transfer: UART upload (about 5-9 minutes per image) or the SD card route (about 30 seconds; copy the two release files into a folder `cv206/` on a FAT32 card, **not** named `app.sqsh`).
   Close every other program on the serial port; never touch the port while an upload runs.

## Stages

**Stage 1 - read-only look at U-Boot (no writes).** Start `tools/uart_interrupt.py logs/uboot.log` *before* rebooting the camera from the page, stop at `HKVS #`, then
`tools/ubcmd.py "printenv" "help loadk"` and save the `printenv` output as `dump/env_current.txt` (private). Pass: the environment matches README "Flash layout and boot" (`boot_from`, `verify=n`, our `a1..a3`, `s1`, `bootcmd`). Then boot normally (`boot` or power-cycle).

**Stage 2 - can our firmware run with `mem=38M`? (RAM boot, no flash write).** Stop at U-Boot again and boot our release kernel from RAM with the stock path's arguments:
`tools/ramkernel.py _release/sys-1.0.0.uImage "mem=38M console=ttyAMA0,115200" "cv206 init"` (the app comes from slot A as usual). Check over the UART: `cat /proc/cmdline`, the `video-up` line "media memory: start ... size 26M", the streamer is up, `ffprobe rtsp://root:PASS@CAMERA/stream=0` shows 1080p, Wi-Fi and the page work.
Pass: all of that. Fail (for example the encoder runs out of memory): we need `s1` equal to `a1` (`mem=36M ... panic=10`), which is an `env` change (stage 6) - the plan continues, but that step needs its own OK.

**Stage 3 - write the golden image into slot B. NEEDS OK ("write sys_bak and app_bak").** At the U-Boot prompt (or via the SD route with the card inserted):
```
./flash_write.py -p $CV206_SERIAL --partition sys_bak _release/sys-1.0.0.uImage --yes     # add: --from-sd sys-1.0.0.uImage  for the SD route
./flash_write.py -p $CV206_SERIAL --partition app_bak _release/app-1.0.0.sqsh --yes       # add: --from-sd app-1.0.0.sqsh
```
Each run checks that the live slot equals the verified stock backup, CRC-checks the image in RAM, erases, writes and reads back; `dump/flashed_crcs.txt` records it. Pass: both finish with "verified". Fail: the tool stops without guessing; slot A is untouched, the camera boots normally. Undo at any time: `--partition sys_bak --restore --yes` (and `app_bak`) writes the original stock content back from the dump.

**Stage 4 - boot slot B by hand (no writes).** At the prompt, using only unsaved commands:
`setenv bootargs mem=38M console=ttyAMA0,115200` ; `sf probe 0` ; `sf read 0x80007fc0 0x320000 0x2c0000` ; `bootm 0x80007fc0`.
Pass: our firmware starts from slot B's kernel, the page shows the same build, RTSP works (this is the exact kernel path the fallback uses, minus `loadk`'s copy). Then power-cycle (the unsaved `setenv` is gone).

**Stage 5 - the real fallback and self-repair test. NEEDS OK ("write sys with a deliberately broken kernel").** Keep the UART attached and logged (`tools/uart_log.py`).
1. Stop at U-Boot, `./flash_write.py -p $CV206_SERIAL --partition sys build/bad-magic.uImage --yes` (slot A's kernel now has a bad magic number; slot B is fine).
2. Boot with the normal saved `bootcmd` (power-cycle or `boot`). Expected on the console: "Bad Magic Number" from `bootm`, then `loadk` "Erasing [sys] ... Writing [sys]" (B copied to A), then our kernel starts from B, the camera joins Wi-Fi by itself.
3. Pass: the camera is up within about two minutes without any help, and slot A is repaired: `./flash_dump.py -p $CV206_SERIAL sys` and compare its checksum with `_release/sys-1.0.0.uImage` padded with 0xFF (or run `flash_write.py ... --partition sys _release/sys-1.0.0.uImage` and see "live content equals" in its checks).
4. If it stops at the prompt: run the stage 4 commands to boot B, then write slot A normally with `flash_write.py` (release image) - nothing is lost. If it boots B but does not repair A: acceptable, then Variant 2 (above) is the honest description of the behaviour.

**Stage 6 - environment. DONE 2026-11-10 (see Results).** (It was needed: stage 2 showed `mem=38M` breaks motion detection.) Only if stage 2 failed: test `setenv s1 'setenv bootargs mem=36M console=ttyAMA0,115200 panic=10'` unsaved in stage 4 and 5 first, then `saveenv`. First save a copy of the current environment (`printenv` output from stage 1 plus `dump/env_before_change.txt`). Revert: `setenv s1 'setenv bootargs mem=38M console=ttyAMA0,115200'` + `saveenv`.

**Stage 7 - documentation and tools.** README/REFERENCE "Boot" section (the fallback is our golden image), INSTALL (the install writes slot B too: UART/SD routes write `sys_bak`/`app_bak` as well; `tools/make-spi-image.py` gets an option that puts the same images into slot B), `TODO.md`, the safety rules. Later: a "make this release the golden copy" button/tool (copy A to B after a release has proven itself).

**Stage 8 - erase `cfg` (separate decision, later).** After stages 1-7 have passed and the camera has run for a while: at the prompt `sf probe 0; sf erase 0xe60000 0x100000`, read back to check it is blank (`sf read` + `crc32`), keep the dump. The stock firmware cannot run afterwards. `flash_write.py` refuses `cfg` by design, so this is a deliberate manual step with its own OK.

## Results so far (2026-11-10)

- **Stage 1 passed:** the environment is as documented (`a1..a3`, `s1`, `bootcmd`, `boot_from=PART_BKUP`, `verify=n`, `app_verify=y`); `help loadk` says nothing more. Saved as `dump/env_current.txt` (private, contains the MAC). New: `update_source=sd`, `update_flag=update_` and the boot log line `reading ezviz.dav` (the stock U-Boot's update-from-SD path).
- **Stage 2 partly failed, which is the useful result:** our release booted from RAM with the stock path's `mem=38M`: Wi-Fi, page and 1080p video all fine (same packet rate as with `mem=36M`), but the media memory is 26 MB (VB pool of 3 blocks instead of 5) and
  **motion detection fails** (`HI_ERR_IVE_NOMEM`, `Cannot create MD chn 0`). Nothing was written to flash; the camera was rebooted to its normal boot afterwards and motion detection starts again.
- **Stage 3 DONE (2026-11-10, owner approved, SD route):** the two release files were copied onto the card in `cv206/` through the camera (checksums on the camera equal `_release/SHA256SUMS`), the card was ejected from the page, U-Boot was stopped, and `flash_write.py --from-sd` wrote
  `sys_bak` (read-back CRC `5fa6aec5`, the same as our slot-A kernel) and `app_bak` (read-back CRC `54eba50d` for the padded app image); the tool had first confirmed that both slots still equalled the verified stock backup (CRCs `cea78227`, `2438e439`). Slot B on this camera is now our release; the stock slot-B images exist only in `dump/flash_dump.bin`
  (restore with `flash_write.py --partition sys_bak --restore` / `app_bak`). Afterwards the camera was reset and booted normally from slot A (nothing in slot A was touched).
- **Stage 6 DONE (2026-11-10, owner approved):** `s1` is now `setenv bootargs mem=36M console=ttyAMA0,115200 panic=10` (same as `a1`), saved with `saveenv` (U-Boot erased and rewrote the 64 KB environment sector); after `reset` the camera booted our firmware from flash, and reading the environment partition from Linux shows `s1`, `a1`, `a3`, `bootcmd`, `boot_from`, `verify` as intended. Everything else in the environment is unchanged. Revert: `setenv s1 'setenv bootargs mem=38M console=ttyAMA0,115200'` + `saveenv`. (The first attempt on the same day was interrupted at the `saveenv` step at the owner's request and saved nothing.)
- **Consequence (decided):** the fallback must not use `mem=38M`. Either `s1` becomes `mem=36M console=ttyAMA0,115200 panic=10` (stage 6, an `env` change, needs the owner's OK) or Variant 2 boots slot B with the same arguments as slot A. Stage 6 has therefore been done first; stages 3-5 now test the fallback with the final arguments.
- **Later the same day (owner approved `mem=35M`): `a1` and `s1` are now `setenv bootargs mem=35M console=ttyAMA0,115200 panic=10`.** Reason: with `mem=36M` (28 MB media memory) a motion-recording camera with the on-screen display left only 3992 KB after start-up and the first snapshot failed (`ERR_VENC_NOMEM`); `mem=35M` leaves 5016 KB. A RAM-only boot with 35M came first, then `saveenv` (previous environment: `dump/env_before_mem35.txt`), then a reset: the camera booted by itself. Slot B was not rewritten (it is the same kernel, the arguments come from the environment).
- **Stage 7 done (docs and tools):** README, REFERENCE, INSTALL and the changelog describe slot B as our copy; the UART and SD routes write `sys_bak` and `app_bak` too; `tools/make-spi-image.py` writes slot B (tested on the host, not on a camera).

## What can go wrong

| Risk | Effect | Mitigation |
|---|---|---|
| Power loss while writing slot B (stage 3) | slot B incomplete; slot A still boots | repeat stage 3; only the fallback is weaker meanwhile |
| Power loss while writing slot A (stage 5) | slot A bad; slot B holds the golden image | boots through `loadk`/stage 4 commands, then rewrite A |
| `mem=38M` does not work with our kernel | the fallback boots but video fails | stage 2 finds it before any write; stage 6 |
| `loadk` does not behave as assumed | no automatic repair | stage 5 tells us; Variant 2 |
| The golden copy is an old release | an old-but-working system after a failure | update B deliberately after a release has proven itself |
| A kernel that starts and then panics, or a broken app | loops or hangs (not a `bootm` failure) | not solved here: boot-loop protection (`TODO.md` item 2); SD override and UART recover |
| Mistyped command at the prompt | wrong region written | all writes go through `flash_write.py` (only `sys`, `sys_bak`, `app`, `app_bak`); the manual commands in stages 4-5 only read |

## What the owner has to do

Be present for stages 1-5 (about an hour in total), keep the UART connected, power-cycle the camera when asked, and (SD route) move the card between the camera and the PC. Three explicit approvals are needed: stage 3, stage 5, and (only if required) stage 6; stage 8 later.
