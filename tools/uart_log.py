# SPDX-License-Identifier: GPL-2.0-or-later
"""Passive UART logger: usage uart_log.py OUTFILE SECONDS. Sends nothing."""
import os, sys, time, termios, select
fd=os.open("/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0",os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK)
a=termios.tcgetattr(fd); a[0]=0;a[1]=0;a[3]=0; a[2]=termios.CS8|termios.CREAD|termios.CLOCAL
a[4]=a[5]=termios.B115200; a[6][termios.VMIN]=0;a[6][termios.VTIME]=0; termios.tcsetattr(fd,termios.TCSANOW,a)
out=open(sys.argv[1],"ab",buffering=0); end=time.time()+int(sys.argv[2])
while time.time()<end:
    if select.select([fd],[],[],0.2)[0]:
        try: out.write(os.read(fd,4096))
        except BlockingIOError: pass
