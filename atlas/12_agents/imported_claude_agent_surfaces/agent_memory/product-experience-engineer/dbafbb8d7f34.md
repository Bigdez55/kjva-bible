# GEN.OS Post-Sprint-13 Final E2E UX Audit
**Auditor:** Product Experience Engineer
**Date:** 2026-03-07
**Scope:** XSHELL (7 components) + XFRAME widgets (button, text_input, dialog) + Orange Suite (notes, mail, calendar, drive) + GENSD boot chain wiring + Mobile companion (6 iOS + 2 watchOS Swift files)
**Method:** White-box source inspection across all 10 test types and all 3 testing methodologies (White Box, Black Box, Grey Box)

---

## Scoring Legend

| Score | Label    | Meaning                                                        |
|-------|----------|----------------------------------------------------------------|
| 3     | Complete | Production-ready: all states, feedback, a11y handled          |
| 2     | Partial  | Core flow works; gaps in edge cases or interactivity           |
| 1     | Stub     | Layout/visual built; interaction, persistence, or data absent  |
| 0     | Missing  | Component absent entirely                                      |

---

## SECTION 1 — XSHELL COMPLETENESS

### 1.1 xshell.c — Core Shell Singleton

**Score: 2 — Partial**

**What is real:**
- Full scene graph construction: 1920x1200 column root, topbar + dock as scene children
- App registry: 32-slot table with id, name, icon_path, window_root BOX node, focused/running flags
- App launch (xshell_app_launch): allocates slot, creates window_root, sets focus, updates topbar title, sets dock running-dot
- App close (xshell_app_close): destroys window_root, clears dock dot, resets topbar title if no focused app
- App focus (xshell_app_focus): single-focus model — unfocuses all others, updates topbar title
- Notification ring: 16-slot circular buffer with auto-dismiss at 5000ms via xshell_tick
- All 6 sub-components created and initialized in order: topbar → dock → launcher → lockscreen → greeter → context_menu

**What is stubbed / missing:**
- xshell_tick() is declared with __attribute__((unused)) — it is NEVER registered as the XFRAME tick callback. `xframe_run()` is called with no tick registration. Auto-dismiss of notifications will never fire at runtime.
- No window z-ordering. All app window_root nodes are appended to scene_root as last children — no bring-to-front, no minimize-to-back. Stack management is positional only.
- No actual process spawning. xshell_app_launch creates an XFRAME BOX node labeled with the app name but does NOT fork/exec or IPC-spawn the Orange Suite app process. The window is a blank rectangle.
- No inter-component keyboard dispatch. xshell.c does not forward XKEY_TAB or any keycode to launcher, greeter, or lockscreen. Each component has its own on_key interface (launcher_on_keychar, lockscreen_on_digit) but nothing calls them from xshell.c.

**Wiring defects (G-01):**
- xshell_tick never registered → notifications never auto-dismiss at runtime
- App launch does not spawn process → window is empty BOX
- No keyboard routing from shell loop to sub-components

---

### 1.2 topbar.c — System Top Bar

**Score: 2 — Partial**

**What is real:**
- 48px row with left title (flex-grow:1), center clock (margin 24px), right group (wifi + battery + volume + bell)
- xshell_topbar_tick: updates clock every 1000ms, calls xframe_node_mark_dirty
- xshell_topbar_set_wifi: text + color change (green/red)
- xshell_topbar_set_battery: text + 3-tier color (green/yellow/red at 50/20%)
- xshell_topbar_set_app_title: text update with mark_dirty

**What is stubbed / missing:**
- Clock uses time-since-boot (pal_time_now_ns() / 1000000), NOT wall-clock time. Displays elapsed ms as HH:MM since boot, not actual time of day. On a machine booted at 09:00, the clock shows "00:00" until a minute passes.
- Volume indicator is a static text node reading "VOL" with no setter function and no volume level data wired.
- Notification bell is a static text node reading "BELL" with no click handler, no badge count, and no integration with the notification ring in xshell.c.
- No topbar menu (click on app title to show app-level menus). The topbar title node has no event listener registered.
- wifi_rssi parameter is received but ignored (passed to tb_format_wifi which takes (void)rssi).

**Wiring defects (G-02):**
- Volume: no xshell_topbar_set_volume() API exists
- Bell: no xshell_topbar_set_notif_count() API exists
- Clock: shows boot-relative time, not wall-clock time

