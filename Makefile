.PHONY: all run test clean

all:
	gcc -O2 -Wall -Wextra -o server server.c

run: all
	./server

test: all
	python3 tests/test_api.py

clean:
	rm -f server
