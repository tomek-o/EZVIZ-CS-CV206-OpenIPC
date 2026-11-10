# SPDX-License-Identifier: GPL-2.0-or-later
"""From the U-Boot prompt: upload the kernel to RAM (loady), verify CRC, boot with our usual args. Writes nothing to flash."""
import os, re, sys, time, termios, select, subprocess, zlib
PORT = os.environ.get("CV206_SERIAL", "/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0"); ADDR=0x82000000; P=b"HKVS # "
IMG=sys.argv[1]; BARGS=sys.argv[2] if len(sys.argv)>2 else "mem=35M console=ttyAMA0,115200 panic=10"; WAIT=sys.argv[3].encode() if len(sys.argv)>3 else b"first stage"; data=open(IMG,"rb").read(); crc=zlib.crc32(data)&0xffffffff
def setraw(fd,nb):
    a=termios.tcgetattr(fd); a[0]=0;a[1]=0;a[3]=0
    a[2]=termios.CS8|termios.CREAD|termios.CLOCAL; a[4]=a[5]=termios.B115200
    a[6][termios.VMIN]=0 if nb else 1; a[6][termios.VTIME]=0; termios.tcsetattr(fd,termios.TCSANOW,a)
def rd(fd,pred,t):
    b=b"";s=time.time()
    while time.time()-s<t:
        if select.select([fd],[],[],0.1)[0]:
            try: b+=os.read(fd,65536)
            except BlockingIOError: pass
        if pred(b): break
    return b
fd=os.open(PORT,os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK); setraw(fd,True)
os.write(fd,b"\r"); rd(fd,lambda b:b.endswith(P),3)
os.write(fd,("loady 0x%x\r"%ADDR).encode()); rd(fd,lambda b:b"download" in b.lower(),5); os.close(fd)
bfd=os.open(PORT,os.O_RDWR|os.O_NOCTTY); setraw(bfd,False)
t=time.time(); p=subprocess.run(["sz","--ymodem",IMG],stdin=bfd,stdout=bfd,stderr=subprocess.DEVNULL); os.close(bfd)
print("sz rc",p.returncode,"%.0fs"%(time.time()-t),flush=True)
fd=os.open(PORT,os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK); setraw(fd,True); rd(fd,lambda b:b.endswith(P),15)
os.write(fd,("crc32 0x%x 0x%x\r"%(ADDR,len(data))).encode()); o=rd(fd,lambda b:b.endswith(P),20).decode(errors="replace")
m=re.search(r"==> ([0-9a-f]{8})",o); print("crc",m and m.group(1),"want %08x"%crc,flush=True)
if not m or int(m.group(1),16)!=crc: sys.exit(2)
os.write(fd,("setenv bootargs "+BARGS+"\r").encode()); rd(fd,lambda b:b.endswith(P),3)
os.write(fd,b"bootm 0x82000000\r")
b=rd(fd,lambda b:WAIT in b and b.rstrip().endswith(b"#") and b"Starting kernel" in b,90); open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ramkernel_boot.log"),"wb").write(b); print("booted" if WAIT in b else "NO SHELL",flush=True)
