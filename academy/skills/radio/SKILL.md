---
name: radio
description: Inter-agent messaging within a KiroCrew crew using mbox files in /var/mail. Use when one agent needs to hand off work to another, or wait on a result from another agent's task — each dispatched task runs in its own isolated working directory, so this is the coordination channel across them.
allowed-tools: Bash(python3:*), Bash(cat:*), Bash(test:*), Bash(grep:*), Bash(sleep:*)
metadata:
  author: ghostship
  version: "1.0"
---

# Radio

Inter-agent messaging within a KiroCrew crew using mbox files in `/var/mail/`.

No MTA needed — messages are written directly as RFC 2822 mbox entries.

## Agent Identity

Each dispatched agent has a unique task ID (e.g. `d07eb161`). Use plus-extension addressing to make your mailbox address instance-specific:

```
ghost+d07eb161@localhost   — this specific ghost instance
spectre+6bf99101@localhost — this specific spectre instance
```

Your task ID is available via the workspace path:
```bash
TASK_ID=$(basename $PWD | sed 's/subagent_//')
echo "I am ghost+${TASK_ID}"
```

Use `ghost+$TASK_ID` as your `From:` address and ask recipients to reply to it. When reading `/var/mail/ghost`, filter by the `To:` header to find replies addressed to your specific instance.

## Overview

Each agent persona has a mailbox file:
- `/var/mail/ghost`
- `/var/mail/spectre`
- `/var/mail/banshee`
- `/var/mail/wraith`
- `/var/mail/reaper`

The Captain office also has the generic mailbox `/var/mail/captain`, addressed as
`captain@localhost`. Captain is a role, not a separate persona; Raven is the
usual reader for this mailbox during its persistent scheduled check-in. Standing
orders arrive there from the transport on the Admiral's behalf.
Messages are ephemeral — they exist only for the lifetime of the container.

## Sending Mail

Use this Python one-liner to send a message:

```bash
python3 -c "
import os, time, datetime
to = 'spectre'
subject = 'TICKET-123 ready for review'
body = 'Committed abc1234. Please review src/components/Example.tsx.'
ts = datetime.datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0000')
msg = f'From ghost@localhost {time.strftime(\"%a %b %d %H:%M:%S %Y\")}\nFrom: ghost@localhost\nTo: {to}@localhost\nSubject: {subject}\nDate: {ts}\n\n{body}\n\n'
mbox = f'/var/mail/{to}'
os.makedirs('/var/mail', exist_ok=True)
open(mbox, 'a').write(msg)
print(f'Sent to {to}')
"
```

Or write a helper script `/tmp/radio.py`:

```python
#!/usr/bin/env python3
import sys, os, time, datetime

def send(to, subject, body, sender='ghost'):
    ts = datetime.datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0000')
    msg = (
        f'From {sender}@localhost {time.strftime("%a %b %d %H:%M:%S %Y")}\n'
        f'From: {sender}@localhost\n'
        f'To: {to}@localhost\n'
        f'Subject: {subject}\n'
        f'Date: {ts}\n'
        f'\n'
        f'{body}\n\n'
    )
    mbox = f'/var/mail/{to}'
    os.makedirs('/var/mail', exist_ok=True)
    with open(mbox, 'a') as f:
        f.write(msg)
    print(f'Radio: sent to {to}')

if __name__ == '__main__':
    # Usage: python3 /tmp/radio.py <to> <subject> <body>
    send(sys.argv[1], sys.argv[2], sys.argv[3])
```

Then: `python3 /tmp/radio.py spectre "TICKET-123 ready for review" "Committed abc1234."`

## Checking Mail

A `To:` header can use either of two address forms:

- `ghost@localhost` is a **generic** address. Any instance of Ghost that is checking `/var/mail/ghost` should treat it as addressed to itself.
- `ghost+<task_id>@localhost` is an **instance** address. Only the Ghost instance whose task ID exactly matches `<task_id>` should treat it as addressed to itself; other instances should ignore it.

When checking mail, accept generic messages and instance-addressed messages for your own task ID, while ignoring instance-addressed messages for other task IDs. The following single pattern waits up to five minutes and applies both rules (change `PERSONA` for the persona whose mailbox you are checking):

