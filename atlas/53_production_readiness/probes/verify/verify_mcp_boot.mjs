/**
 * Runtime BOOT + SECURITY probe for the ATLAS MCP server.
 *
 * Proves the SERVER (not just the tool source files) is reachable: it imports
 * createMcpServer from apps/backend/mcp/src/server-factory.ts and CONSTRUCTS the
 * server. That construction is the single thing that was broken before the fix —
 * it imports `Server` from @modelcontextprotocol/sdk and wires the request
 * handlers. When the SDK dist was dehydrated by OneDrive (empty dist/esm/server,
 * missing package.json), this import threw ERR_MODULE_NOT_FOUND and the server
 * could not boot at all. So: construct succeeds => SDK rehydrated + server wires.
 *
 * Layered wiring proofs on top of construction:
 *   1. The exported TOOL_LIST advertises the WRITE tools (atlas_repo_commit_push,
 *      atlas_knowledge_note_write, atlas_checklist_verdict_write).
 *   2. handleTool is reachable and a READ tool (atlas_graph_query, filesystem-backed
 *      so it always returns a non-error response on the real repo) returns a
 *      non-error response — proving the dispatch path executes, not just exists.
 *
 * SECURITY regression guards (added for #3 + #4):
 *   A. AUTH GATE — with NO ATLAS_API_KEY, a MUTATING tool (atlas_repo_file_write)
 *      is REFUSED at dispatch (isError + an auth message). With a key set, the
 *      same call is NOT auth-refused (it proceeds to confinement).
 *   B. TENANT CONFINEMENT — with a key set, a repoPath OUTSIDE the tenant's
 *      twin_root is rejected; a repoPath UNDER the tenant's twin_root is accepted
 *      (the write succeeds). Uses a throwaway temp SQLite DB + a seeded
 *      repo_connectors row, so it never touches the real ATLAS db.
 *   C. SSE TRANSPORT — POST /mcp/messages no longer returns the
 *      "stream is not readable" 400 (the global express.json() drain). Drives the
 *      real exported `app` in-process: GET /mcp/sse to obtain a session, then POST
 *      a JSON-RPC `initialize`, and assert a 2xx (202 Accepted) — proving the raw
 *      stream reaches handlePostMessage.
 *
 * Run: node --experimental-strip-types verify_mcp_boot.mjs   (from repo root)
 * Prints VERIFY_OK on success; exits nonzero + VERIFY_FAIL on failure.
 */

// Silence Node's "SQLite is an experimental feature" ExperimentalWarning emitted on
// stderr when node:sqlite is loaded transitively (via the knowledge tools). It is
// benign and otherwise becomes the last line of combined stdout+stderr, making the
// probe's recorded evidence tail read `(Use node --trace-warnings ...)` instead of
// the VERIFY_OK line. The PASS verdict is unaffected (the runner greps for the
// VERIFY_OK token anywhere in the combined output); this only keeps evidence legible.
process.removeAllListeners("warning");
process.on("warning", (w) => {
  if (w && w.name === "ExperimentalWarning" && /SQLite/i.test(String(w.message))) return;
  console.warn(w?.stack || String(w));
});

import { DatabaseSync } from "node:sqlite";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import http from "node:http";

/**
 * Raw HTTP GET that lets us set an ARBITRARY Host header. `fetch` treats Host as a
 * forbidden header and silently drops/overrides it, so the DNS-rebinding test must
 * use the low-level client to actually exercise the Host allowlist.
 */
function rawGet(port, pathName, hostHeader, extraHeaders = {}) {
  return new Promise((resolve, reject) => {
    const req = http.request(
      {
        host: "127.0.0.1",
        port,
        path: pathName,
        method: "GET",
        headers: { Host: hostHeader, ...extraHeaders },
      },
      (res) => {
        let body = "";
        res.on("data", (c) => (body += c));
        res.on("end", () => resolve({ status: res.statusCode, body }));
      },
    );
    req.on("error", reject);
    req.end();
  });
}

function assert(cond, msg) {
  if (!cond) throw new Error(`ASSERT FAILED: ${msg}`);
}

