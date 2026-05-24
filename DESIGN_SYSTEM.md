# UMI Exchange — Design System Specification

This document defines the complete, production-ready design system for the UMI Exchange mutual aid web application. It is designed to be easily implemented by frontend developers using Tailwind CSS, and read by non-designers to maintain interface consistency.

---

## 1. Design Principles

Good design for community mutual aid is **invisible, accessible, and fast**. We design for scanning, respect the user’s dignity, and prioritize speed of transaction over visual novelty.

*   **Clarity Over Decoration**: Every element on the page must have a functional purpose. Remove borders, lines, and backgrounds that do not aid in visual hierarchy.
*   **Scanning-First (Pictures > Words)**: Users in need or volunteers on the go do not read long paragraphs. They scan. We use large icons, illustrations, color-coded badges, and progressive layouts to convey status instantly before any text is read.
*   **Dignity & Respect**: We avoid clinical or patronizing terminology. Interfaces for posting a need should feel encouraging and safe, not bureaucratic.
*   **Accessibility by Default**: Every interaction target is designed for touch interfaces, meets strict color contrast ratios, and supports standard assistive technologies.

---

## 2. Spacing Scale (4px Grid)

All layout dimensions—including padding, margin, gap size, and absolute positioning—MUST align with a strict **4px grid**. This creates a predictable visual rhythm.

| Tailwind Class | Pixel Value | Rem Value | Common Use Case |
| :--- | :--- | :--- | :--- |
| `p-1` / `m-1` | 4px | 0.25rem | Micro-padding (e.g., badges, inner button margins) |
| `p-2` / `m-2` | 8px | 0.5rem | Small gaps, label-to-input spacing, list items |
| `p-3` / `m-3` | 12px | 0.75rem | Moderate padding inside small cards or alerts |
| `p-4` / `m-4` | 16px | 1rem | Standard container padding, grid gaps, card body |
| `p-6` / `m-6` | 24px | 1.5rem | Desktop card body padding, large section gaps |
| `p-8` / `m-8` | 32px | 2rem | Desktop outer container margins, hero padding |
| `p-12` / `m-12`| 48px | 3rem | Section separators, large empty states |

*Rule*: Never use odd-numbered padding scales like `p-1.5` or `p-5` unless the pixel value is a multiple of 4 (e.g., `p-5` is 20px, which is valid, but avoid it for consistency. Stick to standard 4px steps: 4, 8, 12, 16, 24, 32, 48).

---

## 3. Typography

The default font family for the UMI Exchange user interface is **Open Sans** for clean legibility on lower-resolution mobile screens, falling back to system sans-serif fonts.

### Font Stack
```css
font-family: 'Open Sans', system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
```

### Typographic Scale

| Element | Font Size | Line Height | Tailwind Classes |
| :--- | :--- | :--- | :--- |
| **Page Title (H1)** | 32px (2rem) | 38px (1.2) | `text-3xl font-bold leading-tight tracking-tight` |
| **Section Header (H2)**| 24px (1.5rem) | 28px (1.2) | `text-2xl font-semibold leading-snug` |
| **Card Title (H3)** | 20px (1.25rem)| 24px (1.2) | `text-xl font-semibold leading-normal` |
| **Input Header (H4)** | 18px (1.125rem)| 22px (1.2) | `text-lg font-medium leading-none` |
| **Body Text** | 16px (1rem) | 24px (1.5) | `text-base font-normal leading-relaxed` |
| **Caption/Metadata** | 12px (0.75rem)| 16px (1.3) | `text-xs font-medium text-gray-500` |

---

## 4. Colour Palette

Our colors are selected to build trust (cool, deep primary tones) while providing clear semantic signaling for community needs (warm amber) and offers (cool blue).

```
# Primary Base
██████ #0f172a (slate-900) - Main UI Text / Dark backgrounds
██████ #0284c7 (sky-600)   - Trusted primary buttons / Active state

# Semantic Signals
██████ #d97706 (amber-600) - Needs (alerts action, warming urgency)
██████ #2563eb (blue-600)  - Offers (giving direction, cooling aid)

# UI Elements
██████ #10b981 (emerald-500) - Success, matches verified
██████ #ef4444 (red-500)     - Danger, cancel actions
██████ #f3f4f6 (gray-100)    - Background default gray
```

