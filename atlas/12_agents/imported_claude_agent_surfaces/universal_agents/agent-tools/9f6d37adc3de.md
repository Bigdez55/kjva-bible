# Apollo16 Agent Tools & Utilities

This file provides reusable tools, scripts, and validation commands that agents can reference during their work.

---

## Build & Test Commands

### Build Project
```bash
cd /Users/desmondearly/Library/CloudStorage/OneDrive-Personal/Apollo16-main
xcodebuild -scheme Apollo16 build
```

### Run Unit Tests
```bash
xcodebuild -scheme Apollo16 test
```

### Build for Specific iOS Version
```bash
# iOS 13
xcodebuild -scheme Apollo16 -sdk iphoneos13.7 build

# iOS 17
xcodebuild -scheme Apollo16 -sdk iphoneos17.0 build

# Latest
xcodebuild -scheme Apollo16 build
```

### Clean Build
```bash
xcodebuild -scheme Apollo16 clean build
```

---

## Code Search & Validation

### Find All Force-Unwraps
```bash
grep -rn "!" Apollo16/ --include="*.swift" | grep -E "as!|\..*!" | head -20
```

### Find All Force-Casts
```bash
grep -rn "as!" Apollo16/ --include="*.swift"
```

### Find All IUO Optionals
```bash
grep -rn "!:" Apollo16/ --include="*.swift" | grep -v "//"
```

### Find All print() Statements
```bash
grep -rn "print(" Apollo16/ --include="*.swift" | grep -v "//" | grep -v "DEBUG"
```

### Find All Deprecated API Usage
```bash
# UIGraphicsBeginImageContextWithOptions
grep -rn "UIGraphicsBeginImageContextWithOptions" Apollo16/

# keyWindow
grep -rn "\.keyWindow" Apollo16/ --include="*.swift"

# synchronize
grep -rn "\.synchronize()" Apollo16/ --include="*.swift"

# Alamofire 4 API
grep -rn "Alamofire\.request\|Alamofire\.upload" Apollo16/ --include="*.swift"
```

### Find All Private API Usage
```bash
# Private class name matching
grep -rn "String(describing: type(" Apollo16/ --include="*.swift"

# UITableViewCellReorderControl
grep -rn "UITableViewCellReorderControl" Apollo16/

# NSClassFromString
grep -rn "NSClassFromString\|NSStringFromClass" Apollo16/
```

### Find All Commented-Out Code
```bash
grep -rn "^[[:space:]]*//" Apollo16/ --include="*.swift" | head -20
```

### Find Global Variables
```bash
grep -rn "^var " Apollo16/ --include="*.swift" | grep -v "private\|let\|class\|struct"
```

### Find All TODO/FIXME Comments
```bash
grep -rn "TODO\|FIXME\|HACK\|XXX" Apollo16/ --include="*.swift"
```

---

## Git & PR Management

### Check Uncommitted Changes
```bash
git -C /Users/desmondearly/Library/CloudStorage/OneDrive-Personal/Apollo16-main status
```

### Stage Changes
```bash
cd /Users/desmondearly/Library/CloudStorage/OneDrive-Personal/Apollo16-main
git add Apollo16/MODELS/Song.swift
git add Apollo16/MODELS/Note.swift
# ... add other modified files
```

### Create Commit
```bash
git commit -m "Fix Song.isDropbox persistence bug

- Encode isDropbox flag alongside other properties
- Fixes: Dropbox songs lose playback context on restart
- Test: Add Dropbox song → Restart → Verify playback works

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

### View Diff
```bash
git -C Apollo16-main diff Apollo16/MODELS/Song.swift
```

### View Commit Log
```bash
git -C Apollo16-main log --oneline -10
```

---

## Dependency Management

### Update CocoaPods
```bash
sudo gem install cocoapods -v 1.16.0
```

### Verify CocoaPods Version
```bash
pod --version
# Should output: 1.16.0 or later
```

### Install Pods
```bash
cd /Users/desmondearly/Library/CloudStorage/OneDrive-Personal/Apollo16-main
rm -rf Pods/ Podfile.lock
pod install --verbose
```

### List Outdated Pods
```bash
pod outdated
```

### Check Pod Version in Podfile.lock
```bash
grep "COCOAPODS:" Podfile.lock
# Should output: COCOAPODS: 1.16.0 (or later)
```

---

## Profiling & Debugging

### Memory Leak Detection
```bash
# Run with Address Sanitizer
xcodebuild -scheme Apollo16 -enableAddressSanitizer YES test
```

### Instruments (Time Profiler)
```bash
# Build and run with Instruments
xcodebuild -scheme Apollo16 build
open /Users/desmondearly/Library/CloudStorage/OneDrive-Personal/Apollo16-main/build/Release-iphoneos/Apollo16.app
# Use Xcode → Debug → Profiler → Time Profiler
```

### Check App Size
```bash
ls -lh build/Release-iphoneos/Apollo16.app
# Example: Apollo16.app (234.5 MB)
```

### Check Binary for Private APIs
```bash
nm build/Release-iphoneos/Apollo16.app/Apollo16 | grep "UITableViewCellReorderControl"
# Should return: 0 results
```

---

## File-Specific Validation

### Validate Note.swift Model
```bash
# Check for force-casts
grep -n "as!" Apollo16/MODELS/Note.swift