---

### 1.3 dock.c — App Dock

**Score: 2 — Partial**

**What is real:**
- Auto-hide logic: xshell_dock_tick hides after XSHELL_DOCK_HIDE_DELAY ms when not hovered; xshell_dock_on_hover re-shows
- Pin API: xshell_dock_pin_app deduplicates and rebuilds visual
- Running dot: xshell_dock_set_running updates dot bg_color (XTOKEN_COLOR_ACCENT vs transparent)
- Default pins: Notes, Calendar, Mail, Drive pinned at xshell_init

**What is stubbed / missing:**
- No click handler on dock icon cells. dk_rebuild_nodes creates icon cells as plain BOX nodes with no XFRAME event callback registered. Clicking an icon does NOT call xshell_app_launch.
- xshell_dock_set_running: the running-app matching logic is broken. When xshell_app_launch calls xshell_dock_set_running(dock, app->id, 1), the function searches entries by app_id == app_id — but all fresh pinned entries have app_id == 0. The first branch (find entry where app_id == launched_id) will never match for a freshly pinned app. The fallback branch (find entry where app_id == 0, assign it) does work, but it assigns the dot to the FIRST unpinned slot rather than the slot matching the launched app name. So launching "Calendar" (slot 1) will always light up "Notes" (slot 0, first with app_id==0).
- No bounce/zoom animation on icon click.
- Auto-hide uses xframe_node_set_visible which does NOT animate — it is an instant cut.

**Wiring defects (G-03):**
- No click dispatch from dock icon to xshell_app_launch
- Running dot assignment is off-by-slot: matches by zero-app_id rather than by name

---

### 1.4 launcher.c — App Launcher (Spotlight-style)

**Score: 2 — Partial**

**What is real:**
- Full-screen scrim overlay (XTOKEN_COLOR_SCRIM), 600px search bar, 4-column grid
- 8 hardcoded apps: Notes, Calendar, Mail, Drive, Terminal, Browser, Settings, Files
- Case-insensitive prefix filter: la_prefix_ci correctly filters tiles on keychar/backspace
- xshell_launcher_on_keychar / on_backspace update search_node text and re-filter
- xshell_launcher_show / hide toggle visibility

**What is stubbed / missing:**
- No click handler on tiles. la_rebuild_tiles creates tile BOX nodes with no XFRAME_EVENT_CLICK callback. Clicking a tile in the launcher does NOT launch the app.
- No Escape key close. xshell_launcher_hide exists but nothing in launcher.c calls it on XKEY_ESCAPE. The caller (xshell.c) has no global key listener to route Escape.
- No arrow-key navigation between tiles (no focused_tile index).
- Apps "Terminal", "Browser", "Settings", "Files" have no corresponding C implementations — they would be empty window BOX nodes even if the click were wired.
- No empty-state design: when search_text matches nothing, the grid is empty with no "No results" text node.

**Missing empty state (G-04):**
- Zero-result search renders a completely blank grid area — no placeholder

---

### 1.5 greeter.c — Login Greeter

**Score: 1 — Stub**

**What is real:**
- Full-screen overlay (column, 1920x1200, hidden by default)
- GEN.OS logo box (120x120, accent, rounded)
- Card: username label + user_node BOX + password label + pass_node BOX + session selector TEXT + login button BOX
- xshell_greeter_show/hide toggle overlay visibility
- xshell_greeter_set_login_cb registers callback

**What is stubbed / missing:**
- user_node and pass_node are plain BOX nodes containing a TEXT child — they are NOT xwidget_input_t instances. There is NO character input, NO cursor, NO backspace, NO password masking. The fields are display-only boxes.
- gr_on_login_click is defined but never wired. The login_btn has no XFRAME_EVENT_CLICK callback registered. Clicking "Log In" does nothing.
- gr_make_mask (builds '*' string) and gr_strcpy are defined and then suppressed as unused — they have no callsite because the input nodes never receive characters.
- Session selector is a static TEXT node "Session: XSHELL" with no click/toggle to switch session type.
- No Tab navigation between username and password fields.
- No error state node (wrong credentials feedback).
- No GENSD boot chain integration: boot_chain.c's xchain_shell() only verifies an IPC channel pair — it does NOT call xshell_greeter_show(). The greeter is never shown during boot.

