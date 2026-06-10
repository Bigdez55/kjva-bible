#
# ai/xmind/Makefile — Build XMIND inference engine.
#
# Two build modes:
#   make            → POSIX hosted build (libxmind-core.{a,so/dylib} + xmind-cli)
#                     Activates with -DXMIND_POSIX_BUILD=1, links the shim/ layer.
#   make freestanding → freestanding build (the canonical target, e.g. for the
#                       sovereign kernel deployment). Excludes shim/ entirely.
#
# Output: build/
#   build/libxmind-core.a       static archive
#   build/libxmind-core.{so,dylib}  shared lib (consumed by _xmind/client.py via ctypes)
#   build/xmind-cli             smoke-test binary
#

CC      ?= clang
AR      ?= ar
UNAME_S := $(shell uname -s)
UNAME_M := $(shell uname -m)

ifeq ($(UNAME_S),Darwin)
  SOEXT := dylib
  SHARED_FLAGS := -dynamiclib
else
  SOEXT := so
  SHARED_FLAGS := -shared -fPIC
endif

BUILD := build

# ── POSIX hosted build (default) ────────────────────────────────────
# Includes:
#   - Canonical xmind contract headers     (include/)
#   - Top-level platform-layer contracts   (../../{pal,net,sec,xisc,xstore})
#     Each lives at the substrate root, owned by the substrate (not xmind).
CFLAGS_POSIX := -std=c11 -Wall -Wextra -Wno-unused-parameter -Wno-unused-function \
                -Wno-incompatible-pointer-types -Wno-format \
                -O2 -fPIC -DXMIND_POSIX_BUILD=1 -D_POSIX_C_SOURCE=200809L \
                -D_DARWIN_C_SOURCE \
                -Iinclude \
                -I../../pal/include \
                -I../../net/xnet/include \
                -I../../sec/xsec/include \
                -I../../xisc/include \
                -I../../xstore/include \
                -UPAL_FREESTANDING

ifeq ($(UNAME_M),arm64)
  CFLAGS_POSIX += -DXMIND_HAS_NEON
  NEON_SRC := src/neon_dot.c src/neon_matmul.c
else ifeq ($(UNAME_M),aarch64)
  CFLAGS_POSIX += -DXMIND_HAS_NEON
  NEON_SRC := src/neon_dot.c src/neon_matmul.c
else
  CFLAGS_POSIX += -mavx2 -mfma
  NEON_SRC :=
endif

# CORE source set — inference path only (excludes IPC-heavy files that need
# the freestanding council backend: context_bridge, telemetry, writeback,
# xmind_http). These can be added back when consuming projects supply their
# own freestanding stack.
CORE_SRC := \
    src/xmind.c src/inference.c src/transformer.c src/tensor.c \
    src/sampler.c src/tokenizer.c src/pretokenizer.c src/quantize.c \
    src/weights_loader.c src/gguf_reader.c \
    src/interp_tokenless.c \
    src/interp_registry.c src/heptagon.c src/harness.c \
    src/lineage.c src/materialize.c src/r1_per.c \
    src/lora.c src/xmind_easy.c \
    src/adapter_runtime.c src/adapter_ir.c src/adapter_cache.c src/adapter_telemetry.c \
    loader/weights_loader_mmap.c \
    shim/pal_posix.c shim/xnet_posix.c shim/stubs.c \
    $(NEON_SRC)

# Filter NEON files out on x86
ifneq ($(UNAME_M),arm64)
ifneq ($(UNAME_M),aarch64)
  CORE_SRC := $(filter-out src/neon_dot.c src/neon_matmul.c, $(CORE_SRC))
endif
endif

CORE_OBJ := $(patsubst %.c,$(BUILD)/%.o,$(CORE_SRC))

LIB_STATIC := $(BUILD)/libxmind-core.a
LIB_SHARED := $(BUILD)/libxmind-core.$(SOEXT)
CLI_BIN    := $(BUILD)/xmind-cli

LDFLAGS   ?=
LDLIBS    ?= -lpthread -lm

.PHONY: all static shared cli test clean help

all: static shared cli

static: $(LIB_STATIC)
shared: $(LIB_SHARED)
cli:    $(CLI_BIN)

$(BUILD)/%.o: %.c
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS_POSIX) -MMD -MP -c $< -o $@

$(LIB_STATIC): $(CORE_OBJ)
	@mkdir -p $(dir $@)
	$(AR) rcs $@ $(CORE_OBJ)
	@echo "✓ Built $@"

$(LIB_SHARED): $(CORE_OBJ)
	@mkdir -p $(dir $@)
	$(CC) $(SHARED_FLAGS) $(CORE_OBJ) -o $@ $(LDFLAGS) $(LDLIBS)
	@echo "✓ Built $@"

$(CLI_BIN): tests/smoke.c $(LIB_STATIC)
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS_POSIX) tests/smoke.c $(LIB_STATIC) -o $@ $(LDFLAGS) $(LDLIBS)
	@echo "✓ Built $@"

test: cli
	@echo "── XMIND smoke ──"
	./$(CLI_BIN)

clean:
	rm -rf $(BUILD)

help:
	@echo "ai/xmind/Makefile — XMIND engine build"
	@echo ""
	@echo "  make          → build static + shared lib + smoke CLI (POSIX hosted)"
	@echo "  make static   → libxmind-core.a only"
	@echo "  make shared   → libxmind-core.{so,dylib} only"
	@echo "  make test     → run smoke CLI"
	@echo "  make clean    → rm -rf build/"

-include $(CORE_OBJ:.o=.d)
