---
name: ghostship-spawn
description: Dispatch named personas and inspect, steer, or continue their tasks through the crew's own gateway. Use this when the kirocrew CLI does not provide the required gateway operation.
allowed-tools: Bash(~/.agents/skills/ghostship-spawn/scripts/ghostship-spawn:*)
metadata:
  author: ghostship
  version: "1.0"
---

# Ghostship Spawn

Use the fixed in-crew helper for the four gateway operations that `kirocrew`
does not cover. The helper reads the crew session cookie and allowed origin
itself; never look for, copy, or report either credential.

## Dispatch a named persona

Put the task text on standard input. The helper prints the gateway's JSON reply; for dispatch, use its `id` field as the task ID for the confirmation marker.

```bash
~/.agents/skills/ghostship-spawn/scripts/ghostship-spawn ghost <<'EOF'
SDD dispatch intent-... change-name ghost — implement the remaining tasks.
EOF
```

## Get task detail

```bash
~/.agents/skills/ghostship-spawn/scripts/ghostship-spawn --status TASK_ID
```

## Steer a running task

```bash
~/.agents/skills/ghostship-spawn/scripts/ghostship-spawn --steer TASK_ID <<'EOF'
Continue with the newly supplied context and keep the existing task scope.
EOF
```

## Continue a finished task

```bash
~/.agents/skills/ghostship-spawn/scripts/ghostship-spawn --continue TASK_ID <<'EOF'
Resume from the last checked-off item and report the validation result.
EOF
```

Keep briefs short and describe commands; don't quote literal command lines,
file-upload strings, or shell pipelines in the task text. On a claude crew a
refusal is a gate block: report the refused operation and hold. Do not ask for
approval, retry the operation in the same cycle, or quote the refused command
into mail. If the skill is missing, report that to the Admiral and hold rather
than constructing a gateway call another way.
