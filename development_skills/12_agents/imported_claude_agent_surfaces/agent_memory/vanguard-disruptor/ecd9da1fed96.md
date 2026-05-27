# Orange Suite P0-P3 Fix Red Team Audit (2026-02-24)

## Overall Assessment
8 fixes applied. Net improvement: 1.5 -> 2.16 composite (+0.66 points / +44% relative).
All fixes address symptoms, not structural defects.

## Fix-by-Fix Scores

| # | Fix | Composite | Verdict |
|---|-----|-----------|---------|
| 1 | Singleton IDB | 2.5/10 | Band-aid. Replace with Dexie.js |
| 2 | Debounce 500ms | 2.75/10 | Arbitrary. Use rIC + hard deadline |
| 3 | React.memo views | 3.25/10 | Necessary but not premature |
| 4 | useMemo indexing | 3.25/10 | Correct but indexes wrong thing (no duration) |
| 5 | Form validation | 2.25/10 | Client-only, no preload validation |
| 6 | AbortController 10s | 1.0/10 | ACTIVELY HARMFUL on target hardware |
| 7 | Inline folder form | 1.25/10 | Cosmetic over unfixed data bug |
| 8 | Export HTML | 1.0/10 | Lost useful functionality |

## Most Urgent Actions
1. Fix AbortController to 60s or replace with streaming inference
2. Delete dead main.js files from all 3 apps
3. Implement actual markdown export (turndown library, 3KB)
4. Add server-side folder creation (upload .keep sentinel)
5. Switch GO Drive download to ArrayBuffer for binary file support

## Key Technical Details
- index.html in all 3 apps points to main.tsx (Vite compiles this)
- main.js files are obsolete dead code with old bugs
- Ollama cold start: 13-35s; warm: 3-12s; 10s timeout intersects failure zone
- Yjs is in package.json but completely unused in GO Notes renderer
- Calendar useMemo depends on [events] which is correct for referential equality
- React.memo on Date objects: shallow compare is reference-based, currentDate creates new ref on "Today" click
