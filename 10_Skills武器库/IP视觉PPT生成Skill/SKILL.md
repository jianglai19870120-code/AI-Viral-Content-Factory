---
name: IP视觉PPT生成Skill
description: 用固定 IP 角色把已定稿中文文案制作成关键词对应的手绘视觉笔记整页图与封面；不审核或改写正文。
---

# IP视觉PPT生成 Skill

把已定稿中文文案转成手绘视觉笔记图。正文只提供分页、原文配字与画面语义；本 Skill 不做正文审核、改写或可编辑 PPT。

唯一需要触发的小审门禁是 `audit_visual_work_package.py` 的视觉工作包预审；它不替代或触发 `audit_dry_goods_v6.py`，也不得启动正文 V6.11/V6.12 审核或重写。

## 唯一合同：v4.1

- 新任务只接受 `contract_version = 4.1.0` 与 `render-plan-v4.1`。`4.0.0` 工作包不得续跑、不得正式生图、不得进入审核；必须从原始正文重建 v4.1 工作包。
- 每个正文页从当页原文选 2–5 张主卡，并写入 `visual_blueprint.keyword_visual_mappings`。每张主卡必须有原文出处、可画对象、动作/关系、唯一模块、卡槽、提示词片段，以及 **1–3 条 `evidence_nodes`**。
- `evidence_nodes` 是主卡内部的原文短句，不增加主卡数量。每项必须带可见短句、原文出处、父主卡、唯一视觉模块、具体对象和对象/流程/因果关系；不允许“主标题 + 装饰图标”的降级画法。
- 遇到“第1个 / 第2个 / 第3个”等并列分支，先以分支聚合主卡，再把投入、条件、操作、结果、限制放入该分支的证据节点。不得把“装修、囤货”等从属条件误做成与“餐饮、电商、技能”并列的主卡。
- `visual_blueprint` 是整页不可变骨架：主卡、证据节点、角色动作、构图变体和归一化文字槽位必须在 handoff、提示词、模型内文字几何计划与审核证据中一致。
- 创意仅在已确定蓝图内发生。不得通过换脸、换服装、泛化主持姿态、无关行业场景或收益承诺制造变化。

## 最终图一体生成与角色

- 原生生图必须一次生成可审核的最终视觉笔记：标题、2–5 张主卡、每张卡的 1–3 条原文证据短句、已填文字的手绘模块卡、对应小场景/图标、对象关系和 IP 人物必须同时出现在同一张 PNG 中。禁止“先出无字底图、以后叠字”；不存在任何正式后处理叠字链路。
- 每页自动生成“本页原文文字清单”：标题、主卡文字及主卡内部证据短句三层白名单。它不是固定词库，也不需要用户维护；它只确保最终出现的中文均能回指本页原文。图标、坑位、箭头、图表、路牌和说明文字不得自行臆想中文；钱币、沙漏、收益柱等元素并非禁用，但只能在本页原文标签确有对应语义时使用，且跨页不得原样复用同一“标签 + 物件 + 关系”组合。
- `visual_objects` 必须填写可直接画出的具体对象，例如“多年时间轴 + 循环运转齿轮”；禁止“某某具体手绘场景”“某某关系节点”“通用图标”等元描述。没有至少 2 条具体、可回溯且互不重复的图文映射时，应在生图前失败，不能用占位卡凑数。
- 原生生图结果若缺标题、缺任一清单文字、出现空白标题栏/空白卡槽、存在清单外中文，或文字与邻近配图不匹配，必须直接退回重画当前页；不得展示为“生成结果”、不得送审、不得归档。
- 默认角色 `zhifuxingqiu-host`。每次正式出图必须实际挂载 `refs/ip-face-anchor-top-left.png`；不得以文字描述代替主脸锚点。
- 每次正式出图还必须实际读取并挂载 [合格成图基准](assets/quality-reference/approved-visual-note-page-01.png)。它只约束整页信息密度、标题完整、图文一体、手绘模块卡和对象关系，不是文字或语义来源；严禁照抄案例标题、标签和图形内容。使用前读取 [基准判定说明](references/approved-image-baseline.md)。
- 正文 16:9，左下 3cm × 3cm 为纯背景禁绘区；封面只显示标题及最多两条原文短标签，禁止英文。原生 PNG 写入 `final-review/` 后、建立任何成图审核表前，允许唯一的受控导出归一化：运行 `scripts/normalize_reserved_zone.py --workdir <workdir>`，只将这一已声明的无绘制区写为本页 `background_color` 的精确 RGB。它不得叠字、绘制、改语义或改禁绘区外像素，必须在 `evidence/reserved-zone-normalization.json` 记录原生输入哈希、最终 PNG 哈希和禁绘区外像素摘要；小审只对归一化后的最终 PNG 绑定审核哈希。

