# 全局技能版本台账

> 由 `global-skill-version` 技能维护。
> 结构：上面是「技能 → 来源」索引；下面是「来源列表」，每个来源的版本与**更新方式**写在那里（各来源不同）。
> 手写内容放在文末「备注」，更新台账时原样保留。

**最近核对:** 2026-10-05
**扫描范围:** `~/.agents/skills`（仅此目录）

## 技能 → 来源

| 技能 | 来源 |
| --- | --- |
| ask-matt | mattpocock/skills |
| code-review | mattpocock/skills |
| codebase-design | mattpocock/skills |
| diagnosing-bugs | mattpocock/skills |
| domain-modeling | mattpocock/skills |
| grill-with-docs | mattpocock/skills |
| implement | mattpocock/skills |
| implement-spec | mattpocock/skills |
| improve-codebase-architecture | mattpocock/skills |
| pr | mattpocock/skills |
| prototype | mattpocock/skills |
| research | mattpocock/skills |
| retro | mattpocock/skills |
| setup-matt-pocock-skills | mattpocock/skills |
| tdd | mattpocock/skills |
| to-spec | mattpocock/skills |
| to-tickets | mattpocock/skills |
| triage | mattpocock/skills |
| wayfinder | mattpocock/skills |
| wizard | mattpocock/skills |
| grill-me | mattpocock/skills |
| grilling | mattpocock/skills |
| handoff | mattpocock/skills |
| teach | mattpocock/skills |
| to-questionnaire | mattpocock/skills |
| wait-what | mattpocock/skills |
| writing-for-agents | mattpocock/skills |
| herdr | herdrdev/herdr |
| serial-implement | 本地自建 |

## 来源列表

| 来源 | 版本 | 更新方式 | 上次核对 | 备注 |
| --- | --- | --- | --- | --- |
| github.com/mattpocock/skills | 1.3.1（tag `v1.3.1`） | git 从 GitHub 拉取，checkout `v1.3.1`，把正式技能拷贝到 `~/.agents/skills/` 覆盖（**不用 npx**），不包含in-progress、deprecated等。且在技能废弃时，需要将其删除并告知用户 | 2026-10-05 | 已核实本地与该 tag 逐字节一致（仅 CRLF 换行差异）。由 AI 手动安装。上游技能位于 `skills/<桶>/<技能>/`；本组只取 engineering 20 + productivity 7，**未取** `misc` 4 个与 `in-progress` 7 个。 |
| github.com/herdrdev/herdr | 未核实 | herdr安装或更新时，自动更新 | 2026-10-05 | 独立来源，单独维护。 |
| 本地自建（非上游） | — | 直接编辑 `~/.agents/skills/<技能>/SKILL.md`，更新后台账加一行 | 2026-10-22 | 用户自建技能，非 mattpocock/skills 上游：`serial-implement`。 |

## 偏好

- 技能安装/更新**不使用 `npx` / `skills` CLI**：用 git 从 GitHub 拉取后手动拷贝。
- 台账在技能更新时更新。

## 版本历史

| 日期 | 来源 | 从 | 到 | 说明 |
| --- | --- | --- | --- | --- |
| 2026-10-05 | mattpocock/skills | — | 1.3.1 | 首次记录（已核实） |
| 2026-10-07 | 本地自建 | — | — | 新增 `serial-implement` |
| 2026-10-22 | 本地自建 | — | — | `serial-implement` 改为以 spec 为唯一口径，开工前核对 ticket 重心并排除无依据约束 |

## 备注

<!-- 手写内容，更新台账时原样保留 -->
