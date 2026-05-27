---
agent_id: rhyming-words-completion
agent_name: Rhyming Words Feature Completion Agent
tier: 2
priority: P1
status: pending
depends_on: [critical-bug-fix]
created_date: 2026-04-25
---

# Rhyming Words Feature Completion Agent

## Overview
Complete the broken rhyming-words feature end-to-end: restore selection functionality, implement word insertion, verify network fetch still works.

## Tier & Priority
- **Tier:** 2 (Feature Integrity)
- **Priority:** P1
- **Estimated Duration:** 2–3 hours
- **Blocker:** No (feature is unused, but if shipped, currently broken)

## Scope

### Issue #1: tableView(_:didSelectRowAt:) Commented Out
**File:** `Apollo16/VIEW CONTROLLERS/SearchTableViewController.swift`, line ~80  
**Severity:** HIGH

**Current Code:**
```swift
// Entire method is commented out
/*
override func tableView(_ tableView: UITableView, didSelectRowAt indexPath: IndexPath) {
    // ...
}
*/
```

**Fix:**
```swift
override func tableView(_ tableView: UITableView, didSelectRowAt indexPath: IndexPath) {
    let selectedWord = filteredResults[indexPath.row]
    delegate?.searchTableViewController(
        self,
        didSelectSearchResult: selectedWord,
        searchedText: searchedText
    )
    tableView.deselectRow(at: indexPath, animated: true)
}
```

---

### Issue #2: Delegate Method Empty (No-Op)
**File:** `Apollo16/VIEW CONTROLLERS/AddNote.swift`, `searchTableViewController(_:didSelectSearchResult:searchedText:)`  
**Severity:** HIGH

**Current Code:**
```swift
func searchTableViewController(_ controller: SearchTableViewController,
                            didSelectSearchResult result: String,
                            searchedText: String) {
    // Empty body — nothing happens
}
```

**Fix:**
```swift
func searchTableViewController(_ controller: SearchTableViewController,
                            didSelectSearchResult result: String,
                            searchedText: String) {
    handleAddingRhyme(word: result)
}
```

---

### Issue #3: handleAddingRhyme() Is Empty
**File:** `Apollo16/VIEW CONTROLLERS/AddNote.swift`, `handleAddingRhyme()` function  
**Severity:** HIGH

**Current Code:**
```swift
func handleAddingRhyme() {
    // Empty
}
```

**Fix:**
```swift
func handleAddingRhyme(word: String) {
    // Get current cursor position
    let cursorPosition = textView.selectedRange.location
    
    // Insert word at cursor with a space
    let insertText = word + " "
    
    if let range = Range(textView.selectedRange, in: textView.text) {
        textView.text.replaceSubrange(range, with: insertText)
        
        // Move cursor after inserted word
        let newCursorPosition = cursorPosition + insertText.count
        textView.selectedRange = NSRange(location: newCursorPosition, length: 0)
    }
    
    // Dismiss search controller
    if let searchVC = presentedViewController as? UISearchController {
        searchVC.dismiss(animated: true)
    }
}
```

---

### Issue #4: Verify Network Fetch Still Works
**File:** `Apollo16/NETWORK/AFWrapper.swift`, `hitGetRhymeWords(word:completion:)` function  
**Severity:** MEDIUM

**Current Implementation:** (Should already work, but verify)
```swift
func hitGetRhymeWords(word: String, completion: @escaping ([String]) -> Void) {
    let urlString = "https://api.datamuse.com/words?rel_rhy=\(word.lowercased())"
    
    Alamofire.request(urlString).responseJSON { response in
        switch response.result {
        case .success(let value):
            guard let json = value as? [[String: Any]] else {
                completion([])
                return
            }
            
            let words = json.compactMap { $0["word"] as? String }
            completion(words)
            
        case .failure(let error):
            print("Rhyming words request failed: \(error.localizedDescription)")
            completion([])
        }
    }
}
```

**Test:**
1. Create or open a note
2. Type a word like "cat"
3. Tap the rhyming words button (floating action button or search icon)
4. Verify: table populates with rhyming words (bat, hat, mat, etc.)
5. Tap one (e.g., "bat")
6. Verify: "bat" is inserted at cursor in the note text view
7. Dismiss search view

---

## Output Requirements

### PR Description
```
## Complete Rhyming Words Feature (P1)

### Uncomment tableView(_:didSelectRowAt:)
- Restore selection handler in SearchTableViewController
- Dispatches delegate callback with selected word

### Implement Delegate Callback
- searchTableViewController delegate method now calls handleAddingRhyme()
- Word is inserted into note text view at cursor position

### Implement Word Insertion Logic
- handleAddingRhyme() inserts word + space at cursor
- Cursor moves after inserted word
- Search view auto-dismisses

### Verify Network Fetch
- Datamuse API request works end-to-end
- Results populate table correctly

Test Steps:
1. Create/open note
2. Type "cat"
3. Tap rhyming words button
4. Verify table shows rhymes (bat, hat, mat, etc.)
5. Tap "hat"
6. Verify "hat " inserted in note text

Fixes: Rhyming words feature
Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

---

## Success Criteria

- [ ] SearchTableViewController.tableView(_:didSelectRowAt:) uncommented and functional
- [ ] Delegate callback method implemented (not empty)
- [ ] handleAddingRhyme() inserts word at cursor with space
- [ ] Cursor position correct after insertion
- [ ] Search view auto-dismisses after selection
- [ ] Network request to Datamuse API works
- [ ] Manual test: type word → see rhymes → select → word inserted
- [ ] No crashes on network error or empty results

---

## Dependencies & Handoffs

### Prerequisites
- CRITICAL-BUG-FIX merged (no direct dependency, but good to have)

### Parallel Agents
- GLOBAL-STATE-MANAGEMENT
- FIREBASE-BACKEND

---

## Agent Notes

**Key Files:**
- `Apollo16/VIEW CONTROLLERS/SearchTableViewController.swift`
- `Apollo16/VIEW CONTROLLERS/AddNote.swift`
- `Apollo16/NETWORK/AFWrapper.swift` (verify, don't change)

**Test Commands:**
```bash
# Verify network request works
curl 'https://api.datamuse.com/words?rel_rhy=cat' | jq .

# Build and test
xcodebuild -scheme Apollo16 build
```

**Manual QA:**
- Rhyming words button is visible
- Button opens search/rhyming words view
- Network request fires (monitor with Instruments)
- Words display in table
- Selection inserts word into note
- Search dismisses cleanly

**Edge Cases:**
- No rhymes found (empty results) — show "no results" message
- Network error — show error message, allow retry
- User cancels search without selecting — dismiss cleanly
- Cursor not in text view (edge case) — handle gracefully