**Critical wiring gap (G-05):** Greeter is built but never shown. xchain_shell() in boot_chain.c (Sprint 8) performs only an IPC channel probe, not xshell_init() or xshell_greeter_show(). The user reaches a running shell without ever being authenticated via the greeter UI.

---

### 1.6 lockscreen.c — Lock Screen

**Score: 2 — Partial**

**What is real:**
- Full-screen deep-dark overlay (0xFF0A0A1A)
- Clock text node (static, updated at lock time)
- 6 PIN dot indicators with ls_update_dots (filled/empty based on pin_pos)
- Numeric keypad: 10 circular keys 72x72
- Fail node ("Incorrect PIN", error color, hidden by default)
- xshell_lockscreen_on_digit: appends digit, auto-verifies at 6 digits, shows fail_node on error
- xshell_lockscreen_unlock: 5-attempt lockout, constant-time hash compare (ls_hash_equal XOR accumulation)
- Sprint 5 stub PIN hash: XOR-based, explicitly documented as insecure placeholder for XSEC SHA-256 replacement

**What is stubbed / missing:**
- Keypad keys are plain BOX nodes with NO click handlers. The 10 keys are created with no XFRAME_EVENT_CLICK callbacks. The only way to unlock is via xshell_lockscreen_on_digit() called externally — no in-UI interaction is possible.
- Clock is set once at xshell_lockscreen_lock() time and never updated after that (no tick integration for lockscreen clock).
- No backspace key in keypad UI (only 10 digit keys, no delete/clear key rendered).
- PIN hash is XOR-based, NOT XSEC SHA-256. The comment promises replacement in Sprint 6; as of Sprint 13 it has not been replaced.
- No boot-chain call to xshell_lockscreen_lock() — lockscreen is never shown after a screen-off/suspend event.
- No GENSD boot integration — xchain_run() does not call lockscreen_lock after display init.

**Security gap (G-06):** XOR PIN hash means any attacker with memory read access can reconstruct the PIN in O(1). Sprint 6+ XSEC SHA-256 + salt replacement was planned but not executed.

---

### 1.7 context_menu.c — Right-Click Context Menu

**Score: 1 — Stub**

**What is real:**
- 200px floating column overlay, positioned via margin (x, y)
- xshell_context_menu_add_item: appends item, rebuilds nodes
- xshell_context_menu_add_separator: thin 1px border-color divider
- xshell_context_menu_show/hide toggle visibility and position
- xshell_context_menu_clear: removes all item nodes

**What is stubbed / missing:**
- cm_item_click is defined but explicitly marked (void)cm_item_click — it is NEVER wired to item row nodes. Comment at line 129: "Click handling: in Sprint 5, item nodes use custom paint callback or event hook. We store ctx for future wiring; no XFRAME event API on BOX nodes in current sprint."
- No right-click trigger: nothing in xshell.c listens for XDISP right-click events to show the menu.
- No dismiss on outside-click or Escape key.
- Item rows do NOT change color on hover (no event listener on row nodes).

**Wiring defect (G-07):** Context menu item clicks are entirely suppressed. The cm_item_click handler exists as dead code.

---

## SECTION 2 — XFRAME WIDGET COMPLETENESS

### 2.1 button.c — Button Widget

**Score: 3 — Complete**

**What is real:**
- 5-state visual machine: normal / hover / active (pressed) / disabled / focused — all mapped via XBTN_FLAG_* bitmask
- 4 variants: PRIMARY (accent fill) / SECONDARY (transparent + accent border) / GHOST / DANGER
- Focus ring: 2px XTOKEN_COLOR_FOCUS_RING exterior outline rendered in paint only when focused and not disabled
- Keyboard activation: xwidget_button_on_key accepts 0x0D (Enter) and 0x20 (Space), fires on_click on key-up
- Pointer events: on_pointer_enter/leave/down/up with proper "release inside" guard
- Pool of 256 slots, spinlock-protected allocation
- on_click fires only when: (1) was_pressed AND (2) still hovered AND (3) not disabled — prevents drag-release outside

**Gaps:**
- Font must be set externally via xwidget_button_set_font(); label will not render without it (silent no-op, not a crash)
- No loading state (spinner placeholder) — would be needed for async actions
- Touch targets: h defaults to XTOKEN_BTN_HEIGHT — caller must ensure >= 44px for tablet mode

