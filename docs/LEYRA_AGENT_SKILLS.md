# LEYRA IA — Agent Skills

LEYRA supports the open [Agent Skills](https://agentskills.io) folder format through
progressive disclosure. The implementation is provider-neutral and is available in
both the FastAPI gateway and the Python-standard-library server.

## Loading model

1. **Tier 1 — catalog:** only each skill's `name` and `description` are returned.
2. **Tier 2 — activation:** the full Markdown body of `SKILL.md` is returned only
   when the skill is activated.
3. **Tier 3 — resources:** scripts, references, and assets are listed at activation
   and fetched individually when needed. They are not eagerly loaded.

A skill directory contains a `SKILL.md` file with YAML frontmatter:

```yaml
---
name: code-review
description: Review code for correctness, security, and maintainability.
---
# Code review
Follow the project's conventions and report actionable findings.
```

Optional sibling directories such as `scripts/`, `references/`, and `assets/`
are supported.

## Discovery locations

LEYRA scans these directories:

- Project: `.agents/skills/`, `.leyra/skills/`, `.claude/skills/`
- User: `~/.agents/skills/`, `~/.leyra/skills/`, `~/.claude/skills/`
- Additional user-managed roots: `LEYRA_SKILLS_PATHS` (path-separated list)

Project skills are **disabled by default** because repository content can be
untrusted. Enable them only for a project you trust:

```bash
export LEYRA_TRUST_PROJECT_SKILLS=true
```

Project-level skills override user-level skills with the same name. Collisions and
malformed skills emit warnings. Scanning skips common generated directories,
does not follow symlinks, and applies depth, directory, skill-count, and file-size
limits. If PyYAML is installed it is used for frontmatter; otherwise LEYRA uses a
small standard-library parser for common frontmatter fields.

## Authenticated API

All routes below require the existing LEYRA Bearer token.

| Method | Route | Purpose |
|---|---|---|
| GET | `/leyra/v1/skills` | Tier-1 metadata catalog |
| GET | `/leyra/v1/skills/{name}/activate` | Tier-2 instructions and tier-3 resource listing |
| GET | `/leyra/v1/skills/{name}/resources/{path}` | Read one resource from the selected skill |

Example:

```bash
curl http://127.0.0.1:8000/leyra/v1/skills \
  -H "Authorization: Bearer $LEYRA_GATEWAY_TOKEN"

curl http://127.0.0.1:8000/leyra/v1/skills/code-review/activate \
  -H "Authorization: Bearer $LEYRA_GATEWAY_TOKEN"

curl http://127.0.0.1:8000/leyra/v1/skills/code-review/resources/references/checklist.md \
  -H "Authorization: Bearer $LEYRA_GATEWAY_TOKEN"
```

The resource endpoint blocks path traversal and symlink escapes. Skill content is
untrusted input: the model/runtime must treat it as task guidance, never as
higher-priority system policy or permission to reveal secrets or perform unsafe
actions. The gateway does not execute bundled scripts automatically.

## Runtime integration notes

The endpoints are available in both `src/leyra_gateway.py` (FastAPI) and
`src/leyra_stdlib_server.py` (Termux-friendly standard library mode). Existing
provider routes and credentials are unchanged. The caller/agent runtime should
place the catalog in its session context, activate a relevant skill when needed,
and fetch referenced resources individually. Project skill trust must be an
explicit local configuration decision.
