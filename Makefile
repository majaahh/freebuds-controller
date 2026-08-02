# Copyright (c) 2026 Majaahh
# SPDX-License-Identifier: GPL-3.0-or-later

CC := clang
CFLAGS ?= -std=c11 -Wall -Wextra -O2
LDLIBS ?= -lbluetooth

SRC := src/main.c src/cli.c src/controller.c src/protocol.c src/frame.c src/crc16.c
OBJ := $(SRC:.c=.o)
BIN := freebuds

.PHONY: all clean

all: $(BIN)

$(BIN): $(OBJ)
	$(CC) $(CFLAGS) -o $@ $(OBJ) $(LDLIBS)

src/%.o: src/%.c
	$(CC) $(CFLAGS) -c -o $@ $<

clean:
	rm -f $(OBJ) $(BIN)