# Check for optional properties
grep -n "?" Apollo16/MODELS/Note.swift | head -10
```

### Validate Song.swift Model
```bash
# Check encode method
grep -A 10 "func encode" Apollo16/MODELS/Song.swift

# Check init(coder:) method
grep -A 10 "init?(coder" Apollo16/MODELS/Song.swift
```

### Validate UIColorFromHex
```bash
# Check division constant
grep -n "/256\|/255" Apollo16/GLOBALS/Functions.swift

# Should output three /255.0 lines
```

### Validate AppDelegate
```bash
# Check for Thread.sleep
grep -n "Thread.sleep" Apollo16/AppDelegate.swift
# Should return: 0 results

# Check for Firebase.configure
grep -n "FirebaseApp.configure\|FirebaseManager.shared.initialize" Apollo16/AppDelegate.swift
```

---

## Manual Testing Checklists

### Audio Recording Flow
```
[ ] Tap record button
[ ] Verify microphone permission prompt (if not granted)
[ ] Record some audio
[ ] Tap stop
[ ] Verify audio file created and metadata displayed
[ ] Tap play
[ ] Verify audio plays back
```

### Audio Playback Flow
```
[ ] Open a note with audio attachment
[ ] Tap play button
[ ] Verify audio plays
[ ] Tap pause
[ ] Verify pause works
[ ] Check remote controls on lock screen
[ ] Verify skip forward/back works
```

### Music Library Integration
```
[ ] Tap "Add Music" button
[ ] Verify MPMediaPickerController appears
[ ] Select a song
[ ] Verify song added to note
[ ] Close note
[ ] Reopen note
[ ] Verify song still there
[ ] Play song
```

### Dropbox Integration
```
[ ] Tap "Add from Dropbox"
[ ] Verify Dropbox auth flow
[ ] Browse and select a music file
[ ] Verify file download started
[ ] Verify file added to note
[ ] Close note, reopen
[ ] Verify file still accessible
[ ] Verify isDropbox flag persists across restart
```

### Undo/Redo
```
[ ] Type some text
[ ] Tap undo
[ ] Verify text reverted
[ ] Tap redo
[ ] Verify text restored
[ ] Verify undo/redo buttons enable/disable correctly
```

### Multi-Select & Delete
```
[ ] Long-press a note
[ ] Tap select all
[ ] Verify all notes selected
[ ] Tap delete
[ ] Verify notes moved to trash
[ ] Open trash
[ ] Tap select all trashed notes
[ ] Tap restore
[ ] Verify notes back in active list
```

---

## PR Review Checklist for Agents

Before committing:
- [ ] Code compiles without errors
- [ ] No new compiler warnings
- [ ] Unit tests added (where applicable)
- [ ] Manual testing checklist completed
- [ ] No unrelated changes included
- [ ] Commit message follows template
- [ ] No secrets or API keys in diff
- [ ] No large binary files committed

---

## Common Error Messages & Fixes

### "EXC_BAD_INSTRUCTION" at App Launch
**Cause:** Force-cast failed (likely in Note deserialization)  
**Fix:** Check Note.swift for force-casts, convert to optional-casts

### "Cannot find reference" for Firebase
**Cause:** Firebase pod not installed  
**Fix:** Run `pod install` and rebuild

### "Use of unresolved identifier 'AF'"
**Cause:** Alamofire import missing or old API used  
**Fix:** Add `import Alamofire` and use `AF.request(...)` (not `Alamofire.request(...)`)

### "Sending '<>' is deprecated"
**Cause:** Using deprecated UIKit API  
**Fix:** Check which API (e.g., keyWindow, UIGraphicsBeginImageContextWithOptions) and upgrade to modern replacement

### "Thread 1: EXC_BAD_ACCESS" during rotation
**Cause:** Accessing view.bounds before layout pass  
**Fix:** Check ChooseSource.curved() and show() methods, ensure layout is complete

---

## Useful Xcode Shortcuts

- **Build:** Cmd + B
- **Run:** Cmd + R
- **Test:** Cmd + U
- **Clean Build Folder:** Shift + Cmd + K
- **Debug View Hierarchy:** Debug → View Hierarchy
- **Memory Debugger:** Debug → Memory Graph

---

## Contact Points

- **Architecture Questions:** Check AGENT-COORDINATION.md dependency graph
- **Blocked by Another Agent:** Check MEMORY.md for agent status
- **Unclear Scope:** Re-read agent's memory file (e.g., 01-critical-bug-fix.md)
- **Build Failures:** Run `xcodebuild clean build` and check recent changes
- **Test Failures:** Run failing test in isolation with `xcodebuild test -only-testing:...`

---

## Notes for Agents

1. **Use these tools liberally** — Commands are here to help validate your work
2. **Run full test suite before PR** — Catches regressions early
3. **Check both build and tests** — Build succeeds but tests fail is still a failure
4. **Reference specific line numbers** — Helps reviewers navigate large files
5. **Screenshot progress** — If you hit a blocker, capture state and escalate

---

## Last Updated

- Created: 2026-04-25
- Last Modified: 2026-04-25

All tools tested and validated on Apollo16 codebase.

