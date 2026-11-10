/* SPDX-License-Identifier: GPL-2.0-or-later */
/* jget FILE PATH [DEFAULT]  -- print a value from a JSON file; PATH is dot separated, numbers index arrays (wifi.networks.0.ssid)
   jget FILE PATH --len      -- number of elements of an array (0 if missing)
   Exit 0 and prints the value (strings raw, booleans true/false); prints DEFAULT (or nothing) if the key is missing. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <json-c/json.h>
int main(int argc, char **argv) {
    if (argc < 3) { fprintf(stderr, "usage: jget FILE PATH [DEFAULT|--len]\n"); return 2; }
    int len = argc > 3 && !strcmp(argv[3], "--len");
    const char *def = (argc > 3 && !len) ? argv[3] : "";
    struct json_object *o = json_object_from_file(argv[1]);
    if (o) {
        char *p = strdup(argv[2]), *save = NULL;
        for (char *t = strtok_r(p, ".", &save); t && o; t = strtok_r(NULL, ".", &save)) {
            struct json_object *n = NULL;
            if (json_object_is_type(o, json_type_array)) {
                char *e; long i = strtol(t, &e, 10);
                if (*e || i < 0 || (size_t)i >= json_object_array_length(o)) { o = NULL; break; }
                n = json_object_array_get_idx(o, i);
            } else if (!json_object_object_get_ex(o, t, &n)) { o = NULL; break; }
            o = n;
        }
    }
    if (len) { printf("%zu\n", (o && json_object_is_type(o, json_type_array)) ? json_object_array_length(o) : 0); return 0; }
    if (!o || json_object_is_type(o, json_type_null)) { puts(def); return 0; }
    if (json_object_is_type(o, json_type_string)) puts(json_object_get_string(o));
    else puts(json_object_to_json_string_ext(o, JSON_C_TO_STRING_PLAIN));
    return 0;
}
