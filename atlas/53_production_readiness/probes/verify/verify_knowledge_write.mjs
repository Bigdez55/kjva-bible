/**
 * Runtime verify probe for CAP_KNOWLEDGE_NOTE_WRITE.
 *
 * Exercises the REAL knowledgeNoteWrite() (apps/backend/mcp/src/tools/knowledge-note-write.ts)
 * against a THROWAWAY temp SQLite file. The implementation writes directly to the
 * on-disk SQLite file via node:sqlite (DatabaseSync) — see that file's header for
 * why it is node:sqlite and not better-sqlite3 (the shell's native addon is
 * unbuilt; node:sqlite produces the identical file format). This probe therefore
 * uses node:sqlite too, so the table it creates and the row it reads back are the
 * exact same dialect/format the tool writes.
 *
 * Steps:
 *   0. mkdtemp a temp DIR; point ATLAS_SQLITE_PATH at a db file inside it.
 *      Create a MINIMAL knowledge_notes table matching schema.ts COLUMNS.
 *      IMPORTANT: omit the `REFERENCES tenants(id)` FK — the tool runs
 *      `PRAGMA foreign_keys = ON`, and there is no tenants table here, so a real
 *      FK clause would make op:create's INSERT fail. The task asks for columns.
 *   1. op:create — insert a note; read it back from a FRESH connection and assert
 *      title/tenant_id/body/note_type/status/source_rank + backlinks JSON.
 *   2. op:update — patch title+body; read back and assert the patch applied AND an
 *      untouched field (note_type) is intact; updated_at advanced.
 *   3. op:link — merge backlinks/relatedGraphNodes; assert dedup + union.
 *   4. IDOR gate (the load-bearing safety property): op:update with a DIFFERENT
 *      tenantId on the same id MUST throw and MUST NOT mutate the row.
 *   5. Input validation: op:create without title is rejected; missing tenantId is
 *      rejected.
 *
 * Prints VERIFY_OK on success and removes the whole temp dir (incl. WAL sidecars).
 *
 * Run: ATLAS_RUNTIME=desktop ATLAS_SQLITE_PATH=/tmp/<f>.db \
 *      node --experimental-strip-types verify_knowledge_write.mjs
 * (ATLAS_SQLITE_PATH is also set by this script before the first call, so the env
 *  prefix is belt-and-suspenders. ATLAS_RUNTIME is irrelevant to this tool — it
 *  reads ATLAS_SQLITE_PATH directly and never calls getDb() — set only to follow
 *  the run instruction literally.)
 */

import { DatabaseSync } from "node:sqlite";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

function assert(cond, msg) {
  if (!cond) throw new Error(`ASSERT FAILED: ${msg}`);
}

// Read one row back through a fresh connection so we are testing on-disk state,
// not the tool's return value or any in-memory cache.
function readRow(dbPath, id, tenantId) {
  const db = new DatabaseSync(dbPath);
  try {
    return db
      .prepare(
        `SELECT id, tenant_id, title, note_type, status, source_rank, excerpt,
                body, backlinks, related_graph_nodes, created_at, updated_at
           FROM knowledge_notes WHERE id = ? AND tenant_id = ?`,
      )
      .get(id, tenantId);
  } finally {
    db.close();
  }
}

