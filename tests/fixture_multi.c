#include <stdio.h>
#include <stdlib.h>
int extra(int input);
int main(int argc, char **argv) {
    int input = argc > 1 ? atoi(argv[1]) : 0;
    printf("%d\n", extra(input));
    return 0;
}
