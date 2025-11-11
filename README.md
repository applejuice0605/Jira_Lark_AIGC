# jira-lark-agent

一个用于从 Jira 拉取问题数据、汇总每日报告，并通过飞书（Lark）机器人 webhook 推送消息的轻量代理。支持本地定时任务与 GitHub Actions 两种运行方式。

## 目录结构

```
jira-lark-agent/
├─ README.md
├─ .env.example
├─ requirements.txt
├─ main.py
├─ config.py
├─ jira_client.py
├─ lark_client.py
├─ formatter.py
├─ scheduler.py
├─ utils.py
├─ logs/ (运行时生成)
└─ .github/workflows/daily_report.yml
```

## 快速开始

- 环境要求：`Python >= 3.9`，建议 `3.10+`
- 在 Windows 上创建虚拟环境并安装依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

- 配置环境变量：复制示例文件并填入你的凭据

```powershell
copy .env.example .env
```

`.env.example` 示例（请根据实际情况填写）：

```
# Jira 访问配置
JIRA_BASE_URL=https://your-domain.atlassian.net
JIRA_EMAIL=your.email@company.com
JIRA_API_TOKEN=***************

# 飞书机器人配置
LARK_WEBHOOK_URL=https://open.larksuite.com/open-apis/bot/v2/hook/xxxxx

# 报告配置
REPORT_PROJECT_KEYS=ABC,XYZ
REPORT_JQL=project in (ABC, XYZ) AND updated >= -1d ORDER BY updated DESC
TIMEZONE=Asia/Shanghai
REPORT_CRON=0 9 * * *  # 每天 9:00 推送

# 其他
LOG_LEVEL=INFO
## 可选配置
- `MESSAGE_TYPE`: `text` 或 `post`（默认 `post`），控制推送消息类型。
- `REPORT_TOP_N`: 明细展示的最大条数（默认 `10`）。
- `MAX_RESULTS`: 从 Jira 查询的最大条数（默认 `100`）。
- `ENABLE_LINKS`: 在 `post` 富文本中为 issue key 生成可点击链接（默认开启）。
## 认证方式
- `JIRA_AUTH_METHOD`：`token` 或 `basic`
  - `token`（推荐，Jira Cloud）：需提供 `JIRA_EMAIL` + `JIRA_API_TOKEN`
  - `basic`（Jira Server/DC）：需提供 `JIRA_USERNAME` + `JIRA_PASSWORD`
- 注意：Jira Cloud 不支持用户名+密码的 Basic 认证，必须使用 API Token。

## 必填与推荐参数
- 必填（视认证方式）：
  - `JIRA_BASE_URL`
  - 当 `token`：`JIRA_EMAIL`, `JIRA_API_TOKEN`
  - 当 `basic`：`JIRA_USERNAME`, `JIRA_PASSWORD`
  - `LARK_WEBHOOK_URL`
- 推荐：
  - `REPORT_JQL`（示例已给出）
  - `MESSAGE_TYPE=post`, `ENABLE_LINKS=true`
  - `REPORT_TOP_N`, `MAX_RESULTS`