const REQUIRED_TOOLS = [
  "atlas_repo_commit_push",
  "atlas_knowledge_note_write",
  "atlas_checklist_verdict_write",
];

// --- isolate the DB BEFORE importing any module that resolves the db path. ---
// Confinement (tenantTwinRoots) reads repoConnectors via resolveDbPath(); pointing
// it at a throwaway file keeps the probe hermetic (never the real ATLAS db).
const sandbox = mkdtempSync(path.join(tmpdir(), "atlas-mcp-boot-"));
const dbPath = path.join(sandbox, "atlas-probe.db");
process.env.ATLAS_SQLITE_PATH = dbPath;
process.env.ATLAS_RUNTIME = "desktop";
// Start with NO key so the auth-gate refuse-branch is exercised first.
delete process.env.ATLAS_API_KEY;
// Pin a deterministic port for the in-process HTTP/SSE test (Host allowlist needs it).
const SSE_PORT = 4399;
process.env.PORT = String(SSE_PORT);

const TENANT = "probe-tenant";

async function main() {
  // Dynamic import so a module-resolution failure (e.g. dehydrated SDK) surfaces
  // here as a caught VERIFY_FAIL with the exact error, not an unhandled crash.
  const mod = await import(
    "../../../../../apps/backend/mcp/src/server-factory.ts"
  );
  const { createMcpServer, TOOL_LIST, handleTool } = mod;

  assert(typeof createMcpServer === "function", "createMcpServer must be an exported function");
  assert(Array.isArray(TOOL_LIST), "TOOL_LIST must be an exported array");
  assert(typeof handleTool === "function", "handleTool must be an exported function");

  // --- 1. SERVER CONSTRUCTS (the load-bearing boot proof). ---
  // This is the line that imports `Server` from the SDK and calls setRequestHandler.
  // If the SDK is dehydrated/missing, this throws and the server cannot boot.
  const server = createMcpServer();
  assert(server, "createMcpServer() must return a truthy Server instance");
  // The MCP Server exposes connect(); its presence confirms we got a real Server.
  assert(typeof server.connect === "function", "constructed server must expose connect()");

  // --- 2. ListTools surface advertises the required tools. ---
  // (TOOL_LIST is the STATIC export — always whole, even with no key. The auth-gated
  // DYNAMIC ListTools surface is a separate path; this asserts the static manifest.)
  const names = new Set(TOOL_LIST.map((t) => t && t.name));
  for (const required of REQUIRED_TOOLS) {
    assert(names.has(required), `TOOL_LIST must include ${required} (got: ${[...names].join(", ")})`);
  }
  const toolCount = TOOL_LIST.length;
  assert(toolCount > 0, "TOOL_LIST must be non-empty");

  // --- 3. handleTool dispatch is reachable for a READ tool. ---
  // atlas_graph_query mode:"full" -> buildGraph() is filesystem-backed (safeList
  // fallbacks) and returns a non-error textResponse on the real repo. We assert the
  // response shape AND that it is NOT an error response.
  const res = await handleTool("atlas_graph_query", { mode: "full" });
  assert(res && Array.isArray(res.content), "handleTool must return a {content:[...]} response");
  assert(!res.isError, `READ tool atlas_graph_query must return a non-error response (got isError, text="${res.content?.[0]?.text?.slice(0, 120)}")`);
  assert(
    typeof res.content[0]?.text === "string" && res.content[0].text.length > 0,
    "atlas_graph_query response must carry non-empty text content",
  );

  // --- A. AUTH GATE: keyless mutating call is REFUSED. ---
  // No ATLAS_API_KEY is set (deleted above). A write tool MUST refuse at dispatch.
  delete process.env.ATLAS_API_KEY;
  const refused = await handleTool("atlas_repo_file_write", {
    tenantId: TENANT,
    repoPath: "/tmp/anywhere",
    filePath: "x.txt",
    content: "should not be written",
  });
  assert(refused?.isError === true, "keyless atlas_repo_file_write MUST return isError");
  assert(
    /ATLAS_API_KEY|auth|refus/i.test(refused.content?.[0]?.text ?? ""),
    `keyless write refusal must cite auth/ATLAS_API_KEY (got: "${refused.content?.[0]?.text?.slice(0, 160)}")`,
  );

  // --- B. TENANT CONFINEMENT: with a key, repoPath must be under twin_root. ---
  // Seed a throwaway DB: a tenant + a repo_connectors row whose twin_root is an
  // allowed dir under our sandbox. The confinement helper + ensureSchema read this
  // SAME db (ATLAS_SQLITE_PATH set above).
  const allowedRoot = path.join(sandbox, "allowed-repo");
  // ensureSchema (invoked transitively by the first confined write below) creates the
  // schema; but we must INSERT the connector row first, which itself needs the schema.
  // Trigger schema creation deterministically, then insert.
  const schemaMod = await import("../../../../../apps/backend/mcp/src/ensure-schema.ts");
  schemaMod.ensureSchema(TENANT);
  {
    const db = new DatabaseSync(dbPath);
    try {
      db.exec("PRAGMA foreign_keys = ON");
      const now = Date.now();
      db.prepare(
        `INSERT INTO repo_connectors
           (id, tenant_id, repo_name, repo_key, twin_root, created_at, updated_at)
         VALUES (?, ?, ?, ?, ?, ?, ?)`,
      ).run("rc:probe", TENANT, "probe-repo", "probe-key", allowedRoot, now, now);
    } finally {
      db.close();
    }
  }

  // Now set a key so the auth gate is satisfied and confinement is what's tested.
  process.env.ATLAS_API_KEY = "probe-secret-key";

  // Sanity: with a key, the SAME write is NOT auth-refused (it proceeds to confinement).
  // An OUTSIDE-tenant repoPath is still rejected — but with a CONFINEMENT message,
  // not the auth message.
  const outside = await handleTool("atlas_repo_file_write", {
    tenantId: TENANT,
    repoPath: "/tmp/not-in-tenant",
    filePath: "x.txt",
    content: "nope",
  });
  assert(outside?.isError === true, "out-of-tenant repoPath MUST return isError");
  assert(
    !/ATLAS_API_KEY/i.test(outside.content?.[0]?.text ?? ""),
    "with a key set, the rejection must NOT be the auth message (confinement should run)",
  );
  assert(
    /not within|allowed|twin_root|tenant/i.test(outside.content?.[0]?.text ?? ""),
    `out-of-tenant rejection must cite confinement (got: "${outside.content?.[0]?.text?.slice(0, 160)}")`,
  );

  // A repoPath UNDER the tenant's twin_root is ACCEPTED — the write succeeds.
  const inside = await handleTool("atlas_repo_file_write", {
    tenantId: TENANT,
    repoPath: allowedRoot,
    filePath: "note.txt",
    content: "written inside tenant work-tree\n",
  });
  assert(inside?.isError !== true, `in-tenant write must succeed (got error: "${inside.content?.[0]?.text?.slice(0, 160)}")`);
  assert(
    /"written": true/.test(inside.content?.[0]?.text ?? ""),
    `in-tenant write must report written:true (got: "${inside.content?.[0]?.text?.slice(0, 160)}")`,
  );

  // --- C. SSE TRANSPORT: POST /mcp/messages no longer 400s "stream is not readable". ---
  // Drive the REAL exported express app in-process. Key is set, so /mcp routes
  // accept (api-key middleware passes with the Bearer token).
  const apiMod = await import("../../../../../apps/backend/mcp/src/api-server.ts");
  const { app } = apiMod;
  assert(typeof app === "function", "api-server.ts must export the express `app`");

  const listener = app.listen(SSE_PORT, "127.0.0.1");
  await new Promise((resolve, reject) => {
    listener.once("listening", resolve);
    listener.once("error", reject);
  });

  // Declared out here so the finally can cancel it even when an assertion throws
  // AFTER the SSE stream is opened — otherwise the open socket would block
  // listener.close() and the probe would HANG to the harness timeout instead of
  // failing fast with VERIFY_FAIL.
  let reader = null;
  try {
    const base = `http://127.0.0.1:${SSE_PORT}`;
    const authHeader = { Authorization: `Bearer ${process.env.ATLAS_API_KEY}` };

    // 1) Open the SSE stream; read the `endpoint` event to learn the sessionId.
    const sseRes = await fetch(`${base}/mcp/sse`, {
      headers: { ...authHeader, Accept: "text/event-stream", Host: `127.0.0.1:${SSE_PORT}` },
    });
    assert(sseRes.status === 200, `GET /mcp/sse must return 200 (got ${sseRes.status})`);

    // Read just enough of the stream to capture the endpoint event, then bail.
    reader = sseRes.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let messagesPath = null;
    const deadline = Date.now() + 5000;
    while (!messagesPath && Date.now() < deadline) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const m = buffer.match(/event: endpoint\s*\ndata: (\/mcp\/messages\?sessionId=[^\s]+)/);
      if (m) messagesPath = m[1];
    }
    assert(messagesPath, "SSE stream must emit an `endpoint` event carrying the messages URL + sessionId");

    // 2) POST a JSON-RPC initialize to /mcp/messages. The REGRESSION: with the old
    //    global express.json(), getRawBody() saw an already-drained stream and the
    //    transport returned 400 "stream is not readable". Now the raw stream reaches
    //    handlePostMessage and a valid initialize returns 202 Accepted.
    const initBody = JSON.stringify({
      jsonrpc: "2.0",
      id: 1,
      method: "initialize",
      params: {
        protocolVersion: "2024-11-05",
        capabilities: {},
        clientInfo: { name: "atlas-verify-probe", version: "1.0.0" },
      },
    });
    const postRes = await fetch(`${base}${messagesPath}`, {
      method: "POST",
      headers: { ...authHeader, "Content-Type": "application/json", Host: `127.0.0.1:${SSE_PORT}` },
      body: initBody,
    });
    const postText = await postRes.text();

    // The load-bearing assertion: it is NOT the drained-stream 400.
    assert(
      !/stream is not readable/i.test(postText),
      `POST /mcp/messages must NOT 400 with "stream is not readable" (got ${postRes.status}: "${postText.slice(0, 160)}")`,
    );
    assert(
      postRes.status >= 200 && postRes.status < 300,
      `POST /mcp/messages (initialize) must return 2xx (got ${postRes.status}: "${postText.slice(0, 160)}")`,
    );

    // 3) DNS-rebinding defense: a request with a non-allowlisted Host is refused.
    //    Use a raw HTTP client (fetch drops/overrides the Host header).
    const rebind = await rawGet(SSE_PORT, "/health", "evil.attacker.example");
    assert(
      rebind.status === 421,
      `Host allowlist must reject a foreign Host with 421 (got ${rebind.status})`,
    );
    // Positive control: the allowlisted loopback Host passes the same path.
    const allowed = await rawGet(SSE_PORT, "/health", `127.0.0.1:${SSE_PORT}`);
    assert(
      allowed.status === 200,
      `Host allowlist must ACCEPT the loopback Host (got ${allowed.status})`,
    );
  } finally {
    // Fail FAST on any assertion error: cancel the SSE reader and force-drop any
    // lingering keep-alive sockets so listener.close() cannot block on the open SSE
    // connection. Without this, a future regression that throws mid-test would hang
    // the probe to the harness's 120s timeout instead of printing VERIFY_FAIL.
    if (reader) await reader.cancel().catch(() => {});
    if (typeof listener.closeAllConnections === "function") listener.closeAllConnections();
    await new Promise((resolve) => listener.close(resolve));
  }

  console.log(
    `VERIFY_OK mcp-boot: server constructs, ${toolCount} tools listed, handleTool reachable; ` +
      `auth-gate refuses keyless write; out-of-tenant repoPath rejected; in-tenant write OK; ` +
      `SSE POST /mcp/messages 2xx (no stream-drain 400); Host allowlist enforced`,
  );
}

main()
  .catch((err) => {
    console.error("VERIFY_FAIL:", err && err.message ? err.message : err);
    process.exitCode = 1;
  })
  .finally(() => {
    try {
      rmSync(sandbox, { recursive: true, force: true });
    } catch {
      /* best-effort cleanup */
    }
  });
