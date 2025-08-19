CC=clang
CFLAGS=-fprofile-instr-generate -fcoverage-mapping

all: main

main: main.c
	$(CC) $(CFLAGS) -o main main.c

clean:
	rm -f main *.profraw
