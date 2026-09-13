# 视频痛点卡 547 篇批次审核合同

小审只审不改。每批必须有已审核校对源清单（`video-pain-batch-source-ledger-v1` 或 `video-source-correction-approved-batch-v1`）与机器 manifest（`video-pain-batch-machine-v1` 或 `video-pain-batch-machine-manifest-v1`）：前者逐篇绑定原识别源、校对候选与 approved 校对回执；后者可经总台账的 `active_batch` 绑定前者，并绑定仅 pain 的 JSON machine-evidence、bundle、机器索引和上一批 approved 回执。

- 批次 1 至 109 必须各 5 篇，批次 110 必须 2 篇；缺篇、重复、未校对放行或上一批未 approved 均退回，禁止下一批启动。
- 运行期机器候选不得有 Markdown 浏览卡；正式浏览卡只可在该批 machine audit approved 后渲染。
- 每条痛点表达优先采用连续原文口语；`direct_quote` 必须逐字连续，`light_splice` 必须提供每段的文本和字符定位，且拼接后不得增加改写。每条证据必须有 `pain-expression-completeness-v1`，逐项列示对象/人物、场景、痛点或矛盾、结果或领悟四维中原文可得及已覆盖的部分；孤立结论退回。短但完整的原话可保留，但要给出 `concise_complete_reason`，不能只以字数作为通过或退回依据。
- 清理旧格式前，必须由 `legacy-cleanup-plan` 审核计划的逐卡哈希、15 个 `video-pain-card-v1` 范围与 15 条精确索引行；`PAIN-A02-VIDEO-SELF-EXPRESSION` 新格式卡及其唯一索引行必须明确排除并保持不变。
- 每批在解锁下一批前，必须提交 `video-pain-batch-release-v1`：总台账仍锁定本批；校对清单、机器候选和批次门禁回执均为 approved；`video-pain-approved-contribution-registry-v1` 连续包含 1 至当前批的 approved 机器证据；人读卡只在暂存目录渲染，暂存索引按 pain ID 去重并与卡片一一对应；`video-pain-batch-merge-v1` 合并回执绑定当前暂存索引哈希。该阶段任一项退回，调度器不得解锁下一批或写入正式库。
- 已发布批次因表达质量重建时，必须改用 `video-pain-batch-replacement-release-v1`，不得沿用常规新增发布。`operation=replace` 要逐项列明且哈希锁定旧正式卡与旧索引行；`operation=add` 只适用于此前未正式发布的 pain_id，必须声明 `old_cards=[]` 且验证正式目标和现有索引均不存在。两种分支都要绑定 `video-pain-rebuilt-contribution-lineage-v1` 和新的 approved machine audit、受影响 pain_id、替换后暂存卡/索引及 `video-pain-batch-replacement-merge-v1`（操作类型一致）。同时列出所有保留资产（至少新格式样本和既有其他批卡）及其哈希。小审只在范围与谱系完全相同、索引无重复、保留资产未漂移时签发回执；提交动作必须原子替换或原子新增该批，不得重写样本或其他批。
- 某来源经独立判断没有可成立痛点时，`video-pain-no-pain-coverage-v1` 可记录单篇 `source_id/status=no_pain`，或以 `no_pain_sources` 集合覆盖本批多篇。集合中每篇必须唯一、存在于重建证据包、未被 pain 证据使用，并写有明确的无痛点理由；来源不是空白文本时，不得仅因非空而判作痛点。
- 全量切换前必须生成 `video-pain-rebuild-coverage-v1`：覆盖标准化 manifest 的全部 547 个 source_id，无重无漏，四账号分布一致，所有批次审核回执均为 approved。
- 正式库切换另须复核人读卡暂存格式、暂存索引、旧库归档清单和切换前哈希。覆盖台账未通过时，不得批准正式库切换。
- 已接入结构选择的痛点卡，还必须同时通过 `video-pain-angle-matching-audit-contract.md`：正式卡角度与活跃 `angle_id` 索引一一对应，来源锚点可逐字回原文，未受影响的旧角度 ID 不得漂移；结构三仅可选活跃正式角度，且匹配理由必须具体说明对象、人群场景、核心矛盾与目标小框架功能。

---

• 带你3小时跑通用AI做IP，批量出爆款。
• 有任何使用问题，可加入我们会员答疑群。
• 我是姜来已来，微信： lact175

---
