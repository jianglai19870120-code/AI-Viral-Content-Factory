# AI爆款内容工厂

面向 Windows + Codex Desktop 的本地内容生产系统。正式链路固定为：选题 → 已审核对标复刻拆解 → 文案结构 → 用户冻结结构四 → 正文成稿 → 小审 → 输出库。

> 当前公开包仅支持 Windows。macOS 版本尚未发布，请勿在 macOS 上安装工作台守护或尝试运行 Windows 桥接脚本。

## 首次安装

1. 安装 Git、Python 3.11–3.13 与 Codex Desktop，并克隆本仓库。若要使用工作台内的 CLI 交接，请确认 `codex --version` 可在 PowerShell 中执行；缺少该命令时，工作台仍可启动，但会明确提示你改用已打开的 Codex Desktop 手动交接。
2. 在仓库根目录创建并激活虚拟环境：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python run.py install --dev
```

3. 检查环境与已安装的仓库级 Skill：

```powershell
python run.py doctor
python run.py sync-platform --target codex
```

4. 在 Codex Desktop 中打开本仓库根目录。`.agents/skills` 中的适配入口会让 Codex 读取同目录下已注册的正式 Skill 真源。

## 激活工作台

```powershell
python run.py workbench start
```

启动成功后浏览器会打开 `http://127.0.0.1:8766`。常用控制命令：

```powershell
python run.py workbench status
python run.py workbench stop
python run.py workbench install    # 可选：安装 Windows 登录/开机守护，可能需要管理员权限
python run.py workbench uninstall
```

工作台运行数据、上传附件与 SQLite 状态存放在 `%LOCALAPPDATA%\AI-Viral-Content-Factory\workbench`，不会写回仓库。Windows 桌面桥接用于创建可见 Codex 任务；任务仍须遵循小姜分配 → 专业 Agent 执行 → 小审审核。

## 日常校验与发布

```powershell
python run.py validate
python run.py test
python run.py audit-baseline
python run.py release-check
```

GitHub 发布采用“源码可用、会员内容占位”边界：任何 `（会员专享）` 目录只保留占位文件；原始输入资料、生成配图库、机器安装的 Node 依赖、授权字体、运行态、审核/调度记录、历史恢复材料与本机路径留痕均不进入公开包。详见 [跨电脑安装与发布](00_系统说明/跨电脑安装与发布.md)。

---

• 带你3小时跑通用AI做IP，批量出爆款。
• 有任何使用问题，可加入我们会员答疑群。
• 我是姜来已来，微信： lact175

---
