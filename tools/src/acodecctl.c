/* SPDX-License-Identifier: GPL-2.0-or-later */
/* acodecctl: control the internal HiSilicon audio codec (/dev/acodec). Usage: acodecctl dump | CMD VALUE ...
 * CMD: fs (8000|16000|32000|48000) mixer (in|ind) micgain N adcvol N dacvol N micmute 0|1 dacmute 0|1 pdadc 0|1 pddac 0|1 */
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>
#include "acodec.h"
static int fd;
static void get(const char *n, unsigned long c)
{ unsigned int v = 0xdead; int r = ioctl(fd, c, &v); printf("%s = %u (0x%x)%s\n", n, v, v, r ? " [ioctl failed]" : ""); }
static void getv(const char *n, unsigned long c)
{ ACODEC_VOL_CTRL v = {0xdead, 0xdead}; int r = ioctl(fd, c, &v); printf("%s = vol %u mute %u%s\n", n, v.vol_ctrl, v.vol_ctrl_mute, r ? " [ioctl failed]" : ""); }
int main(int argc, char **argv)
{
    fd = open("/dev/acodec", O_RDWR);
    if (fd < 0) { perror("/dev/acodec"); return 1; }
    if (argc < 2 || !strcmp(argv[1], "dump")) {
        get("micl gain", ACODEC_GET_GAIN_MICL); get("micr gain", ACODEC_GET_GAIN_MICR);
        getv("adcl", ACODEC_GET_ADCL_VOL); getv("adcr", ACODEC_GET_ADCR_VOL); getv("dacl", ACODEC_GET_DACL_VOL); getv("dacr", ACODEC_GET_DACR_VOL);
        return 0;
    }
    for (int i = 1; i + 1 < argc; i += 2) {
        const char *c = argv[i], *a = argv[i + 1]; unsigned int v = strtoul(a, NULL, 0); int r = 0;
        if (!strcmp(c, "fs")) { v = v == 8000 ? ACODEC_FS_8000 : v == 16000 ? ACODEC_FS_16000 : v == 32000 ? ACODEC_FS_32000 : ACODEC_FS_48000; r = ioctl(fd, ACODEC_SET_I2S1_FS, &v); }
        else if (!strcmp(c, "mixer")) { v = !strcmp(a, "ind") ? ACODEC_MIXER_IN_D : ACODEC_MIXER_IN; r = ioctl(fd, ACODEC_SET_MIXER_MIC, &v); }
        else if (!strcmp(c, "micgain")) { r = ioctl(fd, ACODEC_SET_GAIN_MICL, &v); r |= ioctl(fd, ACODEC_SET_GAIN_MICR, &v); }
        else if (!strcmp(c, "adcvol")) { ACODEC_VOL_CTRL x = {v, 0}; r = ioctl(fd, ACODEC_SET_ADCL_VOL, &x); r |= ioctl(fd, ACODEC_SET_ADCR_VOL, &x); }
        else if (!strcmp(c, "dacvol")) { ACODEC_VOL_CTRL x = {v, 0}; r = ioctl(fd, ACODEC_SET_DACL_VOL, &x); r |= ioctl(fd, ACODEC_SET_DACR_VOL, &x); }
        else if (!strcmp(c, "micmute")) { r = ioctl(fd, ACODEC_SET_MICL_MUTE, &v); r |= ioctl(fd, ACODEC_SET_MICR_MUTE, &v); }
        else if (!strcmp(c, "dacmute")) { r = ioctl(fd, ACODEC_SET_DACL_MUTE, &v); r |= ioctl(fd, ACODEC_SET_DACR_MUTE, &v); }
        else if (!strcmp(c, "pdadc")) { r = ioctl(fd, ACODEC_SET_PD_ADCL, &v); r |= ioctl(fd, ACODEC_SET_PD_ADCR, &v); }
        else if (!strcmp(c, "pddac")) { r = ioctl(fd, ACODEC_SET_PD_DACL, &v); r |= ioctl(fd, ACODEC_SET_PD_DACR, &v); }
        else { fprintf(stderr, "unknown command %s\n", c); return 2; }
        printf("%s %s: %s\n", c, a, r ? "FAILED" : "ok");
    }
    return 0;
}
