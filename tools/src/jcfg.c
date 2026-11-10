/* SPDX-License-Identifier: GPL-2.0-or-later */
/* jcfg - settings helper for the camera (json-c). Pattern taken from tSIP's SettingsUtils: defaults + partial user file,
 * atomic update with .bak, read with recovery.
 *
 *   jcfg effective DEFAULTS USER OUT   merge defaults <- user (user file, else USER.bak) and write OUT; status on stderr
 *   jcfg update    DEFAULTS USER       read a JSON patch from stdin, validate, merge into USER atomically (USER.next -> USER, old -> USER.bak)
 *                                      prints {"ok":true} or {"ok":false,"error":"..."}; exit 0/1
 *   jcfg public    EFFECTIVE           print EFFECTIVE without secrets (psk / root_password become *_set flags)
 *   jcfg check     FILE                validate a complete settings file (exit 0/1, message on stderr)
 *
 * Secrets: an empty "psk" or "root_password" in an UPDATE patch means "keep the current value".
 */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <errno.h>
#include <fcntl.h>
#include <ctype.h>
#include <stdint.h>
#include <arpa/inet.h>
#include <json-c/json.h>

static char errbuf[200];
#define FAIL(...) do { snprintf(errbuf, sizeof errbuf, __VA_ARGS__); return 0; } while (0)

static struct json_object *load(const char *path) { return path ? json_object_from_file(path) : NULL; }

/* deep merge: objects merge recursively, everything else (scalars, arrays) is replaced */
static void merge(struct json_object *dst, struct json_object *src)
{
    json_object_object_foreach(src, k, v) {
        struct json_object *d = NULL;
        if (json_object_is_type(v, json_type_object) && json_object_object_get_ex(dst, k, &d) && json_object_is_type(d, json_type_object))
            merge(d, v);
        else
            json_object_object_add(dst, k, json_object_get(v));
    }
}

static struct json_object *jdup(struct json_object *o)
{
    struct json_object *n = NULL;
    json_object_deep_copy(o, &n, NULL);
    return n;
}

static int is_str(struct json_object *o) { return o && json_object_is_type(o, json_type_string); }
static int is_int(struct json_object *o) { return o && json_object_is_type(o, json_type_int); }
static int is_bool(struct json_object *o) { return o && json_object_is_type(o, json_type_boolean); }

static int printable(const char *s)
{
    for (; *s; s++) if ((unsigned char)*s < 0x20 || *s == 0x7f) return 0;
    return 1;
}

static int get(struct json_object *o, const char *key, struct json_object **out)
{
    return json_object_object_get_ex(o, key, out);
}

static int check_keys(struct json_object *o, const char *section, const char *const *allowed)
{
    json_object_object_foreach(o, k, v) {
        (void)v; int ok = 0;
        for (const char *const *a = allowed; *a; a++) if (!strcmp(k, *a)) ok = 1;
        if (!ok) FAIL("unknown setting %s%s%s", section, *section ? "." : "", k);
    }
    return 1;
}

static int range(struct json_object *s, const char *name, long lo, long hi)
{
    struct json_object *v;
    if (!get(s, name, &v)) return 1;
    if (!is_int(v)) FAIL("%s must be a number", name);
    long n = json_object_get_int64(v);
    if (n < lo || n > hi) FAIL("%s must be between %ld and %ld", name, lo, hi);
    return 1;
}

/* IPv4 address in dotted form; returns it in host order or 0 with *ok = 0 */
static uint32_t ipv4(const char *t, int *ok)
{
    struct in_addr a;
    *ok = inet_pton(AF_INET, t, &a) == 1 && strspn(t, "0123456789.") == strlen(t);
    return *ok ? ntohl(a.s_addr) : 0;
}

