#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Test client for the ONVIF RTSP audio back-channel: send a raw G.711 u-law (8 kHz mono) file to the camera's speaker.
usage: rtsp_talk.py HOST USER PASSWORD FILE.ulaw   (make a tone: ffmpeg -f lavfi -i sine=frequency=800:duration=2:sample_rate=8000 -ar 8000 -ac 1 -f mulaw tone.ulaw)"""
import base64, random, re, socket, struct, sys, time
host, user, pw, path = sys.argv[1:5]
data = open(path, "rb").read()
s = socket.create_connection((host, 554), timeout=8)
auth = base64.b64encode(f"{user}:{pw}".encode()).decode()
cseq = [0]; sess = [None]
def rtsp(method, url, extra=""):
    cseq[0] += 1
    h = f"{method} {url} RTSP/1.0\r\nCSeq: {cseq[0]}\r\nRequire: www.onvif.org/ver20/backchannel\r\nAuthorization: Basic {auth}\r\n" + (f"Session: {sess[0]}\r\n" if sess[0] else "") + extra + "\r\n"
    s.send(h.encode()); time.sleep(0.6)
    r = s.recv(16384).decode(errors="replace")
    m = re.search(r"Session:\s*([^;\r\n]+)", r)
    if m: sess[0] = m.group(1).strip()
    print(method, r.split("\r\n")[0]); return r
base = f"rtsp://{host}/stream=0"
rtsp("DESCRIBE", base, "Accept: application/sdp\r\n")
r = rtsp("SETUP", base + "/audio-backchannel", "Transport: RTP/AVP/TCP;unicast;interleaved=0-1;mode=record\r\n")
if "200 OK" not in r: print(r); sys.exit(1)
r = rtsp("PLAY", base, "Range: npt=0.000-\r\n")
ssrc = random.getrandbits(32); seq = random.getrandbits(16); ts = random.getrandbits(32)
t0 = time.time()
for i in range(0, len(data) - 159, 160):
    pkt = struct.pack("!BBHII", 0x80, 0, seq & 0xFFFF, ts & 0xFFFFFFFF, ssrc) + data[i:i + 160]
    s.send(b"$" + struct.pack("!BH", 0, len(pkt)) + pkt)
    seq += 1; ts += 160
    time.sleep(max(0, t0 + (i // 160 + 1) * 0.02 - time.time()))
time.sleep(0.5)
rtsp("TEARDOWN", base)
print("sent", len(data), "bytes")
