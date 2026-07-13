---
name: jira_issue_status_monitor
description: 定时监控并推送指定 Jira 项目中 Open（打开）、Resolved（已解决）以及 Micro 项目的未解决 Bug 缺陷列表。
---

# Jira Issue Status Monitor (工单状态监控告警)

该技能用于对 Jira 上的 Bug 工单进行不同状态的扫描和通知。包含以下 3 个独立的监控子脚本：
1. `open_issue.py`: 扫描并报告处于 `Open` 状态的 UAT/SIT 环境 Bug。
2. `resolved_issue.py`: 扫描并报告处于 `Resolved` 已解决状态、需要 QA 进行验证的 Bug。
3. `MicroOpen_issue.py`: 专门扫描并报告 Micro 项目下处于 `Open` 状态的缺陷。

## 使用场景
- 当用户询问“有哪些 Resolved 缺陷需要验证”或“帮我列出 CS 项目下的 Open Bug 列表”时。

## 运行方式
根据监控的目标，分别运行对应的脚本：
- **监控 Open 缺陷**：
  ```bash
  python .agents/skills/jira_issue_status_monitor/scripts/open_issue.py
  ```
- **监控已解决（Resolved）待验证缺陷**：
  ```bash
  python .agents/skills/jira_issue_status_monitor/scripts/resolved_issue.py
  ```
- **监控 Micro 项目缺陷**：
  ```bash
  python .agents/skills/jira_issue_status_monitor/scripts/MicroOpen_issue.py
  ```

## 配置覆盖说明
用户可在根目录的 `.env` 中通过以下环境变量覆盖默认的业务行为：
- `JIRA_BASE_URL`: Jira 实例地址
- `JIRA_USERNAME`: Jira 用户名
- `JIRA_PASSWORD`: Jira 密码
- `LARK_WEBHOOK_URL`: 各脚本默认对应的飞书群 Webhook 接收地址（也可在脚本内针对不同状态单独定义）
