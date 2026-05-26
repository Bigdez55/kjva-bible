/*
 * design-system/src/tokens.ts - Tokenless companion design tokens
 *
 * Copyright (c) 2026 Tokenless Models Project. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-Proprietary
 *
 * Tokenless companion design tokens for the React/Web layer.
 *
 * The default palette is intentionally generic. Consuming projects can replace
 * these values with their own brand system.
 *
 * Non-color tokens (spacing, radius, motion, z-order) ARE synchronized
 * with design_tokens.h and must remain in sync.
 *
 * See also: nativeColors export for C-layer aligned values.
 *
 * LAST SYNC (non-color): Sprint 34 audit (2026-03-20)
 */

// ── Colors ────────────────────────────────────────────────────────────────────
// Derived from XTOKEN_COLOR_* in design_tokens.h.

export const colors = {
  // ── Tokenless default palette ──────────────────────────────────────────────
  // These are companion defaults; consuming projects may override them.
  primary:     "#ff7518",
  primaryMuted: "#cc5f14",  // Darker orange for hover/muted
  secondary:   "#1aa7ec",   // Blue accent
  neutral0:    "#0d1115",   // Deep dark background
  neutral100:  "#151b22",   // Card / panel surfaces
  neutral200:  "#202a34",   // Elevated surfaces
  neutral300:  "#334152",   // Borders, dividers
  neutral900:  "#f7fbff",   // Primary text (near-white)
  success:     "#17b978",   // Success green
  warning:     "#ffbe0b",   // Warning amber
  danger:      "#ef476f",   // Danger red

  // Semantic aliases (same values, clearer naming)
  bgPrimary:     "#0d1115",
  bgSecondary:   "#151b22",
  bgTertiary:    "#202a34",
  textPrimary:   "#f7fbff",
  textSecondary: "#94a3b8",
  textDisabled:  "#475569",
  error:         "#ef476f",
  errorBg:       "#2d1018",
  successBg:     "#0d2818",
  warningBg:     "#2d2208",
  info:          "#1aa7ec",
  gold:          "#B5830C",
  accent:        "#ff7518",   // Same as primary
  accentHover:   "#cc5f14",
  accentActive:  "#a84d10",

  // Borders
  border:      "#334152",
  borderFocus: "#ff7518",   // Orange focus ring (brand)
  focusRing:   "#ff7518",

  // Scrim / overlay
  scrim: "rgba(0, 0, 0, 0.6)",

  // Selection
  selection: "rgba(255, 117, 24, 0.25)",   // Orange selection highlight

  // Scrollbar
  scrollbarTrack: "#1a1f26",
  scrollbarThumb: "#334152",
  scrollbarHover: "#475569",

  // Editor / spreadsheet surfaces
  slideBg:       "#FFFFFF",
  sheetHeader:   "#1a1f26",
  sheetSelected: "rgba(255, 117, 24, 0.20)",
  sheetGrid:     "#252d38",
  gutterBg:      "#0d1115",
  lineHighlight: "#151b22",
} as const;

// ── Native C-Layer Colors ────────────────────────────────────────────────────
// These match design_tokens.h XTOKEN_COLOR_* exactly. Used ONLY by code that
// must render identically to the C XCOMP/XFRAME compositor (e.g., ts_bridge).
// Product UI code should use `colors` above, NOT `nativeColors`.
export const nativeColors = {
  accent:       "#3A8FE8",   // XTOKEN_COLOR_ACCENT
  accentHover:  "#5AA0F0",   // XTOKEN_COLOR_ACCENT_HOVER
  accentActive: "#2A6FC8",   // XTOKEN_COLOR_ACCENT_ACTIVE
  bgPrimary:    "#0A0A1A",   // XTOKEN_COLOR_BG_PRIMARY
  bgSecondary:  "#1A1A2E",   // XTOKEN_COLOR_BG_SECONDARY
  bgTertiary:   "#2A2A3E",   // XTOKEN_COLOR_BG_TERTIARY
  textPrimary:  "#FFFFFF",   // XTOKEN_COLOR_TEXT_PRIMARY
  textSecondary:"#B0B0C0",   // XTOKEN_COLOR_TEXT_SECONDARY
  error:        "#E84040",   // XTOKEN_COLOR_ERROR
  success:      "#40C040",   // XTOKEN_COLOR_SUCCESS
  warning:      "#E8A040",   // XTOKEN_COLOR_WARNING
  info:         "#4080E8",   // XTOKEN_COLOR_INFO
  border:       "#3A3A4E",   // XTOKEN_COLOR_BORDER
} as const;

