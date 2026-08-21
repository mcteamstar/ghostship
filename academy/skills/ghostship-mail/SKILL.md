---
name: ghostship-mail
description: Inter-agent messaging within a KiroCrew crew using mbox files in /var/mail. Use when one agent needs to hand off work to another, or wait on a result from another agent's task — each dispatched task runs in its own isolated working directory, so mail is the coordination channel across them.
allowed-tools: Bash(python3:*), Bash(cat:*), Bash(test:*), Bash(grep:*), Bash(sleep:*)
metadata:
  author: ghostship
  version: "2.0"
---

# Mail

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

## Subject-First Convention

**The subject line carries the complete message wherever possible.** A one-liner
status, a handoff notification, a request — put it entirely in the subject, with
an empty body. Reserve the body for genuinely long content: diffs, multi-step
task lists, error logs.

When reading a mailbox, read subject lines first to assess what's present. Only
open a message body when the subject alone isn't sufficient to understand what
action is needed.

## Sending Mail

Use this Python one-liner to send a message (subject-only, no body):

```bash
python3 -c "
import os, time, datetime
to = 'spectre'
subject = 'SRV-68 tasks done, committed abc1234 — ready for review'
body = ''
ts = datetime.datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0000')
task_id = os.path.basename(os.getcwd()).replace('subagent_', '')
sender = f'ghost+{task_id}'
msg = f'From {sender}@localhost {time.strftime(\"%a %b %d %H:%M:%S %Y\")}\nFrom: {sender}@localhost\nTo: {to}@localhost\nSubject: {subject}\nDate: {ts}\n\n{body}\n\n'
mbox = f'/var/mail/{to}'
os.makedirs('/var/mail', exist_ok=True)
open(mbox, 'a').write(msg)
print(f'Sent to {to}')
"
```

For messages with a body (long content):

```bash
python3 -c "
import os, time, datetime
to = 'spectre'
subject = 'SRV-68 review findings — 3 issues'
body = '''1. Missing null check in handler.py:45
2. Test coverage gap for edge case
3. Docstring outdated on process_batch()'''
ts = datetime.datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0000')
task_id = os.path.basename(os.getcwd()).replace('subagent_', '')
sender = f'ghost+{task_id}'
msg = f'From {sender}@localhost {time.strftime(\"%a %b %d %H:%M:%S %Y\")}\nFrom: {sender}@localhost\nTo: {to}@localhost\nSubject: {subject}\nDate: {ts}\n\n{body}\n\n'
mbox = f'/var/mail/{to}'
os.makedirs('/var/mail', exist_ok=True)
open(mbox, 'a').write(msg)
print(f'Sent to {to}')
"
```

Or write a helper script `/tmp/mail.py`:

```python
#!/usr/bin/env python3
import sys, os, time, datetime

def send(to, subject, body='', sender='ghost'):
    task_id = os.path.basename(os.getcwd()).replace('subagent_', '')
    from_addr = f'{sender}+{task_id}'
    ts = datetime.datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0000')
    msg = (
        f'From {from_addr}@localhost {time.strftime("%a %b %d %H:%M:%S %Y")}\n'
        f'From: {from_addr}@localhost\n'
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
    print(f'Mail: sent to {to}')

if __name__ == '__main__':
    # Usage: python3 /tmp/mail.py <to> <subject> [body]
    body = sys.argv[3] if len(sys.argv) > 3 else ''
    send(sys.argv[1], sys.argv[2], body)
```

Then: `python3 /tmp/mail.py spectre "SRV-68 ready for review"` (subject-only, empty body)

## Reading Mail

**Read subject lines first** when checking any mailbox — they tell you what's
there without opening bodies. Only open a body when the subject alone isn't
sufficient to understand what action is needed.

A `To:` header can use either of two address forms:

- `ghost@localhost` is a **generic** address. Any instance of Ghost that is checking `/var/mail/ghost` should treat it as addressed to itself.
- `ghost+<task_id>@localhost` is an **instance** address. Only the Ghost instance whose task ID exactly matches `<task_id>` should treat it as addressed to itself; other instances should ignore it.

When checking mail, accept generic messages and instance-addressed messages for your own task ID, while ignoring instance-addressed messages for other task IDs. The following single pattern waits up to five minutes and applies both rules:

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

- **Subject-first**: the subject carries the complete message. Body only for long content (diffs, task lists, error logs).
- **Subject line**: include the ticket ID if relevant (e.g. `SRV-68 tasks done, committed abc1234`)
- **Addressing a not-yet-dispatched recipient**: use the generic form (`ghost@localhost`) because that recipient does not have a task ID yet. This is correct and expected for a first-contact handoff, not an error, fallback, or degraded case.
- **Targeted replies**: once the recipient's task ID is known, use the instance form (for example, `ghost+d07eb161@localhost`) so only that instance treats the reply as addressed to it.
- **Ghost → Spectre**: ghost sends mail to spectre when implementation is committed and ready for review
- **Spectre → Ghost**: spectre sends mail to ghost with a task list if issues are found
- **Keep bodies short**: one paragraph max — put detail in a file, reference it by path
- **Include commit hash**: always include so the reviewer knows exactly what to look at

## Example Workflow

Ghost implements, then signals spectre (subject-only):
```bash
TASK_ID=$(basename $PWD | sed 's/subagent_//')
git -C /workspace/white commit -am "feat: G hotkey likes focused card"
HASH=$(git -C /workspace/white rev-parse --short HEAD)

python3 -c "
import os, time, datetime
task_id = '$TASK_ID'
to = 'spectre'
subject = f'TICKET-123 ready for review — committed $HASH in src/components/Example.tsx'
body = ''
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
subject = 'Re: TICKET-123 — LGTM, one nit on guard condition'
body = ''
ts = datetime.datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0000')
msg = (f'From spectre@localhost {time.strftime(\"%a %b %d %H:%M:%S %Y\")}\n'
       f'From: spectre@localhost\nTo: {to_addr}@localhost\nSubject: {subject}\nDate: {ts}\n\n{body}\n\n')
open('/var/mail/ghost', 'a').write(msg)
print('replied')
"
```