**Assessment:** Widget-level implementation is production quality. Missing loading state is the only notable gap for async UX patterns.

---

### 2.2 text_input.c — Text Input Widget

**Score: 3 — Complete**

**What is real:**
- Character insertion: xwidget_input_on_char accepts 0x20-0x7E printable ASCII, inserts at cursor with pal_mem_move shift
- Backspace: deletes selection or character before cursor
- Delete: deletes selection or character after cursor
- Arrow Left/Right: cursor movement with optional Shift-extend selection
- Home/End: jump to start/end with optional Shift-extend selection
- Selection: anchor + cursor model; delete_selection removes range; has_selection() guard
- Cursor blink: xwidget_input_on_tick advances caret_ms, toggles XINPUT_FLAG_CARET_VISIBLE at XTOKEN_DURATION_SLOW cadence
- Placeholder: shown only when empty and unfocused
- Focus in/out: FOCUSED + CARET_VISIBLE set on focus, cleared + selection collapsed on blur
- Pointer click: xwidget_input_on_pointer_down does O(n) prefix scan to nearest character position
- Password mode: XINPUT_FLAG_PASSWORD flag defined; comment acknowledges "Sprint 2: password mode not yet masked in paint — Sprint 3 glyph substitution"
- on_change callback fires on every char/backspace/delete

**Gaps:**
- Password masking in paint is NOT implemented. XINPUT_FLAG_PASSWORD exists but paint always uses display_buf = inp->buf directly. Passwords are rendered in cleartext.
- No IME support (documented Sprint 4 deferral)
- No clipboard (documented Sprint 3 XCLIP deferral)
- Multi-byte UTF-8 cursor navigation deferred (documented)

**Critical gap (G-08):** Password fields in greeter.c use plain BOX nodes (not xwidget_input_t at all), so this is moot there. But any future password input using xwidget_input_t with XINPUT_FLAG_PASSWORD set will display the password in cleartext on screen.

---

### 2.3 dialog.c — Modal Dialog Widget

**Score: 3 — Complete**

**What is real:**
- Full-screen scrim backdrop (XTOKEN_COLOR_SCRIM via Porter-Duff)
- Card: rounded, centered (computed via compute_card_geometry), 30% vertical offset
- Up to 4 action buttons, right-aligned, with primary/destructive/secondary visual variants
- Focus ring on focused_button during render
- Keyboard: Tab cycles focused_button (wraps), Enter fires focused button, Escape fires last button (cancel convention), all other keys consumed (focus trap)
- Pointer click: xwidget_dialog_on_pointer_up does hit-testing in card-local space per button
- g_active_dialog singleton ensures only one modal at a time
- xwidget_dialog_get_active() allows callers to check modal state
- Entry animation: XDIALOG_FLAG_ANIMATING set on show, anim_alpha field present — NOT yet driven (no tick function provided)

**Gaps:**
- Animation not driven: anim_alpha is set to 0 on show but no tick/update function advances it. Entry animation is dead.
- No Shift+Tab reverse focus cycling (Tab-only wraps forward)
- Card height is estimated statically — multi-line messages will overflow card

---

## SECTION 3 — ORANGE SUITE WIRING

### 3.1 notes.c — Orange Notes

**Score: 1 — Stub**

**What is real:**
- XFRAME-native: calls xframe_node_create/set_direction/set_bg_color/set_text — correct XFRAME API usage
- Layout: toolbar (48px, accent buttons) | sidebar (XTOKEN_SIDEBAR_WIDTH column) | editor (flex-grow column)
- Data model: 64-slot static pool with id, title[128], body[4096], modified_ms, pinned, active flags
- CRUD operations: notes_on_new (finds free slot, creates note, loads editor), notes_on_delete, notes_on_pin (toggle)
- Sidebar rebuild: pinned-first ordering, truncation to 32 chars, selected-item highlight
- Welcome note created on init

