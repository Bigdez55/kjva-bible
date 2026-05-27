---
agent_id: deprecated-api-removal
agent_name: Deprecated API Removal Agent
tier: 4
priority: P1
status: pending
depends_on: [critical-bug-fix]
created_date: 2026-04-25
---

# Deprecated API Removal Agent

## Overview
Remove and replace deprecated UIKit APIs that break on iOS 17+ and generate compiler warnings.

## Tier & Priority
- **Tier:** 4 (Deprecated API, Security, App Store Readiness)
- **Priority:** P1
- **Estimated Duration:** 4–5 hours
- **Blocker:** iOS 17+ support requires this

## Scope

### Issue #1: UIGraphicsBeginImageContextWithOptions (Deprecated iOS 17)
**File:** `Apollo16/GLOBALS/EXTENSIONS/UIImage.swift`  
**Severity:** HIGH

**Current Code:**
```swift
func tinted(with color: UIColor) -> UIImage {
    UIGraphicsBeginImageContextWithOptions(self.size, false, self.scale)
    color.setFill()
    // ... drawing code ...
    let tintedImage = UIGraphicsGetImageFromCurrentImageContext()!
    UIGraphicsEndImageContext()
    return tintedImage
}
```

**Problem:** Deprecated since iOS 17, doesn't support wide color (Display P3).

**Fix:**
```swift
func tinted(with color: UIColor) -> UIImage {
    let renderer = UIGraphicsImageRenderer(size: self.size)
    
    return renderer.image { context in
        color.setFill()
        UIRectFill(CGRect(origin: .zero, size: self.size))
        
        self.draw(at: .zero, blendMode: .destinationIn, alpha: 1.0)
    }
}
```

**Test:** Build on iOS 13, 17, latest beta. No compiler warnings. Tinted image renders correctly.

---

### Issue #2: UIApplication.shared.keyWindow (Deprecated iOS 13)
**Files:**
- `Apollo16/AppDelegate.swift`, `getTopViewController()`
- `Apollo16/SceneDelegate.swift`, `getTopViewController()`

**Severity:** HIGH

**Current Code:**
```swift
var topController = UIApplication.shared.keyWindow!.rootViewController
```

**Problem:** Deprecated since iOS 13. On multi-scene apps, returns arbitrary window. Force-unwrap crashes if called before scene ready.

**Fix:**
```swift
private func getTopViewController() -> UIViewController? {
    // Get the window scene for the connected scenes
    guard let windowScene = UIApplication.shared.connectedScenes.first(where: { $0 is UIWindowScene }) as? UIWindowScene,
          let keyWindow = windowScene.windows.first(where: { $0.isKeyWindow }) else {
        return nil
    }
    
    var topController = keyWindow.rootViewController
    
    while let presentedViewController = topController?.presentedViewController {
        topController = presentedViewController
    }
    
    return topController
}
```

**Test:** Build on iOS 13+. Call from multiple threads/scenes. No crashes.

---

### Issue #3: MPMediaPickerController Pushed Instead of Presented
**File:** `Apollo16/VIEW CONTROLLERS/AddNote.swift`, `presentPicker()` function  
**Severity:** HIGH (UI Behavior)

**Current Code:**
```swift
func presentPicker() {
    let picker = MPMediaPickerController(mediaTypes: .music)
    self.navigationController?.pushViewController(picker, animated: true)
}
```

**Problem:** MPMediaPickerController is designed to be presented modally, not pushed. Dismiss button doesn't work.

**Fix:**
```swift
func presentPicker() {
    let picker = MPMediaPickerController(mediaTypes: .music)
    picker.delegate = self
    self.present(picker, animated: true)
}

// And ensure:
extension AddNote: MPMediaPickerControllerDelegate {
    func mediaPicker(_ mediaPicker: MPMediaPickerController,
                    didPickMediaItems mediaItemCollection: MPMediaItemCollection) {
        // Handle selection
        mediaPicker.dismiss(animated: true)
    }
    
    func mediaPickerDidCancel(_ mediaPicker: MPMediaPickerController) {
        mediaPicker.dismiss(animated: true)
    }
}
```

**Test:** Open music picker, select song, verify picker dismisses. Tap cancel, verify dismisses.

---

### Issue #4: class Constraint on Protocol (Deprecated Swift 5.7)
**File:** `Apollo16/VIEW CONTROLLERS/SearchTableViewController.swift`, line 11  
**Severity:** LOW (Compiler warning)

**Current Code:**
```swift
protocol SearchTableViewControllerDelegate: class {
    func btn_copyTapped(at: IndexPath)
}
```

**Fix:**
```swift
protocol SearchTableViewControllerDelegate: AnyObject {
    func btn_copyTapped(at: IndexPath)
}
```

**Test:** Build with Swift 5.7+. No warnings.

---

### Issue #5: ChooseSource Bottom Sheet Gesture Issues
**File:** `Apollo16/NIBS/Bottom Sheet/ChooseSource.swift`, `setupGesture()`  
**Severity:** MEDIUM (Non-functional code)

