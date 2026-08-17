# PisGo product UI

PisGo is a modern agricultural operations console for deciding when Cavendish bananas should be harvested, shipped, and expected to arrive. It must feel useful before it feels designed.

## Product character

- Quiet, precise, field-ready, and operational.
- Logistics clarity with a restrained agricultural identity.
- No landing-page storytelling, marketing copy, decorative illustration, or invented insight.
- Show only information that helps an operator make the harvest and shipping decision.

## Information hierarchy

1. **Harvest → Ship → Arrive** recommendation.
2. Expected maturity at arrival and recommendation status.
3. Route map, origin, destination, distance, and driving duration.
4. DAF, current maturity, target maturity, confidence, and model context.
5. Baseline-development disclosure.

Never give supporting evidence the same visual weight as the recommendation.

## Layout

### Desktop

- Use a compact `56px` product header and a workspace below it.
- Left control rail: `400px` nominal width, `360–440px` acceptable.
- Main workspace: all remaining width; map and decision schedule belong to this same working surface.
- Before analysis, let the map dominate the visible workspace. After analysis, reduce its height enough to expose the recommendation without making the map secondary.
- Keep the map large and flat; do not place it in a decorative dashboard card.
- Group rail controls with whitespace and thin section dividers, not a card per field.
- Put the recommendation directly below the map as one connected schedule surface, never as a detached page section.
- Keep the complete form, map, and empty recommendation useful within the first desktop screen where practical.

### Mobile

Use this sequence without imitating the desktop sidebar:

1. Banana information and flowering date.
2. Calculated DAF and specimen image.
3. Target maturity.
4. Origin and destination.
5. Analyze action.
6. Map and route facts.
7. Harvest → Ship → Arrive recommendation.
8. Supporting evidence and maturity scale.

All controls are full-width with comfortable touch targets.

## Typography

- UI and body: Geist Sans.
- Technical values only: Geist Mono.
- Use tabular figures for dates, DAF, maturity, confidence, distance, and duration.
- Base UI text must remain comfortably legible: about `14px` for supporting copy and `12–13px` for labels; reserve smaller text for map attribution or nonessential metadata.
- Application heading scale only; no oversized editorial or marketing headlines.
- Sentence case for headings and labels.
- Interface copy uses English consistently; do not mix languages inside one workflow.

## Color

```css
--canvas: #f4f1e9;
--surface: #fbfaf6;
--surface-muted: #eeebe2;
--ink: #172019;
--muted: #687068;
--line: #d8d4c9;
--line-strong: #aaa99f;
--accent: #285b3a;
--accent-deep: #1e462d;
--accent-soft: #dce8de;
--maturity: #a77a24;
--maturity-soft: #eee2c6;
--error: #9a3f38;
--error-soft: #f4e5e1;
```

- Warm off-white canvas and near-black green text.
- Deep agricultural green is the sole primary accent.
- Muted gold is reserved for maturity or important timing.
- Color communicates state; it is not decoration.
- Light mode is the product default. Add dark mode only after it has a documented operational need.

## Surfaces and shape

- Flat surfaces, thin dividers, alignment, contrast, and whitespace.
- No gradients, glassmorphism, glow, decorative blobs, texture overlays, or large shadows.
- Avoid cards; add a bounded surface only when it clarifies hierarchy or interaction.
- No cards inside cards.
- Border radius: `6–10px` only where an input, button, preview, or control needs it.
- Shadows are limited to the autocomplete popover.

## Components

### Inputs

- Labels stay visible above controls.
- Minimum control height: `44px` mobile, `42px` desktop.
- Use clear focus rings in agricultural green.
- Validation is inline and direct.

### Image input

- Treat the upload as a specimen/photo field.
- Empty state: simple dashed border, concise instruction, one selection action.
- Filled state: clean preview, file name/size, and explicit Replace/Remove controls.

### Map

- Keep Leaflet controls usable and unobtrusive.
- Before route selection, show an instructive planning state on the map.
- After origin and destination are selected, show markers and the `light_truck` route.
- Attach distance and driving duration to the map edge.

### Recommendation

- Use one connected schedule, never three KPI cards.
- Desktop is horizontal; mobile remains a single connected sequence.
- Labels are `HARVEST`, `SHIP`, and `ARRIVE`; dates use mono values.
- Expected arrival maturity uses muted gold sparingly.

### Evidence

- Use compact rows or a flat information strip.
- Use one seven-step maturity scale with clear current and target markers.
- No gauges, radial charts, speedometers, metric-card grids, or decorative charts.

## Motion

- Low intensity only: short hover/focus transitions, route loading feedback, and one short result reveal.
- No scroll choreography, staggered entrances, floating motion, looping ambient motion, or animated gradients.
- Respect `prefers-reduced-motion`.

## Accessibility

- Keep the skip link, semantic landmarks, visible labels, inline errors, and keyboard-operable autocomplete.
- Preserve visible focus states.
- Meaningful images require descriptive alt text.
- Do not rely on color alone for recommendation or maturity states.