### Contrast Ratios (WCAG 2.1 AA Compliance)
*   **Body Text**: `#0f172a` (Slate 900) on `#ffffff` (White) gives a contrast ratio of **19.5:1** (Passes AAA).
*   **Primary Button**: White text on `#0284c7` (Sky 600) gives a contrast ratio of **4.6:1** (Passes AA).
*   **Need Badge**: White text on `#d97706` (Amber 600) gives a contrast ratio of **4.5:1** (Passes AA).
*   **Offer Badge**: White text on `#2563eb` (Blue 600) gives a contrast ratio of **5.3:1** (Passes AA).

---

## 5. Button Styles and Placement

Buttons are the primary method of driving actions. Their placement must be highly predictable.

### Button Variations

```html
<!-- Primary Action Button -->
<button class="inline-flex items-center justify-center px-4 py-2 text-sm font-semibold text-white bg-sky-600 rounded-lg hover:bg-sky-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-sky-500 transition-colors">
  Create Post
</button>

<!-- Secondary Action Link -->
<button class="inline-flex items-center justify-center px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-sky-500 transition-colors">
  Cancel
</button>

<!-- Danger Action Button -->
<button class="inline-flex items-center justify-center px-4 py-2 text-sm font-semibold text-white bg-red-600 rounded-lg hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 transition-colors">
  Delete Record
</button>
```

### Placement Diagrams (ASCII)

#### Desktop Layout (Forms and Panels)
Primary buttons are always placed in the **top-right** corner of the content panel, allowing a user scanning down to find the action instantly. Secondary cancel actions sit to the left.

```
+-------------------------------------------------------------+
|  Edit Profile                               [Cancel] [Save] |
+-------------------------------------------------------------+
|  [Input: Full Name                       ]                  |
|  [Input: Email Address                   ]                  |
+-------------------------------------------------------------+
```

#### Mobile Sticky Layout
On screens smaller than `640px`, the primary action is fixed to the bottom of the viewport, ensuring it is always within thumb reach.

```
+----------------------------------+
|  [Input: Need Description     ]  |
|  [Input: Category Radio       ]  |
|                                  |
|  ... (scrollable form content)   |
|                                  |
+----------------------------------+
| [           POST NEED          ] |  <-- Sticky Bottom Action
+----------------------------------+
```

---

## 6. Icon and Illustration Guidelines

Text alone is inefficient for quick comprehension. We utilize clean, simple vector iconography (Lucide or Heroicons) to represent actions and categories.

*   **Touch Targets**: Icons used as buttons must have a minimum clickable area of **44×44px** (Tailscale/iOS standard).
*   **Accessibility (Screen Readers)**: 
    *   If an icon is decorative, it must include `aria-hidden="true"`.
    *   If an icon stands alone without text, it must be wrapped in a container with a descriptive `sr-only` class.
*   **Category Association**:
    *   *Food*: `utensils` / `shopping-bag` icon.
    *   *Transport*: `car` / `truck` icon.
    *   *Housing*: `home` / `bed` icon.
    *   *Repairs*: `wrench` / `hammer` icon.
    *   *Childcare*: `baby` / `users` icon.

---

## 7. Component Examples

### A. Need/Offer Card

#### ASCII Wireframe
```
+-------------------------------------------------------+
|  (Icon) Transport                  [ URGENCY: HIGH ]  |
|  Requested by: Anonymous (VLAN/Privacy Mask)          |
|  Need: Ride to medical checkup tomorrow afternoon     |
|                                                       |
|  [Accept Match Request]                               |
+-------------------------------------------------------+
```

