/**
 * Runtime verification probe for CAP_REPO_GIT_WRITEBACK.
 *
 * Exercises the REAL repoGitCommitPush() against a THROWAWAY temp git repo:
 *   1. mkdtemp + `git init` (hermetic: local user.name/email, branch=main)
 *   2. write a file, call repoGitCommitPush({ push:false }) — commit-only
 *   3. assert a real commit SHA now exists in that repo (`git log` / rev-parse)
 *   4. assert pushed === false (no remote was ever contacted)
 *   5. negative test: path traversal in `files` is REJECTED
 *   6. negative test: a non-git directory is REJECTED
 *
 * Prints VERIFY_OK + the sha on success. Never touches the real repo or any remote.
 *
 * Run: node --experimental-strip-types <this file>
 */

import { execFileSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { repoGitCommitPush } from "../../../../../apps/backend/mcp/src/tools/repo-git-writeback.ts";

function gitInit(dir) {
  // -b main pins the branch regardless of the machine's init.defaultBranch.
  execFileSync("git", ["init", "-b", "main", dir], { stdio: "pipe" });
  // Hermetic identity so `git commit` never inherits/depends on global config.
  execFileSync("git", ["-C", dir, "config", "user.email", "probe@atlas.local"], { stdio: "pipe" });
  execFileSync("git", ["-C", dir, "config", "user.name", "ATLAS Probe"], { stdio: "pipe" });
  execFileSync("git", ["-C", dir, "config", "commit.gpgsign", "false"], { stdio: "pipe" });
}

function assert(cond, msg) {
  if (!cond) throw new Error(`ASSERT FAILED: ${msg}`);
}

async function main() {
  const sandbox = mkdtempSync(path.join(tmpdir(), "atlas-git-writeback-"));
  // Separate temp dir for the non-repo negative test. It must NOT be nested
  // under `sandbox`, because git walks UP to a parent .git and would treat a
  // nested dir as inside the sandbox work-tree.
  const nonRepo = mkdtempSync(path.join(tmpdir(), "atlas-not-a-repo-"));
  let createdSha = null;
  try {
    // ---- happy path: commit-only ----
    gitInit(sandbox);
    const filename = "hello.txt";
    writeFileSync(path.join(sandbox, filename), "ATLAS writeback probe\n", "utf-8");

    const result = await repoGitCommitPush({
      repoPath: sandbox,
      message: "probe: initial commit via CAP_REPO_GIT_WRITEBACK",
      files: [filename], // explicit staging of a NEW (untracked) file
      push: false, // commit-only / safe — never contact a remote
    });

    assert(result.committed === true, "expected committed=true");
    assert(typeof result.sha === "string" && /^[0-9a-f]{40}$/.test(result.sha), "expected a 40-char SHA");
    assert(result.pushed === false, "expected pushed=false (commit-only)");
    assert(result.branch === "main", `expected branch=main, got ${result.branch}`);
    createdSha = result.sha;

    // Independent confirmation: the SHA really exists in the repo's history.
    const logSha = execFileSync("git", ["-C", sandbox, "rev-parse", "HEAD"], { encoding: "utf-8" }).trim();
    assert(logSha === createdSha, `git HEAD (${logSha}) must equal returned sha (${createdSha})`);
    const logLine = execFileSync("git", ["-C", sandbox, "log", "--oneline", "-1"], { encoding: "utf-8" }).trim();
    assert(logLine.includes("probe: initial commit"), `git log must show the commit message, got: ${logLine}`);

    // ---- negative: path traversal must be rejected ----
    let traversalRejected = false;
    try {
      await repoGitCommitPush({
        repoPath: sandbox,
        message: "should never happen",
        files: ["../escape.txt"],
        push: false,
      });
    } catch (err) {
      traversalRejected = /traversal|escapes/i.test(String(err && err.message));
    }
    assert(traversalRejected, "path traversal in files[] must be rejected");

    // ---- negative: a non-git directory must be rejected ----
    let nonRepoRejected = false;
    try {
      await repoGitCommitPush({ repoPath: nonRepo, message: "x", files: ["a.txt"], push: false });
    } catch (err) {
      nonRepoRejected = /work-tree/i.test(String(err && err.message));
    }
    assert(nonRepoRejected, "non-git directory must be rejected");

    console.log("VERIFY_OK", createdSha);
  } finally {
    rmSync(sandbox, { recursive: true, force: true });
    rmSync(nonRepo, { recursive: true, force: true });
  }
}

main().catch((err) => {
  console.error("VERIFY_FAIL:", err && err.message ? err.message : err);
  process.exit(1);
});
