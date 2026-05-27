# Skills Wave 2 Extraction — XISC, Cloud, Toolchain, Pkg, Net

## Date: 2026-03-31

## Domains Covered
- XISC native layer: 8 C files (process, channel, vnode, vmar, vmo, handles, wait, audit)
- XISC personalities: Linux syscall dispatch (80+ syscalls), ELF loader, WASM stub, translator_manager.py
- XISC conformance: xkabi_conformance.c (26 tests), test_memory.py (intent model)
- Cloud platform services: registry, gate, admission webhook, identity, sync, provenance, TEI calculator
- Cloud infrastructure: genos_cloud.py, cloud_controld.py, vdram_rdma.py, godrive_syncd.c, godrive_file_delta.c
- Gateway: qp_relay.c (zero-copy IB/RoCEv2/UET), entropy_classifier.c
- Toolchain: xcc_lexer.c, xcc_parser.c, xcc_preproc.c, xcc_irgen.c, xcc_typeck.c
- Build: xbuild.c, graph.c, executor.c, scanner.c
- Package manager: xpkg.c (orchestrator + verify + refusal gate)
- Network: captive_portal.c, vpn.c, smb_client.c
- vDRAM: libvdram/src/vdram.c

## Total Skills: 60
## Key Patterns Observed
- All XISC native code is freestanding C, no libc
- PAL abstraction layer used throughout (12/14 subsystems in vdram.c alone)
- Cloud services use FastAPI + SQLAlchemy + Ed25519 JWT
- XCC compiler is self-hosting with freestanding + host dual-mode
- XBUILD uses DAG topo sort + mtime-based incremental compilation
- XPKG has refusal gate policy engine with per-gate enable/force flags