async function main() {
  const sandbox = mkdtempSync(path.join(tmpdir(), "atlas-knowledge-write-"));
  const dbPath = path.join(sandbox, "atlas.db");
  // resolveDbPath() reads ATLAS_SQLITE_PATH at call time — set BEFORE importing
  // is unnecessary (the import has no side effects), but set before the FIRST call.
  process.env.ATLAS_SQLITE_PATH = dbPath;

  // Dynamic import AFTER env is set (harmless either way; keeps intent explicit).
  const { knowledgeNoteWrite } = await import(
    "../../../../../apps/backend/mcp/src/tools/knowledge-note-write.ts"
  );

  try {
    // --- 0. Minimal table matching schema.ts COLUMNS (no tenants FK). ---
    {
      const db = new DatabaseSync(dbPath);
      try {
        db.exec(
          `CREATE TABLE knowledge_notes (
             id TEXT PRIMARY KEY,
             tenant_id TEXT NOT NULL,
             title TEXT NOT NULL,
             note_type TEXT,
             status TEXT,
             source_rank TEXT,
             excerpt TEXT,
             body TEXT,
             backlinks TEXT,
             related_graph_nodes TEXT,
             created_at INTEGER NOT NULL,
             updated_at INTEGER NOT NULL
           )`,
        );
      } finally {
        db.close();
      }
    }

    const tenantA = "tenant:alpha";
    const tenantB = "tenant:beta";
    const noteId = "note:probe-001";

    // --- 1. op:create ---
    const created = knowledgeNoteWrite({
      tenantId: tenantA,
      op: "create",
      id: noteId,
      title: "Probe Note",
      body: "initial body",
      noteType: "decision",
      status: "active",
      excerpt: "short",
      backlinks: ["note:a", "note:b"],
      relatedGraphNodes: ["sys:graph"],
    });
    assert(created.written === true, "create.written must be true");
    assert(created.op === "create", "create.op must be 'create'");
    assert(created.id === noteId, `create.id must echo ${noteId}, got ${created.id}`);

    const row1 = readRow(dbPath, noteId, tenantA);
    assert(row1, "created row must exist on disk");
    assert(row1.tenant_id === tenantA, `tenant_id must be ${tenantA}, got ${row1.tenant_id}`);
    assert(row1.title === "Probe Note", `title must persist, got ${row1.title}`);
    assert(row1.body === "initial body", `body must persist, got ${row1.body}`);
    assert(row1.note_type === "decision", `note_type must persist, got ${row1.note_type}`);
    assert(row1.status === "active", `status must persist, got ${row1.status}`);
    assert(row1.source_rank === "primary", `source_rank must default to 'primary', got ${row1.source_rank}`);
    assert(row1.excerpt === "short", `excerpt must persist, got ${row1.excerpt}`);
    const bl1 = JSON.parse(row1.backlinks);
    assert(Array.isArray(bl1) && bl1.length === 2 && bl1[0] === "note:a" && bl1[1] === "note:b",
      `backlinks JSON must be ["note:a","note:b"], got ${row1.backlinks}`);
    const rg1 = JSON.parse(row1.related_graph_nodes);
    assert(Array.isArray(rg1) && rg1[0] === "sys:graph", `related_graph_nodes must persist, got ${row1.related_graph_nodes}`);
    assert(typeof row1.created_at === "number" && row1.created_at > 0, "created_at must be a positive integer");

    const createdAt = row1.created_at;

    // --- 2. op:update — patch title+body, leave note_type intact. ---
    const updated = knowledgeNoteWrite({
      tenantId: tenantA,
      op: "update",
      id: noteId,
      title: "Probe Note (edited)",
      body: "edited body",
    });
    assert(updated.written === true, "update.written must be true");
    assert(updated.op === "update", "update.op must be 'update'");

    const row2 = readRow(dbPath, noteId, tenantA);
    assert(row2.title === "Probe Note (edited)", `update must change title, got ${row2.title}`);
    assert(row2.body === "edited body", `update must change body, got ${row2.body}`);
    assert(row2.note_type === "decision", `update must LEAVE note_type intact, got ${row2.note_type}`);
    assert(row2.status === "active", `update must LEAVE status intact, got ${row2.status}`);
    assert(row2.created_at === createdAt, "update must NOT change created_at");
    assert(row2.updated_at >= createdAt, "update must advance/keep updated_at >= created_at");

    // --- 3. op:link — merge backlinks (dedup) + relatedGraphNodes (union). ---
    const linked = knowledgeNoteWrite({
      tenantId: tenantA,
      op: "link",
      id: noteId,
      backlinks: ["note:b", "note:c"], // "note:b" already present -> deduped
      relatedGraphNodes: ["sys:graph", "sys:vault"], // "sys:graph" already present
    });
    assert(linked.written === true, "link.written must be true");
    assert(linked.op === "link", "link.op must be 'link'");

    const row3 = readRow(dbPath, noteId, tenantA);
    const bl3 = JSON.parse(row3.backlinks);
    assert(
      bl3.length === 3 && bl3.includes("note:a") && bl3.includes("note:b") && bl3.includes("note:c"),
      `link must merge+dedup backlinks to [a,b,c], got ${row3.backlinks}`,
    );
    const rg3 = JSON.parse(row3.related_graph_nodes);
    assert(
      rg3.length === 2 && rg3.includes("sys:graph") && rg3.includes("sys:vault"),
      `link must merge+dedup relatedGraphNodes, got ${row3.related_graph_nodes}`,
    );
    // link must NOT clobber title/body set by the prior update.
    assert(row3.title === "Probe Note (edited)", "link must not clobber title");
    assert(row3.body === "edited body", "link must not clobber body");

    // --- 4. IDOR gate: a DIFFERENT tenant cannot mutate this note. ---
    let idorBlocked = false;
    try {
      knowledgeNoteWrite({
        tenantId: tenantB, // wrong tenant
        op: "update",
        id: noteId,
        title: "HIJACKED",
      });
    } catch (err) {
      idorBlocked = /not found in tenant scope/i.test(String(err && err.message));
    }
    assert(idorBlocked, "cross-tenant update MUST be rejected (IDOR gate)");
    // And the row owned by tenantA must be UNCHANGED.
    const rowAfterIdor = readRow(dbPath, noteId, tenantA);
    assert(rowAfterIdor.title === "Probe Note (edited)", "IDOR attempt must NOT mutate the victim row's title");

    // Cross-tenant LINK is likewise rejected.
    let idorLinkBlocked = false;
    try {
      knowledgeNoteWrite({ tenantId: tenantB, op: "link", id: noteId, backlinks: ["note:evil"] });
    } catch (err) {
      idorLinkBlocked = /not found in tenant scope/i.test(String(err && err.message));
    }
    assert(idorLinkBlocked, "cross-tenant link MUST be rejected (IDOR gate)");

    // --- 5. Input validation. ---
    let noTitleRejected = false;
    try {
      knowledgeNoteWrite({ tenantId: tenantA, op: "create", id: "note:notitle" });
    } catch (err) {
      noTitleRejected = /title is required/i.test(String(err && err.message));
    }
    assert(noTitleRejected, "op:create without title MUST be rejected");

    let noTenantRejected = false;
    try {
      knowledgeNoteWrite({ tenantId: "", op: "create", title: "x" });
    } catch (err) {
      noTenantRejected = /tenantId is required/i.test(String(err && err.message));
    }
    assert(noTenantRejected, "missing tenantId MUST be rejected");

    let updateNoIdRejected = false;
    try {
      knowledgeNoteWrite({ tenantId: tenantA, op: "update", title: "x" });
    } catch (err) {
      updateNoIdRejected = /id is required/i.test(String(err && err.message));
    }
    assert(updateNoIdRejected, "op:update without id MUST be rejected");

    console.log("VERIFY_OK");
  } finally {
    // rmSync the whole temp dir — WAL leaves -wal/-shm sidecars next to the .db.
    rmSync(sandbox, { recursive: true, force: true });
  }
}

main().catch((err) => {
  console.error("VERIFY_FAIL:", err && err.message ? err.message : err);
  process.exit(1);
});
