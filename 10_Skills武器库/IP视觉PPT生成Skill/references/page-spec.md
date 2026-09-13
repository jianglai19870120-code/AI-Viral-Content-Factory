# v4.1 页面规格约定

唯一新合同：`contract_version = 4.1.0`、`render_plan_version = render-plan-v4.1`、`visual_blueprint.version = visual-blueprint-v4.1`。`4.0.0` 工作包不得续跑、正式生图或审核，必须从正文重建。

## visual_blueprint

每个正文页必须含：

- `content_hash`：由本页标题、正文、角色签名产生，重试时不可改变。
- `creative_variant`、`layout_skeleton`、`role`：允许插画表达发挥，但跨页动作和构图必须去重。
- `keyword_visual_mappings`：2–5 张主卡。每条都有 `keyword`、`source_quote`、`source_label`、`visual_objects`、`action_or_relation`、`expected_visual_module`、`visual_module_id`、`page_slot`、`prompt_fragment` 和 1–3 条 `evidence_nodes`。
- `evidence_nodes`：每项都有 `text`、`source_quote`、`source_field`、`parent_visual_module_id`、自身 `visual_module_id`、`visual_objects` 与 `action_or_relation`。`text` 是来自本页原文的可见短句，必须在父主卡内和对象/流程/因果关系成对出现，不能另起独立卡片。
- `text_slots`：标题、每条主卡及每条证据节点各有一个归一化 `[x, y, width, height]` 文字带；主卡与证据都绑定同一个 `module_rect`，并含 `icon_rect`。这些槽位是原生生图的一体化构图指令：模型必须在同一张图中画出已填原文卡、内部证据与邻近语义小场景，不是留给后续程序叠字的空位。
- `final_visual_note_gate`：每页只认原生一次生成的完整视觉笔记图。它必须同时具备标题、每条映射的已填文字卡、对应手绘语义对象/关系和嵌入主结构的人物；纯人物插画、纯关系符号、无文字底图或未填卡槽均不得作为候选交付。
- `reserved_zone`：正文页左下 3cm × 3cm；每像素与声明背景色一致。封面为禁用。原生 PNG 进入 `final-review/` 后且小审成图审核表创建前，受控导出器仅可覆写这个已声明的无绘制区为本页 `background_color` 精确 RGB；其余像素、全部文字和图文语义不得改变。它必须记录原生输入哈希、最终 PNG 哈希，以及禁绘区外 RGB 像素摘要相等的证据；小审审核和发布一律绑定最终 PNG 哈希。

`render_plan.keyword_visual_mappings`、`evidence_nodes`、handoff、提示词与 `visual_blueprint` 必须完全一致。主卡不是图标名；必须先译为原文支持的可画物件和关系。每个主卡在最终图中同时拥有一个已填原文卡、1–3 条内部证据和对应手绘对象/关系，不能只留下文本卡或只留下装饰性图标。对于“第1个/第2个/第3个”并列分支，分支本身为主卡；投入、条件和操作链只可作为该分支的证据。

`visual_objects` 只能使用可直接画出的具体物件或小场景构件；“某某具体手绘场景”“某某关系节点”“通用图标”“占位”“抽象节点”均为非法占位描述。同页两条映射不得复用同一组对象；无法得到至少 2 条具体映射时必须停止生图并退回语义映射，不得降级成空卡或泛化图标。

跨页差异化只限制**无依据的复用**：钱币、沙漏、收益柱、时钟等元素可以使用，但必须由当前页的原文标签与关系直接支持。若同一元素在前页已经出现，当前页必须改用当前原文特有的对象、关系或构图；不得把同一“标签 + 物件 + 关系”组合换个位置再用。

## 提示词

正文上限 5,000 字符，封面上限 1,800 字符，固定六段：画布风格、角色与品质参考、关键词视觉地图、内容密度计划、本页原文文字清单与手绘模块卡、禁止项。模型必须在原生最终 PNG 中逐字渲染标题、全部主卡和全部证据短句。最终图禁止空白卡槽、伪文字、清单外中文和任何漏字。

## 返工和归档

`attempt-ledger.json` 按页记录蓝图哈希、提示词哈希、审核状态、退回原因和修正指令。任何退回只重画该页，不限次数直到审核放行；不得更换关键词、原文、锚点或蓝图。

工作包在 `outputs/<选题>-work/`；正式根目录只允许 `page-xx.png`、`cover-3x4.png`、`cover-4x3.png` 与 `evidence/`。

---

• 带你3小时跑通用AI做IP，批量出爆款。
• 有任何使用问题，可加入我们会员答疑群。
• 我是姜来已来，微信： lact175

---
正文页背景必须是声明 `background_color` 的纯色平面；不得使用渐变、暗角、纹理或色彩过渡。这样左下角 3cm × 3cm 禁绘区与页面底色保持一致，不得出现可见补丁色块。
