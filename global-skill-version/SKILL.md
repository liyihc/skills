---
name: global-skill-version
description: Record and maintain the versions of globally installed agent skills in `~/.agents/skills/SKILL-VERSIONS.md`, mapping each skill to its upstream source and keeping each source's update method so later refreshes are reproducible. Use when installing or updating global skills.
---

# Global Skill Version

Own the ledger `~/.agents/skills/SKILL-VERSIONS.md`. It holds two indices:

- **技能 → 来源** — which upstream source each installed skill comes from.
- **来源列表** — per source, the installed version and **how to update it**. Update methods differ from source to source, so they live here in the ledger, **not** in this skill.

## When this runs

- **After installing or updating global skills** — refresh the ledger so it never drifts. This is the common case; do it without being asked.
- **When the user asks to see or record installed global skill versions.**

## Updating a source

1. Look up the source's row in the ledger's **来源列表** and read its Version and 更新方式.
2. Follow **that source's recorded 更新方式** exactly. Every source may differ — never assume one approach fits all, and never substitute `npx` / the `skills` CLI (the user dislikes it; standing preferences live in the ledger's **偏好** section).
3. Update the ledger: set the new Version, refresh **上次核对**, and append a row to **版本历史**.

## Recording conventions

- **技能 → 来源**: one line per installed skill, mapping it to its source repo. Verify the skill really exists at that source before claiming it; otherwise write `unknown`.
- **来源列表**, one row per source: `来源 | 版本 | 更新方式 | 上次核对 | 备注`.
  - **版本** — the upstream release/tag the installed copy matches, e.g. `1.3.1` (reproducible as tag `v1.3.1`). Compare against the tag's content; if it does not match, mark it `unverified`.
  - **更新方式** — written per source, because each source differs.
  - **备注** — carry anything else worth keeping, e.g. what upstream ships but is deliberately not installed.
- **偏好** — standing user preferences (e.g. no `npx`) belong here.

Do **not** compute content hashes — identity comes from source + tag alone.

## Keeping the file stable

- Rewrite the generated rows from the current state of disk, but **preserve the hand-written `## 备注` section verbatim**.
- Append a row to **版本历史** on every version change; never silently rewrite history.
- Do not delete the row of a source that has vanished from disk — mark it in its 备注 instead, so there is a trace.
- Keep `SKILL-VERSIONS.md` in the language it already uses (Chinese) and keep it short.