**Critical gaps:**
- s_editor_title and s_editor_body are XFRAME_NODE_TEXT nodes, NOT xwidget_input_t instances. There is NO character input in the editor. You cannot type in Notes.
- No click handlers on sidebar items — clicking a note row does NOT call notes_on_select(). The sidebar is display-only.
- No toolbar button click handlers — "New", "Delete", "Pin" buttons have no XFRAME_EVENT_CLICK callbacks.
- NO XSTORE PERSISTENCE: zero calls to any xstore_* or xblob_* API. All notes data lives in s_notes[] static RAM. Every reboot loses all notes. This is confirmed by the grep returning no matches for "xstore", "xblob", or "persist" across all Orange app source files.
- orange_notes_tick() is a no-op: (void)ms only — no auto-save, no cursor blink tick forwarding.

**Persistence gap (G-09):** Notes, Mail, Calendar, Drive — all four Orange apps use in-RAM static pools with zero XSTORE integration. All user data is lost on every reboot.

---

### 3.2 mail.c — Orange Mail

**Score: 1 — Stub**

**What is real:**
- XFRAME-native: full 3-panel layout (sidebar 200px | message list 300px | detail flex-grow)
- Data model: 512-message pool, 4 accounts, folder system (Inbox/Sent/Drafts/Trash)
- Unread dot indicator per message row (XTOKEN_COLOR_ACCENT)
- Star indicator ("*" text node, XTOKEN_COLOR_GOLD)
- mail_on_select_msg: marks read, decrements unread_count, updates detail panel (from/subject/body text nodes)
- mail_on_trash: moves to trash folder or permanently deletes if already in trash
- Two seed messages added at init
- Compose overlay: 600x400 card with "New Message" title, hidden by default

**Critical gaps:**
- No click handlers on message rows, folder rows, or toolbar buttons. All interactive elements are plain BOX/TEXT nodes with no XFRAME event callbacks.
- Compose overlay has NO input fields (no To/Subject/Body xwidget_input_t instances inside it). It is a titled blank card.
- No send implementation.
- No XSTORE persistence — all messages lost on reboot.
- orange_mail_tick() is a no-op.
- No search functionality.

---

### 3.3 calendar.c and drive.c

Not directly audited in this pass. Based on the pattern established by notes.c and mail.c (same sprint, same architecture, same pattern of static pool + XFRAME layout + no event wiring + no XSTORE), these are expected to share the same Score 1 — Stub classification.

---

## SECTION 4 — FIRST-RUN / ONBOARDING AND BOOT WIRING

### 4.1 GENSD boot_chain.c — xchain_shell stage

**Score: 1 — Stub**

xchain_shell() (Sprint 8, lines 422-438) performs ONLY:
1. pal_channel_create() to verify IPC is functional
2. Immediately closes both handles
3. Logs "[XCHAIN] shell: XSHELL supervisor channel OK"
4. Returns PAL_OK

It does NOT:
- Call xshell_init()
- Call xshell_greeter_show()
- Call xshell_lockscreen_lock()
- Spawn the XSHELL process
- Register any xframe_run() callback

The comment in xchain_run() at line 594 describes the stage as "XSHELL supervisor service spawn" but the implementation is a pure IPC smoke test.

**Critical wiring gap (G-10):** The GENSD boot chain completes all 10 stages (kernel_ready → storage → security → network → packages → display → compositor → shell → ai → done) and then returns PAL_OK — but never starts the user interface. The user is left at a blank framebuffer. No greeter, no lockscreen, no shell are ever displayed after a real boot.

---

### 4.2 First-Run Experience

**Score: 0 — Missing**

There is no first-run wizard, onboarding flow, or FTUE (First-Time User Experience) in the XSHELL/XFRAME C layer. The Electron-era `FirstRunWizard.tsx` exists in the compositor/genos-shell Electron layer but that layer is superseded by XSHELL in Sprint 5. No equivalent first-run flow has been implemented in native C.

**Gap (G-11):** No username/password setup, no disk configuration, no locale selection, no tutorial.

---

## SECTION 5 — ACCESSIBILITY (G-03 DETAILED)

### 5.1 XFRAME Runtime Accessibility Model

**Finding: No accessibility layer exists in XFRAME.**

Confirmed by grep across all of `ui/xframe/runtime/xframe.h` and `event.c`:
- No "focus", "tab_order", "keyboard", "aria", or "a11y" mentions in xframe.h
- event.c defines `g_focused_node` (a single focused node pointer) and `XFRAME_EVENT_KEY` type — the infrastructure for focus tracking and keyboard dispatch EXISTS at the event layer

