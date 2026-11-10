/* SPDX-License-Identifier: GPL-2.0-or-later */
/* LD_PRELOAD shim: majestic asks libmpi for the SoC id with an ioctl that this
   hi3518e_sys.ko does not implement; the id register (0x20050ee0) itself reads as Hi3518EV200. */
unsigned int HI_MPI_SYS_GetChipId(unsigned int *id) { if (!id) return 0xa0028006; *id = 0x3518e200; return 0; }