## 工作流与返工

0. **不断线控制器是强制入口。** 工作包建立后，`attempt-ledger.json` 是唯一可变事实源，`render-state.json` 只是它的可替换投影。所有恢复动作均由 `python scripts/render_recovery_loop.py --workdir <工作包> next` 决定；先以 `claim --owner <任务或桥接ID>` 获取租约，避免同一页并发重画。不得直接编辑台账或把审核退回写为 `blocked`。
1. 运行 `python scripts/build_ip_ppt.py --input <正文路径> --render-mode codex`，在 `outputs/<选题>-work/` 生成 v4.1 工作包；构建器会初始化恢复控制器并把预审回执录入台账。
2. 必须通过 `audit_visual_work_package.py` 的视觉预审，才可按 handoff 出图。
   - 预审退回必须运行 `record-preflight --receipt <回执>`：首次同类问题输出 `rebuild-work-package`，保留旧包证据并从原正文建立**新的** v4.1 工作包；同一缺陷第二次复现输出 `repair-skill`，工作台桌面桥接自动创建独立 Skill 修复任务，主任务保持 `repairing-skill`。桥接以 `mark-repair-dispatched` 绑定修复任务；修复验证通过后由该任务执行 `mark-repair-verified`，主任务自动重建续跑。
   - 生产任务不得自行放宽审核规则、删除证据槽、改写正文或后续叠字绕过。
3. 单页审核必须运行 `record-asset --asset <page-xx|cover> --status approved|rejected ...`，逐次记录输入哈希、提示词/蓝图哈希、失败类别、修正指令、回执和下次执行时间。退回只重画当前页，不限次数直到审核放行，且不得变更原文、蓝图或角色锚点。ImageGen、文件、桌面桥接或原任务异常必须运行 `record-external --class <...> --reason <...>`：状态为 `reconnecting`，指数退避继续，绝不可 `blocked`。
4. 工作台按页面顺序把主脸锚点、合格成图基准和本页完整提示词一起交给原生生图；原生返回的 PNG 就必须是图文一体的最终图。运行任务只可消费工作包，不得编辑 Skill、审核程序或生成程序来迁就本次输出。
5. 全部最终图先进入工作包 `final-review/`。先运行 `normalize_reserved_zone.py --workdir <workdir>`，再运行 `audit_visual_outputs.py <final-review目录> --create-review-template`，由小审逐主卡、逐证据短句填写实际可见中文和图文关系，再运行该脚本取得 `approved` 回执。归一化后的最终 PNG 是唯一可审核/发布位图；缺少 `evidence/reserved-zone-normalization.json`、`evidence/visual-output-semantic-review.json`、任一证据不可见、出现无文字图/空白卡槽、或未核对案例基准，均不得交付。视觉成品审核放行后，正式目录只保留 `page-xx.png`、两张封面与 `evidence/`；运行文件只能留在工作包或证据目录。

一次调用本 Skill 即代表完成该正文的整套自动串行任务：建立工作包、预审、逐页最终图生成/校验、两张封面、成品审核与受控发布。单页退回只能触发该页重画，不能把两次失败或任意校准失败当作整套任务的停止条件。

只有 `audit_visual_outputs.py` 的正式 `approved` 回执录入 `record-final-audit` 后，控制器才可进入 `release-ready`；发布完成仍须运行 `mark-released --receipt <approved回执>`。`released` 与用户主动 `cancelled` 是配图任务的唯二终态。

详见 [页面规格约定](references/page-spec.md) 与 [调用说明](调用说明-中文.md)。

---

• 带你3小时跑通用AI做IP，批量出爆款。
• 有任何使用问题，可加入我们会员答疑群。
• 我是姜来已来，微信： lact175

---
