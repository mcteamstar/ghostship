## 1. Bound upload processing

- [ ] 1.1 Check HTTP, archive, and bundle defaults against representative transfers and verify a hard bundle storage bound on supported rootless Podman environments. Wire the limits through installer, runtime, and operator docs.
- [ ] 1.2 Enforce declared and actual request size with bounded streaming through staging and the Podman tar handoff. Clean up partial host and crew staging on rejection, disconnect, and handoff failure.
- [ ] 1.3 Enforce archive member and output budgets during staging. Enforce a live Git storage bound covering the object database, temporary files, and checkout. Return 413 for configured budget breaches and preserve the existing destination.
- [ ] 1.4 Test exact and over-limit sizes, missing length, disconnect and handoff cleanup, archive limits, and a bundle that fits on the wire but exceeds its Git storage budget. Verify successful transfers and preservation of existing destinations during rejected forced replacements.
