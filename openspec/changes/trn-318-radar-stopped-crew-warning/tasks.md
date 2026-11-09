# Tasks

## 1. Radar health display

- [x] 1.1 Review the existing local row-rendering change and verify stopped crews omit the warning while unhealthy running crews retain it and healthy running crews have none.
- [x] 1.2 Verify the rendered fleet table in a browser against representative crew states and record the result; run any affected frontend checks. (Corsair: stopped and healthy running live rows, plus a synthetic unhealthy running row; loaded the updated module with a cache-busting URL.)

## 2. Default crew ordering

- [x] 2.1 Sort running and inactive crews newest first by creation time by default, handling missing timestamps and retaining the Last Task sort control.
- [x] 2.2 Verify the default order and Last Task sorting with representative crew data. (Local JavaScript rendering check, including missing timestamps.)
