# MCP Server — Delta Spec (trn-66-docs-infographics)

Updates to the `mcp-server` capability.

## Context

The MCP tool surface is more than a list of callable tools: the `description=`
each tool exposes is what a client-side agent reads — cold, with no other
context — to decide *which* tool to call and *in what order*. Today the spec
tracks only that the tools exist and how they are grouped (see
`mcp-server`'s "Tool surface covers the full crew lifecycle" requirement); it
says nothing about what a tool's description must communicate. Colleague demos
and first-time agent runs surfaced the gap: agents dispatch into a crew before
supplying it, or nuke before evac, because nothing in the tool descriptions
signals the intended sequence or the relationships between tools.

This delta adds a requirement that the eight core lifecycle tools
(`launch`, `supply`, `dispatch`, `pickup`, `steer`, `evac`, `nuke`, `captain`)
and the server-level description carry the workflow order and inter-tool
relationships as content an agent can act on without leaving the tool list.

It is scoped to description/docstring **content** only. It does not change any
tool signature, behavior, grouping, or the tool-discovery ordering already
required by the existing capability.

## MODIFIED Requirements

### Requirement: Tool descriptions reinforce workflow order and make tool relationships explicit

The description text of the core lifecycle tools SHALL make the intended
workflow sequence explicit and name the relationships between tools, so that an
MCP client model selecting tools from the description alone sequences calls
correctly without consulting `docs/`. The canonical sequence is
**launch → supply → dispatch → pickup / steer → evac → nuke**, with `captain`
as the autopilot alternative to the manual dispatch/pickup/steer relay.

For the eight core tools, each description SHALL name its step in that sequence
and its relationship to the adjacent tools:

- **`launch`** — SHALL frame itself as step 1 (create a crew workspace) and
  state that `supply` must precede any repo-touching dispatch.
- **`supply`** — SHALL frame itself as step 2 (seed the workspace) and make the
  guardrail explicit that dispatching into an unsupplied/empty crew is a real
  failure mode.
- **`dispatch`** — SHALL frame itself as step 3 (send a task to an agent
  persona), state that the agent has zero context beyond the `task` string, and
  name `pickup` as the next step.
- **`pickup`** — SHALL frame itself as step 4 (check progress or collect the
  result) and name its relationship to `steer`.
- **`steer`** — SHALL frame itself as step 4b (redirect a running task or
  continue a completed session) and state the running-vs-completed distinction
  up front.
- **`evac`** — SHALL frame itself as step 5 (extract results, diffs, or a git
  bundle) and note that it pairs with `supply` as the file-exchange protocol.
- **`nuke`** — SHALL frame itself as step 6 (destroy the crew and both volumes)
  and state that `evac` must come first because the teardown is irreversible.
- **`captain`** — SHALL frame itself as the autopilot path (hand the full SDD
  cycle to a recurring Raven check-in) and name its relationship to the manual
  dispatch/pickup/steer relay.

The server-level `description=` field SHALL name the workflow sequence
explicitly rather than listing tools without order.

These are content requirements on description text only. No tool signature,
runtime behavior, tool grouping, or the tool-discovery ordering required by
"Tool surface covers the full crew lifecycle" is changed.

#### Scenario: A core tool description names its workflow step

- **WHEN** an MCP client lists tools on the `ghostship` connection and reads the
  description of any of `launch`, `supply`, `dispatch`, `pickup`, `steer`,
  `evac`, or `nuke`
- **THEN** that description names the tool's position in the
  launch → supply → dispatch → pickup/steer → evac → nuke sequence

#### Scenario: Sequencing guardrails are stated in the descriptions that need them

- **WHEN** the `supply` and `nuke` descriptions are read
- **THEN** `supply` states that dispatching into an unsupplied crew is a real
  failure mode, and `nuke` states that `evac` must precede it because teardown
  is irreversible

#### Scenario: Tool relationships are explicit, not implied

- **WHEN** the `dispatch`, `pickup`, `steer`, `evac`, and `captain` descriptions
  are read
- **THEN** `dispatch` names `pickup` as the next step, `pickup` names its
  relationship to `steer`, `evac` names its pairing with `supply`, and
  `captain` names its relationship to the manual dispatch/pickup/steer relay

#### Scenario: Server-level description names the sequence

- **WHEN** a client reads the top-level MCP server `description=` field
- **THEN** it names the workflow sequence
  (launch → supply → dispatch → pickup → steer → evac → nuke) explicitly, rather
  than listing tools with no ordering

#### Scenario: Description edits do not alter behavior

- **WHEN** the tool descriptions are revised to satisfy this requirement
- **THEN** no tool signature, argument, return shape, or runtime behavior
  changes, and the set and ordering of tools returned by tool discovery is
  unchanged