/* validate a (possibly partial) settings object; used for patches and for the merged result */
static int validate(struct json_object *o)
{
    static const char *const top[] = {"info", "hostname", "timezone", "ntp_server", "network", "osd", "recording", "sip", "wifi", "users", "stream", "image", "night", "audio", NULL};
    static const char *const nt[] = {"mode", "ir_light", "gray_at_night", "gain", NULL};
    static const char *const strm[] = {"size", "fps", "bitrate", "codec", NULL};
    static const char *const sizes[] = {"1920x1080", "1280x720", "960x540", "640x360", "320x180", NULL};
    static const char *const img[] = {"mirror", "flip", NULL};
    static const char *const aud[] = {"mic", "mic_volume", "codec", "speaker", "speaker_volume", "talkback", "beeps", NULL};
    static const char *const osdk[] = {"enabled", "text", "position", "size", NULL};
    static const char *const osdpos[] = {"top-left", "top-right", "bottom-left", "bottom-right", NULL};
    static const char *const osdsz[] = {"small", "normal", "large", NULL};
    static const char *const reck[] = {"enabled", "mode", "split", "max_usage", "motion_sensitivity", "pre_roll", "post_roll", "min_clip", "audio", NULL};
    static const char *const sipk[] = {"enabled", "server", "port", "username", "password", "uri", "target", "register", "ring_seconds", "ring_cycles", "allowed_peers", NULL};
    static const char *const usr[] = {"root_password", NULL};
    static const char *const wf[] = {"mode", "networks", "ap", NULL};
    static const char *const apk[] = {"ssid", "psk", "channel", NULL};
    static const char *const netk[] = {"mode", "address", "netmask", "gateway", "dns", NULL};
    struct json_object *v, *s;
    if (!json_object_is_type(o, json_type_object)) FAIL("settings must be a JSON object");
    if (!check_keys(o, "", top)) return 0;
    if (get(o, "hostname", &v)) {
        if (!is_str(v)) FAIL("hostname must be text");
        const char *h = json_object_get_string(v); size_t n = strlen(h);
        if (n < 1 || n > 32) FAIL("hostname must be 1-32 characters");
        for (size_t i = 0; i < n; i++) if (!isalnum((unsigned char)h[i]) && h[i] != '-') FAIL("hostname may contain letters, digits and '-' only");
    }
    if (get(o, "ntp_server", &v)) {
        if (!is_str(v)) FAIL("ntp_server must be text");
        const char *h = json_object_get_string(v); size_t n = strlen(h);
        if (n > 128) FAIL("ntp_server is too long");
        for (size_t i = 0; i < n; i++) if (!isalnum((unsigned char)h[i]) && !strchr("-.:,", h[i])) FAIL("ntp_server: host names or addresses separated by commas (letters, digits, '-', '.'), empty = no time synchronisation");
    }
    if (get(o, "network", &s)) {
        struct json_object *x;
        int ok;
        uint32_t ad = 0, nm = 0, gw = 0;
        const char *a = "", *m = "", *g = "";
        if (!json_object_is_type(s, json_type_object)) FAIL("network must be an object");
        if (!check_keys(s, "network", netk)) return 0;
        if (get(s, "mode", &v) && (!is_str(v) || (strcmp(json_object_get_string(v), "dhcp") && strcmp(json_object_get_string(v), "static")))) FAIL("network.mode must be dhcp or static");
        if (get(s, "address", &x)) { if (!is_str(x)) FAIL("network.address must be text"); a = json_object_get_string(x); }
        if (get(s, "netmask", &x)) { if (!is_str(x)) FAIL("network.netmask must be text"); m = json_object_get_string(x); }
        if (get(s, "gateway", &x)) { if (!is_str(x)) FAIL("network.gateway must be text"); g = json_object_get_string(x); }
        if (*a) {
            ad = ipv4(a, &ok);
            if (!ok) FAIL("network.address: not an IPv4 address like 192.168.1.50");
            if ((ad >> 24) == 0 || (ad >> 24) == 127 || (ad >> 24) >= 224) FAIL("network.address: not a usable host address");
        }
        if (*m) {
            nm = ipv4(m, &ok);
            if (!ok || nm == 0 || ((~nm + 1) & ~nm) != 0 || (nm & 0xFFFFFFFCu) != nm) FAIL("network.netmask: a mask like 255.255.255.0 (prefix 1-30)");
        }
        if (*g) {
            gw = ipv4(g, &ok);
            if (!ok) FAIL("network.gateway: not an IPv4 address");
        }
        if (*a && *m && (ad & ~nm) == 0) FAIL("network.address is the network address, not a host");
        if (*a && *m && (ad | nm) == 0xFFFFFFFFu) FAIL("network.address is the broadcast address");
        if (*g && *a && *m && (gw & nm) != (ad & nm)) FAIL("network.gateway is not in the same network as the address");
        if (*g && *a && gw == ad) FAIL("network.gateway equals the camera's own address");
        if (get(s, "dns", &x)) {
            if (!is_str(x)) FAIL("network.dns must be text");
            const char *d = json_object_get_string(x);
            char buf[100]; int cnt = 0;
            if (strlen(d) >= sizeof buf) FAIL("network.dns is too long");
            snprintf(buf, sizeof buf, "%s", d);
            if (*buf) for (char *t = strtok(buf, ", "); t; t = strtok(NULL, ", ")) { ipv4(t, &ok); if (!ok) FAIL("network.dns: up to 2 IPv4 addresses separated by commas"); cnt++; }
            if (cnt > 2) FAIL("network.dns: at most 2 addresses");
        }
        if (get(s, "mode", &v) && !strcmp(json_object_get_string(v), "static") && (get(s, "address", &x) || get(s, "netmask", &x)) && (!*a || !*m)) FAIL("static addressing needs an address and a netmask");
    }
    if (get(o, "timezone", &v)) {
        if (!is_str(v)) FAIL("timezone must be text");
        const char *t = json_object_get_string(v);
        if (strlen(t) > 40 || !printable(t) || strpbrk(t, "'\"`$\\;&|<>")) FAIL("timezone contains invalid characters");
    }
    if (get(o, "stream", &s)) {
        if (!json_object_is_type(s, json_type_object)) FAIL("stream must be an object");
        if (!check_keys(s, "stream", strm)) return 0;
        if (!range(s, "fps", 1, 30) || !range(s, "bitrate", 64, 8192)) return 0;
        if (get(s, "size", &v)) {
            int ok = 0;
            if (!is_str(v)) FAIL("stream.size must be text like \"1920x1080\"");
            for (const char *const *z = sizes; *z; z++) if (!strcmp(json_object_get_string(v), *z)) ok = 1;
            if (!ok) FAIL("stream.size must be one of 1920x1080, 1280x720, 960x540, 640x360, 320x180");
        }
        if (get(s, "codec", &v) && (!is_str(v) || strcmp(json_object_get_string(v), "h264"))) FAIL("codec must be \"h264\"");
    }
    if (get(o, "image", &s)) {
        if (!json_object_is_type(s, json_type_object)) FAIL("image must be an object");
        if (!check_keys(s, "image", img)) return 0;
        if (get(s, "mirror", &v) && !is_bool(v)) FAIL("image.mirror must be true or false");
        if (get(s, "flip", &v) && !is_bool(v)) FAIL("image.flip must be true or false");
    }
    if (get(o, "night", &s)) {
        if (!json_object_is_type(s, json_type_object)) FAIL("night must be an object");
        if (!check_keys(s, "night", nt)) return 0;
        if (get(s, "mode", &v) && (!is_str(v) || (strcmp(json_object_get_string(v), "auto") && strcmp(json_object_get_string(v), "day") && strcmp(json_object_get_string(v), "night")))) FAIL("night.mode must be auto, day or night");
        if (get(s, "ir_light", &v) && (!is_str(v) || (strcmp(json_object_get_string(v), "auto") && strcmp(json_object_get_string(v), "never")))) FAIL("night.ir_light must be auto or never");
        if (get(s, "gray_at_night", &v) && !is_bool(v)) FAIL("night.gray_at_night must be true or false");
        if (!range(s, "gain", 2, 64)) return 0;
    }
    if (get(o, "osd", &s)) {
        if (!json_object_is_type(s, json_type_object)) FAIL("osd must be an object");
        if (!check_keys(s, "osd", osdk)) return 0;
        if (get(s, "enabled", &v) && !is_bool(v)) FAIL("osd.enabled must be true or false");
        if (get(s, "text", &v)) {
            const char *x = is_str(v) ? json_object_get_string(v) : NULL;
            if (!x || strlen(x) < 1 || strlen(x) > 64 || !printable(x) || strpbrk(x, "\"'`\\$")) FAIL("osd.text: 1-64 printable characters, no quotes, backslash or $ (strftime codes like %%Y-%%m-%%d %%H:%%M:%%S work, also %%{hostname} and %%{ip})");
        }
        for (int k = 0; k < 2; k++) {
            const char *key = k ? "size" : "position", *const *list = k ? osdsz : osdpos;
            if (get(s, key, &v)) {
                int ok = 0;
                if (is_str(v)) for (const char *const *z = list; *z; z++) if (!strcmp(json_object_get_string(v), *z)) ok = 1;
                if (!ok) FAIL("osd.%s: not one of the allowed values", key);
            }
        }
    }
    if (get(o, "sip", &s)) {
        static const char *const txt[] = {"server", "username", "password", "uri", "target", "allowed_peers", NULL};
        static const int lim[] = {64, 64, 64, 96, 200, 120};
        if (!json_object_is_type(s, json_type_object)) FAIL("sip must be an object");
        if (!check_keys(s, "sip", sipk)) return 0;
        if (get(s, "enabled", &v) && !is_bool(v)) FAIL("sip.enabled must be true or false");
        if (get(s, "register", &v) && !is_bool(v)) FAIL("sip.register must be true or false");
        for (int k = 0; txt[k]; k++) if (get(s, txt[k], &v)) {
            const char *x = is_str(v) ? json_object_get_string(v) : NULL;
            if (!x || (int)strlen(x) > lim[k] || !printable(x) || strpbrk(x, "\"'`\\$")) FAIL("sip.%s: at most %d printable characters, no quotes, backslash or $", txt[k], lim[k]);
        }
        if (!range(s, "port", 1, 65535) || !range(s, "ring_seconds", 5, 120) || !range(s, "ring_cycles", 1, 10)) return 0;
    }
    if (get(o, "recording", &s)) {
        if (!json_object_is_type(s, json_type_object)) FAIL("recording must be an object");
        if (!check_keys(s, "recording", reck)) return 0;
        if (get(s, "enabled", &v) && !is_bool(v)) FAIL("recording.enabled must be true or false");
        if (get(s, "mode", &v) && (!is_str(v) || (strcmp(json_object_get_string(v), "continuous") && strcmp(json_object_get_string(v), "motion")))) FAIL("recording.mode must be continuous or motion");
        if (get(s, "audio", &v) && !is_bool(v)) FAIL("recording.audio must be true or false");
        if (!range(s, "split", 1, 60) || !range(s, "max_usage", 50, 95) || !range(s, "motion_sensitivity", 0, 8) || !range(s, "pre_roll", 0, 30) || !range(s, "post_roll", 0, 120) || !range(s, "min_clip", 1, 60)) return 0;
    }
    if (get(o, "audio", &s)) {
        if (!json_object_is_type(s, json_type_object)) FAIL("audio must be an object");
        if (!check_keys(s, "audio", aud)) return 0;
        if (get(s, "mic", &v) && !is_bool(v)) FAIL("audio.mic must be true or false");
        if (get(s, "speaker", &v) && !is_bool(v)) FAIL("audio.speaker must be true or false");
        if (get(s, "talkback", &v) && !is_bool(v)) FAIL("audio.talkback must be true or false");
        if (get(s, "beeps", &v) && !is_bool(v)) FAIL("audio.beeps must be true or false");
        if (!range(s, "mic_volume", 0, 100) || !range(s, "speaker_volume", 0, 100)) return 0;
        if (get(s, "codec", &v)) {
            const char *c = is_str(v) ? json_object_get_string(v) : "";
            if (strcmp(c, "alaw") && strcmp(c, "ulaw") && strcmp(c, "pcm") && strcmp(c, "aac") && strcmp(c, "opus")) FAIL("audio.codec must be alaw, ulaw, pcm, aac or opus");
        }
    }
    if (get(o, "users", &s)) {
        if (!json_object_is_type(s, json_type_object)) FAIL("users must be an object");
        if (!check_keys(s, "users", usr)) return 0;
        if (get(s, "root_password", &v)) {
            if (!is_str(v)) FAIL("password must be text");
            const char *p = json_object_get_string(v); size_t n = strlen(p);
            if (n && (n < 6 || n > 64)) FAIL("password must be 6-64 characters");
            if (!printable(p) || strpbrk(p, "'\"`\\")) FAIL("password contains characters that are not allowed (quotes, backslash, control)");
        }
    }
    if (get(o, "wifi", &s)) {
        if (!json_object_is_type(s, json_type_object)) FAIL("wifi must be an object");
        if (!check_keys(s, "wifi", wf)) return 0;
        if (get(s, "mode", &v) && (!is_str(v) || (strcmp(json_object_get_string(v), "station") && strcmp(json_object_get_string(v), "ap")))) FAIL("wifi.mode must be station or ap");
        if (get(s, "ap", &v)) {
            struct json_object *x;
            if (!json_object_is_type(v, json_type_object)) FAIL("wifi.ap must be an object");
            if (!check_keys(v, "wifi.ap", apk)) return 0;
            if (get(v, "ssid", &x)) {
                const char *a = is_str(x) ? json_object_get_string(x) : NULL;
                if (!a || strlen(a) > 32 || !printable(a) || strpbrk(a, "\"\\")) FAIL("wifi.ap.ssid: up to 32 printable characters, no quotes or backslash (empty = automatic name)");
            }
            if (get(v, "psk", &x)) {
                const char *k = is_str(x) ? json_object_get_string(x) : NULL;
                if (!k || strlen(k) < 8 || strlen(k) > 63 || !printable(k) || strpbrk(k, "\"\\")) FAIL("wifi.ap.psk: 8-63 printable characters, no quotes or backslash");
            }
            if (!range(v, "channel", 1, 11)) return 0;
        }
        if (get(s, "networks", &v)) {
            if (!json_object_is_type(v, json_type_array)) FAIL("wifi.networks must be a list");
            size_t n = json_object_array_length(v);
            if (n > 8) FAIL("at most 8 Wi-Fi networks");
            for (size_t i = 0; i < n; i++) {
                struct json_object *e = json_object_array_get_idx(v, i), *ss, *pp;
                if (!json_object_is_type(e, json_type_object) || !get(e, "ssid", &ss) || !is_str(ss)) FAIL("network %zu needs an \"ssid\"", i + 1);
                const char *sid = json_object_get_string(ss);
                if (!strlen(sid) || strlen(sid) > 32 || !printable(sid) || strpbrk(sid, "\"\\")) FAIL("network %zu: SSID must be 1-32 printable characters, no quotes or backslash", i + 1);
                if (get(e, "psk", &pp)) {
                    if (!is_str(pp)) FAIL("network %zu: psk must be text", i + 1);
                    const char *k = json_object_get_string(pp); size_t kn = strlen(k);
                    if (kn && (kn < 8 || kn > 63)) FAIL("network %zu: WPA password must be 8-63 characters", i + 1);
                    if (!printable(k) || strpbrk(k, "\"\\")) FAIL("network %zu: password contains characters that are not allowed (quote, backslash, control)", i + 1);
                }
            }
        }
    }
    return 1;
}

