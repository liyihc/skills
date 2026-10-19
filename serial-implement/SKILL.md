---
name: serial-implement
description: 串行实现一批 ticket（同 to-tickets），全部完成后统一 code-review，按预算（最多 2 轮）自动修严重/低成本问题，最后把逐 ticket 提交与单个审查修复 commit 本地合回主分支。
disable-model-invocation: true
---

# Serial Implement

把用户传入的一批 ticket **串行**实现到一条 integration branch 上：全部完成后**统一审查一次**、自动修复，最后把**逐 ticket 的提交**和**一个审查修复 commit** 本地合回主分支（`--no-ff`，保留集成分支）。

ticket 形式同 `to-tickets` 产出：每条含「要构建什么」「blocked by」「验收标准」。缺 ticket 就让用户先跑 `/to-tickets`。

## 步骤

### 1. 读取 ticket 列表与任务图

列出全部 ticket 及其 blocking edges。blocker 未完成的 ticket 不开工；串行按 blockers-first 顺序一次一个，纯线性链即自上而下。

同时做 **ticket 溯源**：逐条验收项标注来源——用户原话 / 已确认设计 / agent 补充。agent 在 spec 或 ticket 里自行追加的隐私、安全、质量等要求不得直接实施，先列给用户确认；无法追溯到用户确认口径的验收项，删掉或暂停。

**完成判据**：清单含每条 ticket 的 blocked-by，开工顺序不违反依赖；每条验收项都有来源，agent 补充项已交用户确认。

### 2. （可选）探索子智能体

若 ticket 需要先摸代码库或外部资料，派一个探索子智能体，把笔记存到 repo 外的目录（后续子智能体可读），让 implementer 专注实现而非探索。

**完成判据**：笔记已落盘于 repo 外。

### 3. 建 integration branch

从主分支切一条（如 `feature/<slug>`），全程在此分支上工作。

**完成判据**：当前分支即该 integration branch。

### 4. 串行实现

逐个 ticket 派一个 **implementer 子智能体**，直接写在这条 integration branch 上（不开 worktree、不另建分支、不 merge）。每个 implementer：

- 开工前记下当前 HEAD；
- 调 Skill 工具以 `tdd` 构建该 ticket；
- 完成时把本 ticket 的提交压成**一个** commit（`git reset --soft <开工前 HEAD>` 后重新提交），消息为 `<ticket-id>: <标题>`；
- ticket 无代码改动则跳过，不建空 commit；
- 报告完成。

一个完成，才开下一个。

**完成判据**：每个 ticket 恰好一个 commit，消息符合 `<ticket-id>: <标题>`。

### 5. 统一 code-review

全部完成后，调 Skill 工具以 `code-review`：固定点为 integration branch 的起点（主分支），spec 源为**用户确认的口径 + ticket 列表**。ticket 中第 1 步未获用户确认的验收项先剔除，不作为 review 依据。

**完成判据**：拿到 Standards 与 Spec 两轴的 finding。

### 6. 评审与修复（有预算）

以下两类直接修复 finding：

- **严重 / 非常严重**：Spec 要求缺失或实现错误（正确性），或文档化标准被违反且影响行为；
- **改动量小**：约一次重命名 / 几行，且低风险。

其余一律跳过：纯判断类 baseline 坏味道、风格偏好、推测性泛化、重构代价大而无行为收益。

**修复前先核对口径**：finding 必须能追溯到用户原话、已确认设计或 ticket 的验收项。agent 自写的验收项不等于用户需求；若某条 finding 要求的行为用户从未确认，停下列给用户，不得直接修。

修复由 implementer 子智能体做；它修不动就**新开**一个（干净上下文，带 ticket + 剩余 finding + 分支指针）。修完**再 review 一次**。修复提交全部留在 integration branch，第 7 步会统一压成一个 commit。

**复核范围**：只验证上一轮 finding 是否真的修掉；新 finding 仅限 hard violation 或正确性 bug，不再新开 judgment call。复核又发现新的判断类问题时，记录并交用户，不进入下一轮。

**修复预算**：全局最多 **2 轮**（一轮修复 + 一轮复核）。预算用尽仍有保留项时，**暂停并报告用户**，不硬凑、不自行扩轮。若一直在追同一个问题，先停下来问用户是否必须解决；尤其不要追 ticket 里的小点，扩展范围必须由用户确认。

复杂问题用用户的语言重新编号交给用户评审，由用户决定是否修复。

**完成判据**：review 无保留项；或 2 轮预算用尽，剩余项已列给用户。

### 7. 本地收尾

1. **压缩修复提交**：记下最后一个 ticket commit 的 SHA。若 review 修复产生过提交，在 integration branch 上 `git reset --soft <该 SHA>`，再提交为**一个** commit，消息 `fix: code-review 修复（N 项）`。多轮修复与复核的提交一并压入，全程恰好一个修复 commit；无 finding 时跳过。
2. **合并**：切回主分支，`git merge --no-ff <integration-branch>`，保留逐 ticket commit 与修复 commit。集成分支保留，不删除。
3. **冲突**：合并冲突或异常时停下交用户，不在合并过程中顺手改代码。

**完成判据**：主分支历史为「逐 ticket commit → `fix: code-review 修复（N 项）`（若有）→ merge commit」；报告 merge commit、逐 ticket commit 列表与改动摘要。不 push、不开 PR。
