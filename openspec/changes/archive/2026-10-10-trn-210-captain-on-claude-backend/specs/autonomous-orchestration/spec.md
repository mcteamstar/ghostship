## MODIFIED Requirements

### Requirement: Raven persona prompt uses cookie-only auth for spawn calls

The `raven.json` persona prompt SHALL instruct Raven to authenticate all crew
gateway spawn calls using the dashboard session cookie at
`/home/kirocrew/.kiro/crew/.dashboard_cookie`, and SHALL NOT reference
`.local_secret`, `X-Internal-Secret`, or `X-Session-Key` for any spawn-related
instructions. The persona prompt auth instructions SHALL be consistent with the
`_RAVEN_GATEWAY_ORIENTATION` constant in `transport/captain.py`.

The spawn call pattern in the persona prompt SHALL be:

```bash
COOKIE=$(cat /home/kirocrew/.kiro/crew/.dashboard_cookie)
curl -s -X POST http://localhost:5476/api/spawn \
  -H "Cookie: mc_token_5476=$COOKIE" \
  -H "Origin: $(echo $KIROCREW_CORS_ORIGINS | cut -d, -f1)" \
  -H "Content-Type: application/json" \
  -d '{"task": "...", "agent": "<persona>"}'
```

The same cookie-only pattern applies to steer and continue calls. `X-Internal-Secret`
SHALL NOT be sent alongside the cookie on any of these calls.

#### Scenario: Raven on Claude backend reads persona prompt and dispatches

- **WHEN** Raven is dispatched on a Claude backend crew and reads its persona prompt
- **THEN** the persona prompt does not instruct Raven to read `.local_secret` or send
  `X-Internal-Secret`, and Raven's spawn calls use cookie auth without attempting to
  read a credential file directly

#### Scenario: Persona prompt and task text agree on auth method

- **WHEN** Raven receives both its persona prompt (from `raven.json`) and the Captain
  check-in task text (which includes `_RAVEN_GATEWAY_ORIENTATION`)
- **THEN** both sources describe the same cookie-only authentication pattern, with no
  contradiction between them