/* an update patch: empty secrets mean "keep" - replace them with the current values before merging */
static void keep_secrets(struct json_object *patch, struct json_object *current)
{
    struct json_object *u, *cu, *p, *w, *cw, *nets, *cnets;
    if (get(patch, "users", &u) && get(u, "root_password", &p) && is_str(p) && !*json_object_get_string(p)) {
        if (get(current, "users", &cu) && get(cu, "root_password", &p)) json_object_object_add(u, "root_password", json_object_get(p));
    }
    if (get(patch, "sip", &u) && get(u, "password", &p) && is_str(p) && !*json_object_get_string(p)) {
        struct json_object *cs;
        if (get(current, "sip", &cs) && get(cs, "password", &p)) json_object_object_add(u, "password", json_object_get(p));
    }
    if (get(patch, "wifi", &w) && get(w, "networks", &nets) && json_object_is_type(nets, json_type_array)) {
        cnets = NULL;
        if (get(current, "wifi", &cw)) get(cw, "networks", &cnets);
        for (size_t i = 0; i < json_object_array_length(nets); i++) {
            struct json_object *e = json_object_array_get_idx(nets, i), *ps, *ss;
            if (!get(e, "ssid", &ss) || (get(e, "psk", &ps) && is_str(ps) && *json_object_get_string(ps))) continue;
            if (get(e, "psk", &ps) && !is_str(ps)) continue;
            if (!cnets) continue;
            for (size_t j = 0; j < json_object_array_length(cnets); j++) {      /* same SSID in the current list: keep its password */
                struct json_object *ce = json_object_array_get_idx(cnets, j), *cs, *cp;
                if (get(ce, "ssid", &cs) && is_str(cs) && !strcmp(json_object_get_string(cs), json_object_get_string(ss)) && get(ce, "psk", &cp)) {
                    json_object_object_add(e, "psk", json_object_get(cp)); break;
                }
            }
        }
    }
}

