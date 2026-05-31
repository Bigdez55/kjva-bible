# Orange Suite — Post P0-P3 Fix Architectural Review
# Review date: 2026-02-24 (second pass)
# Scope: same 16 files as initial review

## RESOLVED DEFECTS (confirmed fixed)

### C-3 RESOLVED: Singleton IDB pattern — reconnection correctly handled
- dbInstance module-level let; openDB() returns cached instance.
- `dbInstance.onclose = () => { dbInstance = null; }` — nullifies on unexpected close.
- Re-entrant calls before the open resolves are NOT protected (see NEW-1 below).

### C-4 RESOLVED: Debounce pattern implemented
- pendingSaveRef + saveTimerRef pattern; flush-on-unmount cleanup.
- Remaining issue: saveTimerRef must clear before flush in unmount effect (see NEW-2).

### H-9 RESOLVED: O(1) event lookup Maps via useMemo
- All four views pre-index events into Maps.
- eventsByDate, eventsByDateHour, dayEventsByHour all stable.
- Remaining issue: events array reference instability (see NEW-3).

### C-7 RESOLVED: Download button now fetches on-demand
- Each Download button calls window.goDrive.download(item.name) independently.
- URL.revokeObjectURL called immediately after click — correct.

### AbortController pattern: clearTimeout present in all paths
- Both preloads (go-notes, go-calendar) call clearTimeout in the success path AND in the catch block.
- Pattern is correct — no timeout leak identified.

### M-11 RESOLVED: New Folder uses inline form state, not prompt()
- showFolderInput state + inline input confirmed.

### M-8 PARTIAL: Title tags corrected
- go-notes: "GO Notes" — correct.
- go-calendar: "GO Calendar" — correct.
- go-drive: "GO Drive" — correct.

### H-4 PARTIAL: share() now includes resource in grant body
- `resource: safeFilePath` confirmed in grant body.
- uid validation now uses validateUid() regex.
- Still uses shareTarget.username not a resolved UID (display name vs system UID).

## REMAINING / NEW DEFECTS FOUND IN THIS PASS

### NEW-1 (HIGH): openDB() has a concurrent-open race
- File: go-notes/src/main.tsx lines 29-46
- Description: Between the `if (dbInstance)` guard and the `req.onsuccess` callback,
  multiple concurrent callers (e.g. loadNotes + saveNote firing simultaneously) each
  see dbInstance===null and each issue indexedDB.open(). The first to resolve sets
  dbInstance; the others resolve to different handles pointing at the same DB — not a
  data corruption risk in IDB (IDB handles are safe) but it wastes connections and means
  onclose is only wired once.
- Severity: Annoying, not critical for single-user desktop app. Low blast radius.
- Fix: Promise-coalescence lock:
  ```ts
  let dbInstance: IDBDatabase | null = null;
  let openPromise: Promise<IDBDatabase> | null = null;

  function openDB(): Promise<IDBDatabase> {
    if (dbInstance) return Promise.resolve(dbInstance);
    if (openPromise) return openPromise;
    openPromise = new Promise<IDBDatabase>((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, DB_VERSION);
      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains(STORE_NAME)) {
          db.createObjectStore(STORE_NAME, { keyPath: "id" });
        }
      };
      req.onsuccess = () => {
        dbInstance = req.result;
        dbInstance.onversionchange = () => { dbInstance?.close(); dbInstance = null; };
        dbInstance.onclose = () => { dbInstance = null; openPromise = null; };
        openPromise = null;
        resolve(dbInstance);
      };
      req.onerror = () => { openPromise = null; reject(req.error); };
    });
    return openPromise;
  }
  ```
  Note: onversionchange should also be wired (currently only onclose is wired).

### NEW-2 (MEDIUM): Unmount flush effect fires saveNote without cancelling the in-flight timer first
- File: go-notes/src/main.tsx lines 113-118
- Code:
  ```ts
  return () => {
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    if (pendingSaveRef.current) void saveNote(pendingSaveRef.current);
  };
  ```