**Current Code:**
```swift
func setupGesture() {
    let swipe1 = UISwipeGestureRecognizer(target: self, action: #selector(handleSwipeGesture))
    swipe1.direction = .down
    let swipe2 = UISwipeGestureRecognizer(target: self, action: #selector(handleSwipeGesture))
    swipe1.direction = .down   // ⚠️ sets swipe1 again, not swipe2!
    
    self.addGestureRecognizer(swipe1)
    contentView.addGestureRecognizer(swipe2)
}
```

**Fix:**
```swift
func setupGesture() {
    let swipe1 = UISwipeGestureRecognizer(target: self, action: #selector(handleSwipeGesture))
    swipe1.direction = .down
    let swipe2 = UISwipeGestureRecognizer(target: self, action: #selector(handleSwipeGesture))
    swipe2.direction = .down   // FIX: set swipe2, not swipe1
    
    self.isUserInteractionEnabled = true
    self.addGestureRecognizer(swipe1)
    contentView.isUserInteractionEnabled = true
    contentView.addGestureRecognizer(swipe2)
}
```

---

### Issue #6: ChooseSource Hardcoded center.y (Device-Specific)
**File:** `Apollo16/NIBS/Bottom Sheet/ChooseSource.swift`, `uiRotated()` function  
**Severity:** MEDIUM (Layout breaks on different devices)

**Current Code:**
```swift
@objc func uiRotated() {
    if UIDevice.current.orientation.isLandscape {
        self.center.y = 485
    } else {
        self.center.y = 929
    }
}
```

**Problem:** Values hardcoded for specific device. Breaks on iPad, different iPhones, future screen sizes.

**Fix:**
```swift
@objc func uiRotated() {
    guard let parentView = parentView else { return }
    
    let screenHeight = UIScreen.main.bounds.height
    let viewHeight = self.bounds.height
    
    if UIDevice.current.orientation.isLandscape {
        self.center.y = screenHeight - (viewHeight / 2) - 16
    } else {
        self.center.y = screenHeight - (viewHeight / 2) - 16
    }
}
```

---

## Output Requirements

### PR Description
```
## Remove Deprecated UIKit APIs (P1)

### Replace UIGraphicsBeginImageContextWithOptions
- Upgrade to UIGraphicsImageRenderer
- Supports wide color gamut (Display P3)
- Fixes compiler warning on iOS 17+

### Replace UIApplication.shared.keyWindow
- Use UIApplication.connectedScenes query
- Supports multi-scene apps correctly
- No force-unwrap crashes

### Fix MPMediaPickerController Presentation
- Use present() instead of pushViewController()
- Dismiss button now works correctly
- Proper delegate flow

### Fix Protocol class Constraint
- Replace deprecated `class` with `AnyObject`
- Fixes Swift 5.7+ warnings

### Fix ChooseSource Gesture Setup
- swipe2.direction now set correctly
- Both gestures work as intended

### Fix ChooseSource Hardcoded Positions
- Remove device-specific center.y values
- Compute position relative to parentView
- Works on all device sizes

Changes:
- UIImage.swift: ~10 lines (image renderer)
- AppDelegate.swift: ~10 lines (window query)
- SceneDelegate.swift: ~10 lines (window query)
- AddNote.swift: ~5 lines (present picker)
- SearchTableViewController.swift: ~1 line (class → AnyObject)
- ChooseSource.swift: ~15 lines (gesture + layout fixes)

Fixes: Deprecated APIs, broken presentation, device-specific layout
Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

---

## Success Criteria

- [ ] No UIGraphicsBeginImageContextWithOptions calls remain
- [ ] All window access uses connectedScenes
- [ ] MPMediaPickerController presented modally (not pushed)
- [ ] No `class` constraints on protocols
- [ ] Swipe gestures configured correctly
- [ ] Bottom sheet position works on all device sizes/orientations
- [ ] Builds on iOS 13, 17, latest beta with no warnings
- [ ] Manual QA: pick music, select from rhyming, rotate device, verify layout

---

## Dependencies & Handoffs

### Prerequisites
- CRITICAL-BUG-FIX merged

### Parallel Agents
- Can run in parallel with other Tier 4 agents

---

## Agent Notes

**Files to Modify:**
- `Apollo16/GLOBALS/EXTENSIONS/UIImage.swift`
- `Apollo16/AppDelegate.swift`
- `Apollo16/SceneDelegate.swift`
- `Apollo16/VIEW CONTROLLERS/AddNote.swift`
- `Apollo16/VIEW CONTROLLERS/SearchTableViewController.swift`
- `Apollo16/NIBS/Bottom Sheet/ChooseSource.swift`

**Build Validation:**
```bash
# Build on iOS 13
xcodebuild -scheme Apollo16 -sdk iphoneos13.7 build

# Build on latest
xcodebuild -scheme Apollo16 build

# Check for remaining deprecated APIs
grep -r "UIGraphicsBeginImageContextWithOptions\|keyWindow\|class:" Apollo16/ --include="*.swift"
```

**Critical Notes:**
- Do NOT refactor broader than deprecated API replacement
- Do NOT redesign ChooseSource (just fix bugs)
- Focus on compatibility and correctness