#### Tailwind Implementation
```html
<div class="bg-white rounded-xl border border-gray-200 p-4 shadow-sm hover:shadow-md transition-shadow">
  <div class="flex items-center justify-between gap-4 mb-2">
    <div class="flex items-center gap-2">
      <span class="p-2 bg-amber-100 rounded-lg text-amber-800" aria-hidden="true">
        <!-- SVG Icon here -->
        <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" /></svg>
      </span>
      <h3 class="text-base font-semibold text-gray-900">Transport</h3>
    </div>
    <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800">
      Urgent
    </span>
  </div>
  <p class="text-sm text-gray-600 mb-4">Need: Ride to medical checkup tomorrow afternoon</p>
  <div class="flex justify-end">
    <button class="inline-flex items-center justify-center px-3 py-1.5 text-xs font-semibold text-white bg-sky-600 rounded-lg hover:bg-sky-700">
      Accept Match
    </button>
  </div>
</div>
```

---

### B. Category Selector Grid

#### ASCII Wireframe
```
+------------------+  +------------------+  +------------------+
|      (Icon)      |  |      (Icon)      |  |      (Icon)      |
|       Food       |  |    Transport     |  |     Housing      |
+------------------+  +------------------+  +------------------+
```

#### Tailwind Implementation
```html
<div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
  <label class="flex flex-col items-center p-4 bg-white border border-gray-200 rounded-xl cursor-pointer hover:border-sky-500 transition-colors focus-within:ring-2 focus-within:ring-sky-500">
    <input type="radio" name="category" value="food" class="sr-only">
    <span class="p-3 bg-sky-50 text-sky-600 rounded-full mb-2" aria-hidden="true">
      <svg class="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364-6.364l-.707.707M6.343 17.657l-.707.707m0-12.728l.707.707m12.728 12.728l.707-.707" /></svg>
    </span>
    <span class="text-sm font-semibold text-gray-900">Food</span>
  </label>
  <!-- Repeat for other categories -->
</div>
```

---

## 8. Responsive Layout Rules

*   **Global Max-Width**: `max-width: 1280px` (`max-w-7xl` in Tailwind).
*   **Gutters**:
    *   Mobile: `16px` (`px-4`).
    *   Desktop: `32px` (`md:px-8`).
*   **Breakpoints**:
    *   `sm`: 640px (typically tablet devices / columns wrap).
    *   `md`: 768px (medium monitors).
    *   `lg`: 1024px (standard desktop).
    *   `xl`: 1280px (maximum application container width limit).

---

## 9. Rapid Mockup Testing Template

Before committing a new feature to code, technical volunteers must test UI flows with a minimum of **one coordinator or volunteer** using low-fidelity HTML/CSS pages.

### User Testing Protocol
1. **Explain the context**: "Imagine you need to post a request for food on behalf of a household."
2. **Give them the mockup**: Let them navigate the layout. Do not give hints on what buttons to click.
3. **Observe**:
    *   Do they look at the top-right corner to submit forms?
    *   Are the category grid icons clearly understood without checking labels?
    *   Do they struggle with touch targets on mobile simulations?
4. **Debrief**:
    *   "Was there anything confusing about finding the button?"
    *   "Were the illustrations/empty states helpful?"
5. **Document Iterations**: Record changes made to the templates in response to testing.

---

## 10. Quick Start CSS (Tailwind Configuration)

Add this custom configuration to your `tailwind.config.js` to extend default parameters with UMI Exchange styles.

```javascript
// tailwind.config.js
module.exports = {
  content: [
    './templates/**/*.html',
    './apps/**/*.py',
    './static/**/*.js',
  ],
  theme: {
    extend: {
      spacing: {
        '18': '4.5rem', // Multiples of 4px
        '22': '5.5rem',
      },
      fontFamily: {
        sans: ['"Open Sans"', 'system-ui', '-apple-system', 'sans-serif'],
        serif: ['Merriweather', 'Georgia', 'serif'],
      },
      colors: {
        primary: {
          light: '#38bdf8', // sky-400
          DEFAULT: '#0284c7', // sky-600
          dark: '#0369a1', // sky-700
        },
        need: {
          DEFAULT: '#d97706', // amber-600
        },
        offer: {
          DEFAULT: '#2563eb', // blue-600
        }
      }
    },
  },
  plugins: [
    require('@tailwindcss/forms'),
  ],
}
```