// ── Typography ────────────────────────────────────────────────────────────────
// Font sizes derived from XTOKEN_FONT_SIZE_* in design_tokens.h.
// All values are pixel integers in the C layer; expressed as "Npx" strings here.

export const typography = {
  families: {
    sans: '"Inter", "Noto Sans", sans-serif'
  },
  scale: {
    xs:  "12px",   // XTOKEN_FONT_SIZE_XS  = 12
    sm:  "14px",   // XTOKEN_FONT_SIZE_SM  = 14
    md:  "16px",   // XTOKEN_FONT_SIZE_MD  = 16 (XTOKEN_FONT_SIZE_DEFAULT)
    lg:  "20px",   // XTOKEN_FONT_SIZE_LG  = 20
    xl:  "24px",   // XTOKEN_FONT_SIZE_XL  = 24  ← was "28px" (FIXED S34)
    xxl: "32px",   // XTOKEN_FONT_SIZE_2XL = 32  ← was "2rem" (FIXED S34)
    xxxl: "48px",  // XTOKEN_FONT_SIZE_3XL = 48
  },
  weight: {
    regular:  400,
    medium:   500,
    semibold: 600,
    bold:     700
  },
  lineHeight: {
    tight:  1.20,   // XTOKEN_LINE_HEIGHT_TIGHT  = 120 (×100 fixed-point)
    normal: 1.50,   // XTOKEN_LINE_HEIGHT_NORMAL = 150
    loose:  1.75,   // XTOKEN_LINE_HEIGHT_LOOSE  = 175
  }
} as const;

// ── Spacing ───────────────────────────────────────────────────────────────────
// Derived from XTOKEN_SPACE_* in design_tokens.h.
//
// C token        px   TS name
// XTOKEN_SPACE_2XS  2    (no TS alias — use inline "2px" if needed)
// XTOKEN_SPACE_XS   4    x1
// XTOKEN_SPACE_SM   8    x2
// (no C token)      12   x3  ← TS-only intermediate step
// XTOKEN_SPACE_MD   16   x4
// (no C token)      20   x5  ← TS-only intermediate step
// XTOKEN_SPACE_LG   24   x6
// XTOKEN_SPACE_XL   32   x8
// XTOKEN_SPACE_2XL  48   x12
// XTOKEN_SPACE_3XL  64   x16

export const spacing = {
  x1:  "4px",    // XTOKEN_SPACE_XS  = 4
  x2:  "8px",    // XTOKEN_SPACE_SM  = 8
  x3:  "12px",   // TS-only
  x4:  "16px",   // XTOKEN_SPACE_MD  = 16
  x6:  "24px",   // XTOKEN_SPACE_LG  = 24
  x8:  "32px",   // XTOKEN_SPACE_XL  = 32
  x12: "48px",   // XTOKEN_SPACE_2XL = 48
  x16: "64px",   // XTOKEN_SPACE_3XL = 64
} as const;

// ── Border Radius ─────────────────────────────────────────────────────────────
// Derived from XTOKEN_RADIUS_* in design_tokens.h.
//
// C token           px   TS name
// XTOKEN_RADIUS_XS   2   (no TS alias)
// XTOKEN_RADIUS_SM   4   sm   ← was "8px" (FIXED S34)
// XTOKEN_RADIUS_MD   8   md   ← was "12px" (FIXED S34)
// XTOKEN_RADIUS_LG   12  lg   ← was "16px" (FIXED S34)
// XTOKEN_RADIUS_XL   16  xl
// XTOKEN_RADIUS_FULL 9999 pill ← was "999px" (FIXED S34)

