#include "ini.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    int count;
    int port;
} Config;

static int on_value(void *user, const char *section, const char *name, const char *value) {
    Config *cfg = user;
    ++cfg->count;
    if (strcmp(section, "server") == 0 && strcmp(name, "port") == 0) {
        cfg->port = atoi(value);
    }
    return 1;
}

int main(int argc, char **argv) {
    int mode = argc > 1 ? atoi(argv[1]) : 0;
    const char *input;
    if (mode == 0) {
        input = "[server]\nport=8080\nhost=localhost\n";
    } else if (mode == 1) {
        input = "[server]\nport=3000\n[client]\ntimeout=10\n";
    } else {
        input = "[server\nport=invalid\n";
    }

    Config cfg = {0};
    int result = ini_parse_string(input, on_value, &cfg);
    printf("inih: parse=%d, entries=%d, port=%d\n", result, cfg.count, cfg.port);
    return 0;
}
