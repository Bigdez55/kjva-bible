# File Upload and Media Processing

> Skill: `SKILL_FILE_UPLOAD_MEDIA_001` · Layer: backend · Tier: active
> Owns Production-Readiness Corpus category **File Upload & Media Processing**
> (`PRC.FILE_UPLOAD_AND_MEDIA_PROCESSING`).

## When to use

Invoke this discipline whenever code accepts a user-supplied file or processes
media derived from one:

- Multipart upload endpoints and presigned direct-to-storage uploads.
- Object-storage wiring (S3, GCS, Azure Blob, R2) for user files.
- Image / video / audio / document transcoding, resizing, and thumbnailing.
- Avatar, attachment, bulk-import, and document-upload features.
- Any path that generates or serves download / preview / CDN URLs.
- "Fetch file from URL" / remote-import features.
- Auditing an existing upload or media path for production readiness.

## Why this exists

User uploads are the single richest attack surface in most applications. A naive
upload handler simultaneously exposes memory-exhaustion DoS, stored XSS, path
traversal, content-type spoofing, SSRF, malware distribution, decompression
bombs, and PII leakage through file metadata. This skill owns the
`File Upload & Media Processing` category of the Production-Readiness Corpus,
which had **zero coverage** (`coverage_status: NONE`) before this skill existed,
and teaches how to satisfy each of its hand-authored items.

## Core principle

Treat every byte the client sends — the body, the filename, the extension, the
Content-Type, and the file's internal structure — as hostile and unverified
until your server proves otherwise. **Validate by content, store privately,
serve safely, scan before serving, and process in an idempotent sandbox.**

---

## Key practices by corpus section

### Section 1 — Upload Security & Validation

Corpus items: server-side size limits; content-based type validation; filename
sanitization; storage outside web root; safe serving headers; block/neutralize
executables and scripts; harden parsing; sanitize SVG; auth on endpoints;
presigned URLs; per-tenant rate limit and quota; metadata stored separately.

- Enforce a maximum upload size in **two places**: the edge/reverse proxy
  (`client_max_body_size`, gateway limit) and the application handler. Never
  rely on client-side limits alone.
- **Stream** uploads to disk or object storage; never read the whole body into
  memory before the size check. Abort the stream the instant the limit is hit.
- Determine the real type by inspecting **magic bytes / file signature**, then
  match it against an **allowlist** of accepted MIME types. A blocklist is
  always incomplete; the extension and `Content-Type` header are hints, not
  proof.
- Generate a **server-side random opaque storage key** (UUID + computed
  extension). Never let the client filename become a path or key — that is path
  traversal and overwrite waiting to happen. Keep the display filename as
  sanitized metadata only.
- Store uploads **outside the web root**, in object storage with **private
  ACLs** (default deny). Serve private media only via **scoped, short-lived
  presigned URLs**.
- Serve files with safe `Content-Type` and `Content-Disposition: attachment`
  headers; **sanitize SVG** (strip embedded scripts) and treat HTML as hostile
  so a stored payload cannot run in your origin (stored XSS).
- **Authenticate and authorize** upload endpoints; apply **per-user/per-tenant
  rate limits and storage quotas**, rejecting uploads that would exceed quota.
- Store file **metadata separately** from content with integrity checks
  (checksum / content hash).

### Section 2 — Malware & Content Scanning

Corpus items: malware scanning on all files; quarantine until scan completes;
content moderation; CSAM scanning where applicable; decompression-bomb and
nested-archive limits; polyglot detection; EXIF stripping; PDF/Office macro
scanning; fail closed with alerting; re-scan on signature update; scan logging;
quarantine/remediation workflow.

- **Scan every upload** for malware (ClamAV, vendor AV, or cloud scanning) and
  **quarantine** it until the scan passes before it is available to anyone.
- **Fail closed**: if a scan fails or times out, the file is **not served**, and
  the failure raises an alert and an auditable log entry.
- Enforce **decompression-bomb and nested-archive limits** (max archive depth,
  max expanded size, max image dimensions/pixels/frames) before and during
  decode.
- **Detect polyglot files** (valid as more than one type) and reject them.
- **Strip EXIF and sensitive metadata** (GPS, device IDs, author) from public
  images. Scan **PDF and Office documents for active content / macros**.
- Route user-facing media to **content moderation** and, where applicable,
  **CSAM scanning** (see Trust & Safety category). Provide a **re-scan**
  capability when signatures update and a documented **quarantine and
  remediation workflow**.

### Section 3 — Media Processing Pipeline

Corpus items: robust image processing; responsive variants (WebP/AVIF); video
transcoding (HLS/DASH); thumbnails/previews; async off the request path;
idempotent retryable jobs; dead-letter + alerting; transcode timeouts;
autoscaling; original retained/derivatives regenerable; watermarking;
CPU/GPU cost modeled.

- Process media with a **robust library or service** (sharp/libvips, ffmpeg,
  managed transcoder) — never shell out with an **unsanitized filename or
  untrusted argument**; use argument arrays and pass the safe storage key.
- Run processing **asynchronously off the request path** in **idempotent,
  retryable jobs** keyed by an idempotency key so retries never create
  duplicate or corrupt derivatives.
