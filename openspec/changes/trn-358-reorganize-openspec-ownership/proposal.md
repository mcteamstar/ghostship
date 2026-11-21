## Why

OpenSpec 2 discovers nested capability paths, and Ghostship already uses nested specs for Captain orders, credential profiles, registry durability, and install entry points. The remaining flat specs and broad legacy capabilities make ownership hard to find. Crew lifecycle alone has 51 requirements spanning readiness, capacity, gateway recovery, registry, and task behavior.

## What Changes

Organise the live capability tree around subsystem ownership. Move cohesive specs into feature folders and split mixed specs by requirement ownership. Record the old-to-new paths and keep active changes and maintained references aligned with the new layout.

## Capabilities

No behavior contract changes. This change migrates existing main specs directly because moving a whole capability and transferring requirements between paths are repository organisation changes.

## Impact

Main OpenSpec specs, active delta paths, and maintained capability references. Archived changes retain their historical paths.
