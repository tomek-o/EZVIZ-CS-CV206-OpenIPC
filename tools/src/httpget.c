/* SPDX-License-Identifier: GPL-2.0-or-later */
#define _GNU_SOURCE
/* httpget HOST PORT PATH USER PASSWORD [--ct]  -- with --ct the upstream Content-Type is printed first as a CGI header (for streams); HTTP/1.0 GET with Basic auth, body to stdout; exit 0 only on status 200.
   Used by the web page's snapshot CGI to read majestic's /image.jpg (BusyBox wget hangs on its keep-alive replies). */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <netinet/in.h>
#include <arpa/inet.h>

static void b64(const unsigned char *in, int n, char *out) {
    static const char t[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    int o = 0;
    for (int i = 0; i < n; i += 3) {
        unsigned v = in[i] << 16 | (i + 1 < n ? in[i + 1] << 8 : 0) | (i + 2 < n ? in[i + 2] : 0);
        out[o++] = t[v >> 18 & 63]; out[o++] = t[v >> 12 & 63];
        out[o++] = i + 1 < n ? t[v >> 6 & 63] : '='; out[o++] = i + 2 < n ? t[v & 63] : '=';
    }
    out[o] = 0;
}

int main(int argc, char **argv) {
    if (argc < 6) { fprintf(stderr, "usage: httpget HOST PORT PATH USER PASSWORD\n"); return 2; }
    int s = socket(AF_INET, SOCK_STREAM, 0);
    struct timeval tv = { 6, 0 };
    setsockopt(s, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof tv); setsockopt(s, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof tv);
    struct sockaddr_in a = { .sin_family = AF_INET, .sin_port = htons(atoi(argv[2])) };
    if (inet_pton(AF_INET, argv[1], &a.sin_addr) != 1 || connect(s, (struct sockaddr *)&a, sizeof a) != 0) return 3;
    char cred[300], enc[420], req[900];
    int cn = snprintf(cred, sizeof cred, "%s:%s", argv[4], argv[5]);
    b64((unsigned char *)cred, cn, enc);
    static char body[65536]; int bn = 0, post = argc > 7 && !strcmp(argv[6], "--post");   /* --post FILE: POST the file as audio/x-raw (majestic /play_audio) */
    if (post) { FILE *f = fopen(argv[7], "rb"); if (!f) return 9; bn = fread(body, 1, sizeof body, f); fclose(f); }
    int rn = post ? snprintf(req, sizeof req, "POST %s HTTP/1.0\r\nHost: %s\r\nAuthorization: Basic %s\r\nContent-Type: audio/x-raw\r\nContent-Length: %d\r\nConnection: close\r\n\r\n", argv[3], argv[1], enc, bn)
                  : snprintf(req, sizeof req, "GET %s HTTP/1.0\r\nHost: %s\r\nAuthorization: Basic %s\r\nConnection: close\r\n\r\n", argv[3], argv[1], enc);
    if (write(s, req, rn) != rn || (bn && write(s, body, bn) != bn)) return 4;
    static char buf[16384]; int have = 0, hdr_done = 0, status = 0; ssize_t r;
    while ((r = read(s, buf + have, sizeof buf - have)) > 0) {
        have += r;
        if (!hdr_done) {
            char *e = memmem(buf, have, "\r\n\r\n", 4);
            if (!e) { if (have == (int)sizeof buf) return 5; continue; }
            sscanf(buf, "HTTP/%*d.%*d %d", &status);
            if (status != 200) return 6;
            if (argc > 6 && !strcmp(argv[6], "--ct")) {          /* CGI mode: pass the upstream Content-Type through, then the body */
                char *c = memmem(buf, e - buf, "Content-Type:", 13);
                char ct[200] = "application/octet-stream";
                if (c) { c += 13; while (*c == ' ') c++; int n = 0; while (c < e && *c != '\r' && n < 199) ct[n++] = *c++; ct[n] = 0; }
                printf("Content-Type: %s\r\nCache-Control: no-store\r\n\r\n", ct); fflush(stdout);
            }
            hdr_done = 1; int hl = e + 4 - buf; have -= hl; memmove(buf, buf + hl, have);
        }
        if (have && (fwrite(buf, 1, have, stdout) != (size_t)have || fflush(stdout) != 0)) return 7;
        have = 0;
    }
    return hdr_done ? 0 : 8;
}