static int write_atomic(const char *path, const char *text)
{
    char tmp[512], bak[512];
    snprintf(tmp, sizeof tmp, "%s.next", path); snprintf(bak, sizeof bak, "%s.bak", path);
    int fd = open(tmp, O_WRONLY | O_CREAT | O_TRUNC, 0600);
    if (fd < 0) FAIL("cannot write %s: %s", tmp, strerror(errno));
    size_t n = strlen(text);
    if (write(fd, text, n) != (ssize_t)n || fsync(fd) != 0) { close(fd); unlink(tmp); FAIL("write failed: %s", strerror(errno)); }
    close(fd);
    if (access(path, F_OK) == 0 && rename(path, bak) != 0) { unlink(tmp); FAIL("cannot keep a backup: %s", strerror(errno)); }
    if (rename(tmp, path) != 0) FAIL("cannot replace %s: %s", path, strerror(errno));
    return 1;
}

static void json_msg(int ok, const char *msg)
{
    struct json_object *r = json_object_new_object();
    json_object_object_add(r, "ok", json_object_new_boolean(ok));
    if (!ok) json_object_object_add(r, "error", json_object_new_string(msg));
    puts(json_object_to_json_string_ext(r, JSON_C_TO_STRING_PLAIN));
}

static struct json_object *read_stdin(void)
{
    char *buf = malloc(65536); size_t n = 0; ssize_t r;
    while ((r = read(0, buf + n, 65535 - n)) > 0 && (n += r) < 65535) ;
    buf[n] = 0;
    struct json_object *o = json_tokener_parse(buf);
    free(buf);
    return o;
}

