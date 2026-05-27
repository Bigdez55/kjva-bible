# BSS Bloat Audit — 2026-03-29

## Summary
XENOS kernel BSS = 286 MB (PT_LOAD MemSiz=0x11F0B000). AetherBoot rejects at 256 MB limit.

## Top BSS Contributors (verified from source)

| # | Array | Location | Per-Element | Count | BSS MB |
|---|-------|----------|-------------|-------|--------|
| 1 | s_blob_index | orange_store.c:295 | 56B (xblob_index_entry_t) | 1,048,576 | 56.0 |
| 2 | s_store_disk | orange_store.c:120 | 1B | 16,777,216 | 16.0 |
| 3 | g_tcbs | tcp.c:251 | ~92KB (2x16KB ring + rexmit + ooo) | 128 | 11.5 |
| 4 | s_wl_vocab | weights_loader.c:247 | 68B (id+score+str[60]) | 128,256 | 8.3 |
| 5 | s_blob_disk | orange_store.c:167 | 1B | 8,388,608 | 8.0 |
| 6 | s_framebuf | video.c:82 | 4B | 2,073,600 | 7.9 |
| 7 | s_page_table | vdram_migrate_phys.c:71 | 24B (vdram_page_desc_t) | 65,536 | 1.5 |
| 8 | g_stroke_edges | vector.c:1025 | 20B | 65,536 | 1.25 |
| 9 | s_blob_gc_log | orange_store.c:296 | 56B | 16,384 | 0.9 |
| 10 | s_canvas+undo | imageedit.c:74-75 | 4B each | 240,000 | 0.9 |
| 11 | g_edges | vector.c:208 | 20B | 32,768 | 0.625 |
| 12 | TLS buffers (5x) | tls13.c:202-442 | 1B | ~100KB total | 0.1 |
| 13 | SMB buffers | smb_client.c (many) | 1B | ~200KB total | 0.2 |
| 14 | SFX PCM bufs | system_sounds.c:77,171 | 2B (int16_t) | 88200*2 | 0.34 |
| 15 | Settings pool | settings_init.c:60 | 1B | 262,144 | 0.25 |
| 16 | ICC profile buf | settings_color_profile.c:179 | 1B | 262,144 | 0.25 |
| **Subtotal** | | | | | **~114 MB** |
| Remaining ~170MB | 63 xshell files + orange apps + kernel drivers + misc | | | | ~172 MB |

## Root Cause
All subsystem static arrays are linked into the kernel ELF BSS. The XBLOB 1M-entry index alone (56 MB) is sized for production blob storage but allocated as a kernel-embedded static array.

## Fix Options
1. **Raise kern_span to 512MB** (aetherboot.c:862) — minimal change, physical memory pressure risk
2. **Dynamic allocation** — move top offenders to heap_alloc after heap_init (Step 6)
3. **Reduce array sizes** — XBLOB_INDEX_SLOTS to 64K (3.5MB), TCP_TCB_MAX to 32 (2.9MB)
4. **Separate user-space** — orange_store, video, imageedit should not be kernel-resident
