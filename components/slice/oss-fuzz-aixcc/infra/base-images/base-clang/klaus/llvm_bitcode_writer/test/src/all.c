#include <stdio.h>
#include <stdlib.h>

struct test_struct {
	int aaaa;
	int pad;
	char *b;
	int c;
};

struct common {
    struct test_struct t;
    struct test_struct *tt;
};

int main() {
	struct common c;
    c.tt = malloc(100);
	struct test_struct tt;
	read(0, c.t, sizeof (c.t));
	read(0, c.tt, 100);
	if (c.t.aaaa > 10) {
		c.t.aaaa = 10;
	}
	
	if (c.tt->c > 111)
		c.tt->c = 111;
	c.tt->aaaa = c.tt->c;
	read(0, c.tt->b, 100);
	printf("t b %s\n", c.tt->b);
}