- This is correct ordering: cancel timer, then flush. No bug.
- HOWEVER: React Strict Mode (dev) double-invokes cleanup + effect. In dev, the cleanup
  fires, cancels the timer, fires saveNote, then the component remounts. pendingSaveRef
  is a ref — it survives Strict Mode remount. So the flush is invoked twice in dev only.
  Not a production bug. Document as a known dev-mode double-save.

### NEW-3 (HIGH): React.memo effectiveness is undermined by inline onClickEvent prop
- File: go-calendar/src/main.tsx lines 322-325
- Code: `<MonthView currentDate={currentDate} events={events} onClickEvent={editEvent} />`
- editEvent is wrapped in useCallback with `[]` deps — stable across renders. GOOD.
- BUT: currentDate is a Date object created fresh on each navigate call:
  ```ts
  const navigateBack = (): void => {
    const d = new Date(currentDate);   // new object every time
    ...
    setCurrentDate(d);
  ```
  A new Date object is set to state. React compares by reference. So currentDate state
  changes reference on navigation → memo re-renders all four views. This is CORRECT and
  EXPECTED behaviour — the views MUST re-render on date navigation. No bug here.
- The actual memo benefit is preventing re-renders when unrelated state changes (e.g.
  showForm, suggestion, formError, draft). In those cases, events and currentDate haven't
  changed, so the memo does correctly block re-renders.
- CONCLUSION: React.memo is working correctly. The Map index is stable per-render.

### NEW-4 (MEDIUM): useMemo inside MonthView builds new Map on every events reference change
- File: go-calendar/src/main.tsx lines 58-68 (MonthView), 106-116 (WeekView), 155-166 (DayView)
- The `events` prop is the top-level `events` state array. React.useState guarantees
  referential stability of the array unless setEvents is called. setEvents is only
  called in loadEffect, saveEvent, deleteEvent — not on form/draft changes.
- CONCLUSION: Map is not rebuilt spuriously. Stable.

### NEW-5 (HIGH): Download button — async handler has a race condition with rapid clicks
- File: go-drive/src/main.tsx lines 211-219
- Each click spawns a new async fetch via window.goDrive.download(item.name).
  With rapid double-clicks: two concurrent fetches run. Both will call
  URL.createObjectURL with their own blobs and click two separate anchor elements.
  The first click fires on link1, revokeObjectURL immediately. The second click fires on
  link2, revokeObjectURL immediately. Result: two download dialogs appear.
  Browsers handle this acceptably (two files download), but it is unintended UX.
- Missing: in-flight guard ref or disabled state during download.
- Fix:
  ```tsx
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  // ...
  <button
    disabled={downloadingId === item.id}
    onClick={async () => {
      if (downloadingId) return;
      setDownloadingId(item.id);
      try {
        const data = await window.goDrive.download(item.name);
        const blob = new Blob([data], { type: "application/octet-stream" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = item.name;
        link.click();
        URL.revokeObjectURL(url);
      } finally {
        setDownloadingId(null);
      }
    }}
  >
    {downloadingId === item.id ? "Downloading..." : "Download"}
  </button>
  ```

### NEW-6 (MEDIUM): AbortController clearTimeout — pattern analysis
- Files: go-notes/electron/preload.ts lines 64-82, go-calendar/electron/preload.ts lines 21-38
- Pattern: `const controller = new AbortController(); const timeout = setTimeout(...)`.
  Success path: clearTimeout called before return. CORRECT.
  Catch path: clearTimeout called in catch block. CORRECT.
  Both paths clear the timer.
- Edge case: If fetch() throws synchronously (before yielding), the catch block still
  fires and clearTimeout is called. SAFE.
- CONCLUSION: No timeout leak. Pattern is correct. Cleared in all code paths.

### NEW-7 (LOW): persist() in go-notes still saves only notes[0] — misleading comment
- File: go-notes/src/main.tsx lines 172-176
- Code:
  ```ts
  const persist = useCallback((next: Note[]): void => {
    setNotes(next);
    if (next.length > 0) void saveNote(next[0]);
  }, []);
  ```
  The comment says "Only save the newly added note (first element)" — correct
  as-is because persist() is ONLY called from the "New" button, which prepends
  the new item: `const next = [item, ...notes]; persist(next);`.
  So next[0] is always the newly created note. Behaviorally correct.
  Risk: If persist() is ever called from a different site with a different list
  shape, only the first element is saved while others are silently dropped.
  The intent is fragile. Rename to persistNew(note: Note) and accept a single Note.