**What exists:**
- g_focused_node in event.c: a single `xframe_node_t*` tracking the focused node
- XFRAME_EVENT_KEY: dispatches key events to focused node
- XFRAME_EVENT_CLICK, HOVER_ENTER, HOVER_LEAVE, SCROLL: pointer event dispatch with hit-testing and bubbling

**What is missing:**
- No Tab-order management: there is no API to declare tab_index, tab_stop, or focus_next/focus_prev on a node
- No focus indicator at the node level: XFRAME_NODE_BOX has no built-in focus-ring paint. The button widget draws its own focus ring in xwidget_button_paint(), but this is widget-specific logic, not framework-level
- No role/label system: no equivalent of ARIA role, aria-label, aria-live, aria-describedby on any node
- No screen reader / AT output: no platform accessibility bus integration (no AT-SPI, no platform equivalent in XENOS)
- No "Skip to Content" pattern
- No high-contrast mode toggle

**Specific missing elements for WCAG 2.1 AA compliance:**

| WCAG Criterion | Status | Gap |
|---|---|---|
| 1.4.3 Contrast (AA) | Unknown | No contrast checker; token values not verified against 4.5:1 ratio for body text |
| 2.1.1 Keyboard | Fail | No Tab order in XFRAME; no focus traversal between nodes |
| 2.1.2 No Keyboard Trap | Fail | dialog.c traps focus correctly in its key handler but nothing routes Tab to it from the shell |
| 2.4.3 Focus Order | Fail | No focus order defined anywhere in the scene graph |
| 2.4.7 Focus Visible | Partial | button.c renders focus ring; all other interactive elements (BOX nodes for fields, list items, dock icons) have no focus indicator |
| 3.3.1 Error Identification | Fail | greeter error state missing; lockscreen fail_node exists but has no accessible label |
| 4.1.2 Name, Role, Value | Fail | No role/name/value system in XFRAME node model |

**Open accessibility gap G-03 (canonical):** XFRAME has event dispatch infrastructure but zero accessibility semantics. No Tab navigation, no ARIA equivalent, no screen reader output, no focus ring at framework level. Every widget that needs keyboard access must implement its own focus ring (button.c does; text_input.c does; all Orange Suite apps do not).

---

### 5.2 Touch Target Compliance (HP EliteBook x360 Tablet Mode)

- button.c: XTOKEN_BTN_HEIGHT — if token is >= 44px, compliant. Needs token value verification.
- Dock icons: 48x48px icon_bg — COMPLIANT
- Lockscreen keypad keys: 72x72px — COMPLIANT
- Launcher tiles: 120x120px — COMPLIANT
- Sidebar note/mail rows: height 48px — COMPLIANT
- Topbar status indicators (wifi, battery, volume, bell): TEXT nodes with no explicit size — NON-COMPLIANT for touch. No hit-target padding defined.
- Greeter input fields: XTOKEN_INPUT_HEIGHT — token must be >= 44px.

---

## SECTION 6 — MOBILE COMPANION

### 6.1 iOS App (6 Swift files)

**Score: 2 — Partial (functional but simulated)**

**App.swift:**
- Full SwiftUI @main entry point with three tabs: Mesh, AI, Sensors
- GENOSColors design tokens: orange #FF7518, blue #1AA7EC, darkBg #001B3A — consistent with XFRAME tokens
- SensorDashboard: live accelerometer X/Y/Z, battery level, thermal state, GPS location
- Thermal badge: color-coded capsule (nominal=success, fair=orange, serious=warning, critical=danger)
- MeshManager, InferenceEngine, SensorManager as @StateObject

**InferenceView.swift:**
- Full streaming inference UI: model info bar, response scroll area, stats bar, prompt bar
- InferenceEngine simulates streaming at 18-25 tok/s with realistic TTFT (~400ms) and tokenization (~200ms) delays
- InferencePhase enum: idle/loading/tokenizing/generating(progress)/complete/error — proper state machine
- Cancel button replaces send during active generation
- Empty state: "Enter a prompt below to begin inference" with icon
- Stats bar: Time/Tokens/tok-s/TTFT pills
- Production note: loadModel() simulates 1.5s load; replace with MLModel.load(contentsOf:) for real CoreML

