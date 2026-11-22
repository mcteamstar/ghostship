## Why

The TRN-352 extraction gives task operations a single service boundary. Batch and steer tests still patch the production singleton, and several tests repeat the same setup to assert individual fields of one result.

## What Changes

Exercise dispatch, pickup, and steer with isolated TaskService instances and shared test fakes. Consolidate overlapping cases, move slot-resolution tests next to task tests, and retain focused MCP adapter contract coverage.

## Capabilities

No behavior contract changes.

## Impact

Transport unit tests for tasks and MCP adapters. Existing gateway integration and live E2E suites remain required verification. Launcher and authentication tests are outside this pass.
