# AI爆款内容工厂

面向 Windows + Codex Desktop 的本地内容生产系统。正式链路固定为：选题 → 已审核对标复刻拆解 → 文案结构 → 用户冻结结构四 → 正文成稿 → 小审 → 输出库。

> 当前公开包仅支持 Windows。macOS 版本尚未发布，请勿在 macOS 上安装工作台守护或尝试运行 Windows 桥接脚本。

## 首次安装

1. 安装 Git、Python 3.11–3.13、Node.js 20 LTS 与 Codex Desktop，并克隆本仓库。项目不提交 `node_modules`；安装脚本会按锁定的 `package-lock.json` 下载 Windows x64 Codex CLI。
2. 在仓库根目录创建并激活虚拟环境：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python run.py install --dev
```

3. 检查环境与已安装的仓库级 Skill：

```powershell
python run.py doctor
python run.py sync-platform --target codex --apply
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

GitHub 发布采用“非会员资产公开、会员内容占位”边界：只有目录名带 `（会员专享）` 的目录及其后代只保留占位文件；内容类型的 `memberOnly` 状态只控制工作台会员展示与业务权限，不参与发布判定。其余输入库、处理库、输出库、配图库资产和 OPPOSans 品牌字体均进入公开包。`node_modules`、运行态、审核/调度记录、历史恢复材料、临时文件、配图生成证据、本机路径与凭证始终不进入公开包。正式发布与恢复请遵循 [双轨版本发布标准](00_系统说明/双轨版本发布标准.md)。

---

• 带你3小时跑通用AI做IP，批量出爆款。
• 有任何使用问题，可加入我们会员答疑群。
• 我是姜来已来，微信： lact175

---