int main(int argc, char **argv)
{
    if (argc >= 5 && !strcmp(argv[1], "effective")) {
        struct json_object *d = load(argv[2]), *u = load(argv[3]);
        const char *st = "ok";
        if (!d) { fprintf(stderr, "defaults unreadable\n"); return 1; }
        char bak[512]; snprintf(bak, sizeof bak, "%s.bak", argv[3]);
        if (!u) {
            int exists = access(argv[3], F_OK) == 0;
            u = load(bak);
            st = u ? "recovered-from-backup" : (exists ? "user-file-unreadable" : "no-user-file");
        }
        if (u && !validate(u)) { fprintf(stderr, "user settings rejected: %s\n", errbuf); u = NULL; st = "user-file-invalid"; }
        struct json_object *e = jdup(d);
        if (u) merge(e, u);
        if (!validate(e)) { fprintf(stderr, "effective settings invalid: %s\n", errbuf); return 1; }
        if (json_object_to_file_ext(argv[4], e, JSON_C_TO_STRING_PRETTY) != 0) { fprintf(stderr, "cannot write %s\n", argv[4]); return 1; }
        fprintf(stderr, "%s\n", st);
        return 0;
    }
    if (argc >= 4 && !strcmp(argv[1], "update")) {
        struct json_object *patch = read_stdin(), *d = load(argv[2]);
        if (!patch) { json_msg(0, "request is not valid JSON"); return 1; }
        if (!d) { json_msg(0, "defaults unreadable"); return 1; }
        if (!validate(patch)) { json_msg(0, errbuf); return 1; }
        struct json_object *cur = load(argv[3]);
        if (!cur || !validate(cur)) cur = json_object_new_object();
        struct json_object *merged_user = jdup(cur);
        json_object_object_del(patch, "info");
        struct json_object *cur_eff = jdup(d); merge(cur_eff, merged_user);   /* secrets may come from the defaults (e.g. a baked-in password) */
        keep_secrets(patch, cur_eff);
        int replace = argc >= 5 && !strcmp(argv[4], "--replace");     /* restore: the patch becomes the whole user file (secrets left blank/absent keep their current value) */
        if (replace) {
            struct json_object *w, *ap, *cw, *cap, *cpsk, *pp;
            struct json_object *dw, *dap, *dpsk;   /* only a password that differs from the default is worth keeping in the file */
            int is_default = get(d, "wifi", &dw) && get(dw, "ap", &dap) && get(dap, "psk", &dpsk) && get(cur_eff, "wifi", &cw) && get(cw, "ap", &cap) && get(cap, "psk", &cpsk) && is_str(dpsk) && is_str(cpsk) && !strcmp(json_object_get_string(dpsk), json_object_get_string(cpsk));
            if (!is_default && get(cur_eff, "wifi", &cw) && get(cw, "ap", &cap) && get(cap, "psk", &cpsk) && is_str(cpsk) && *json_object_get_string(cpsk)) {
                if (!get(patch, "wifi", &w)) { json_object_object_add(patch, "wifi", json_object_new_object()); get(patch, "wifi", &w); }
                if (!get(w, "ap", &ap)) { json_object_object_add(w, "ap", json_object_new_object()); get(w, "ap", &ap); }
                if (!get(ap, "psk", &pp)) json_object_object_add(ap, "psk", json_object_get(cpsk));
            }
            merged_user = jdup(patch);
        } else merge(merged_user, patch);
        struct json_object *e = jdup(d); merge(e, merged_user);
        if (!validate(e)) { json_msg(0, errbuf); return 1; }
        if (!write_atomic(argv[3], json_object_to_json_string_ext(merged_user, JSON_C_TO_STRING_PRETTY))) { json_msg(0, errbuf); return 1; }
        json_msg(1, NULL);
        return 0;
    }
    if (argc >= 3 && !strcmp(argv[1], "backup")) {      /* backup USERFILE [--secrets] [--info TEXT]: the saved settings as JSON, passwords and keys blank unless --secrets */
        struct json_object *u = load(argv[2]), *w, *nets, *s, *info = json_object_new_object();
        int secrets = 0; const char *note = "cv206 settings backup";
        for (int i = 3; i < argc; i++) { if (!strcmp(argv[i], "--secrets")) secrets = 1; else if (!strcmp(argv[i], "--info") && i + 1 < argc) note = argv[++i]; }
        if (!u) { char bak[512]; snprintf(bak, sizeof bak, "%s.bak", argv[2]); u = load(bak); }
        u = u ? jdup(u) : json_object_new_object();
        if (!secrets) {
            if (get(u, "users", &s) && get(s, "root_password", NULL)) json_object_object_add(s, "root_password", json_object_new_string(""));
            if (get(u, "sip", &s) && get(s, "password", NULL)) json_object_object_add(s, "password", json_object_new_string(""));
            if (get(u, "wifi", &w)) {
                struct json_object *ap;
                if (get(w, "ap", &ap)) json_object_object_del(ap, "psk");
                if (get(w, "networks", &nets) && json_object_is_type(nets, json_type_array))
                    for (size_t i = 0; i < json_object_array_length(nets); i++) json_object_object_add(json_object_array_get_idx(nets, i), "psk", json_object_new_string(""));
            }
        }
        json_object_object_add(info, "note", json_object_new_string(note));
        json_object_object_add(info, "passwords_included", json_object_new_boolean(secrets));
        json_object_object_add(u, "info", info);
        puts(json_object_to_json_string_ext(u, JSON_C_TO_STRING_PRETTY));
        return 0;
    }
    if (argc >= 3 && !strcmp(argv[1], "public")) {
        struct json_object *e = load(argv[2]), *u, *w, *nets, *p;
        if (!e) return 1;
        if (get(e, "users", &u) && get(u, "root_password", &p)) {
            int set = is_str(p) && *json_object_get_string(p);
            json_object_object_add(u, "root_password", json_object_new_string(""));
            json_object_object_add(u, "root_password_set", json_object_new_boolean(set));
        }
        if (get(e, "sip", &u) && get(u, "password", &p)) {
            int set = is_str(p) && *json_object_get_string(p);
            json_object_object_add(u, "password", json_object_new_string(""));
            json_object_object_add(u, "password_set", json_object_new_boolean(set));
        }
        if (get(e, "wifi", &w) && get(w, "ap", &u) && get(u, "psk", &p)) {
            json_object_object_add(u, "psk", json_object_new_string(""));
            json_object_object_add(u, "psk_set", json_object_new_boolean(1));
        }
        if (get(e, "wifi", &w) && get(w, "networks", &nets) && json_object_is_type(nets, json_type_array))
            for (size_t i = 0; i < json_object_array_length(nets); i++) {
                struct json_object *n = json_object_array_get_idx(nets, i);
                int set = get(n, "psk", &p) && is_str(p) && *json_object_get_string(p);
                json_object_object_add(n, "psk", json_object_new_string(""));
                json_object_object_add(n, "psk_set", json_object_new_boolean(set));
            }
        puts(json_object_to_json_string_ext(e, JSON_C_TO_STRING_PLAIN));
        return 0;
    }
    if (argc >= 3 && !strcmp(argv[1], "check")) {
        struct json_object *o = load(argv[2]);
        if (!o) { fprintf(stderr, "cannot parse %s\n", argv[2]); return 1; }
        if (!validate(o)) { fprintf(stderr, "%s\n", errbuf); return 1; }
        return 0;
    }
    fprintf(stderr, "usage: jcfg effective DEFAULTS USER OUT | update DEFAULTS USER < patch | public EFFECTIVE | check FILE\n");
    return 2;
}
