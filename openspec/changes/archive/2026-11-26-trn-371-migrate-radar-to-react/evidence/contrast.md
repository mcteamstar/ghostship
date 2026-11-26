# Radar UI contrast check (TRN-371, task 6.1)

Checked in a real browser (Chromium, driven through the Playwright browser tool) against
`radar/web/dist` served by the real `radar/server.py` with a stand-in transport on
127.0.0.1. The page was opened with `#crew=alpha`, so one crew's detail panel was open.
The colour scheme was set with the browser's `prefers-color-scheme` emulation.

## Rendered text

Each visible text element was checked against its nearest opaque background, using the
WCAG 2.x contrast ratio. Normal text needs 4.5:1. Large text needs 3:1.

| Theme | Elements checked | Lowest ratio | Failures |
|:------|-----------------:|-------------:|---------:|
| Light | 156 | 6.49 (`2 active`) | 0 |
| Dark  | 156 | 7.99 (`Refreshed at: …`) | 0 |

Excluded: visually hidden text, hidden rows, and disabled buttons (WCAG exempts disabled
controls). Decorative gradients and the starfield are not counted; every text colour sits
on a solid surface token.

## Status and text token pairs

Each pair was read from the page's computed custom properties under the active scheme.

| Pair | Light | Dark |
|:-----|------:|-----:|
| text on surface, surface-alt, page background | 17.74, 15.26, 16.54 | 15.18, 14.11, 15.88 |
| muted on surface, surface-alt | 7.58, 6.52 | 8.59, 7.99 |
| heading and link on surface | 8.98, 9.93 | 10.13, 9.39 |
| running (badge text on its tint) | 6.78 | 9.12 |
| stopped (badge text on its tint) | 6.80 | 8.02 |
| warning (badge text on its tint, and on surface) | 8.15, 9.07 | 9.51, 12.98 |
| error on surface and surface-alt | 8.31, 7.15 | 9.86, 9.16 |
| info, captain and unknown badges | 6.49, 7.57, 8.40 | 10.07, 8.10, 9.85 |
| accent on surface-alt (lowest pair) | 6.11 | 9.42 |

All 23 light pairs and all 23 dark pairs are at least 4.5:1.

## Non-text

- Focus outline (`--color-focus` on surface, WCAG 1.4.11 needs 3:1): light 7.90, dark 6.27.
- Persona accent bars (decorative; the agent name is always printed): light lowest 4.99,
  dark lowest 10.13.

Result: no failing pair in either theme. The check was run against the built bundle from
commit `875229ba` plus the group 6 changes in this working tree.
