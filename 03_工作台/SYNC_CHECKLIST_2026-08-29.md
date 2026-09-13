# 工作台与系统内容 GitHub 同步清单

日期：2026-08-29

## 范围

- `03_工作台`：前端页面、动效、网页编辑器、品牌资源、启动脚本、服务端接口、测试。
- `workflow/`：干货型结构/正文链路、活跃批次、数据中心、回执与状态协议。

## 本次提交分层

### 提交 1：稳定性与系统链路

- `03_工作台/server.py`
- `03_工作台/scripts/`
- `03_工作台/tests/test_server.py`
- `03_工作台/config/`
- `03_工作台/start-workbench.ps1`
- `03_工作台/watch-workbench.ps1`
- `03_工作台/workbench-control.ps1`
- `03_工作台/launch-workbench.cmd`
- `03_工作台/启动工作台.bat`
- `03_工作台/vendor/codex-app-server-schema/`
- `03_工作台/vendor/codex-cli/package*.json`
- `workflow/`

### 提交 2：界面、品牌与体验

- `03_工作台/frontend/`
- `03_工作台/01_品牌设计系统/`
- `03_工作台/design/`
- `03_工作台/README.md`
- `03_工作台/.gitignore`
- `03_工作台/SYNC_CHECKLIST_2026-08-29.md`

## 已完成自检

- `python -m unittest 03_工作台.tests.test_server`：通过，`60` 项。
- `03_工作台/vendor/codex-cli/node_modules/`：未纳入版本库，并已加入忽略规则。

## 待确认项

- `03_工作台/vendor/codex-app-server-schema/` 体积较大，但当前属于工作台桥接所需正式依赖，暂按正式源码同步。
- 当前仓库仍存在大量与本次任务无关的历史修改；本次提交仅针对 `03_工作台` 与 `workflow/`。
