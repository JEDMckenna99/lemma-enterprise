# lemma.id Brand Kit

Shareable reference for design agents. Source of truth in product CSS: `static/css/lemma.css`.

**Product:** lemma.id — site-private person continuity with optional human proof and action binding.  
**Visual direction:** Ink + jewel violet. Institutional, not SaaS blurple. Cool charcoal neutrals — not Tailwind slate defaults. Prefer IBM Plex over Inter/system UI kits.

---

## Logo

**Name:** Orbit mark  
**Concept:** Four overlapping ellipses (orbital rings) centered on a shared origin. Stroke-only, no fill. Brand violet `#4E3D8F`.

### Asset paths (repo)

| File | Use |
|------|-----|
| `logo/lemma_logo.svg` | Canonical SVG mark |
| `static/img/lemma_logo.svg` | Web-served SVG |
| `static/img/lemma_logo.png` | Raster fallback |
| `static/img/favicon.svg` | Favicon (heavier stroke for small sizes) |
| `static/img/apple-touch-icon.png` | Apple touch icon |
| `static/favicon.ico` | Legacy favicon |

### Canonical SVG (copy into Figma / design tools)

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120">
  <g stroke="#4E3D8F" stroke-width="6" fill="none" stroke-linecap="round" stroke-linejoin="round">
    <ellipse cx="60" cy="60" rx="38" ry="14"/>
    <ellipse cx="60" cy="60" rx="38" ry="14" transform="rotate(90 60 60)"/>
    <ellipse cx="60" cy="60" rx="38" ry="14" transform="rotate(45 60 60)"/>
    <ellipse cx="60" cy="60" rx="38" ry="14" transform="rotate(-45 60 60)"/>
  </g>
</svg>
```

### Logo rules

- Keep stroke-only; do not fill the ellipses.
- Default mark color: brand primary `#4E3D8F`.
- On dark surfaces: use white `#FFFFFF` stroke.
- Minimum clear space: roughly 1/4 of the mark’s width on all sides.
- Do not stretch, skew, add glow, gradients, or drop shadows to the mark.
- Wordmark: set **lemma.id** in IBM Plex Sans (semibold/bold for lockups). Prefer lowercase `lemma.id`.

---

## Color palette

### Brand (jewel violet)

| Token | Hex | RGB | Role |
|-------|-----|-----|------|
| Primary / Accent | `#4E3D8F` | `78, 61, 143` | Brand, links, focus accents |
| Primary light | `#6B5CAD` | | Hover / lighter accent |
| Primary 600 | `#433580` | | Mid dark |
| Primary dark / 700 / Secondary | `#3A2D6E` | | Pressed, dark brand |
| Primary 200 (line) | `#C9C2E0` | | Soft borders, dividers |
| Primary 100 | `#E4E0F0` | | Light tint |
| Primary 50 (soft) | `#F2F0F8` | | Soft surfaces, selected rows |

### Neutrals (cool charcoal)

| Token | Hex | Role |
|-------|-----|------|
| Black / Ink | `#12121A` | Deepest ink |
| Gray 900 / Text | `#1A1A24` | Headings, primary buttons |
| Gray 800 | `#2C2C38` | Strong body |
| Gray 700 | `#454554` | Default body |
| Gray 600 / Muted | `#5E5E70` | Secondary text |
| Gray 500 | `#8A8A9A` | Tertiary / labels |
| Gray 400 | `#B4B4C0` | Placeholder-ish |
| Gray 300 | `#D6D6DE` | Strong lines |
| Gray 200 / Line | `#E8E8EE` | Borders |
| Gray 100 / Canvas | `#F4F4F7` | Page canvas |
| White / Surface | `#FFFFFF` | Cards, surfaces |

### Semantic

| Token | Hex | Role |
|-------|-----|------|
| Success | `#1F7A4C` | Positive states |
| Warning | `#B45309` | Caution |
| Error | `#C0392B` | Errors / destructive |

### Common UI pairings (from product UI)

| Use | Spec |
|-----|------|
| Page background | `#FFFFFF` or canvas `#F4F4F7` |
| Primary CTA (marketing) | Fill `#1A1A24`, text white (ink button) — brand violet for links/accents |
| Brand accent CTA | Fill `#4E3D8F`, text white |
| Success chip | bg `#ECFDF3`, border `#A7F3D0`, text `#1F7A4C` |
| Error chip | bg `#FEF2F2`, border `#FECACA`, text `#C0392B` |
| Focus ring | `0 0 0 3px rgba(78, 61, 143, 0.15)` |

### Quick swatches (for agents)

```
Brand:    #4E3D8F  #6B5CAD  #3A2D6E  #F2F0F8  #C9C2E0
Ink:      #12121A  #1A1A24  #5E5E70  #E8E8EE  #F4F4F7  #FFFFFF
Semantic: #1F7A4C  #B45309  #C0392B
```

---

## Typography

| Role | Family |
|------|--------|
| UI / body / headings | **IBM Plex Sans**, fallbacks: `"Segoe UI", system-ui, sans-serif` |
| Code / mono | **IBM Plex Mono**, fallbacks: `"SF Mono", Consolas, monospace` |

### Scale (product)

| Token | Size |
|-------|------|
| xs | 13px |
| sm | 15px |
| base | 17px |
| lg | 19px |
| xl | 22px |
| 2xl | 28px |
| 3xl | 36px |
| 4xl | 48px |

- Body line-height ≈ `1.6`; headings ≈ `1.25`, weight `600`.
- Avoid Inter, Roboto, Arial as the primary face.

---

## Layout tokens (optional)

- Spacing: 8pt grid (`4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48 / 64 / 80 / 96`)
- Max content width: `1200px`
- Default radius: `6px` (not pill-heavy)
- Shadow: `0 1px 2px rgba(18, 18, 26, 0.06)` / large `0 8px 24px rgba(18, 18, 26, 0.1)`

---

## Design do / don’t

**Do**
- Treat brand violet as a jewel accent on ink/white, not a purple-gradient theme.
- Keep whitespace generous; match the marketing site tone (`templates/modern/`).
- Use the orbit mark as a quiet identity signal, not decorative chrome.

**Don’t**
- Default to generic purple-on-white SaaS gradients or indigo kit colors.
- Replace IBM Plex with Inter.
- Soften the brand into pastel lavender or neon glow.
- Put heavy card grids or dashboard chrome on marketing heroes unless the surface is actually a dashboard.

---

## CSS variable map (for implementation parity)

```css
--primary: #4E3D8F;
--primary-dark: #3A2D6E;
--primary-light: #6B5CAD;
--primary-50: #F2F0F8;
--primary-100: #E4E0F0;
--primary-200: #C9C2E0;
--primary-500: #4E3D8F;
--primary-600: #433580;
--primary-700: #3A2D6E;
--black: #12121A;
--gray-900: #1A1A24;
--gray-600: #5E5E70;
--gray-200: #E8E8EE;
--gray-100: #F4F4F7;
--white: #ffffff;
--success: #1F7A4C;
--warning: #B45309;
--error: #C0392B;
--font-family: "IBM Plex Sans", "Segoe UI", system-ui, sans-serif;
--font-mono: "IBM Plex Mono", "SF Mono", Consolas, monospace;
```

Live reference: https://lemma.id
