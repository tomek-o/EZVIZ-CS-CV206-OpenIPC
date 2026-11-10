/* SPDX-License-Identifier: GPL-2.0-or-later */
/* i2cwr BUS ADDR8 FILE: write "reg val" hex pairs (one per line) to a HiSilicon i2c bus (8-bit address in msg.addr) */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <linux/i2c.h>
#include <linux/i2c-dev.h>
int main(int argc,char**argv){
  if(argc<4){fprintf(stderr,"usage: i2cwr BUS ADDR8 FILE\n");return 1;}
  char dev[32]; snprintf(dev,sizeof dev,"/dev/i2c-%s",argv[1]);
  int fd=open(dev,O_RDWR); if(fd<0){perror(dev);return 2;}
  unsigned addr=strtoul(argv[2],0,0); FILE*f=fopen(argv[3],"r"); if(!f){perror("file");return 3;}
  char line[128]; int n=0,bad=0;
  while(fgets(line,sizeof line,f)){
    if(line[0]=='#') continue; unsigned r,v; if(sscanf(line,"%i %i",&r,&v)!=2) continue;
    unsigned char b[2]={r,v}; struct i2c_msg m={.addr=addr,.flags=0,.len=2,.buf=b};
    struct i2c_rdwr_ioctl_data d={.msgs=&m,.nmsgs=1};
    if(ioctl(fd,I2C_RDWR,&d)<0) bad++; n++; usleep(2000);
  }
  printf("wrote %d regs, %d errors\n",n,bad); return 0; }
