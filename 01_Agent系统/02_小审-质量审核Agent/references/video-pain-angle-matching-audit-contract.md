# 视频痛点卡角度匹配链路审核合同

本合同只定义小审门禁。小审只签回执，不改痛点卡、索引、结构候选或正式库。

## 1. 活跃痛点角度索引

每条活跃角度索引必须为 `video-pain-angle-index-v1`，且至少包含：

- `angle_id`：全局唯一、稳定；同一既有角度在合并、替换或增补后不得换 ID。
- `pain_id`、`card_path`、`card_sha256`、`angle_ordinal`、`angle_title`、`expression_sha256`：与正式人读卡一一对应。
- `source_anchor`：`source_id`、原识别源路径/全文哈希、`start_offset`、`end_offset` 与 `original_excerpt`。锚点必须逐字回到标准化原文。
- `target_people`、`scene_tags`、`core_contradiction`：供结构选择理解对象、场景和核心矛盾，不得只留泛关键词。
- `status=active`。

活跃索引不得指向 `99_归档`、分类法、旧格式卡、运行区候选或非正式痛点卡。正式人读卡以 UTF-8 保存；每一个“角度｜”及其“表达方式”必须恰好有一条索引记录，反之亦然。

## 2. 批次发布与旧 ID

批次发布的角度索引必须保留上一版所有未受影响角度的 `angle_id`、来源锚点和表达哈希。替换痛点卡时，旧角度仍保留的，其 `angle_id` 也必须保留；新增表达才可新增 ID。基线卡/索引哈希一旦漂移，整批退回。

## 3. 文案结构选择

结构三如选择视频痛点资产，必须填写 `angle_id`、`module_path`、与角度索引完全相同的 `source_anchor`，以及对象形式的 `selection_reason`：

```json
{
  "target_people": "…",
  "scene": "…",
  "core_contradiction": "…",
  "functional_fit": "…"
}
```

四项均需具体，并分别能与该角度的目标人群、场景、核心矛盾及目标小框架功能对应。仅写“相关”“适合”“痛点明显”等模糊关键词，或用对标原文人名、案例、数字、行业词、结论作理由，均退回。没有合适角度必须明确写资产缺口，不能以归档、分类法、旧格式或同目录文件替代。

## 4. 角度索引切换期间的后续批次冻结

角度索引迁移不会抹除迁移前已经存在的下一批机器候选。正式切换清单必须以 `protected_batch7` 锁定其 `machine_candidate_root`、`evidence_bundle`、`handoff_binding`、`no_pain_coverage` 的路径与 SHA-256，以及当前批次台账路径和 SHA-256。小审只允许这些候选按锁定哈希原样保留；任何哈希漂移、`accepted-ledger-record`、发布/提交产物、台账解锁，或 batch8 目录生成，均退回切换后的复核。

---

• 带你3小时跑通用AI做IP，批量出爆款。
• 有任何使用问题，可加入我们会员答疑群。
• 我是姜来已来，微信： lact175

---