- Handle failures with a **dead-letter queue and alerting**; bound
  **large-file/long-running transcodes with timeouts**; let the pipeline
  **autoscale** with upload volume.
- Generate **responsive image variants** (multiple sizes, WebP/AVIF),
  **thumbnails/previews**, and **adaptive-bitrate video** (HLS/DASH) where
  needed. Apply **watermarking** where required.
- Keep the **original retained or re-derivable** and **derivatives
  regenerable**. **Model and monitor CPU/GPU processing cost**.

### Section 4 — Storage, Delivery & Resilience

Corpus items: object storage with versioning; CDN for public media; signed URLs
with expiry; lifecycle policies; range-request streaming; cross-region
replication for DR; access logging; orphaned-file cleanup; bandwidth/egress
monitoring; broken-reference detection; tested backup/restore; deletion
propagates to CDN and replicas.

- Store media in **object storage with versioning** where needed; deliver public
  media via **CDN**; serve private media via **signed URLs with appropriate
  expiry**.
- Support **range requests** for streaming large media; apply **storage
  lifecycle policies** for cold/obsolete media; replicate **cross-region** for
  DR; enable **storage access logging** for sensitive media.
- Run **orphaned-file cleanup** (uploaded but never attached); monitor
  **bandwidth/egress cost** and **broken media references**; **test backup and
  restore**; ensure **deletion propagates to the CDN and all replicas**.

### Cross-cutting — Secrets & Observability

- Load storage credentials and URL-signing keys from a **secret manager** or
  environment — never hardcoded literals in source.
- Emit **structured logs with a correlation ID** following a file across upload,
  scan, transcode, and serve stages so incidents are traceable.

---

## Workflow / checklist

1. **Limit at the edge.** Proxy + handler max size; stream, do not buffer.
2. **Identify the real type.** Magic-byte sniff against a MIME allowlist.
3. **Rename.** Server-generated opaque key; client filename is metadata only.
4. **Store private.** Object storage, private ACL, outside web root.
5. **Scan + quarantine.** No file is available until malware scan passes (fail closed).
6. **Strip metadata.** Remove EXIF/PII; scan docs for macros; detect polyglots.
7. **Process sandboxed.** Robust library, argument arrays, bomb/timeout limits.
8. **Make it idempotent.** Idempotency key per job; dead-letter + alerting on failure.
9. **Serve safely.** Attachment + safe headers / sanitized SVG; short-lived signed URLs.
10. **Deliver.** CDN for public media; range requests; lifecycle + replication.
11. **Rate-limit + quota.** Per-identity caps; SSRF allowlist for URL imports.
12. **Secrets + logs.** Keys from secret manager; correlation IDs end to end.
13. **Lifecycle.** Orphan cleanup; deletion propagates to CDN and all replicas.

---

## Anti-patterns

| Anti-pattern | Why it fails | Do instead |
| --- | --- | --- |
| Trusting the file extension or `Content-Type` | Content-type spoofing; `.png` can hold a script | Sniff magic bytes against a MIME allowlist |
| Saving under the client-supplied filename | Path traversal (`../`) and overwrite | Server-generated random opaque key |
| Buffering the whole body, then checking size | Memory-exhaustion DoS | Stream and abort at the limit |
| Public object URLs for private files | Enumeration and data leak | Private ACL + short-lived signed URLs |
| Serving SVG/HTML from the app origin | Stored XSS executes in your origin | Sanitize SVG / attachment + safe headers |
| `ffmpeg -i $userFilename` via shell string | Command/argument injection | Argument arrays + safe server key, robust lib |
| Decoding without dimension/archive caps | Decompression / pixel-flood bomb crashes worker | Max dimensions, pixels, archive depth, output size |
| Non-idempotent transcode jobs | Retries create duplicate/corrupt derivatives | Idempotency key per job + dead-letter queue |
| Scan failures fail open | Distributes malware to other users | Quarantine + fail closed + alerting |
| Single-type validation only | Polyglot file passes as image yet is a script | Detect and reject polyglots |
| Hardcoded S3 keys / signing secrets | Leak via VCS and logs | Secret manager or environment |
| "Import from URL" with no allowlist | SSRF to internal/metadata endpoints | Destination allowlist; block private ranges |
| Deleting only the DB row | Orphaned bytes remain on CDN/replicas | Deletion propagates to storage, CDN, replicas |

---

## Related

- `SKILL_PRODUCTION_READINESS_AUDIT_001` — parent audit skill; this skill owns
  one of its corpus categories and fixes its NO-SKILL GAP.
- `SKILL_FIND_BEFORE_CREATE_001` — search before adding a new upload path.
- `SKILL_AUTOMATED_REGRESSION_TESTING_001` — encode the validation tests as
  regression cases.
- `SKILL_CI_PIPELINE_001` — run upload-security checks in the pipeline.
- `SKILL_DRIFT_DETECTION_001` — detect when an upload path drifts from these
  standards.
- Adjacent corpus categories: Trust & Safety / Content Moderation,
  Rate Limiting & Quotas, Data & Privacy Compliance, Caching & CDN Strategy.
