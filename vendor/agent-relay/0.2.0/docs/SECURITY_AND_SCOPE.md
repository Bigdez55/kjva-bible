# Security and scope — 0.2.0

The API and filesystem control account are separate trust levels. Relay enforces
workflow tokens, resource fences, declared context freshness and receipts at its
gateway. It does not isolate hostile native code from the OS account that owns
its database, key or verifier. Use a separate account/OS sandbox and an external
operator boundary for hostile execution; never distribute owner.key to providers.

The new network listener is explicitly enabled, TLS 1.3 mutually authenticated,
bounded to 16 handlers with handshake/read limits, and serves worker operations
only. Each certificate fingerprint is bound to a current grant. Expiry/revocation
is rechecked within every read/command transaction, including command replay.
All durable authority stays on one host; no offline/replicated writable database
is supported. Keep that host and its local filesystem trusted. See NETWORK.md.

The installed MCP adapter classifies native vendor tools and hidden compaction as
outside observation. Context epochs and actual serialized-body hashes govern its
own tools, not a model's comprehension. Provider configuration must not advertise
this adapter as a universal native-tool interception layer.

Migration rotates source and target generations, never rewrites historical event
bytes, and holds the target until evaluated acceptance and explicit reconciliation.
Preactivation rollback retires the target first; newer evidence blocks rollback.
Review HMAC keys stay outside agent context. They are local integrity mechanisms,
not a publisher or human identity attestation. See MIGRATION.md and ACCEPTANCE.md.

No embedded credentials, TLS private keys or preapproved production exceptions
are shipped. Tests generate private, disposable certificates and fixture review
keys; those fixture approvals never appear in the release acceptance report.

The active storage/library environment is in RELEASE_VERIFICATION.json. Unsafe
WAL is refused; unpatched linked SQLite falls back to DELETE/EXTRA. Physical power
loss, macOS hardware, active-active consensus, distributed SQLite, actual native
provider lifecycle and long-duration endurance are not silently certified here.

The previous release's full scope document is retained as
SECURITY_AND_SCOPE_v0.1_REFERENCE.md for lineage, not as current capability status.
