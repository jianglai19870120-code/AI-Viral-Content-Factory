# AI爆款内容工厂工作台（Windows）

工作台只监听 `127.0.0.1:8766`，用于查看正式资产、计划与现役流程；前端不直接执行专业 Skill，也不能绕过小审。

## 启动与诊断

从仓库根目录运行：

```powershell
python run.py doctor
python run.py workbench start
python run.py workbench status
python run.py workbench stop
```

也可以双击 `启动工作台.bat`。如需开机/登录后自动恢复，请以管理员身份运行 `安装并验证工作台守护.cmd`，或执行 `python run.py workbench install`。

运行数据库、附件、任务提示与日志写入 `%LOCALAPPDATA%\AI-Viral-Content-Factory\workbench`，不写入本仓库。

## Codex 交接

Windows 桌面桥接只在已登录用户打开 Codex Desktop 后可用。工作台提交的是受控的小姜任务；正式执行仍遵循：小姜分配 → 专业 Agent 执行 → 小审审核 → 受控发布。

## 验证

```powershell
python -m unittest discover -s 03_工作台/tests -p "test_*.py"
node --check 03_工作台/frontend/app.js
```

---

• 带你3小时跑通用AI做IP，批量出爆款。
• 有任何使用问题，可加入我们会员答疑群。
• 我是姜来已来，微信： lact175

---
