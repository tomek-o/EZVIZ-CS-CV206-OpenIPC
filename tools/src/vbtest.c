/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <stdio.h>
#include <string.h>
typedef struct { unsigned blk, cnt; char mmz[16]; } POOL;
typedef struct { unsigned maxpool; POOL pool[16]; } VBCONF;
extern int HI_MPI_VB_SetConf(VBCONF*), HI_MPI_VB_Init(void), HI_MPI_VB_Exit(void), HI_MPI_SYS_Exit(void), HI_MPI_SYS_Init(void), HI_MPI_SYS_SetConf(void*);
typedef struct { unsigned align; } MPPCFG;
int main(void){
  printf("SYS_Exit 0x%x VB_Exit 0x%x\n", HI_MPI_SYS_Exit(), HI_MPI_VB_Exit());
  VBCONF c; memset(&c,0,sizeof c); c.maxpool=1; c.pool[0].blk=3110400; c.pool[0].cnt=3;
  printf("SetConf 0x%x\n", HI_MPI_VB_SetConf(&c));
  printf("VB_Init 0x%x\n", HI_MPI_VB_Init());
  MPPCFG m={64}; printf("SYS_SetConf 0x%x\n", HI_MPI_SYS_SetConf(&m));
  printf("SYS_Init 0x%x\n", HI_MPI_SYS_Init());
  return 0; }
