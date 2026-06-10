# personas/ — Per-Member Persona Files

This directory holds one `<member-name>.txt` file per Council member. The
filename is the member's identifier (lowercase, hyphenated if multi-word).

## How it wires

At daemon startup, the process reads the env var `MEMBER_NAME`. The
`XMindClient` opens `_xmind/personas/<MEMBER_NAME>.txt` and uses its content
as the persona prefix for every prompt that member produces.

If `MEMBER_NAME` does not match any file here, `XMindClient` falls back to a
generic placeholder persona and logs a warning. The runtime keeps working
but the member has no specialized identity until you supply the file.

## How to add a member

1. Copy `_template.txt` to `<member-name>.txt`
2. Replace the template content with the member's actual persona
3. Strip the leading `#` comment lines
4. Set `MEMBER_NAME=<member-name>` in the member's daemon environment

## Naming convention

- All-lowercase
- ASCII letters, digits, and hyphens
- No file extension other than `.txt`
- Filename matches the value of `MEMBER_NAME`

## What belongs in a persona

| Section | Purpose |
|---|---|
| Identity | One short line declaring who the member is |
| Domain | What the member is responsible for |
| Decision style | How the member reasons (evidence, tone, weights) |
| Out-of-scope | What the member refers to other members |

Keep each persona under ~500 characters. Long personas hurt latency without
adding decision quality.

## Identity neutrality

This template ships with NO predefined members. Consuming projects choose
their own member names, count, and roles. The federated XMIND runtime is
agnostic to how many members exist or what they are called.
