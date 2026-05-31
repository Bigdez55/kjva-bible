# Orange Suite Red Team Audit - Full Detail (2026-02-24)

## Files Audited
- `/orange/go-notes/src/main.tsx` (304 lines)
- `/orange/go-calendar/src/main.tsx` (321 lines)
- `/orange/go-drive/src/main.tsx` (232 lines)
- All corresponding `main.js` (older divergent implementations)
- All `global.d.ts` (preload API contracts)
- `go-notes/src/styles.css`

## GO Notes - Specific Line References
- L24-36: openDB() creates new IDBDatabase connection per call
- L95-104: onUpdate saves to IndexedDB on every keystroke, no debounce
- L131-134: persist() loops all notes saving each individually
- L136-139: syncActive() is manual-only, no auto-sync
- L141: search is title-only, no body search
- L280-291: "export markdown" exports raw HTML with .md extension
- L276-278: AI suggestions displayed but not insertable into editor

## GO Calendar - Specific Line References
- L98-101, L128: Math.floor(getEventHour(ev)) === hour truncates multi-hour events
- L56: events.filter() inside cells.map() = O(cells * events) per render
- L295: recurrence field is plain text input, no RRULE logic
- L296: reminderMinutes captured but never used
- L207-214: load("default") fetches ALL events, no date-range query
- All views: inline style={{}} objects re-allocated on every render

## GO Drive - Specific Line References
- L23, L35: btoa(preview) crashes on binary data (non-Latin1 chars)
- L95-99: handleShare() clears dialog before checking for errors
- L159-169: Download uses `preview || draftContent` - wrong content if no preview loaded
- L118: upload sends textarea content only, no File API
- L126-135: folder creation is client-side only, uses blocking prompt()
- L72-73: empty server response shows stale files from previous directory
- L8-9: file type detection by extension only, no magic bytes

## Cross-App: main.js vs main.tsx Divergence
- go-notes: .js uses localStorage + textarea; .tsx uses IndexedDB + TipTap
- go-calendar: .js has no calendar views; .tsx has Month/Week/Day/Agenda
- go-drive: .js uses alert() for share; .tsx has modal dialog + typed preview
- Build pipeline must be verified to determine which actually runs
