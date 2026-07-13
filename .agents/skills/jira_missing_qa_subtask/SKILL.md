---
name: jira_missing_qa_subtask
description: 检测指定 Jira 版本或周期内漏创建 QA 测试子任务（Test Sub-Task）的 Stories 和 Improvements 并进行警报。
---

# Jira Missing QA Subtask Track (缺失 QA 子任务追踪)

该技能用于自动扫描指定 Jira 项目（如 CS, MP）和版本下，状态为 `PRD APPROVED`、`IN DEV` 或 `DEV DONE` 的 Story 和 Improvement。如果这些主任务下面没有任何 `"Test Sub-Task"` 或 `"Sub-task"` 类型的子任务，脚本将生成一份明细报告并发送到飞书群中提醒相关 QA 和负责人。

## 使用场景
- 当用户询问“帮我找出 v6.22 版本下还有哪些 Story 没有建 QA 子任务”或“检查 CS 项目中缺失测试子任务的任务并报警”时。

## 运行方式
运行 `scripts/missing_qa_subtask.py` 脚本：
```bash
python .agents/skills/jira_missing_qa_subtask/scripts/missing_qa_subtask.py
```

## 配置覆盖说明
用户可在根目录的 `.env` 中通过以下环境变量覆盖默认的业务行为：
- `JIRA_BASE_URL`: Jira 实例地址
- `JIRA_USERNAME`: Jira 用户名
- `JIRA_PASSWORD`: Jira 密码
- `LARK_WEBHOOK_URL`: 飞书机器人的群自定义 Webhook 接收地址
