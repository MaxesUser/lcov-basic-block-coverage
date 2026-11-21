#include "cJSON.h"
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv) {
    const char *input = argc > 1 ? argv[1] : "{}";
    cJSON *root = cJSON_Parse(input);
    if (!root) {
        puts("cJSON: parse error");
        return 0;
    }

    if (cJSON_IsObject(root)) {
        const cJSON *value = cJSON_GetObjectItemCaseSensitive(root, "value");
        if (cJSON_IsNumber(value)) {
            printf("cJSON: value=%d\n", value->valueint);
        } else if (cJSON_IsString(value)) {
            printf("cJSON: value=%s\n", value->valuestring);
        } else {
            puts("cJSON: no supported value");
        }
    } else if (cJSON_IsArray(root)) {
        printf("cJSON: array size=%d\n", cJSON_GetArraySize(root));
    } else {
        puts("cJSON: other JSON type");
    }
    cJSON_Delete(root);
    return 0;
}
