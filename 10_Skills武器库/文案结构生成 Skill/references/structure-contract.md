# 文案结构生成合同 V16

## 输入与边界

活动合同为 `copy-structure-handoff-v16` / `copy-structure-v16`。V15 及更早版本仅作历史查阅。输入仅为选题、已审核对标案例的连续 FNN 大框架，以及结构三所需的处理库正式模块；不读取小框架、功能蓝图、逐句/句群、复刻画像或内容对象池。

## 先锁母逻辑

- 所有候选共用 `title_contract`：`audience`、`title_promise`、`core_conflict`、`terminal_conclusion`、`completion_criteria`。三套结构必须共同兑现标题承诺。
- 结构一至三各有不同的 `mother_logic`，并逐 FNN 写入 `logic_chain`：`answering_question`、`previous_dependency`、`necessary_conclusion`、`removal_impact`、`next_question`。相邻节点必须以前一节点结论为前提；删除任一节点必须使后续问题或最终结论失去支撑。
- 候选行必须原样继承 handoff 的 `framework_block_id`、`framework_label`、`framework_function`、`formal_framework_type`、`asset_framework_type`。这些不是可编辑内容。
- 只有逻辑链完整时才可填写结构一、二内容或让结构三检索同类型正式模块；模块只证明既定节点任务，不能反向决定母逻辑。
- 三条 `terminal_conclusion` 必须与共享标题合同的 `terminal_conclusion` 完全一致；母逻辑、扣题结论和 FNN 推进链是生成内容的上游合同，不是可选预览说明。

## 结构三原文证据

- 每条非空 `evidence_chain` 必须有 `source_evidence`：`source_index`、`source_section`、`excerpt`、`evidence_role`、`support_explanation`。摘录必须是对应 `processing_sources` 文件和章节内可定位的连续原文。
- 案例原文证据须分别覆盖场景/触发、行动/转折、结果/结论；误区须覆盖原误区及漏洞、后果或纠正；解决方案须填写 `step_no` 并摘录对应编号步骤的原文动作。
- 人读稿在结构三每条论据后展示“原文依据（章节）”，便于直接核验；来源路径仍在出处列，哈希、来源索引和内部检索字段不得展示。

## 框架映射

- `big_frameworks` 完整保留对标三列表的 F01、F02……，并为每项固化非原文的 `framework_function`（该段在全文中承担的功能定义），用于正文交接。
- `core_frameworks` 只保留能够映射到处理库正式内容家族的框架：观点、痛点、误区、解决方案、案例、推荐理由；它们按原 FNN 相对顺序出现，允许跳过支撑段编号。大框架名称可带序号或说明，只要名称包含且仅包含一个上述内容类型词，即映射为该类型（如“第二点：误区”→“误区”）；原始展示名称不改。
- 开场、转场、观点回扣、行动引导属于优先排除的正文专属支撑词，即使其中含“观点”等正式类型词，也不得映射为核心框架；同时包含多个正式类型词或未包含任何正式类型词的名称不得猜测类型，应作为正文专属支撑段保留。
- 开场、转场、观点回扣、行动引导等不能映射处理库的支撑段必须写入 `final_copy_only_frameworks`，标记 `generation_owner=final-copy`。它们不属于结构资产，不得出现在结构一至四、三套方向比较或结构三出处表，也不得进行资产检索。
- 结构一至四的 `core_frameworks` 必须逐项覆盖同一核心框架顺序，不能增加、删除、合并或重排。
- 结构一至三由小拆围绕选题填写各框架核心内容；结构四仅由用户填写与冻结。
- 结构三每个非空核心框架必须有一条或多条 `processing_sources`；每项包含 `path`、`sha256`、`framework_type` 与 `section`。`path` 必须位于 `02_资产中心/02_处理库`，`framework_type` 必须等于该行正式模块类型，`sha256` 必须与当前文件一致。
- 人读稿“出处”列只渲染 `processing_sources` 的处理库相对路径和引用段落；禁止渲染 `source_note`、选题表、对标复刻拆解或策划说明。未命中时内容及出处留空，并在 `asset_gap_note` 说明检索缺口。
- 候选、预览和审核回执中不得出现 `structure_segments`、小结构、逐句、句群或复刻画像字段。

## 审核与发布

小审核对标题承诺是否兑现、母逻辑、扣题结论、FNN 总顺序、相邻必然承接、删段是否断链、框架功能定义、核心/正文专属框架归属、结构四留白、结构三逐行出处和原文依据一致性。案例、误区、解决方案若只是可替换知识点、未完成链路任务或未能回到出处原文，一律退回。独立语义审稿必须逐结构提供扣题、承接、删段断裂证据，并逐结构三节点证明原文提取和类型任务。通过的 `copy-structure-v16` 才能进入用户冻结与正文 V3；历史结构只可查阅，不得作为新发布输入。

---

• 带你3小时跑通用AI做IP，批量出爆款。
• 有任何使用问题，可加入我们会员答疑群。
• 我是姜来已来，微信： lact175

---
