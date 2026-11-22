## 1. Bound upload processing

- [x] 1.1 Check HTTP, archive, and bundle defaults against representative transfers and verify a hard bundle storage bound on supported rootless Podman environments. Wire the limits through installer, runtime, and operator docs.

  Representative checkout sample: 3,062 tar members, 22.7 MiB tar / 20.7 MiB expanded, and a 17.0 MiB Git bundle whose clone occupies 38.2 MiB. This is below the 256 MiB request, 1 GiB expanded archive, 100,000-member, and 2 GiB bundle-storage defaults. The rootless tmpfs smoke test stopped writes at exactly 16 MiB on both macOS Podman and native Linux Podman. The live Corsair Podman worker check also verified plain upload, bundle budget rejection, preservation of the existing destination, staging cleanup, and successful checkout and readback across containers.
- [x] 1.2 Enforce declared and actual request size with bounded streaming through staging and the Podman tar handoff. Clean up partial host and crew staging on rejection, disconnect, and handoff failure.
- [x] 1.3 Enforce archive member and output budgets during staging. Enforce a live Git storage bound covering the object database, temporary files, and checkout. Return 413 for configured budget breaches and preserve the existing destination.
- [x] 1.4 Test exact and over-limit sizes, missing length, disconnect and handoff cleanup, archive limits, and a bundle that fits on the wire but exceeds its Git storage budget. Verify successful transfers and preservation of existing destinations during rejected forced replacements.
