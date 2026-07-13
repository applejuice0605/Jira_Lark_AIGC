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
```

## 可选配置
- `MESSAGE_TYPE`: `interactive`（卡片）或 `post`（富文本），控制推送消息类型。
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

## 字段说明
- 部分 Jira 字段（例如 People 面板里的 `QAs`）通常是自定义字段且可能为多人列表；脚本侧应按多人值展示与统计。
- 若某个脚本支持 `QA_FIELD_NAME/QAs` 自动解析，会优先通过 Jira `/rest/api/2/field` 解析出对应的 `customfield_xxxxx`；必要时可直接配置为该 `customfield_xxxxx` 覆盖自动解析。
- 若业务流程需要判断 QA 是否已完成审批，可结合 workflow-wise 的 approval 接口返回（`approved[].displayName`）对比 `QAs` 列表，展示为“已Approve/待Approve”，并仅对“待Approve”的 QA 做 @ 提醒（可通过脚本内 `ENABLE_APPROVAL_CHECK/ONLY_MENTION_PENDING_QA` 开关控制）。

## xxljob 脚本
- [xxljob_ready_to_brief_story_improvement.py](file:///d:/FuseProgram/Jira_Lark_AIGC/xxljob_ready_to_brief_story_improvement.py)：拉取 Ready to Brief 的 Story/Improvement 并推送（支持 QAs 多人字段与审批状态展示）。
  - **新增状态过滤**: 支持在脚本配置 `EXCLUDE_STATUSES` (如 `["SIT Done", "Done"]`) 过滤不需要通知的需求。
  - **新增自定义字段映射**: 支持直接配置 `QA_FIELD_PATH` (如 `customfield_10700`) 和 `APPLICABLE_COUNTRIES_FIELD_PATH` (如 `customfield_10206`) 以应对无法动态解析的场景。
- [xxljob_fix_version_dev_finish_time.py](file:///d:/FuseProgram/Jira_Lark_AIGC/xxljob_fix_version_dev_finish_time.py)：按 Fix Version 汇总需求，并基于子任务“最晚结束开发时间”输出 `DevFinish`，便于 QA 预估提测时间。
    - **支持动态获取版本号**: 在配置中设置 `FIX_VERSION: "AUTO"` 时，会调用 Release Management Board 接口，将获取到的所有带发布时间（releaseDate）的版本按升序排序，并判断当前日期，取第一个发布时间大于或等于当前日期的版本作为当前迭代推送。
    - 开发子任务识别：子任务 assignee 的 displayName 命中 `DEV_MAP_INLINE`（脚本内配置）。
  - 结束开发时间：优先取命中的开发子任务里 `Target end` 最大值（脚本可自动把字段名解析成 `customfield_xxxxx`）；若无 `Target end`，则回退到 `resolutiondate`；若仍为空且子任务处于 Done 类别，再回退到 `updated`。
  - 排序：按 `DevFinish` 由远到近排序，便于 QA 先关注更晚的提测点。
  - 推送格式切换：`SETTINGS["MESSAGE_TYPE"] = "interactive"`（卡片）或 `"post"`（富文本）。
  - 字段直配：若已明确自定义字段 ID，可直接设置 `TARGET_START_FIELD_PATH=customfield_10109`、`TARGET_END_FIELD_PATH=customfield_10110`，跳过按字段名解析。
  - 状态过滤：默认排除 `SIT Done/IN SIT/UAT Done/IN UAT/Open/Closed/Done/On Hold`，避免把不需要关注的需求纳入提测时间预估。
