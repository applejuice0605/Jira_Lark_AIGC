# jira-lark-agent

一个基于 Agent 智能体技能化架构的 Jira 数据拉取、统计与飞书（Lark）推送工具。所有业务功能均以独立的技能（Skills）形式封装在 `.agents/skills/` 目录下。

## 目录结构

```text
jira-lark-agent/
├─ README.md
├─ .env.example
├─ requirements.txt
├─ logs/ (运行时生成)
└─ .agents/
   └─ skills/
      ├─ jira_fix_version_time/             # 开发完成时间统计技能
      │  ├─ SKILL.md
      │  └─ scripts/fix_version_time.py
      ├─ jira_issue_status_monitor/         # Bug/工单状态监控技能
      │  ├─ SKILL.md
      │  └─ scripts/
      │     ├─ open_issue.py
      │     ├─ MicroOpen_issue.py
      │     └─ resolved_issue.py
      ├─ jira_missing_qa_subtask/           # 漏创建 QA 子任务检测技能
      │  ├─ SKILL.md
      │  └─ scripts/missing_qa_subtask.py
      ├─ jira_ready_to_brief/               # Ready to Brief 需求统计技能
      │  ├─ SKILL.md
      │  └─ scripts/ready_to_brief.py
      ├─ jira_workload_qa/                  # QA 工作项与甘特图统计技能
      │  ├─ SKILL.md
      │  └─ scripts/jira_workload_qa.py
      └─ xxljob_scheduler/                  # XXL-JOB 定时任务调度器适配技能
         ├─ SKILL.md
         └─ scripts/
            ├─ xxljob.py
            └─ xxljob_py2.py
```

## 技能列表与运行方式

### 1. 开发计划完成时间统计 (`jira_fix_version_time`)
* **说明**：汇总特定版本（Fix Version）的需求，并基于其子任务中最晚结束开发的时间来输出 `DevFinish`，便于 QA 预估提测时间。
* **运行**：
  ```bash
  python .agents/skills/jira_fix_version_time/scripts/fix_version_time.py
  ```

### 2. 工单状态监控与告警 (`jira_issue_status_monitor`)
* **说明**：支持对 Jira 上的 Bug 工单进行不同状态的扫描和通知（待验证、新创建等）。
* **运行**：
  * **监控 Open 缺陷**：
    ```bash
    python .agents/skills/jira_issue_status_monitor/scripts/open_issue.py
    ```
  * **监控已解决（Resolved）待验证缺陷**：
    ```bash
    python .agents/skills/jira_issue_status_monitor/scripts/resolved_issue.py
    ```
  * **监控 Micro 项目缺陷**：
    ```bash
    python .agents/skills/jira_issue_status_monitor/scripts/MicroOpen_issue.py
    ```

### 3. 缺失 QA 测试子任务检测 (`jira_missing_qa_subtask`)
* **说明**：扫描并检测指定 Jira 项目和版本下，状态为 `PRD APPROVED`、`IN DEV` 或 `DEV DONE` 的 Story/Improvement，若缺失 QA 类型的子任务则告警。
* **运行**：
  ```bash
  python .agents/skills/jira_missing_qa_subtask/scripts/missing_qa_subtask.py
  ```

### 4. 需求就绪统计 (`jira_ready_to_brief`)
* **说明**：拉取处于 `Ready to Brief` 状态的 Story/Improvement 并推送至飞书。
* **运行**：
  ```bash
  python .agents/skills/jira_ready_to_brief/scripts/ready_to_brief.py
  ```

### 5. QA 工作负载与甘特图统计 (`jira_workload_qa`)
* **说明**：分析和统计特定版本下各 QA 人员的工作负载，可生成甘特图并发送至飞书。
* **运行**：
  ```bash
  python .agents/skills/jira_workload_qa/scripts/jira_workload_qa.py --versions <版本号> [--users <人员姓名>] [--send-to-lark] [--lark-group <群名称>] [--chat-id <群ID>]
  ```

### 6. XXL-JOB 调度适配 (`xxljob_scheduler`)
* **说明**：适配 XXL-JOB 定时任务框架的运行脚本。
* **运行**：
  * **Python 3 运行**：
    ```bash
    python .agents/skills/xxljob_scheduler/scripts/xxljob.py
    ```
  * **Python 2 运行**：
    ```bash
    python .agents/skills/xxljob_scheduler/scripts/xxljob_py2.py
    ```

---

## 快速开始

### 运行环境
* `Python >= 3.9`（推荐 `3.10+`）

### 依赖安装
```bash
python -m venv .venv
source .venv/bin/activate  # macOS / Linux
# 或者是 Windows 上: .\.venv\Scripts\activate
pip install -r requirements.txt
```

### 配置环境变量
在项目根目录下，复制 `.env.example` 并重命名为 `.env`，然后填入配置：
```bash
cp .env.example .env
```

#### `.env` 核心配置说明：
```ini
# Jira 访问配置
JIRA_BASE_URL=https://your-domain.atlassian.net
JIRA_AUTH_METHOD=token      # 认证方式：token（推荐，Jira Cloud）或 basic（Jira Server/DC）
JIRA_EMAIL=your.email@company.com
JIRA_API_TOKEN=your_api_token
JIRA_USERNAME=your_username # basic 认证时必填
JIRA_PASSWORD=your_password # basic 认证时必填

# 飞书机器人配置
LARK_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxx

# 报告基础配置
REPORT_PROJECT_KEYS=ABC,XYZ
TIMEZONE=Asia/Shanghai
LOG_LEVEL=INFO
```

---

## 其他配置与字段说明

### 消息显示控制
* `MESSAGE_TYPE`：`interactive`（卡片消息）或 `post`（富文本），控制推送的消息样式。
* `REPORT_TOP_N`：推送列表中明细展示的最大条数。
* `MAX_RESULTS`：单次从 Jira 查询的最大条数（默认 100）。
* `ENABLE_LINKS`：在 `post` 消息中是否将 Issue Key 渲染为可点击的超链接（默认开启）。

### 自动解析字段说明
* 许多特定的 Jira 字段（例如 `QAs`）通常是自定义字段，本工具会自动调用 Jira `/rest/api/2/field` 接口尝试通过字段名称动态解析对应的 `customfield_xxxxx`。
* 也可以在配置文件中直接配置写死 `customfield_xxxxx` 以跳过自动解析阶段。例如：
  * `TARGET_START_FIELD_PATH=customfield_10109`
  * `TARGET_END_FIELD_PATH=customfield_10110`
