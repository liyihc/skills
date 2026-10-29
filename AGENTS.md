# AGENTS.md

本仓库是**全局个人技能（global skills）的同步镜像**，内容等同 `~/.agents/skills`。直接在此编辑文件即等于改动本机已安装的技能，并会被同步。

## 技能结构

- 每个技能一个顶层目录，至少含 `SKILL.md`；其 YAML frontmatter 的 `name` 与 `description` 决定 agent 何时加载它，`description` 要写清触发条件。
- 技能的补充文档随其目录存放：常用全大写文件名（如 `SKILL-MECHANICS.md`）或子目录（如 `scripts/`），由 `SKILL.md` 内的链接引用。
- 不创建 `agents/openai.yaml` 等 agent 专属文件——用户不使用该 agent，此类文件已全部移除，不要重新添加。

## 来源与更新

- 每个技能的来源、当前版本、以及**各来源各自的更新方式**记录在 [`SKILL-VERSIONS.md`](SKILL-VERSIONS.md)，由 `global-skill-version` 技能维护（安装/更新/删除技能后刷新它）。
- 更新某个技能前，先读 `SKILL-VERSIONS.md` 中对应来源的「更新方式」并照做；上游技能与本地自建技能的处理方式不同。
- 更新外部来源的技能时，先对比本地副本与 `SKILL-VERSIONS.md` 中该来源已记录的版本，找出本地自有改动；把这些改动**合并**进新版，**不得直接覆盖**。合并**必须有人参与确认**，且动手前要说明合并策略与改动范围。上游原文可以保留英文，本地改动视为长期维护的一部分。本地自建技能（如 `serial-implement`）直接维护，无需合并。
- 固定偏好：更新**不使用** `npx` / `skills` CLI，改为从上游 git 拉取后手动拷贝。

## 编辑技能文档时

技能与 `AGENTS.md` 都是「写给 agent 的文档」，遵循 `writing-for-agents` 技能的原则（context pointer、单一事实来源、渐进披露、避免 no-op）。
