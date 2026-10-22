---
name: serial-implement
description: 串行实现一批 ticket，逐条按 spec 核对口径；全部完成后统一 code-review、按预算修复，再把逐 ticket 提交合回主分支。
disable-model-invocation: true
---

# Serial Implement

把用户传入的一批 ticket **串行**实现到一条 integration branch 上：派发前以 spec 核对验收项、排除 agent 自加的约束；全部完成后**统一审查一次**、按预算自动修复，最后把**逐 ticket 的提交**和**一个审查修复 commit** 本地合回主分支（`--no-ff`，保留集成分支）。

ticket 形式同 `to-tickets` 产出：每条含「要构建什么」「blocked by」「验收标准」。缺 ticket 就让用户先跑 `/to-tickets`。

## 步骤

### 1. 读取 ticket 列表、任务图与 spec

列出全部 ticket 及其 blocking edges。blocker 未完成的 ticket 不开工；串行按 blockers-first 顺序一次一个，纯线性链即自上而下。

同时定位 **spec 工件**：ticket 引用的 issue、用户给的路径，或 `docs/`、`specs/`、`.scratch/` 下与 feature 匹配的文件。记下指针，后续各步只认它。spec 不存在时**开跑前问用户一次**：补 spec，或明确接受「以 ticket 为唯一口径、本轮不做来源核查」。

不要在这里逐条审计验收项。**口径**：spec 是唯一依据；ticket 只在 spec 覆盖的范围内有效，冲突以 spec 为准。验收项的来源核对发生在第 4 步派发前。

**完成判据**：清单含每条 ticket 的 blocked-by，开工顺序不违反依赖；spec 指针已确定，或用户已选定退化口径。

### 2. （可选）探索子智能体

若 ticket 需要先摸代码库或外部资料，把彼此独立的问题**一次**派给同一个探索子智能体（问题互不相干且体量大时，同一消息内并发多个 subagent 调用），把笔记存到不进版本库、后续子智能体可读的位置（按本仓库的临时区约定；没有就放 repo 外），让 implementer 专注实现而非探索。

笔记必须含一张**落点清单**：逐 ticket 列出要碰的 `文件:行/符号` 及它为何相关。这是第 4 步派发的必带上下文——implementer 不再自己重摸一遍地图。

**完成判据**：笔记已落盘于不进版本库的位置（本仓临时区或 repo 外），且含逐 ticket 的落点清单。

### 3. 建 integration branch

从主分支切一条（如 `feature/<slug>`），全程在此分支上工作。

### 4. 串行实现

逐个 ticket 派一个 **implementer 子智能体**，直接写在这条 integration branch 上（不开 worktree、不另建分支、不 merge）。传给它的上下文：该 ticket、spec 的相关段落与指针、该 ticket 的**落点清单**（从探索笔记或设计文档切出本 ticket 的行；缺了就派发前补齐）、「已排除，不要实现」累积清单、run 目录（与探索笔记同处；口径核对记录一 ticket 一份）。

**派发前先核口径（父会话做，不占 implementer 的回合）**：逐条给验收项标 spec 来源——有依据的照做，无依据的排除并记入「已排除」清单，两种解释都成立才算**不确定**。不确定项暂停整条串行，一次性列给用户并附推荐答案；实现细节（命名、复用哪个 helper、文件放哪）不属于范围，由 implementer 自行决定。纯技术改动只要不改变行为，可以 ticket 为口径，报告标注「无 spec 依据」。

implementer 开工约定：

- 开工前记下当前 HEAD；
- 一批互不依赖的读取/改动合并到**一条消息**里发出：同一文件的不同方法、互不相关的多个文件都属于这一类；写测试 → 跑 → 改实现这种有依赖的步骤仍分回合；
- 只合并互不重叠的 hunk——两条 `edit` 改同一段代码时，后一条的 `oldString` 已被前一条改掉，白跑一个回合；
- 调 Skill 工具以 `tdd` 构建该 ticket；
- 完成时把本 ticket 的提交压成**一个** commit（`git reset --soft <开工前 HEAD>` 后重新提交），消息为 `<ticket-id>: <标题>`；
- ticket 无代码改动则跳过，不建空 commit；
- 报告完成。

一个完成，才开下一个。本 ticket 的排除项并入累积清单，随上下文传给后续 implementer。

**完成判据**：每个 ticket 的验收项都在派发前核过口径；排除项未被实现；每个 ticket 恰好一个 commit，消息符合 `<ticket-id>: <标题>`。

### 5. 审查与修复（最多 2 轮）

全部完成后，调 Skill 工具以 `code-review`：固定点为 integration branch 的起点（主分支），spec 源为**第 1 步定位的 spec 工件**；ticket 仅作上下文，不进入 Spec 轴。退化口径下 spec 源为 ticket 列表，并在报告中注明来源核查已禁用。

只修两类 finding：

- **严重 / 非常严重**：spec 要求缺失或实现错误（正确性），或文档化标准被违反且影响行为；
- **改动量小**：约一次重命名 / 几行，且低风险。

其余一律跳过：纯判断类 baseline 坏味道、风格偏好、推测性泛化、重构代价大而无行为收益。修复前按第 1 步的口径核对：finding 必须能追溯到 spec，spec 从未写明就停下列给用户，不直接修。

修复由 implementer 子智能体做；它修不动就**新开**一个（干净上下文，带 ticket + 剩余 finding + 分支指针）。修复提交留在 integration branch，第 6 步统一压成一个 commit。

**复核与预算**：全局最多 2 轮（一轮修复 + 一轮复核）。复核只验上一轮的 finding；新发现仅限 hard violation 或正确性 bug，判断类记录给用户，不再开新 finding。预算用尽、或同一个问题追不动时，停下列给用户，不扩轮、不扩范围；剩余项用用户的语言重新编号交用户决定。

**完成判据**：review 无保留项；或 2 轮预算用尽，剩余项已列给用户。

### 6. 本地收尾

1. 若 review 修复产生过提交，在 integration branch 上 `git reset --soft <最后一个 ticket commit>`，再提交为**一个** `fix: code-review 修复（N 项）`；无 finding 时跳过。
2. 切回主分支 `git merge --no-ff <integration-branch>`，保留集成分支；冲突或异常时停下交用户，不在合并过程中顺手改代码。

**完成判据**：主分支历史为「逐 ticket commit → `fix: code-review 修复（N 项）`（若有）→ merge commit」；报告 merge commit、逐 ticket commit 列表、改动摘要，以及**排除项汇总、spec 冲突记录、标为「无 spec 依据」的 ticket**。不 push、不开 PR。
