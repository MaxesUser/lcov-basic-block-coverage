#define _GNU_SOURCE
#include <dlfcn.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define MAX_MODULES 4096

typedef struct {
    unsigned char *flags;
    size_t flag_count;
    const uintptr_t *pcs;
    size_t pc_count;
} CovModule;

static CovModule modules[MAX_MODULES];
static size_t module_count;
static int registered;

static void emit_json_string(FILE *out, const char *value) {
    fputc('"', out);
    for (const unsigned char *p = (const unsigned char *)value; *p; ++p) {
        if (*p == '"' || *p == '\\') {
            fputc('\\', out);
            fputc(*p, out);
        } else if (*p < 32) {
            fprintf(out, "\\u%04x", *p);
        } else {
            fputc(*p, out);
        }
    }
    fputc('"', out);
}

static void dump_coverage(void) {
    const char *dir = getenv("BBRAW_DIR");
    if (!dir || !*dir) {
        return;
    }

    char filename[PATH_MAX];
    if (snprintf(filename, sizeof filename, "%s/bb-%ld.jsonl", dir, (long)getpid()) >= (int)sizeof filename) {
        fputs("bb-runtime: BBRAW_DIR path too long\n", stderr);
        return;
    }

    FILE *out = fopen(filename, "w");
    if (!out) {
        perror("bb-runtime: fopen");
        return;
    }

    size_t slot = 0;
    for (size_t m = 0; m < module_count; ++m) {
        const CovModule *mod = &modules[m];
        if (!mod->flags || !mod->pcs || mod->flag_count != mod->pc_count) {
            fprintf(stderr, "bb-runtime: unmatched SanitizerCoverage tables in module %zu\n", m);
            continue;
        }
        for (size_t i = 0; i < mod->pc_count; ++i) {
            uintptr_t pc = mod->pcs[2 * i];
            size_t table_slot = slot++;
            Dl_info info;
            memset(&info, 0, sizeof info);
            if (!pc || !dladdr((void *)pc, &info) || !info.dli_fname || !info.dli_fbase) {
                fprintf(stderr, "bb-runtime: cannot resolve PC for module %zu block %zu\n", m, i);
                continue;
            }
            char resolved[PATH_MAX];
            const char *name = realpath(info.dli_fname, resolved) ? resolved : info.dli_fname;
            uintptr_t offset = pc - (uintptr_t)info.dli_fbase;
            fputs("{\"module\":", out);
            emit_json_string(out, name);
            fprintf(out, ",\"pc\":\"0x%zx\",\"slot\":%zu,\"hit\":%s}\n",
                    (size_t)offset, table_slot, mod->flags[i] ? "true" : "false");
        }
    }
    if (fclose(out)) {
        perror("bb-runtime: fclose");
    }
}

static void register_dump(void) {
    if (!registered) {
        atexit(dump_coverage);
        registered = 1;
    }
}

static CovModule *find_module(size_t count, int needs_flags) {
    for (size_t i = 0; i < module_count; ++i) {
        CovModule *mod = &modules[i];
        if (needs_flags && !mod->flags && mod->pcs && mod->pc_count == count) return mod;
        if (!needs_flags && !mod->pcs && mod->flags && mod->flag_count == count) return mod;
    }
    if (module_count >= MAX_MODULES) {
        fputs("bb-runtime: too many instrumented modules\n", stderr);
        abort();
    }
    CovModule *mod = &modules[module_count++];
    memset(mod, 0, sizeof *mod);
    return mod;
}

/* Compile this file without -fsanitize-coverage. */
void __sanitizer_cov_bool_flag_init(unsigned char *start, unsigned char *end) {
    if (start == end) return;
    register_dump();
    CovModule *mod = find_module((size_t)(end - start), 1);
    mod->flags = start;
    mod->flag_count = (size_t)(end - start);
}

void __sanitizer_cov_pcs_init(const uintptr_t *start, const uintptr_t *end) {
    if (start == end) return;
    if ((end - start) % 2 != 0) {
        fputs("bb-runtime: invalid PC table\n", stderr);
        abort();
    }
    register_dump();
    size_t count = (size_t)(end - start) / 2;
    CovModule *mod = find_module(count, 0);
    mod->pcs = start;
    mod->pc_count = count;
}
