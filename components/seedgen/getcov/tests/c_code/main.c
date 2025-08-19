#include <stdio.h>

void test_function(int x) {
    int squared = x * x;
    int cubed = squared * x;

    /*
    This is a block comment.
    */
    
    if (x > 10) {
        printf("Large positive: %d\n", x); /* this is an inline-block comment */
        if (squared > 200) {
            printf("Square is very large: %d\n", squared);
        }
    } else if (x > 0) {
        printf("Small positive: %d\n", x);
        if (cubed < 100) {
            printf("Cube is relatively small: %d\n", cubed);
        }
    } else if (x < -5) {
        printf("Large negative: %d\n", x);
        int abs_x = -x;
        if (abs_x > 10) {
            printf("Absolute value is big: %d\n", abs_x);
        }
    } else {
        // this is a line comment.
        printf("Small negative or zero: %d\n", x);
        if (x == 0) {
            printf("Number is exactly zero!\n");
        }
    }

    // this is a line comment.

    /* this is a block comment. */

    // Again, this is a line comment.
}

int main() {
    test_function(1);
    return 0;
}
