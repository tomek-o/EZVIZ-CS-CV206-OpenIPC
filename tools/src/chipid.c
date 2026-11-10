/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <stdio.h>
#include <fcntl.h>
#include <errno.h>
#include <string.h>
#include <sys/ioctl.h>
int main(void){
  int fd=open("/dev/sys",O_RDWR); if(fd<0){perror("open /dev/sys");return 1;}
  unsigned id=0; int r=ioctl(fd,0x8004590f,&id);
  printf("ioctl ret %d errno %d (%s) id 0x%x\n",r,errno,strerror(errno),id);
  return 0; }
