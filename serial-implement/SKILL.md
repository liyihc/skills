---
name: serial-implement
description: 串行实现一批 ticket，逐条按 spec 核对口径；全部完成后统一 code-review、按预算修复，再把逐 ticket 提交合回主分支。
disable-model-invocation: true
---

# Serial Implement

把用户传入的一批 ticket **串行**实现到一条 integration branch 上：派发前以 spec 核对验收项、排除 agent 自加的约束；全部完成后**统一审查一次**、按预算自动修复，最后把**逐 ticket 的提交**和**一个审查修复 commit** 本地合回主分支（`--no-ff`，保留集成分支）。

开工前先按需探索，产出一份**共享简报**，让每个 implementer 不必重复摸代码库。

ticket 形式同 `to-tickets` 产出：每条含「要构建什么」「blocked by」「验收标准」。缺 ticket 就让用户先跑 `/to-tickets`。

## 步骤

### 1. 读取 ticket 列表、任务图与 spec

列出全部 ticket 及其 blocking edges。blocker 未完成的 ticket 不开工；串行按 blockers-first 顺序一次一个，纯线性链即自上而下。

同时定位 **spec 工件**：ticket 引用的 issue、用户给的路径，或 `docs/`、`specs/`、`.scratch/` 下与 feature 匹配的文件。记下指针，后续各步只认它。spec 不存在时**开跑前问用户一次**：补 spec，或明确接受「以 ticket 为唯一口径、本轮不做来源核查」。

不要在这里逐条审计验收项。**口径**：spec 是唯一依据；ticket 只在 spec 覆盖的范围内有效，冲突以 spec 为准。验收项的来源核对发生在第 4 步派发前。

**完成判据**：清单含每条 ticket 的 blocked-by，开工顺序不违反依赖；spec 指针已确定，或用户已选定退化口径。

### 2. 探索与简报

implementer 是全新上下文，主 agent 读过的东西不会自动传过去。本步的交付物是**一份简报**，不是「探索」；探索只是填充简报的方式。

**判断**：逐条 ticket 自问能否说出落点（相关文件/入口、现有测试、构建-测试命令、模块约定）。

- 能，且依据是当前 session 真读过 / 讨论过的事实（含 `/to-tickets` 阶段的探索）→ 主 agent 直接从上下文写简报，不派探索。
- 不能，或只有模糊印象 → 派一个**可写文件的 general 子 agent** 探索。给它全部 ticket 与 spec 指针，只回「简报绝对路径 + 每条 ticket 的落点数/无落点项 + 未决问题 + ≤10 行摘要」，正文留在文件里。
- 不确定就探索：漏探的代价是每个 ticket 各探一遍，错探的代价只是一次。

**范围**：所有 ticket 区域的并集 + 共享约定；够开工即可，通常不需要全库通读。探索前先读 `GLOSSARY.md` 与相关 ADR（按 `docs/agents/domain.md` 的约定）。

**路径**：放进不进版本库、后续子智能体可读的位置。优先用仓库约定的不进版本库临时区；没有就解析 `$TMPDIR` → `/tmp` → `%TEMP%`，在系统临时目录下建 `<tmpdir>/serial-implement-<feature-slug>-<timestamp>/`。该目录（本轮简报目录）放 `brief.md` 与逐 ticket 的口径核对记录；在派发任何 implementer 前确定绝对路径。`<feature-slug>` 沿用 spec/tickets 的 slug。

**简报模板**（探索子 agent 与主 agent 都照此写）：

1. **落点清单**：每条 ticket → 相关文件/入口/现有测试，以及它为何相关。`file:line`/符号可以用，简报是单次运行的，不担心长期失效。
2. **项目约定**：构建/测试/lint 命令（从配置或脚本确认，不靠猜）、目录分层、错误处理与命名习惯；有 `CODING_STANDARDS.md` / `CONTRIBUTING.md` 就把相关条目指过来。
3. **领域词汇与决策**：相关 `GLOSSARY.md` 术语、相关 ADR 及其约束。
4. **陷阱与可复用模式**：容易踩的坑、可复用的现成组件。
5. **外部资料**（仅当 ticket 依赖外部 API/库）：结论 + 来源/版本，不贴大段文档。
6. **未决问题**：ticket 与代码冲突、歧义、缺口。
7. **更正**：implementer 运行时追加的、影响后续 ticket 的修正；不写过程日志。