export const radius = {
  sm:   "4px",     // XTOKEN_RADIUS_SM   = 4
  md:   "8px",     // XTOKEN_RADIUS_MD   = 8  (XTOKEN_RADIUS_BTN, XTOKEN_RADIUS_INPUT via SM)
  lg:   "12px",    // XTOKEN_RADIUS_LG   = 12 (XTOKEN_RADIUS_CARD)
  xl:   "16px",    // XTOKEN_RADIUS_XL   = 16
  pill: "9999px",  // XTOKEN_RADIUS_FULL = 9999
} as const;

// ── Shadows ───────────────────────────────────────────────────────────────────
// No direct C equivalents — shadow tokens are TS-only (C layer uses flat
// compositor surfaces without box-shadow). These are used exclusively by the
// Electron/web shell layer.

export const shadows = {
  low:  "0 2px 8px rgba(0, 0, 0, 0.2)",
  mid:  "0 8px 20px rgba(0, 0, 0, 0.26)",
  high: "0 16px 36px rgba(0, 0, 0, 0.34)"
} as const;

// ── Motion ────────────────────────────────────────────────────────────────────
// Durations derived from XTOKEN_DURATION_* in design_tokens.h.
// Easing is TS-only (C layer uses xanim_easing_t enum values).
//
// XTOKEN_DURATION_FAST   = 120ms ✓
// XTOKEN_DURATION_NORMAL = 220ms ✓
// XTOKEN_DURATION_SLOW   = 340ms ✓

export const motion = {
  fast:   "120ms cubic-bezier(0.2, 0, 0.2, 1)",   // XTOKEN_DURATION_FAST
  normal: "220ms cubic-bezier(0.2, 0, 0.2, 1)",   // XTOKEN_DURATION_NORMAL
  slow:   "340ms cubic-bezier(0.2, 0, 0.2, 1)",   // XTOKEN_DURATION_SLOW
} as const;

// ── Z-order ───────────────────────────────────────────────────────────────────
// Derived from XTOKEN_Z_* in design_tokens.h.
// Values MUST match the compositor z conventions exactly.
// Used in CSS z-index; negative values are valid.

export const zOrder = {
  wallpaper: -100,   // XTOKEN_Z_WALLPAPER = -100
  desktop:     0,    // XTOKEN_Z_DESKTOP   = 0
  window:    100,    // XTOKEN_Z_WINDOW    = 100
  panel:     200,    // XTOKEN_Z_PANEL     = 200
  modal:     500,    // XTOKEN_Z_MODAL     = 500
  dropdown:  600,    // XTOKEN_Z_DROPDOWN  = 600
  toast:     800,    // XTOKEN_Z_TOAST     = 800
  tooltip:   900,    // XTOKEN_Z_TOOLTIP   = 900
  cursor:  32767,    // XTOKEN_Z_CURSOR    = 32767
} as const;

// ── Component Dimensions ──────────────────────────────────────────────────────
// Derived from XTOKEN_BTN_HEIGHT, XTOKEN_INPUT_HEIGHT, etc. in design_tokens.h.

export const dimensions = {
  btnHeight:         "36px",    // XTOKEN_BTN_HEIGHT    = 36
  btnHeightSm:       "28px",    // XTOKEN_BTN_HEIGHT_SM = 28
  inputHeight:       "36px",    // XTOKEN_INPUT_HEIGHT  = 36
  sidebarWidth:      "240px",   // XTOKEN_SIDEBAR_WIDTH = 240
  sidebarWidthCollapsed: "48px", // XTOKEN_SIDEBAR_WIDTH_COLLAPSED = 48
  scrollbarWidth:    "8px",     // XTOKEN_SCROLLBAR_WIDTH = 8
  scrollbarThumbMin: "24px",    // XTOKEN_SCROLLBAR_THUMB_MIN = 24
  dialogMaxWidth:    "480px",   // XTOKEN_DIALOG_MAX_W = 480
  toastWidth:        "320px",   // XTOKEN_TOAST_WIDTH  = 320
} as const;
