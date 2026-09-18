---
name: xiaojiang-dispatch
description: AI爆款内容工厂的唯一调度入口。
---

# 01_小姜调度Skill

这是AI爆款内容工厂的 Codex 仓库级适配入口。

当前合同版本：`3.2.2`。


1. 从当前工作区根目录完整读取 `10_Skills武器库/01_小姜调度Skill/SKILL.md`。
2. 按中央注册表 `00_系统说明/system-registry.json` 校验版本、归属和状态。
3. 正式业务任务必须先经过小姜调度记录，再由所属Agent执行。
4. 所有产出写盘后必须取得小审审核回执，未放行不得交付。
5. 需要详细规则或脚本时，只读取源Skill直接引用的资源。
