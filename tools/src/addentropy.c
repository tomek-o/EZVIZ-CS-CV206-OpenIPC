/* SPDX-License-Identifier: GPL-2.0-or-later */
/* addentropy: credit 256 bytes from /dev/urandom (the CRNG is initialised at that point) to the /dev/random pool.
 * This camera's pool stays almost empty and wpa_supplicant (AP mode) refuses the first WPA handshake while /dev/random would block. */
#include <fcntl.h>
#include <linux/random.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>
int main(void)
{
    struct { struct rand_pool_info i; unsigned char b[256]; } p;
    int u = open("/dev/urandom", O_RDONLY), r = open("/dev/random", O_RDWR);
    if (u < 0 || r < 0 || read(u, p.b, sizeof p.b) != (ssize_t)sizeof p.b) { perror("addentropy"); return 1; }
    p.i.buf_size = sizeof p.b; p.i.entropy_count = sizeof p.b * 8;
    if (ioctl(r, RNDADDENTROPY, &p.i) != 0) { perror("RNDADDENTROPY"); return 1; }
    return 0;
}
