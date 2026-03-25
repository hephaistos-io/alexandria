# Design System Specification: The Tactical Monolith

## 1. Overview & Creative North Star
**Creative North Star: The Tactical Monolith**

This design system is a sophisticated departure from "friendly" consumer tech. It rejects the soft, bubbly aesthetics of the modern web in favor of a precise, high-density, "cyber-intelligence" environment. We are building a digital cockpit where data is the hero.

By combining the brutalist rigidity of a terminal (0px border radii) with the ethereal depth of a high-end intelligence dashboard, we create a "Tactical Monolith." The layout is driven by intentional asymmetry, grid-based logic, and "tech accents"—like coordinate markers and scanning lines—that make the interface feel like a living, breathing piece of advanced hardware. We avoid "standard" layouts by treating the screen as a canvas of layered data rather than a collection of cards.

---

## 2. Colors & Surface Logic

The palette is anchored in deep navies (`surface`) and energized by pastel "intelligence" blues (`primary`).

### The Surface Hierarchy
Depth is achieved through **Tonal Layering**, not lines. 
- **Base Level:** `surface` (#0f131c)
- **Primary Content Areas:** `surface-container-low` (#181c24)
- **Nested Data Nodes:** `surface-container` (#1c2028)
- **Active/Elevated Elements:** `surface-container-high` (#262a33)

### The "No-Line" Rule
Prohibit the use of 1px solid borders for structural sectioning. You must define boundaries through background color shifts. For example, a sidebar should not have a border; it should simply exist as a `surface-container-lowest` block against a `surface` background.

### The "Glass & Glow" Rule
To elevate the "hacky" terminal aesthetic to a premium level:
- **Glassmorphism:** Use semi-transparent versions of `surface-variant` with a `20px` backdrop-blur for floating overlays.
- **Signature Glow:** Primary actions and critical data points should utilize a subtle outer glow. Use the `primary` token (#a9c7ff) with a spread of `2px` and a blur of `12px` at 30% opacity to simulate a high-tech phosphor display.

---

## 3. Typography
The system uses a high-contrast typographic pairing to distinguish between "Interface Instruction" and "Data Output."

- **The UI Layer (Space Grotesk):** Used for Headlines and Labels. Its geometric quirks reinforce the "tech" aesthetic.
- **The Information Layer (Inter):** Used for Body and Title scales to ensure maximum legibility during long-form data consumption.
- **The Data Layer (Monospace):** While not in the primary scale, all numerical values, coordinates, and "system logs" must be rendered in a Monospace font (e.g., JetBrains Mono) at the `label-sm` or `body-sm` size to maintain the terminal soul.

**Key Scale Principle:** Use `display-lg` for impactful, asymmetrical headers that break the grid, providing an editorial feel to a data-heavy page.

---

## 4. Elevation & Depth
In a system with **0px roundedness**, traditional shadows look out of place. We use **Tonal Stacking** and **Ambient Light**.

- **The Layering Principle:** Stack containers to create hierarchy. A `surface-container-highest` card sitting on a `surface-container-low` section creates a natural "lift" without artificial shadows.
- **The Ghost Border:** If a container requires definition against a similar background, use the "Ghost Border"—the `outline-variant` token (#424751) at **15% opacity**. This provides a whisper of structure that mimics a glass edge.
- **Scanning Lines:** On large hero surfaces, apply a 2px repeating linear gradient of `on-surface` at 2% opacity to create a subtle "monitor scanline" texture.

---

## 5. Components

### Buttons
- **Primary:** Background `primary`, text `on-primary`. Sharp 0px corners. Add a `primary` glow on hover.
- **Secondary:** Ghost Border (15% `outline-variant`) with `secondary` text. No background.
- **Tertiary:** Pure text in `tertiary` with a `_` (underscore) prefix to mimic a terminal command.

### Inputs & Terminal Fields
- **Default State:** Background `surface-container-highest`, bottom-border only (1px `outline`).
- **Focus State:** Bottom-border shifts to `primary` with a subtle `primary` glow bleeding upward.
- **Hacky Accent:** Append a small Monospace coordinate (e.g., `[40.7128° N]`) in the top-right corner using `label-sm` in `outline` color.

### Cards & Data Modules
- **Rule:** No dividers. 
- Use vertical white space (Spacing `8` or `10`) to separate content groups. 
- Use a `surface-container-lowest` "header strip" for cards to house titles, creating a clear visual anchor without lines.

### Tech Accents (The Signature)
- **The "Crosshair":** Use 1px `outline-variant` lines that extend slightly past the corners of a primary image or data visualization.
- **The "Status Indicator":** A 4px x 4px square of `tertiary` (green-blue) next to active headers to signal "System Live."

---

## 6. Do's and Don'ts

### Do:
- **Respect the Grid:** Everything must align to the Spacing Scale. If a component is off by 1px, the "tactical" feel is lost.
- **Use Intentional Asymmetry:** Let a column of data sit slightly off-center or have a "floating" coordinate set in the margin.
- **Embrace Density:** This system is for power users. It is okay to have a high volume of information if the hierarchy is clear via color shifts.

### Don't:
- **No Border Radius:** Never use rounded corners. Everything is a sharp 90-degree angle.
- **No Drop Shadows:** Avoid standard "Material Design" shadows. Use tonal shifts or glows instead.
- **No Generic Icons:** Use thin-stroke, geometric icons that match the `outline` weight. Avoid filled, "bubbly" icons.
- **No Pure White:** Never use #FFFFFF. Use `on-surface` (#dfe2ee) to maintain the low-light, cyber-intelligence atmosphere.