# Tasks

## 1. Read Linux available memory

- [x] 1.1 Read and convert `MemAvailable` from `/proc/meminfo` on Linux; preserve the existing Podman-info path on non-Linux hosts, and verify parsing, unit conversion, and platform selection with focused unit tests.
- [x] 1.2 Reject unreadable or malformed Linux memory data without falling back to `MemFree`; verify the helper and memory reporting expose the unavailable result clearly.

## 2. Apply the memory result to crew admission

- [x] 2.1 Make crew admission fail closed with a clear error when Linux `MemAvailable` cannot be determined; verify no crew container starts in that case and existing threshold/wait behavior still passes its focused tests.
