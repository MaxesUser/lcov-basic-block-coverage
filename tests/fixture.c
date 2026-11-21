#include <stdio.h>
#include <stdlib.h>
static int classify(int x) {
    if (x < 0) return -1;
    if (x == 0) return 0;
    return x % 2 ? 1 : 2;
}
int main(int argc, char **argv) {
    int x = argc > 1 ? atoi(argv[1]) : 0;
    printf("class=%d\n", classify(x));
    return 0;
}