### NEW-8 (MEDIUM): Calendar — events array loaded via JSON.parse(doc.body) without type validation
- File: go-calendar/electron/preload.ts lines 65-73 and go-calendar/src/main.tsx lines 251-256
- Preload correctly guarded-parses doc.body. But the renderer casts directly:
  ```ts
  setEvents((data as Record<string, unknown>).events as EventItem[]);
  ```
  No isEventItem() guard. Invalid events (e.g. missing `time`) cause getEventDate()
  to return Invalid Date, placing events at wrong positions silently.
  This was H-3 in the original register. Still not fixed.

### NEW-9 (LOW): SyncClient has no retry logic on network failure
- File: orange/common/sync-client.ts
- Every method throws immediately on non-ok response. No exponential backoff.
  On a k3s single-node cluster, transient pod restarts (5-10s) will cause
  every save during that window to throw and be silently swallowed by the
  preload catch blocks.
- Fix: Wrap fetch calls in a retryWithBackoff(maxAttempts=3, baseDelayMs=500) utility.

### NEW-10 (MEDIUM): go-drive reload() is not wrapped in useCallback
- File: go-drive/src/main.tsx lines 106-124
- Originally H-6. Confirmed still present. reload is a plain async function
  defined inside the component, not useCallback. The useEffect dependency
  array is `[currentPath]` which is correct, but the stale closure risk is real
  if reload is ever passed to a child or called from a ref.
  In the current code the risk is contained but the pattern is fragile.

### NEW-11 (MEDIUM): Upload button has no in-flight guard
- File: go-drive/src/main.tsx lines 150-158
- Same pattern as Download — rapid clicks fire multiple concurrent uploads.
  setSyncStatus("syncing") gives no per-file guard. Two concurrent uploads
  can race on setItems, leading to duplicate entries in the local list.
- Fix: Disable the Upload button while upload is in flight.

### SURVIVING FROM ORIGINAL REGISTER (still open)
- C-1: sandbox:true + process.env — TOKEN empty. Critical. Not fixed.
- C-2: yjs import in doc-model.ts — build break if bundled. Critical. Not fixed.
- H-1: common/ not in build output — runtime module resolution fails. High. Not fixed.
- H-2: Empty catch blocks — sync failures invisible. High. Partially fixed (some catch blocks now return {ok:false} but no console.error).
- H-3: Calendar events not validated on load. High. Not fixed (NEW-8 above).
- H-5: TipTap useEffect missing `active` dep + no setContent false flag. High. Not fixed.
- H-6: reload() not useCallback. Medium. Not fixed (NEW-10 above).
- H-7: Export HTML extension. High. Fixed (export now uses .html).
- H-8: AgendaView locale key collision. High. Not fixed.
- M-1: go-calendar and go-drive tsconfig missing baseUrl. Medium. Not fixed.
- M-2: IdentityClient unused. Medium. Not fixed.
- M-3: SyncClient.getDoc() no runtime validation. Medium. Not fixed.
- M-10: EventItem.duration string not number; recurrence string not union. Medium. Not fixed.
- C-5: Calendar single-document pattern. Critical scalability cliff. Not fixed.

## CROSS-APP CONSISTENCY MATRIX
| Concern                        | go-notes | go-calendar | go-drive |
|-------------------------------|----------|-------------|----------|
| AbortController pattern        | CORRECT  | CORRECT     | N/A      |
| Token from process.env (bug)   | BUG      | BUG         | BUG      |
| contextBridge input validation | GOOD     | GOOD        | BEST     |
| Inline style vs CSS class      | CSS      | inline      | inline   |
| useCallback for callbacks      | GOOD     | PARTIAL     | MISSING  |
| Error surfaced to renderer     | NO       | NO          | NO       |
| Type guard on remote data      | N/A      | MISSING     | N/A      |
| baseUrl in tsconfig            | YES      | NO          | NO       |
| React.memo on views            | N/A      | CORRECT     | N/A      |
| Singleton IDB                  | PARTIAL  | N/A         | N/A      |