```bash
PERSONA=ghost
TASK_ID=$(basename "$PWD" | sed 's/^subagent_//')
export PERSONA TASK_ID

# Wait up to five minutes for mail.
for _ in {1..60}; do
    if test -s "/var/mail/$PERSONA"; then
        break
    fi
    sleep 5
done

if ! test -s "/var/mail/$PERSONA"; then
    echo "no mail after 5 minutes"
else
    python3 - <<'PYEOF'
import os, re

persona = os.environ["PERSONA"]
task_id = os.environ["TASK_ID"]
mbox = f"/var/mail/{persona}"

for message in open(mbox).read().split("\nFrom "):
    match = re.search(r"^To: (\S+)@localhost$", message, re.M)
    if not match:
        continue
    recipient = match.group(1)
    is_generic = recipient == persona
    is_targeted = (
        recipient.startswith(f"{persona}+")
        and recipient.split("+", 1)[1] == task_id
    )
    if is_generic or is_targeted:
        print("--- addressed to me ---")
        print(message.strip())
PYEOF
fi
```

## Conventions

- **Subject line**: include the ticket ID if relevant (e.g. `TICKET-123 ready for review`)
- **Addressing a not-yet-dispatched recipient**: use the generic form (`ghost@localhost`) because that recipient does not have a task ID yet. This is correct and expected for a first-contact handoff, not an error, fallback, or degraded case.
- **Targeted replies**: once the recipient's task ID is known, use the instance form (for example, `ghost+d07eb161@localhost`) so only that instance treats the reply as addressed to it.
- **Ghost → Spectre**: ghost sends mail to spectre when implementation is committed and ready for review
- **Spectre → Ghost**: spectre sends mail to ghost with a task list if issues are found
- **Keep bodies short**: one paragraph max — put detail in a file, reference it by path
- **Include commit hash**: always include so the reviewer knows exactly what to look at

## Example Workflow

Ghost implements, then signals spectre with its instance address:
```bash
TASK_ID=$(basename $PWD | sed 's/subagent_//')
git -C /workspace/white commit -am "feat: G hotkey likes focused card"
HASH=$(git -C /workspace/white rev-parse --short HEAD)

python3 -c "
import os, time, datetime
task_id = '$TASK_ID'
to, subject = 'spectre', 'TICKET-123 ready for review'
body = f'Committed $HASH. Please review src/components/Example.tsx.\nReply to ghost+{task_id}@localhost.'
ts = datetime.datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0000')
msg = (f'From ghost+{task_id}@localhost {time.strftime(\"%a %b %d %H:%M:%S %Y\")}\n'
       f'From: ghost+{task_id}@localhost\nTo: spectre@localhost\nSubject: {subject}\nDate: {ts}\n\n{body}\n\n')
open('/var/mail/spectre', 'a').write(msg)
print('sent')
"
```

Spectre polls, reviews, replies:
```bash
# Wait up to five minutes for mail.
for _ in {1..60}; do
    if test -s /var/mail/spectre; then
        break
    fi
    sleep 5
done
test -s /var/mail/spectre || { echo "no mail after 5 minutes"; exit 1; }
cat /var/mail/spectre

# Reply to the specific ghost instance
REPLY_TO=$(grep '^From:' /var/mail/spectre | tail -1 | awk '{print $2}')
python3 -c "
import os, time, datetime
to_addr = '$REPLY_TO'.replace('@localhost','')  # e.g. ghost+d07eb161
msg_body = 'LGTM. One nit: add a comment on the guard condition.'
ts = datetime.datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0000')
msg = (f'From spectre@localhost {time.strftime(\"%a %b %d %H:%M:%S %Y\")}\n'
       f'From: spectre@localhost\nTo: {to_addr}@localhost\nSubject: Re: TICKET-123 ready for review\nDate: {ts}\n\n{msg_body}\n\n')
open('/var/mail/ghost', 'a').write(msg)
print('replied')
"
```

Ghost checks for generic replies or replies addressed to its specific instance:
```bash
TASK_ID=$(basename $PWD | sed 's/^subagent_//')
grep -A5 -E "^To: ghost(@localhost|\\+${TASK_ID}@localhost)$" /var/mail/ghost || echo "no reply yet"
```
