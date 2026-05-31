---
agent_id: color-math-fix
agent_name: Color Math Fix Agent
tier: 5
priority: P2
status: pending
depends_on: critical-bug-fix
created_date: 2026-04-25
---

# Color Math Fix Agent

## Overview
Fix UIColorFromHex division constant: replace all `/256.0` with `/255.0` so pure colors achieve full saturation.

## Tier & Priority
- **Tier:** 5 (Polish, UI Correctness)
- **Priority:** P2 (Visual Quality)
- **Estimated Duration:** 1 hour
- **Blocker:** No (affects perceived color purity, but not critical)

## Scope

### Issue: UIColorFromHex Divides by 256 Instead of 255
**File:** `Apollo16/GLOBALS/Functions.swift`, line 21  
**Severity:** MEDIUM (Visual Quality)

**Current Code:**
```swift
func UIColorFromHex(rgbValue:UInt32, alpha:Double=1.0)->UIColor {
    let red = CGFloat((rgbValue & 0xFF0000) >> 16)/256.0
    let green = CGFloat((rgbValue & 0xFF00) >> 8)/256.0
    let blue = CGFloat(rgbValue & 0xFF)/256.0
    return UIColor(red:red, green:green, blue:blue, alpha:CGFloat(alpha))
}
```

**Problem:**
- 8-bit color channel range is 0–255, not 0–256
- Dividing by 256 means max value (0xFF = 255) → 255/256 = 0.99609, not 1.0
- Pure red 0xFF0000 becomes RGB(0.996, 0, 0) instead of RGB(1.0, 0, 0)
- Pure white 0xFFFFFF becomes (0.996, 0.996, 0.996) — slightly off-white
- Affects every color in the app — all are fractionally desaturated

**Visual Impact:**
- On an sRGB display, imperceptible to the eye (~0.4% desaturation)
- On wide-color displays (Display P3), becomes slightly more noticeable
- Over time, inconsistency accumulates: custom colors don't match design intent
- Screenshot comparison: official brand colors look slightly muted

**Fix:**
```swift
func UIColorFromHex(rgbValue:UInt32, alpha:Double=1.0)->UIColor {
    let red = CGFloat((rgbValue & 0xFF0000) >> 16)/255.0
    let green = CGFloat((rgbValue & 0xFF00) >> 8)/255.0
    let blue = CGFloat(rgbValue & 0xFF)/255.0
    return UIColor(red:red, green:green, blue:blue, alpha:CGFloat(alpha))
}
```

**One-Line Changes:**
- Line ~21: `/256.0` → `/255.0` (red)
- Line ~22: `/256.0` → `/255.0` (green)
- Line ~23: `/256.0` → `/255.0` (blue)

**Test:**
```swift
let pureRed = UIColorFromHex(0xFF0000)
assert(pureRed.redComponent == 1.0)    // Should pass after fix
assert(pureRed.greenComponent == 0.0)
assert(pureRed.blueComponent == 0.0)

let pureWhite = UIColorFromHex(0xFFFFFF)
assert(pureWhite.redComponent == 1.0)  // Should pass after fix
assert(pureWhite.greenComponent == 1.0)
assert(pureWhite.blueComponent == 1.0)
```

---

### Audit: Check for Workarounds
**Approach:** Search for any compensation logic that might have been added to work around this bug

**Search for:**
```bash
grep -r "1.004\|0.996\|compensation\|* 1.00" Apollo16/
```

**Expected Result:** None (no workarounds found)

If workarounds are found, they should be removed since the root cause is now fixed.

---

## Output Requirements

### PR Description
```
## Fix UIColorFromHex Color Math (P2)

### Correct Division Constant
- UIColorFromHex now divides by 255 (correct 8-bit max) instead of 256
- Pure red (0xFF0000) now maps to RGB(1.0, 0, 0) instead of RGB(0.996, 0, 0)
- Pure white (0xFFFFFF) now maps to RGB(1.0, 1.0, 1.0) instead of RGB(0.996, 0.996, 0.996)

### Impact
- All theme colors now achieve intended saturation
- Brand colors match design spec exactly
- ~0.4% saturation improvement across entire UI

Test Results:
- [x] Pure red component == 1.0
- [x] Pure green component == 1.0
- [x] Pure blue component == 1.0
- [x] Pure white components == 1.0
- [x] Gray values unchanged (e.g., 0x808080 → 0.5)
- [x] UI appearance consistent (imperceptible change on sRGB)
- [x] No color compensation needed elsewhere

Changes: 3 lines (3 × /256.0 → /255.0)

Fixes: Color accuracy
Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

---

## Success Criteria

- [ ] All three `/256.0` replaced with `/255.0`
- [ ] UIColorFromHex(0xFF0000).redComponent == 1.0
- [ ] UIColorFromHex(0xFFFFFF) == white
- [ ] No color-compensation workarounds elsewhere
- [ ] UI visually consistent before/after (imperceptible on sRGB)
- [ ] Unit test added to verify math

---

## Dependencies & Handoffs

### Prerequisites
- CRITICAL-BUG-FIX merged

### Parallel Agents
- Can run anytime in Tier 5

---

## Agent Notes

**Files to Modify:**
- `Apollo16/GLOBALS/Functions.swift` (3 lines)

**Unit Test to Add:**
```swift
func testUIColorFromHexMath() {
    let red = UIColorFromHex(0xFF0000)
    XCTAssertEqual(red.redComponent, 1.0)
    XCTAssertEqual(red.greenComponent, 0.0)
    XCTAssertEqual(red.blueComponent, 0.0)
    
    let white = UIColorFromHex(0xFFFFFF)
    XCTAssertEqual(white.redComponent, 1.0)
    XCTAssertEqual(white.greenComponent, 1.0)
    XCTAssertEqual(white.blueComponent, 1.0)
    
    let gray = UIColorFromHex(0x808080)
    XCTAssertEqual(gray.redComponent, 0.5, accuracy: 0.01)
}
```

**Validation:**
```bash
# Build and test
xcodebuild -scheme Apollo16 test

# Screenshot comparison (optional)
# Before: colors look slightly muted
# After: colors look crisp (imperceptible change on sRGB)
```

**Critical Notes:**
- This is a 3-line fix
- Do NOT refactor color usage
- Do NOT add new color functions
- Focus on correctness of math only