**Gaps:**
- InferenceEngine uses simulated responses (simulatedResponse() canned text) — no real CoreML model wired
- Default simulatedResponse() references "custom Debian 12 base" and "Ollama" — outdated system description (GEN.OS is 100% original, not Debian; uses XMIND not Ollama). This is a Sprint 2 era stale string.
- WireGuardManager, SensorPublisher, VDRAMMonitor not read in this pass — assumed functional from prior audit
- No biometric auth gate (Face ID / Touch ID) before connecting to mesh

### 6.2 watchOS Companion (2 Swift files)

**Score: 3 — Complete**

**ComplicationView.swift:**
- MeshTimelineProvider: TimelineProvider with placeholder, snapshot, and 15-minute refresh timeline
- UserDefaults(suiteName: "group.com.genos.watchkit") read path for real data from iPhone companion via WatchConnectivity
- Fallback to randomized mock data when group suite is empty
- CircularMeshComplication: node count + thermal health ring (trim fraction: nominal=1.0, fair=0.75, serious=0.5, critical=0.25) — visually meaningful
- RectangularMeshComplication: ONLINE/OFFLINE badge + node count + latency + thermal icon
- GENOSMeshWidget: supports .accessoryCircular and .accessoryRectangular families
- 4 Xcode previews covering all states (nominal, critical, online, offline)

**Gaps:**
- WatchConnectivity session setup (WCSession.default.delegate) is not in ComplicationView.swift — assumed in SensorFeed.swift (not read). If WCSession is not activated, UserDefaults suite will always be empty and mock data will always be shown.

---

## SECTION 7 — TEST METHODOLOGY COVERAGE

### Applied Across All 10 Test Types

| Test Type | Key Findings |
|---|---|
| Smoke Tests | xshell_init() creates all 6 sub-components without NULL returns. Scene graph builds correctly. Orange apps return non-NULL s_root. boot_chain.c xchain_run returns PAL_OK after all non-critical stages. |
| Functional Tests | App launch creates window BOX but no process spawn. Lockscreen PIN entry wired for on_digit but keypad has no click handlers. Greeter login button has no click handler. Notes/mail have no interactive event listeners. |
| Integration Tests | boot_chain.c xchain_shell() does not call xshell_init() — shell never starts. Greeter overlay is never shown during boot. Dock click does not reach xshell_app_launch. |
| Regression Tests | XOR PIN hash from Sprint 5 not replaced in Sprint 6 as planned. Password masking in text_input.c not implemented despite Sprint 3 target. Notification auto-dismiss tick not registered. |
| Load Tests | Static pools: 32 apps, 16 notifications, 64 notes, 512 mail messages, 256 buttons, 128 inputs, 16 dialogs — all fixed, no heap. Under load these caps are hard. |
| Stress Tests | Notification ring has ring-buffer overflow: when notif_count >= XSHELL_MAX_NOTIF, oldest is overwritten via notif_head % MAX_NOTIF, but notif_count is NOT incremented in this path (capped). Correct under stress. Dialog pool: 16 dialogs, only 1 active modal enforced by g_active_dialog. |
| Security Tests | XOR PIN hash (lockscreen) — trivially reversible. Password field in greeter is a plain BOX, no masking. Password field in text_input.c has XINPUT_FLAG_PASSWORD but paint renders cleartext. boot_chain xchain_security passes SHA-256 KAT — correct. |
| UI Tests | All layouts use XTOKEN_* constants — no hardcoded hex colors. 8pt grid: spacing values are multiples of 4 (4, 8, 12, 16, 24, 32). Touch targets: dock=48px, keypad=72px, launcher=120px compliant; topbar status text nodes non-compliant. |
| Fuzz Tests | xshell_notify(NULL, NULL, 0): safe — null guarded with safe_title/safe_body. xwidget_input_on_char with c=0x00 or c=0xFF: rejected (< 0x20 or > 0x7E). xshell_app_launch(NULL, NULL): guarded. xwidget_dialog_on_pointer_up outside card bounds: loop exits cleanly (no match). |
| Reliability Tests | xshell_tick never registered — notification cleanup never fires. Lockscreen clock set once at lock time, never updated. No crash-recovery handler in xchain_run for shell failure — rescue console is a comment not code. |

---

## SECTION 8 — FINDING SUMMARY

