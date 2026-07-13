---
name: jira_workload_qa
description: 统计特定版本的 QA 的 Jira 工作项并发送统计结果或甘特图至飞书。
---

# Jira Version Workload Stat (Jira 版本工作负载统计)

该技能用于分析和统计 QA 人员在特定 Jira 版本中的工作负载，并可以选择以 Markdown 消息和甘特图图片形式发送至飞书群。

## 使用场景
- 当用户询问“统计 v6.18 版本下所有 QA 的工作负载”或“帮我生成 v6.20 版本的 QA 甘特图并发到飞书”时。

## 运行方式
运行 `scripts/jira_workload_qa.py` 脚本：
```bash
python .agents/skills/jira_workload_qa/scripts/jira_workload_qa.py --versions <版本号> [--users <人员姓名>] [--send-to-lark] [--lark-group <群名称>] [--chat-id <群ID>]
```

### 参数说明：
- `--versions`, `-v`: 必填。逗号分隔的版本号，如 `v6.18,v6.20`。
- `--users`, `-u`: 可选。逗号分隔的姓名，不填则默认统计配置文件 `resources/default_config.json` 中的所有 QA 人员。
- `--send-to-lark`: 可选。添加此 flag 会真正调用 `lark-cli` 发送富文本 Markdown 消息及甘特图到飞书。
- `--lark-group`: 可选。目标飞书群名称，默认读取配置。
- `--chat-id`: 可选。直接指定飞书 chat_id。

## 配置覆盖说明
用户可在根目录的 `.env` 中通过以下环境变量覆盖默认的业务行为：
- `JIRA_DEVELOPERS_FIELD`: 开发人员自定义字段，默认 `customfield_10606`
- `JIRA_TARGET_START_FIELD`: 计划开始日期字段，默认 `customfield_10109`
- `JIRA_TARGET_END_FIELD`: 计划结束日期字段，默认 `customfield_10110`
- `LARK_DEFAULT_GROUP`: 默认飞书群名，默认 `深圳--后端`
- `JIRA_DONE_STATUSES`: 已完成状态名（逗号分隔）
- `JIRA_IN_PROGRESS_STATUSES`: 进行中状态名（逗号分隔）
- `JIRA_BLOCKED_STATUSES`: 阻塞状态名（逗号分隔）
- `JIRA_REVIEW_STATUSES`: 评审/测试状态名（逗号分隔）
