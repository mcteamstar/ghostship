# Responsive layout check (TRN-371 task 6.4)

## Setup

- Chromium, driven by Playwright.
- The built bundle from `radar/web/dist`, served by `radar/server.py` (`build_app`) on 127.0.0.1:8080.
- A stand-in transport on 127.0.0.1:64058 with four crews: alpha, beta and delta running, gamma stopped.
- Not covered: the Podman image, Caddy, and a live fleet.

## Results

| Width | innerWidth / scrollWidth | Horizontal scroll | Layout observed | Screenshot |
|---|---|---|---|---|
| 360 px | 360 / 360 | none | Crew rows and cells are block-level. The column header is visually hidden (absolute, 1 px wide). Six `data-label` values are present: Status, Backend, Comp, Uptime, Last task, Dashboard. | `screenshots/radar-360px.png` (360 px wide, full page) |
| 768 px | 768 / 768 | none | Table layout: rows are `table-row` and the table header is 726 px wide. | `screenshots/radar-768px.png` (768 px wide, full page) |
| 1280 px | 1280 / 1280 | none | The alpha row is expanded. Sections: Active tasks ("RUNNING · 2", "Finished · 11"), Captain, Credentials, Scheduled jobs, Mailbox subjects (ghost 2, captain 1). Fleet summary: Running 3, Stopped 1, Capacity 3 / 3 crews, Free memory 4.1 GB. | `screenshots/radar-1280px.png` (1280 px wide, full page) |

## Notes

- At 1280 px, Scheduled jobs shows its unavailable state ("Scheduled jobs unavailable."). This check does not assess that section's data.
- Full-page captures at 360 and 768 px are as wide as their viewports, which matches the measured scroll widths.
