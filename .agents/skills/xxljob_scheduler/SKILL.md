---
name: xxljob_scheduler
description: 提供在 XXL-JOB 分布式任务调度平台上周期性执行 Jira bug 工单状态统计并推送的适配脚本。
---

# XXL-JOB Cron Scheduler (定时任务执行核心)

该技能包含适配 XXL-JOB 分布式调度系统运行规范的执行脚本，用于在 XXL-JOB 的 Executor 中被定时唤醒并抓取 Jira 中的 SIT/UAT 缺陷详情推送到飞书群：
1. `xxljob.py`: 面向 Python 3 环境的调度执行脚本。
2. `xxljob_py2.py`: 兼容旧版 Python 2.x 环境的调度执行脚本。

## 使用场景
- 当用户询问“配置或查找与 XXL-JOB 平台周期运行对接的脚本”或“查看 Python 2.x 兼容环境下的 bug 推送脚本”时。

## 运行方式
- **Python 3 运行**：
  ```bash
  python .agents/skills/xxljob_scheduler/scripts/xxljob.py
  ```
- **Python 2 运行**：
  ```bash
  python .agents/skills/xxljob_scheduler/scripts/xxljob_py2.py
  ```

## 配置覆盖说明
用户可在根目录的 `.env` 中通过以下环境变量覆盖默认的业务行为：
- `JIRA_BASE_URL`: Jira 实例地址
- `JIRA_USERNAME`: Jira 用户名
- `JIRA_PASSWORD`: Jira 密码
- `LARK_WEBHOOK_URL`: 飞书机器人群 Webhook 接收地址
