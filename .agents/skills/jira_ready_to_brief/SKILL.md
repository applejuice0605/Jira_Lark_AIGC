---
name: jira_ready_to_brief
description: 统计并推送指定 Jira 项目中处于 "Ready to Brief" 状态的 Stories 和 Improvements。
---

# Jira Ready to Brief Story Track (就绪 Briefing 需求统计)

该技能用于自动扫描指定 Jira 项目（如 CS, MP）和版本下，状态为 `Ready to Brief` 的 Story 和 Improvement。这些任务已经完成了前期设计并准备向开发/测试团队进行 Brief。脚本将生成一份卡片消息，列出详细任务及其指派的 QA 负责人并发送到飞书群。

## 使用场景
- 当用户询问“统计哪些 Story 准备好进行 Briefing 了”或“列出 v6.22 版本中 Ready to Brief 状态的需求”时。

## 运行方式
运行 `scripts/ready_to_brief.py` 脚本：
```bash
python .agents/skills/jira_ready_to_brief/scripts/ready_to_brief.py
```

## 配置覆盖说明
用户可在根目录的 `.env` 中通过以下环境变量覆盖默认的业务行为：
- `JIRA_BASE_URL`: Jira 实例地址
- `JIRA_USERNAME`: Jira 用户名
- `JIRA_PASSWORD`: Jira 密码
- `LARK_WEBHOOK_URL`: 飞书群 Webhook 接收地址
