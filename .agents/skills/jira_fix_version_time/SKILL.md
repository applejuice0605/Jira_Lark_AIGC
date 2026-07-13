---
name: jira_fix_version_time
description: 统计并推送指定 Jira 版本或周期内各开发任务的计划开发完成时间（Dev Finish Time）。
---

# Jira Fix Version Time Track (开发完成时间管理)

该技能用于自动扫描指定 Jira 项目（如 CS, MP）和版本下，所有处于开发中状态的任务，并读取其“开发计划开始时间”与“开发计划完成时间”。脚本会生成一份统计报告发往飞书群中，使相关 QA 和项目管理人员能够实时追踪版本需求的开发排期。

## 使用场景
- 当用户询问“统计 v6.22 版本下开发任务的计划完成时间”或“查看项目需求的排期和 Dev Finish Time”时。

## 运行方式
运行 `scripts/fix_version_time.py` 脚本：
```bash
python .agents/skills/jira_fix_version_time/scripts/fix_version_time.py
```

## 配置覆盖说明
用户可在根目录的 `.env` 中通过以下环境变量覆盖默认的业务行为：
- `JIRA_BASE_URL`: Jira 实例地址
- `JIRA_USERNAME`: Jira 用户名
- `JIRA_PASSWORD`: Jira 密码
- `LARK_WEBHOOK_URL`: 飞书群 Webhook 接收地址