铁律：只写「去哪看、约定是什么」，不复述代码实现——复述会过期，也浪费 implementer 的上下文。设计文档、探索笔记先并进简报，后续只认简报。简报只提供代码事实与约定，不改变用户确认的口径；与 ticket/spec 冲突时以用户确认的口径为准，并记入未决问题/更正。

**完成判据**：简报已写到已知绝对路径，相关小节填好或标 N/A；每条 ticket 至少一个落点（主 agent 自写则直接核对，子 agent 探索则看摘要）；探索发现的未决问题已列给用户，其中影响落点或简报可信度的代码与 spec 冲突 → 暂停等用户确认；验收项的来源核对统一在第 4 步做，不在这里重复。跳过探索时，在简报开头写明依据（哪些文件/事实已在上下文）。任一 ticket 无落点 → 补探或问用户。

### 3. 建 integration branch

从主分支切一条（如 `feature/<slug>`），全程在此分支上工作。

### 4. 串行实现

逐个 ticket 派一个 **implementer 子智能体**，直接写在这条 integration branch 上（不开 worktree、不另建分支、不 merge）。传给它的上下文：该 ticket、spec 的相关段落与指针、**简报绝对路径**（本 ticket 的落点读简报里对应小节；缺了就派发前补齐）、「已排除，不要实现」累积清单。

**派发前先核口径（父会话做，不占 implementer 的回合）**：逐条给验收项标 spec 来源——有依据的照做，无依据的排除并记入「已排除」清单，两种解释都成立才算**不确定**。不确定项暂停整条串行，一次性列给用户并附推荐答案；实现细节（命名、复用哪个 helper、文件放哪）不属于范围，由 implementer 自行决定。纯技术改动只要不改变行为，可以 ticket 为口径，报告标注「无 spec 依据」。

implementer 开工约定：

- 开工前记下当前 HEAD；
- 开工前先读简报（绝对路径由主 agent 传入），重点看本 ticket 的落点与共享约定。需要的东西大概率已在简报里；你仍可打开或搜索任何需要的文件，只是不必从零重走一遍大范围探索；
- 一批互不依赖的读取/改动合并到**一条消息**里发出：同一文件的不同方法、互不相关的多个文件都属于这一类；写测试 → 跑 → 改实现这种有依赖的步骤仍分回合；
- 只合并互不重叠的 hunk——两条 `edit` 改同一段代码时，后一条的 `oldString` 已被前一条改掉，白跑一个回合；
- 调 Skill 工具以 `tdd` 构建该 ticket；
- 完成时把本 ticket 的提交压成**一个** commit（`git reset --soft <开工前 HEAD>` 后重新提交），消息为 `<ticket-id>: <标题>`；
- ticket 无代码改动则跳过，不建空 commit；
- 完工前维护简报：简报与代码不符时以代码为准；本 ticket 改了落点（重命名/移动/删除/新增可复用文件）→ 原地改受影响的后继 ticket 落点（含新增）；非落点的新事实（约定变了、新坑）→ 追加到「更正」；后续 ticket 发现简报不对也可顺手更正。不重写整份简报；
- 报告完成，并写明「简报已更新：<哪些落点/更正>」或「无需更新」；
- 简报缺失/读不到 → 先报告主 agent 补齐；你可以同时自行看需要的文件，把关键发现回报，避免后续 ticket 重复。

一个完成，才开下一个。本 ticket 的排除项并入累积清单，随上下文传给后续 implementer。主 agent 信任 implementer 的简报更新报告，不逐条复核。

**完成判据**：每个 ticket 的验收项都在派发前核过口径；排除项未被实现；每个 ticket 恰好一个 commit，消息符合 `<ticket-id>: <标题>`；简报已按需更新并在报告中声明。

### 5. 审查与修复（最多 2 轮）

全部完成后，调 Skill 工具以 `code-review`：固定点为 integration branch 的起点（主分支），spec 源为**第 1 步定位的 spec 工件**；ticket 仅作上下文，不进入 Spec 轴。退化口径下 spec 源为 ticket 列表，并在报告中注明来源核查已禁用。

简报不交给 code-review：Spec 轴直接读 spec 工件，Standards 轴直接读仓库标准文件，避免二手摘要成为第二事实来源。

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
