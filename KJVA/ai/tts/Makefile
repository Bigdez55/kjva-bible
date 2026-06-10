#
# ai/tts/Makefile -- Hosted ctypes build for the XTTS formant synthesizer.
#
# This Makefile builds ONLY the hosted shared library consumed by
# tts_bridge.py via ctypes. It does NOT replace the canonical freestanding
# kernel build documented at the top of tts_engine.c (that build excludes
# pal_shim.c and provides pal_console_printf from the PAL backend).
#
#   make            -> build/libtts.{dylib,so}   (shared lib for ctypes)
#   make test       -> build the lib, then run the Python bridge self-test
#   make clean      -> remove build/
#
# The shared library is gitignored-by-convention (binary artifact); only the
# source (tts_engine.c, pal_shim.c) is tracked. Rebuild with `make` anywhere
# clang is available.
#

CC      ?= clang
UNAME_S := $(shell uname -s)

ifeq ($(UNAME_S),Darwin)
  SOEXT        := dylib
  SHARED_FLAGS := -dynamiclib
else
  SOEXT        := so
  SHARED_FLAGS := -shared -fPIC
endif

BUILD := build
LIB   := $(BUILD)/libtts.$(SOEXT)

# Hosted build: PAL_FREESTANDING stays UNDEFINED, so libc (string.h) is used.
# -Wno-unused-* keeps the engine's freestanding-oriented helpers quiet.
CFLAGS := -std=c11 -O2 -fPIC \
          -Wall -Wextra \
          -Wno-unused-parameter -Wno-unused-function \
          -I.

SRCS := tts_engine.c pal_shim.c

.PHONY: all test clean
all: $(LIB)

$(LIB): $(SRCS) tts_engine.h | $(BUILD)
	$(CC) $(CFLAGS) $(SHARED_FLAGS) -o $@ $(SRCS)
	@echo "[tts] built $@"

$(BUILD):
	@mkdir -p $(BUILD)

test: $(LIB)
	@python3 tts_bridge.py

clean:
	@rm -rf $(BUILD)
	@echo "[tts] cleaned"
