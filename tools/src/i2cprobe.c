/* SPDX-License-Identifier: GPL-2.0-or-later */
/* i2cprobe BUS ADDR8 REG [COUNT]: HiSilicon i2c-hisilicon wants the 8-bit device address in msg.addr.
   Reads COUNT registers starting at REG (one single-read message each). */
#include <stdio.h>
#include <stdlib.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <linux/i2c.h>
#include <linux/i2c-dev.h>
int main(int argc, char **argv) {
    if (argc < 4) { fprintf(stderr, "usage: i2cprobe BUS ADDR8 REG [COUNT]\n"); return 1; }
    char dev[32]; snprintf(dev, sizeof dev, "/dev/i2c-%s", argv[1]);
    int fd = open(dev, O_RDWR); if (fd < 0) { perror(dev); return 2; }
    unsigned addr = strtoul(argv[2], 0, 0), reg = strtoul(argv[3], 0, 0);
    int n = argc > 4 ? atoi(argv[4]) : 1;
    for (int i = 0; i < n; i++) {
        unsigned char buf[2] = { reg + i, 0 };
        struct i2c_msg m = { .addr = addr, .flags = I2C_M_RD, .len = 1, .buf = buf };
        struct i2c_rdwr_ioctl_data d = { .msgs = &m, .nmsgs = 1 };
        if (ioctl(fd, I2C_RDWR, &d) < 0) { printf("reg 0x%02x: ERR\n", reg + i); continue; }
        printf("reg 0x%02x: 0x%02x\n", reg + i, buf[0]);
    }
    return 0;
}