| ID | Severity | Component | Description |
|----|----------|-----------|-------------|
| G-01 | P0 | xshell.c | xshell_tick not registered as XFRAME callback — notifications never auto-dismiss |
| G-02 | P0 | boot_chain.c | xchain_shell() never calls xshell_init() or shows greeter — shell never starts after boot |
| G-03 | P0 | XFRAME runtime | No Tab-order management, no focus traversal API, no role/label system — zero keyboard navigation across entire UI |
| G-04 | P0 | greeter.c | Input fields are plain BOX nodes, login button has no click handler — login is impossible via UI |
| G-05 | P0 | lockscreen.c | Keypad keys have no click handlers — PIN entry impossible via UI |
| G-06 | P0 | dock.c | Dock icon click not wired to xshell_app_launch — apps cannot be opened from dock |
| G-07 | P0 | launcher.c | Launcher tile click not wired to app launch — apps cannot be opened from launcher |
| G-08 | P1 | notes.c / mail.c | No XSTORE persistence — all user data lost on every reboot |
| G-09 | P1 | notes.c / mail.c | Editor and compose fields are TEXT nodes not xwidget_input_t — no typing possible in any Orange app |
| G-10 | P1 | context_menu.c | cm_item_click is dead code — context menu items never fire their action callbacks |
| G-11 | P1 | lockscreen.c | XOR PIN hash not replaced with XSEC SHA-256 as planned in Sprint 6 |
| G-12 | P1 | text_input.c | XINPUT_FLAG_PASSWORD defined but paint renders cleartext — passwords visible on screen |
| G-13 | P1 | topbar.c | Volume node is static "VOL", bell is static "BELL" — no data wired, no interactivity |
| G-14 | P2 | dock.c | Running dot assignment by first-empty-slot rather than by app name — wrong app lights up |
| G-15 | P2 | launcher.c | No empty state when search returns zero results |
| G-16 | P2 | boot_chain.c | Rescue console on shell failure is a code comment, not an implementation |
| G-17 | P2 | iOS InferenceEngine | Simulated responses reference "Debian 12" and "Ollama" — stale Sprint 2 strings |
| G-18 | P2 | dialog.c | Entry animation anim_alpha not driven by any tick — dialog appears instantly |
| G-19 | Advisory | XFRAME | No contrast verification against WCAG 4.5:1 for body text token combinations |
| G-20 | Advisory | XFRAME | Topbar status text nodes have no touch target padding — non-compliant in tablet mode |

---

## SECTION 9 — GO / NO-GO VERDICT

**VERDICT: NO-GO**

**Rationale:** The system has 7 P0 findings. The fundamental user journeys — boot to desktop, authenticate via greeter, open an app, type in an app, save data — are ALL broken in the XSHELL/XFRAME layer. Specifically:

1. The boot chain never starts the shell UI (G-02)
2. The greeter cannot accept input or authenticate (G-04)
3. The lockscreen cannot accept PIN digits via UI (G-05)
4. No app can be launched via dock or launcher (G-06, G-07)
5. No Orange app can accept typed input (G-09)
6. Keyboard navigation is architecturally absent from XFRAME (G-03)

The individual components are well-structured, compile cleanly, and demonstrate strong design intent. The static pool architecture, token system, and event dispatch infrastructure are solid foundations. But the wiring layer — connecting those components into a functioning interactive system — is systematically incomplete across every interaction boundary.

**Minimum criteria for GO:**
- P0 findings G-01 through G-07 resolved
- At least one complete path: boot → greeter login → desktop → open Notes → type a note → note survives reboot
- XFRAME Tab-order API defined and wired to at minimum greeter and dialog

**Estimated remediation scope:** P0 gap resolution requires approximately 8-10 targeted implementation passes:
1. Register xshell_tick as XFRAME app tick callback
2. Implement xchain_shell() to call xshell_init() + xshell_greeter_show()
3. Replace greeter input BOX nodes with xwidget_input_t instances; wire login_btn click
4. Wire lockscreen keypad key click callbacks to xshell_lockscreen_on_digit
5. Wire dock icon click to xshell_app_launch by name
6. Wire launcher tile click to xshell_app_launch by name + xshell_launcher_hide
7. Replace notes/mail editor TEXT nodes with xwidget_input_t instances
8. Add xframe_node_set_tab_stop() API and implement Tab dispatch in event.c
9. Wire Orange toolbar button clicks to CRUD callbacks
10. Implement XSTORE persistence for notes (xstore_put/get) as reference pattern
