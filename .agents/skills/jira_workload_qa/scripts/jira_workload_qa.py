#!/usr/bin/env python3
"""
Jira Version Workload Stat (QA版) — 按版本统计 QA 人员的 Jira 工作项及工时。

用法:
    # 统计指定版本的所有 QA 工时
    python .agents/skills/jira_workload_qa/scripts/jira_workload_qa.py --versions v6.22
    # 统计单个 QA 的工时 (支持部分名字/大小写模糊匹配，如 mim 或 Mim)
    python .agents/skills/jira_workload_qa/scripts/jira_workload_qa.py --versions v6.22 --users mim
    # 统计多个 QA 的工时 (逗号分隔)
    python .agents/skills/jira_workload_qa/scripts/jira_workload_qa.py --versions v6.22 --users "mim, tin"
    # 统计并自动发送 Markdown 与甘特图到默认飞书群
    python .agents/skills/jira_workload_qa/scripts/jira_workload_qa.py --versions v6.22 --send-to-lark
    # 统计并发送到指定的飞书群
    python .agents/skills/jira_workload_qa/scripts/jira_workload_qa.py --versions v6.22 --users "mim" --send-to-lark --lark-group "推送测试"
"""

import argparse              # 解析命令行参数（--versions、--users 等）
import json                  # 解析 Jira / 飞书接口返回的 JSON 数据
import os                    # 读取环境变量、处理文件路径
import subprocess            # 调用外部命令行工具 lark-cli（飞书机器人 CLI）
import sys                   # 输出错误信息到 stderr、退出程序
from collections import defaultdict, OrderedDict  # defaultdict 方便按 key 分组；OrderedDict 保证遍历顺序
from datetime import datetime  # 处理任务的起止日期、截止日期、当前时间
from urllib.request import Request, urlopen  # 不依赖第三方库，用标准库直接发 HTTP 请求给 Jira
from urllib.parse import urlencode            # 把查询参数（如 JQL 语句）编码进 URL
from base64 import b64encode                  # 给 Jira 的 Basic Auth 做 base64 编码

# 尝试加载 .env 配置文件
try:
    from dotenv import load_dotenv
    # 优先加载根目录下的 .env 文件
    load_dotenv()
    # 兼容从技能安装目录下（.agents/skills/jira_workload_qa/）加载 .env
    script_dir = os.path.dirname(os.path.abspath(__file__))
    skill_dir = os.path.dirname(script_dir)
    skill_env = os.path.join(skill_dir, ".env")
    if os.path.exists(skill_env):
        load_dotenv(skill_env, override=True)
except ImportError:
    pass

# ── 默认回退配置 ──────────────────────────────────────────────
FALLBACK_CONFIG = {
    "DEFAULT_USERS": {
        "lifei": "李飞(Bruce)",
        "wuwei": "吴维(Shirley)",
        "huxuesong": "胡雪松(Malcolm)",
        "caishubin": "蔡淑彬(Nora)",
        "mim": "Thikumporn (Mim) Homeaw",
        "tin": "Nguyen Tin",
        "faris": "Faris Harun Ahmad",
        "aaron": "aaron",
        "nanda": "Nanda Caesar"
    },
    "DEVELOPERS_FIELD": "customfield_10606",
    "TARGET_START": "customfield_10109",
    "TARGET_END": "customfield_10110",
    "DEFAULT_LARK_GROUP": "深圳--后端",
    "STATUS_CLASSIFICATIONS": {
        "done": [
            "done", "closed", "resolved", "已完成", "已关闭", "已解决",
            "完成", "已发布", "已上线", "released", "verified"
        ],
        "in_progress": [
            "in progress", "进行中", "处理中", "开发中", "implementing",
            "developing", "working"
        ],
        "blocked": [
            "blocked", "impeded", "阻塞", "受阻", "on hold"
        ],
        "review": [
            "in review", "code review", "reviewing", "待评审", "评审中",
            "待测试", "testing", "测试中", "uat"
        ],
        "todo": [
            "to do", "open", "backlog", "待处理", "待开始", "new", "reopened"
        ]
    },
        "GANTT_CONFIG": {
            "issue_type_colors": {
                "Task": {
                    "fill": "#5B9BD5",
                    "text": "#FFFFFF"
                },
                "Sub-task": {
                    "fill": "#70AD47",
                    "text": "#FFFFFF"
                },
                "Test Sub-Task": {
                    "fill": "#FFC000",
                    "text": "#FFFFFF"
                }
            },
            "issue_type_order": {
                "Task": 0,
                "Sub-task": 1,
                "Test Sub-Task": 2
            },
            "fonts": [
                "Arial Unicode MS",
                "Heiti TC",
                "Hiragino Sans GB",
                "PingFang SC"
            ],
            "row_colors": [
                "#EBF5FB",
                "#FEF9E7",
                "#E8F8F5",
                "#F5EEF8",
                "#FDEDEC"
            ],
            "nd_colors": {
                "Task": {
                    "bg": "#F0F7FF",
                    "icon": "📋",
                    "text": "#2B579A"
                },
                "Sub-task": {
                    "bg": "#F0FFF0",
                    "icon": "  └",
                    "text": "#3E7D3E"
                },
                "Test Sub-Task": {
                    "bg": "#FFFDF0",
                    "icon": "  └",
                    "text": "#8A6D00"
                }
            }
        }
}

def load_default_config():
    """寻找并加载默认配置文件 default_config.json"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    paths = [
        os.path.join(script_dir, "../resources/default_config.json"),
        os.path.join(script_dir, "default_config.json"),
        os.path.join(os.getcwd(), "default_config.json"),
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️ 读取配置文件 {p} 失败: {e}", file=sys.stderr)
    return {}

# 加载配置
CONFIG = load_default_config()


def resolve_jira_username(input_name, user_map):
    """
    将用户输入的局部名字/拼音，解析为匹配的 Jira 用户名（即 user_map 的 value）。
    匹配规则：
    1. 优先进行不区分大小写的 key 精确匹配。
    2. 如果没找到，检查输入名称是否是不区分大小写的 key 的一部分（例如 "mi" -> "mim"）。
    3. 如果还是没找到，检查输入名称是否是不区分大小写的 value 的一部分（例如 "mim" -> "Thikumporn (Mim) Homeaw"）。
    4. 如果均未匹配，返回原始输入名。
    """
    inp = input_name.strip().lower()
    if not inp:
        return input_name

    # 1. 精确匹配 key (如 "mim" -> "Thikumporn (Mim) Homeaw")
    for k, v in user_map.items():
        if k.strip().lower() == inp:
            return v

    # 2. 匹配 key 的一部分 (如 "mi" -> "mim" -> "Thikumporn (Mim) Homeaw")
    for k, v in user_map.items():
        k_clean = k.strip().lower()
        if inp in k_clean or k_clean in inp:
            return v

    # 3. 匹配 value 的一部分 (如 "Thikumporn" -> "Thikumporn (Mim) Homeaw")
    for k, v in user_map.items():
        v_clean = v.strip().lower()
        if inp in v_clean or v_clean in inp:
            return v

    return input_name


def get_search_name(resolved_name):
    """提取适合飞书搜索的用户名称，中文提取中文，英文去括号"""
    if "(" in resolved_name:
        first_part = resolved_name.split("(")[0].strip()
        # 判断是否有中文
        if any('\u4e00' <= char <= '\u9fff' for char in first_part):
            return first_part
        return resolved_name.replace("(", "").replace(")", "")
    return resolved_name


# ── 业务参数解析 (优先使用环境变量, 其次是 default_config.json, 最后是 fallback 默认值) ──
def get_config_val(key, default_val):
    return CONFIG.get(key, default_val)

# 用户名映射
DEFAULT_USERS = get_config_val("DEFAULT_USERS", FALLBACK_CONFIG["DEFAULT_USERS"])
env_users = os.environ.get("JIRA_DEFAULT_USERS")
if env_users:
    try:
        DEFAULT_USERS = json.loads(env_users)
    except Exception as e:
        print(f"⚠️ 解析环境变量 JIRA_DEFAULT_USERS 失败: {e}", file=sys.stderr)

# 自定义字段及飞书默认群
DEVELOPERS_FIELD = os.environ.get("JIRA_DEVELOPERS_FIELD", get_config_val("DEVELOPERS_FIELD", FALLBACK_CONFIG["DEVELOPERS_FIELD"]))
TARGET_START = os.environ.get("JIRA_TARGET_START_FIELD", get_config_val("TARGET_START", FALLBACK_CONFIG["TARGET_START"]))
TARGET_END = os.environ.get("JIRA_TARGET_END_FIELD", get_config_val("TARGET_END", FALLBACK_CONFIG["TARGET_END"]))
DEFAULT_LARK_GROUP = os.environ.get("LARK_DEFAULT_GROUP", get_config_val("DEFAULT_LARK_GROUP", FALLBACK_CONFIG["DEFAULT_LARK_GROUP"]))

# 状态分类定义
def get_status_set(status_key, fallback_list):
    env_val = os.environ.get(f"JIRA_{status_key.upper()}_STATUSES")
    if env_val:
        return {s.strip().lower() for s in env_val.split(",") if s.strip()}
    config_statuses = CONFIG.get("STATUS_CLASSIFICATIONS", {}).get(status_key, fallback_list)
    return {s.strip().lower() for s in config_statuses if s.strip()}

DONE_STATUSES = get_status_set("done", FALLBACK_CONFIG["STATUS_CLASSIFICATIONS"]["done"])
IN_PROGRESS_STATUSES = get_status_set("in_progress", FALLBACK_CONFIG["STATUS_CLASSIFICATIONS"]["in_progress"])
BLOCKED_STATUSES = get_status_set("blocked", FALLBACK_CONFIG["STATUS_CLASSIFICATIONS"]["blocked"])
REVIEW_STATUSES = get_status_set("review", FALLBACK_CONFIG["STATUS_CLASSIFICATIONS"]["review"])
TODO_STATUSES = get_status_set("todo", FALLBACK_CONFIG["STATUS_CLASSIFICATIONS"]["todo"])

# 甘特图配置
GANTT_CONFIG = CONFIG.get("GANTT_CONFIG", FALLBACK_CONFIG["GANTT_CONFIG"])
ISSUE_TYPE_COLORS = GANTT_CONFIG.get("issue_type_colors", FALLBACK_CONFIG["GANTT_CONFIG"]["issue_type_colors"])
env_color_task = os.environ.get("GANTT_COLOR_TASK")
if env_color_task:
    ISSUE_TYPE_COLORS.setdefault("Task", {})["fill"] = env_color_task
env_color_subtask = os.environ.get("GANTT_COLOR_SUBTASK")
if env_color_subtask:
    ISSUE_TYPE_COLORS.setdefault("Sub-task", {})["fill"] = env_color_subtask

ISSUE_TYPE_ORDER = GANTT_CONFIG.get("issue_type_order", FALLBACK_CONFIG["GANTT_CONFIG"]["issue_type_order"])
GANTT_FONTS = GANTT_CONFIG.get("fonts", FALLBACK_CONFIG["GANTT_CONFIG"]["fonts"])
env_fonts = os.environ.get("GANTT_FONT_FAMILY")
if env_fonts:
    GANTT_FONTS = [f.strip() for f in env_fonts.split(",") if f.strip()]

GANTT_ROW_COLORS = GANTT_CONFIG.get("row_colors", FALLBACK_CONFIG["GANTT_CONFIG"]["row_colors"])
GANTT_ND_COLORS = GANTT_CONFIG.get("nd_colors", FALLBACK_CONFIG["GANTT_CONFIG"]["nd_colors"])

# 查询 Jira 时需要拉取的字段列表（父任务：Story / Task / Improvement / Debt）
JIRA_FIELDS = [
    "summary", "issuetype", "status", "priority",
    "assignee", "fixVersions", DEVELOPERS_FIELD,
    TARGET_START, TARGET_END, "created", "duedate",
]
# 子任务（Sub-task）比父任务多一个 "parent" 字段，用来知道它属于哪个父任务
JIRA_FIELDS_SUBTASK = JIRA_FIELDS + ["parent"]


# ── 认证 ──────────────────────────────────────────────────────
def load_config():
    """获取 Jira 的访问地址和鉴权 header，按优先级依次尝试几种配置来源：
    1. 环境变量 JIRA_BASE_URL + JIRA_USERNAME + JIRA_PASSWORD（Basic Auth，常见于自建 Jira）
    2. 环境变量 JIRA_URL + JIRA_EMAIL + JIRA_API_TOKEN（Basic Auth，常见于 Jira Cloud）
    3. 环境变量 JIRA_URL + JIRA_PERSONAL_TOKEN（Bearer Token，常见于 Jira Server/Data Center）
    4. 本地配置文件 ~/.jira_config.json 或 Claude MCP 的配置文件 ~/.claude/mcp.json
    如果都找不到就报错退出。
    """
    # 1. 优先尝试本地项目的 .env 常用配置
    base_url = os.environ.get("JIRA_BASE_URL", "").strip().strip('"').strip("'")
    username = os.environ.get("JIRA_USERNAME", "").strip().strip('"').strip("'")
    password = os.environ.get("JIRA_PASSWORD", "").strip().strip('"').strip("'")
    if base_url and username and password:
        return base_url, "Basic " + b64encode(f"{username}:{password}".encode()).decode()

    # 2. 尝试标准 JIRA_URL / API Token 配置
    url = os.environ.get("JIRA_URL", "").strip().strip('"').strip("'")
    email = os.environ.get("JIRA_EMAIL", "").strip().strip('"').strip("'")
    api_token = os.environ.get("JIRA_API_TOKEN", "").strip().strip('"').strip("'")
    if url and email and api_token:
        # 用邮箱 + API Token 拼成 "email:token"，再做 base64，组成 Basic Auth 的值
        return url, "Basic " + b64encode(f"{email}:{api_token}".encode()).decode()

    personal_token = os.environ.get("JIRA_PERSONAL_TOKEN", "").strip().strip('"').strip("'")
    if (url or base_url) and personal_token:
        target_url = url if url else base_url
        # 直接用个人 Token 做 Bearer Auth
        return target_url, "Bearer " + personal_token
    # 环境变量都没有的话，尝试从本地配置文件读取
    for path in [os.path.expanduser("~/.jira_config.json"),
                 os.path.expanduser("~/.claude/mcp.json")]:
        if os.path.exists(path):
            with open(path) as f:
                cfg = json.load(f)
            if "mcpServers" in cfg:
                # 兼容 Claude MCP 的配置格式，从 atlassian 这个 MCP server 的 env 里取认证信息
                env = cfg["mcpServers"]["atlassian"]["env"]
                return env["JIRA_URL"], "Bearer " + env["JIRA_PERSONAL_TOKEN"]
            if cfg.get("email"):
                return cfg["url"], "Basic " + b64encode(
                    f"{cfg['email']}:{cfg['api_token']}".encode()).decode()
            if cfg.get("personal_token"):
                return cfg["url"], "Bearer " + cfg["personal_token"]
    # 上述方式都没找到认证信息，打印错误并以非 0 状态码退出
    print("❌ 未找到 Jira 认证信息。", file=sys.stderr)
    sys.exit(1)


# ── 飞书 open_id ──────────────────────────────────────────────
def get_open_ids(user_names):
    """把一批中文姓名转换成飞书的 open_id（飞书发消息 @人 时需要用 open_id）。
    通过命令行工具 lark-cli 按姓名搜索用户，找最匹配的结果。
    某个人查询失败或查不到，就不会出现在返回的字典里（后续发消息时只是不能 @ 到他）。
    """
    result = {}
    for name in user_names:
        try:
            # 调用 lark-cli 的用户搜索接口，按姓名查询，返回 JSON
            r = subprocess.run(
                ["lark-cli", "contact", "+search-user", "--query", name, "--format", "json"],
                capture_output=True, text=True, timeout=10)
            data = json.loads(r.stdout)
            users = data.get("data", {}).get("users", [])
            # 优先选择"匹配片段"里包含完整姓名的那个用户（更精确的匹配）
            for u in users:
                if u.get("match_segments") and name in u["match_segments"]:
                    result[name] = u["open_id"]
                    break
            # 如果没有精确匹配，但确实搜到了结果，就退而求其次取第一个
            if name not in result and users:
                result[name] = users[0]["open_id"]
        except Exception:
            # 搜索失败（网络问题、命令不存在等）就跳过，不影响其他人的查询
            pass
    return result


# ── Jira API ──────────────────────────────────────────────────
def jira_request(url, auth_header, jql, fields, max_results=200):
    """调用 Jira 的 REST 搜索接口 /rest/api/2/search，传入 JQL 查询语句和需要的字段列表。
    返回匹配到的 issue 列表（原始 JSON 结构），请求失败则打印警告并返回空列表。
    """
    params = {"jql": jql, "fields": ",".join(fields), "maxResults": max_results}
    api_url = f"{url.rstrip('/')}/rest/api/2/search?{urlencode(params)}"
    req = Request(api_url)
    req.add_header("Authorization", auth_header)
    req.add_header("Accept", "application/json")
    try:
        with urlopen(req) as resp:
            return json.loads(resp.read()).get("issues", [])
    except Exception as e:
        print(f"⚠️  Jira API 请求失败: {e}", file=sys.stderr)
        return []


def query_stories(url, ah, versions_str, username):
    """查询指定版本下、issuetype 为 Story 的任务，且该用户是 assignee（指派人）
    或者在"开发人员"自定义字段里出现。"""
    jql = (f'fixVersion in ({versions_str}) AND issuetype = Story '
           f'AND (assignee = "{username}" OR cf[{DEVELOPERS_FIELD.split("_")[1]}] = "{username}")')
    return jira_request(url, ah, jql, JIRA_FIELDS)


def query_subtasks(url, ah, versions_str, username, parent_keys=None):
    """查询该用户名下的所有 Sub-task（子任务），用于后面按父任务分组展示。
    且其自身或父任务属于指定版本。"""
    version_cond = f'fixVersion in ({versions_str})'
    if parent_keys:
        keys_chunk = parent_keys[:300]  # 限制在 300 个以防止 JQL 超过长度限制
        keys_str = ",".join(keys_chunk)
        version_cond = f'({version_cond} OR parent in ({keys_str}))'

    jql = (f'issuetype in ("Sub-task", "Test Sub-Task") AND {version_cond} '
           f'AND (assignee = "{username}" OR cf[{DEVELOPERS_FIELD.split("_")[1]}] = "{username}")')
    return jira_request(url, ah, jql, JIRA_FIELDS_SUBTASK)


def query_tasks(url, ah, versions_str, username):
    """查询该用户名下的所有 Task。"""
    jql = (f'fixVersion in ({versions_str}) AND issuetype = Task '
           f'AND (assignee = "{username}" OR cf[{DEVELOPERS_FIELD.split("_")[1]}] = "{username}")')
    return jira_request(url, ah, jql, JIRA_FIELDS)


def query_improvements(url, ah, versions_str, username):
    """查询该用户名下的所有 Improvement（优化类需求）。"""
    jql = (f'fixVersion in ({versions_str}) AND issuetype = Improvement '
           f'AND (assignee = "{username}" OR cf[{DEVELOPERS_FIELD.split("_")[1]}] = "{username}")')
    return jira_request(url, ah, jql, JIRA_FIELDS)


def query_debts(url, ah, versions_str, username):
    """查询该用户名下的所有 Debt（技术债类任务）。"""
    jql = (f'fixVersion in ({versions_str}) AND issuetype = Debt '
           f'AND (assignee = "{username}" OR cf[{DEVELOPERS_FIELD.split("_")[1]}] = "{username}")')
    return jira_request(url, ah, jql, JIRA_FIELDS)


# ── 工具函数 ──────────────────────────────────────────────────
def _status_icon(status_name):
    """返回状态对应的图标。"""
    s = status_name.strip().lower()
    if s in DONE_STATUSES:
        return "✅"
    if s in BLOCKED_STATUSES:
        return "🚫"
    if s in IN_PROGRESS_STATUSES:
        return "🔄"
    if s in REVIEW_STATUSES:
        return "🔍"
    if s in TODO_STATUSES:
        return "🔄"
    return "❓"  # 未知状态


def _is_overdue(issue):
    """任务未完成且已超过截止日期。"""
    f = issue["fields"]
    status = (f.get("status") or {}).get("name", "")
    if status.strip().lower() in DONE_STATUSES:
        return False
    due = f.get("duedate") or ""
    if not due:
        return False
    try:
        due_date = datetime.strptime(due.strip(), "%Y-%m-%d")
        return due_date < datetime.now()
    except ValueError:
        return False


def get_date_range(issue):
    """把任务的计划开始日期和结束日期拼成一个展示用的字符串，
    例如 "2026-05-06 → 2026-05-29"；只有一边有值就用 "?" 占位；都没有就返回空字符串。"""
    f = issue["fields"]
    s = f.get(TARGET_START) or ""
    e = f.get(TARGET_END) or ""
    if s and e:
        return f"{s} → {e}"
    elif s:
        return f"{s} → ?"
    elif e:
        return f"? → {e}"
    return ""


def get_versions(issue):
    """提取任务挂的所有 fixVersion 名称，只保留以 "v" 开头的版本号（过滤掉其他无关版本标签）。"""
    fvs = issue["fields"].get("fixVersions", []) or []
    names = [v["name"] for v in fvs if v.get("name")]
    return [n for n in names if n.startswith("v")]


def get_parent_key(subtask):
    """取子任务对应的父任务 key（如 "CS-26480"）；取不到（没有父任务/字段结构异常）就返回 None。"""
    try:
        return subtask["fields"]["parent"]["key"]
    except (KeyError, TypeError):
        return None


# ── 飞书 Post 构建 ────────────────────────────────────────────
def elem_text(text):
    """构造飞书富文本消息里的一个"纯文本"元素（目前脚本里未实际使用，是备用的工具函数）。"""
    return {"tag": "text", "text": text}


def elem_at(open_id, name):
    """构造飞书富文本消息里的一个"@某人"元素（目前脚本里未实际使用，是备用的工具函数）。"""
    return {"tag": "at", "user_id": open_id, "user_name": name}


def issue_line(issue, indent=0):
    """父任务 indent=0: `- CS-26480 [P0] 摘要 Status [v6.18] (05-06 → 05-29)`
       子任务 indent=1: `  └ CS-26863 [P2] 子任务 In Progress (06-08 → 06-08)`"""
    key = issue["key"]
    f = issue["fields"]
    summary = f["summary"]
    status = f["status"]["name"] if f.get("status") else "?"
    priority = f["priority"]["name"] if f.get("priority") else ""
    versions = get_versions(issue)
    date_range = get_date_range(issue)

    overdue = _is_overdue(issue)
    prefix = "- " if indent == 0 else "  - "

    status_display = f"**{status}**" if status.strip().lower() not in DONE_STATUSES else status

    line = f"{prefix}{key} [{priority}] {summary} {status_display}"
    line += f" {_status_icon(status)}"
    if overdue:
        line += " ⚠️ 逾期"
    if versions:
        line += f" [{', '.join(versions)}]"
    if date_range:
        short_dr = date_range.replace(str(datetime.now().year) + "-", "")
        line += f" ({short_dr})"
    return line


def build_markdown(user_name, open_id, stories, story_subtasks,
                   tasks, task_subtasks, improvements, improvement_subtasks,
                   debts, debt_subtasks, version_label):
    """构建 Markdown 消息文本。"""
    lines = []
    lines.append(f"📊 {user_name} — {version_label} 工作任务统计")
    lines.append("")

    def add_section(icon, label, items, sub_map):
        if not items:
            return
        lines.append(f"**{icon} {label}（{len(items)}个）**")
        for issue in items:
            lines.append(issue_line(issue, indent=0))
            for st in sub_map.get(issue["key"], []):
                lines.append(issue_line(st, indent=1))

    add_section("📖", "Story", stories, story_subtasks)
    lines.append("")
    add_section("📋", "Task", tasks, task_subtasks)
    lines.append("")
    add_section("🔧", "Improvement", improvements, improvement_subtasks)
    lines.append("")
    add_section("💸", "Debt", debts, debt_subtasks)

    return "\n".join(lines)


# ── 飞书发送 ──────────────────────────────────────────────────
def get_lark_chat_id(group_name):
    """按群名称搜索飞书群，返回匹配到的 chat_id。优先精确匹配名称完全相等的群，
    否则取搜索结果里的第一个；搜索失败或没有结果则返回 None。"""
    try:
        r = subprocess.run(
            ["lark-cli", "im", "+chat-search",
             "--query", group_name, "--as", "bot", "--format", "json"],
            capture_output=True, text=True, timeout=15)
        data = json.loads(r.stdout)
        items = data.get("data", {}).get("chats", [])
        for item in items:
            if item.get("name", "").strip() == group_name.strip():
                return item["chat_id"]
        return items[0]["chat_id"] if items else None
    except Exception:
        return None


def send_markdown(md_text, chat_id):
    """通过 lark-cli 以 markdown 格式发送到飞书群。"""
    try:
        r = subprocess.run(
            ["lark-cli", "im", "+messages-send",
             "--as", "bot",
             "--chat-id", chat_id,
             "--markdown", md_text],
            capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            print(f"❌ 发送失败: {r.stderr}", file=sys.stderr)
            return False
        print("✅ 已发送到飞书群")
        return True
    except Exception as e:
        print(f"❌ 发送异常: {e}", file=sys.stderr)
        return False


def send_image(image_path, chat_id):
    try:
        rel_path = os.path.relpath(image_path)
        r = subprocess.run(
            ["lark-cli", "im", "+messages-send",
             "--as", "bot",
             "--chat-id", chat_id,
             "--image", rel_path],
            capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            print(f"❌ 图片发送失败: {r.stderr}", file=sys.stderr)
            return False
        print("✅ 甘特图已发送到飞书群")
        return True
    except Exception as e:
        print(f"❌ 发送异常: {e}", file=sys.stderr)
        return False


# ── 甘特图生成 ──────────────────────────────────────────────────
def _parse_date(d):
    """解析 YYYY-MM-DD 字符串，容错返回 None。"""
    if not d:
        return None
    try:
        return datetime.strptime(d.strip(), "%Y-%m-%d")
    except ValueError:
        return None


def build_gantt(all_user_data, version_label):
    """根据所有人员任务数据生成甘特图，返回图片路径。每天一格，任务跨天填充多格。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.font_manager import FontProperties

    plt.rcParams.update({
        "font.family": "sans-serif",
        "axes.edgecolor": "#E0E0E0",
        "xtick.color": "#555555",
        "ytick.color": "#555555",
    })

    # 中文字体
    cn_font = FontProperties(fname=None)
    cn_opts = GANTT_FONTS
    available = {f.name for f in matplotlib.font_manager.fontManager.ttflist}
    for name in cn_opts:
        if name in available:
            cn_font = FontProperties(family=name)
            break

    # 收集所有带日期范围的任务 和 无日期任务
    rows = []
    no_date_rows = []  # 没有填写起止时间的任务
    for ud in all_user_data:
        for issue, issue_type in ud["items"]:
            f = issue["fields"]
            s = f.get(TARGET_START, "") or ""
            e = f.get(TARGET_END, "") or ""
            sd = _parse_date(s)
            ed = _parse_date(e)
            if not sd or not ed:
                no_date_rows.append({
                    "user": ud["user"],
                    "key": issue["key"],
                    "summary": f["summary"],
                    "issue_type": issue_type,
                    "status": (f.get("status") or {}).get("name", ""),
                    "start_str": s or "",
                    "end_str": e or "",
                })
                continue
            rows.append({
                "user": ud["user"],
                "key": issue["key"],
                "summary": f["summary"],
                "issue_type": issue_type,
                "start": sd,
                "end": ed,
                "status": (f.get("status") or {}).get("name", ""),
            })

    if not rows:
        if not no_date_rows:
            print("⚠️  没有任何任务，跳过甘特图。")
            return None
        # 只有未排期任务，使用当天作为占位日期生成纯文本列表
        today_dt = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        global_start = today_dt
        global_end = today_dt
        all_dates = [today_dt]
        num_tasks = 0
        num_days = 1
        has_no_date = True
    else:
        rows.sort(key=lambda r: (r["user"], r["start"], ISSUE_TYPE_ORDER.get(r["issue_type"], 99)))

        global_start = min(r["start"] for r in rows)
        global_end = max(r["end"] for r in rows)
        all_dates = []
        d = global_start
        while d <= global_end:
            all_dates.append(d)
            d = datetime.fromordinal(d.toordinal() + 1)

        num_tasks = len(rows)
        num_days = len(all_dates)
        has_no_date = len(no_date_rows) > 0

    # Figure 布局：有无日期任务时增加右侧面板
    fig_width = max(18, num_days * 0.55)
    fig_height = max(6, num_tasks * 0.65 + 2.0)

    if has_no_date:
        fig_width += 5.5
        # 确保高度足以容纳未排期任务列表
        nd_groups = OrderedDict()
        for nd in no_date_rows:
            nd_groups.setdefault(nd["user"], []).append(nd)
        nd_height = (len(no_date_rows) + len(nd_groups)) * 0.28 + 3.0
        fig_height = max(fig_height, nd_height)

    fig = plt.figure(figsize=(fig_width, fig_height), facecolor="white")

    if has_no_date:
        gs = fig.add_gridspec(1, 2, width_ratios=[0.76, 0.24],
                              left=0.07, right=0.98, top=0.84, bottom=0.12, wspace=0.02)
        ax = fig.add_subplot(gs[0, 0])
        ax_no_date = fig.add_subplot(gs[0, 1])
    else:
        gs = fig.add_gridspec(1, 1, left=0.10, right=0.90, top=0.84, bottom=0.12)
        ax = fig.add_subplot(gs[0, 0])

    ax.set_xlim(-0.5, max(num_days - 0.5, 0.5))
    ax.set_ylim(-0.5, max(num_tasks - 0.5, 0.5))
    ax.invert_yaxis()
    ax.tick_params(left=False, labelleft=False)
    ax.tick_params(bottom=False, pad=4)

    # 今天竖线
    today = datetime.now().date()
    today_idx = None
    for di, dt in enumerate(all_dates):
        if dt.date() == today:
            today_idx = di
            break
    if today_idx is not None:
        ax.axvline(x=today_idx + 0.5, color="#FF6B6B", linewidth=1.5,
                   linestyle="-", zorder=5, alpha=0.8)
        ax.text(today_idx + 0.5, -1.0, "今天", ha="center", fontsize=15,
                color="#FF6B6B", fontweight="bold", fontproperties=cn_font, zorder=6)

    # 行背景交替色
    for i in range(num_tasks):
        if i % 2 == 0:
            rect = mpatches.Rectangle((-0.5, i - 0.5), num_days, 1,
                                      facecolor="#FAFBFC", edgecolor="none", zorder=0)
            ax.add_patch(rect)

    # 用户分组背景和姓名标签
    user_groups = OrderedDict()
    for i, row in enumerate(rows):
        user_groups.setdefault(row["user"], []).append(i)
    user_colors = GANTT_ROW_COLORS
    uci = 0
    for user, indices in user_groups.items():
        top = indices[0] - 0.5
        bot = indices[-1] + 0.5
        mid_y = (top + bot) / 2
        if uci < len(user_colors):
            rect = mpatches.Rectangle((-0.5, top), num_days, bot - top,
                                      facecolor=user_colors[uci], edgecolor="none",
                                      zorder=0, alpha=0.6)
            ax.add_patch(rect)
        if indices[0] > 0:
            ax.axhline(y=top, color="#D0D0D0", linewidth=0.6, zorder=1)
        # 用户名标签 — 放在图表左侧，与对应行居中对齐
        ax.text(-0.5, mid_y, f"  {user}  ", ha="center", va="center", fontsize=15,
                fontweight="bold", color="#333333", fontproperties=cn_font,
                zorder=10, clip_on=False,
                bbox=dict(boxstyle="round,pad=0.2", facecolor="white",
                          edgecolor="#D0D0D0", alpha=0.9))
        uci += 1

    # 先画任务格子
    for i, row in enumerate(rows):
        start_idx = (row["start"] - global_start).days
        end_idx = (row["end"] - global_start).days
        cfg = ISSUE_TYPE_COLORS.get(row["issue_type"],
                                    {"fill": "#AAAAAA", "text": "#FFFFFF"})
        for day_idx in range(start_idx, end_idx + 1):
            # 周末格子也用统一的灰色填充
            is_weekend = all_dates[day_idx].weekday() >= 5
            fill_color = "#E0E0E0" if is_weekend else cfg["fill"]
            rect = mpatches.Rectangle(
                (day_idx - 0.5, i - 0.5), 1, 1,
                facecolor=fill_color, edgecolor="white", linewidth=0.6,
                zorder=3
            )
            ax.add_patch(rect)

    # 未占用的周末格子也填充灰色
    for di, dt in enumerate(all_dates):
        if dt.weekday() >= 5:
            rect = mpatches.Rectangle((di - 0.5, -0.5), 1, num_tasks,
                                      facecolor="#E0E0E0", edgecolor="none", zorder=0)
            ax.add_patch(rect)

    # 完整表格线：竖向（每天）+ 横向（每任务）
    for day_idx in range(num_days + 1):
        x = day_idx - 0.5
        ax.axvline(x=x, color="#D5D5D5", linewidth=0.5, zorder=0)
    for task_idx in range(num_tasks + 1):
        y = task_idx - 0.5
        ax.axhline(y=y, color="#D5D5D5", linewidth=0.5, zorder=0)

    # 后画文字，确保在所有格子之上
    for i, row in enumerate(rows):
        start_idx = (row["start"] - global_start).days
        end_idx = (row["end"] - global_start).days
        cfg = ISSUE_TYPE_COLORS.get(row["issue_type"],
                                    {"fill": "#AAAAAA", "text": "#FFFFFF"})
        label = f"{row['key']} {row['summary']}"
        mid_day = (start_idx + end_idx) / 2
        ax.text(mid_day, i, label, ha="center", va="center", fontsize=12,
                color="#222222", fontproperties=cn_font, zorder=99,
                fontweight="medium", clip_on=False,
                bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                          edgecolor="none", alpha=0.85))

    # X 轴刻度
    if num_days <= 12:
        tick_step = 1
    elif num_days <= 24:
        tick_step = 2
    elif num_days <= 45:
        tick_step = 4
    else:
        tick_step = max(7, num_days // 12)

    tick_indices = list(range(0, num_days, tick_step))
    # 确保最后一天在刻度上
    if tick_indices[-1] != num_days - 1 and num_days - 1 - tick_indices[-1] >= tick_step // 2:
        tick_indices.append(num_days - 1)
    ax.set_xticks(tick_indices)
    labels = []
    for i in tick_indices:
        dt = all_dates[i]
        labels.append(dt.strftime("%m/%d"))
    ax.set_xticklabels(labels, fontsize=15, color="#333333", rotation=30, ha="right")

    # 顶部也显示日期刻度
    ax_top = ax.twiny()
    ax_top.set_xlim(ax.get_xlim())
    ax_top.set_xticks(tick_indices)
    ax_top.set_xticklabels(labels, fontsize=15, color="#333333", rotation=30, ha="left")
    ax_top.tick_params(bottom=False, top=False, pad=4)

    # 右侧也显示用户名
    for user, indices in user_groups.items():
        top = indices[0] - 0.5
        bot = indices[-1] + 0.5
        mid_y = (top + bot) / 2
        ax.text(num_days - 0.5 + 0.5, mid_y, f"  {user}  ", ha="center", va="center",
                fontsize=15, fontweight="bold", color="#333333",
                fontproperties=cn_font, zorder=10, clip_on=False,
                bbox=dict(boxstyle="round,pad=0.2", facecolor="white",
                          edgecolor="#D0D0D0", alpha=0.9))

    # 月份分隔竖线
    prev_month = None
    for di, dt in enumerate(all_dates):
        month_key = dt.strftime("%Y-%m")
        if prev_month and month_key != prev_month:
            ax.axvline(x=di - 0.5, color="#B0B0B0", linewidth=0.8, zorder=1, alpha=0.7)
        prev_month = month_key
    # 添加月份标注
    month_positions = {}
    for di, dt in enumerate(all_dates):
        mk = dt.strftime("%m月")
        if mk not in month_positions:
            month_positions[mk] = []
        month_positions[mk].append(di)
    for mk, positions in month_positions.items():
        center = (positions[0] + positions[-1]) / 2
        ax.text(center, -1.55, mk, ha="center", fontsize=10,
                color="#555555", fontweight="bold", fontproperties=cn_font, zorder=6)

    # 标题
    ax.set_title(f"工作负载甘特图 — {version_label}", fontsize=15, fontweight="bold",
                 color="#222222", fontproperties=cn_font, pad=35)

    # 图例
    legend_patches = []
    for t in ("Task", "Sub-task", "Test Sub-Task"):
        cfg = ISSUE_TYPE_COLORS.get(t, {})
        if cfg:
            legend_patches.append(mpatches.Patch(facecolor=cfg["fill"], edgecolor="white",
                                                 label=t))
    ax.legend(handles=legend_patches, loc="upper right",
              fontsize=15, ncol=len(legend_patches), frameon=True, framealpha=0.9,
              edgecolor="#E0E0E0", prop=cn_font)

    # ── 未排期任务右侧面板 ──
    if has_no_date:
        ax_no_date.set_xlim(0, 1)

        nd_groups = OrderedDict()
        for nd in no_date_rows:
            nd_groups.setdefault(nd["user"], []).append(nd)
        nd_items = list(nd_groups.items())
        total_groups = len(nd_items)

        ax_no_date.axis("off")

        # 计算每个用户分区高度
        total_height = total_groups * 15 + 5 + 2
        ax_no_date.set_ylim(0, total_height)

        group_heights = {}
        y_pos = total_groups * 15 + 5
        for user, items in nd_items:
            group_h = len(items) * 1.6 + 1.5
            y_pos -= group_h
            group_heights[user] = (y_pos, group_h, items)

        # 标题
        ax_no_date.text(0.5, total_groups * 15 + 5 + 1.2,
                        f"未排期任务（{len(no_date_rows)}个）",
                        ha="center", va="center", fontsize=11, fontweight="bold",
                        color="#E67E22", fontproperties=cn_font)

        # 按用户分组展示
        nd_colors = GANTT_ND_COLORS
        for user, (base_y, group_h, items) in group_heights.items():
            # 用户名标签
            ax_no_date.text(0.02, base_y + group_h - 0.6, user,
                            ha="left", va="top", fontsize=10, fontweight="bold",
                            color="#555555", fontproperties=cn_font)
            # 分隔线
            ax_no_date.axhline(y=base_y + group_h - 0.8, color="#E8E8E8",
                               linewidth=0.5, xmin=0.02, xmax=0.98)
            y_item = base_y + group_h - 2.0
            for nd in items:
                cfg = nd_colors.get(nd["issue_type"],
                                    {"bg": "#FAFAFA", "icon": "  ", "text": "#666666"})
                # 背景色块
                rect = mpatches.FancyBboxPatch(
                    (0.03, y_item), 0.94, 1.3,
                    boxstyle="round,pad=0.08", facecolor=cfg["bg"],
                    edgecolor="none", alpha=0.8, zorder=0)
                ax_no_date.add_patch(rect)
                # 任务文字
                label = f"{cfg['icon']} {nd['key']} {nd['summary'][:22]}"
                ax_no_date.text(0.06, y_item + 0.65, label,
                                ha="left", va="center", fontsize=7.5,
                                color=cfg["text"], fontproperties=cn_font)
                # 部分日期提示
                if nd["start_str"] or nd["end_str"]:
                    hint = nd["start_str"] + " → " + nd["end_str"] if nd["start_str"] and nd["end_str"] else nd["start_str"] + " → ?" if nd["start_str"] else "? → " + nd["end_str"]
                    ax_no_date.text(0.97, y_item + 0.65, hint,
                                    ha="right", va="center", fontsize=6.5,
                                    color="#CC0000", fontproperties=cn_font)
                y_item -= 1.6

    # 底部计数
    task_count = sum(1 for r in rows if r["issue_type"] == "Task")
    sub_count = sum(1 for r in rows if r["issue_type"] == "Sub-task")
    ax.text(0.5, -0.04, f"{task_count} Tasks · {sub_count} Sub-tasks · 总计 {num_tasks}",
            transform=ax.transAxes, ha="center", fontsize=9,
            color="#888888", fontproperties=cn_font)

    filename = f"gantt_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    out_path = os.path.abspath(filename)
    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"📊 甘特图已生成: {out_path}")
    return out_path


# ── 终端输出 ──────────────────────────────────────────────────
def fmt_issue_tty(issue, indent=0):
    """格式化一条 issue，用于在终端打印（区分父任务/子任务的缩进）。"""
    f = issue["fields"]
    prefix = "* " if indent == 0 else "   * "
    return f"{prefix}{issue['key']} [{f['priority']['name']}] {f['summary']} {f['status']['name']}"


def print_detail(stories, story_subtasks, tasks, task_subtasks,
                 improvements, improvement_subtasks, debts, debt_subtasks, orphan_subtasks):
    """在终端按 Story / Task / Improvement / Debt 四大类依次打印任务明细，
    每个父任务下面紧跟着打印它对应的子任务；找不到父任务的"孤儿子任务"单独列出来提醒。"""
    print(f"\n📖 Story（{len(stories)}个）")
    if not stories:
        print("  - 无")
    for s in stories:
        print(fmt_issue_tty(s))
        for st in story_subtasks.get(s["key"], []):
            print(fmt_issue_tty(st, indent=1))
    print()

    if orphan_subtasks:
        print(f"⚠️  孤儿子任务")
        for st in orphan_subtasks:
            print(fmt_issue_tty(st))

    print(f"📋 Task（{len(tasks)}个）")
    if not tasks:
        print("  - 无")
    for t in tasks:
        print(fmt_issue_tty(t))
        for st in task_subtasks.get(t["key"], []):
            print(fmt_issue_tty(st, indent=1))
    print()

    print(f"🔧 Improvement（{len(improvements)}个）")
    if not improvements:
        print("  - 无")
    for imp in improvements:
        print(fmt_issue_tty(imp))
        for st in improvement_subtasks.get(imp["key"], []):
            print(fmt_issue_tty(st, indent=1))

    print(f"\n💸 Debt（{len(debts)}个）")
    if not debts:
        print("  - 无")
    for d in debts:
        print(fmt_issue_tty(d))
        for st in debt_subtasks.get(d["key"], []):
            print(fmt_issue_tty(st, indent=1))


# ── 主逻辑 ────────────────────────────────────────────────────
def run(versions, users, send_lark=False, lark_group=DEFAULT_LARK_GROUP, chat_id=""):
    """整个脚本的主流程：
    1. 加载 Jira 认证信息；
    2. 如果要发飞书消息，先准备好 @人 用的 open_id 和目标群的 chat_id；
    3. 依次处理每个用户：分别查询其 Story / Sub-task / Task / Improvement / Debt，
       把子任务挂到对应的父任务下面（找不到父任务的算"孤儿子任务"），
       在终端打印明细，并汇总统计数字；
       如果要发飞书，则生成 Markdown 消息发到群里；
       同时收集该用户的 Task/Sub-task 数据，留给后面画甘特图用；
       4. 所有用户处理完后，如果要发飞书，统一生成一张甘特图并发送到群里。
    """
    url, ah = load_config()
    # 把版本号列表拼成 JQL 里 fixVersion in (...) 需要的格式，例如 "v6.18","v6.20"
    versions_str = ",".join(f'"{v.strip()}"' for v in versions)
    version_label = ", ".join(versions)

    # 提前查询该版本下的所有父任务，以便之后查询子任务时，能够涵盖自身未标明版本但父任务属于该版本的子任务
    parent_jql = f'fixVersion in ({versions_str}) AND issuetype in (Story, Task, Improvement, Debt)'
    parent_issues = jira_request(url, ah, parent_jql, ["key"])
    version_parent_keys = [p["key"] for p in parent_issues]

    open_ids = {}
    if send_lark:
        # 提前把所有要 @ 的人转换成飞书 open_id
        # 为了提高匹配率，先通过 resolve_jira_username 解析，再使用 get_search_name 清理出最适合飞书搜索的名字
        search_names = []
        name_map_back = {}  # 搜索的名字 -> 输入的原始名字
        for u in users:
            resolved_username = resolve_jira_username(u, DEFAULT_USERS)
            search_name = get_search_name(resolved_username)
            search_names.append(search_name)
            name_map_back[search_name] = u

        resolved_open_ids = get_open_ids(search_names)
        for s_name, oid in resolved_open_ids.items():
            orig_name = name_map_back.get(s_name)
            if orig_name:
                open_ids[orig_name] = oid

        if chat_id:
            pass  # 直接使用传入的 chat_id
        else:
            # 没有显式传 chat_id，就按群名称去搜索
            chat_id = get_lark_chat_id(lark_group)
            if not chat_id:
                print(f"❌ 未找到飞书群: {lark_group}", file=sys.stderr)
                sys.exit(1)
        print(f"📤 目标 chat_id: {chat_id}")

    all_user_data = []  # 收集所有人的 Task/Sub-task 数据，最后统一画一张甘特图

    for user_name in users:
        # 局部名字模糊匹配或换成 Jira 用户名；如果均匹配不到，就把传入值直接当用户名用
        username = resolve_jira_username(user_name, DEFAULT_USERS)
        open_id = open_ids.get(user_name)

        print(f"\n{'='*70}")
        print(f"QA：{user_name}（{username}）")
        print(f"{'='*70}")

        # 分别按四种任务类型查询该用户名下的工作项，再单独查所有子任务
        stories = query_stories(url, ah, versions_str, username)
        subtasks = query_subtasks(url, ah, versions_str, username, parent_keys=version_parent_keys)
        tasks = query_tasks(url, ah, versions_str, username)
        improvements = query_improvements(url, ah, versions_str, username)
        debts = query_debts(url, ah, versions_str, username)

        # ── 针对 QA 工作负载：通过子任务反查补全父任务 ─────────────────
        sk = {s["key"] for s in stories}
        tk = {t["key"] for t in tasks}
        ik = {i["key"] for i in improvements}
        dk = {d["key"] for d in debts}

        parent_keys = set()
        for st in subtasks:
            pk = get_parent_key(st)
            if pk:
                parent_keys.add(pk)

        missing_parents = parent_keys - (sk | tk | ik | dk)
        if missing_parents:
            # 批量获取缺少的父任务
            keys_str = ",".join(f'"{key}"' for key in missing_parents)
            jql_parents = f"key in ({keys_str})"
            fetched_parents = jira_request(url, ah, jql_parents, JIRA_FIELDS)
            for p in fetched_parents:
                itype = p["fields"]["issuetype"]["name"]
                if itype == "Story":
                    stories.append(p)
                    sk.add(p["key"])
                elif itype == "Task":
                    tasks.append(p)
                    tk.add(p["key"])
                elif itype == "Improvement":
                    improvements.append(p)
                    ik.add(p["key"])
                elif itype == "Debt":
                    debts.append(p)
                    dk.add(p["key"])
                else:
                    # 默认归为 Task 分类
                    tasks.append(p)
                    tk.add(p["key"])

        # 按父任务类型把子任务分组挂好；挂不上任何已知父任务的归入 orphan（孤儿子任务）
        story_subtasks = defaultdict(list)
        task_subtasks = defaultdict(list)
        improvement_subtasks = defaultdict(list)
        debt_subtasks = defaultdict(list)
        orphan = []
        for st in subtasks:
            pk = get_parent_key(st)
            if pk in sk:
                story_subtasks[pk].append(st)
            elif pk in tk:
                task_subtasks[pk].append(st)
            elif pk in ik:
                improvement_subtasks[pk].append(st)
            elif pk in dk:
                debt_subtasks[pk].append(st)
            else:
                orphan.append(st)

        # 在终端打印这个人的任务明细
        print_detail(stories, story_subtasks, tasks, task_subtasks, improvements, improvement_subtasks, debts, debt_subtasks, orphan)

        # 汇总数字（每类父任务下挂的子任务总数）
        total_ss = sum(len(v) for v in story_subtasks.values())
        total_ts = sum(len(v) for v in task_subtasks.values())
        total_is = sum(len(v) for v in improvement_subtasks.values())
        total_ds = sum(len(v) for v in debt_subtasks.values())
        print(f"\n---")
        print(f"汇总: Story {len(stories)} | Story-Sub-task {total_ss} | "
              f"Task {len(tasks)} | Task-Sub-task {total_ts} | "
              f"Improvement {len(improvements)} | Improvement-Sub-task {total_is} | "
              f"Debt {len(debts)} | Debt-Sub-task {total_ds}")

        if send_lark:
            # 生成这个人的 Markdown 统计消息，发到飞书群（会 @ 这个人，如果拿到了 open_id）
            md = build_markdown(user_name, open_id, stories, story_subtasks,
                                tasks, task_subtasks, improvements, improvement_subtasks,
                                debts, debt_subtasks, version_label)
            send_markdown(md, chat_id)
            import time
            time.sleep(2.0)  # 每次发送后延迟 2 秒以避免触发飞书频控限制 (HTTP 429)

        # 收集甘特图数据（只统计直接指派给该用户的 Task 和 Sub-task）
        user_items = []
        for t in tasks:
            f = t["fields"]
            assignee_obj = f.get("assignee") or {}
            assignee_name = assignee_obj.get("name", "")
            devs = f.get(DEVELOPERS_FIELD) or []
            is_dev = False
            if isinstance(devs, list):
                is_dev = any((d.get("name") == username) for d in devs if isinstance(d, dict))
            elif isinstance(devs, dict):
                is_dev = devs.get("name") == username
            
            if assignee_name == username or is_dev:
                user_items.append((t, "Task"))

        user_items.extend((st, "Sub-task") for st in subtasks)
        all_user_data.append({"user": user_name, "items": user_items})

    # 所有用户处理完后，统一生成一张甘特图，如果启用了 send_lark 则发送到飞书群
    if all_user_data:
        gantt_path = build_gantt(all_user_data, version_label)
        if send_lark and gantt_path:
            send_image(gantt_path, chat_id)


# ── CLI ───────────────────────────────────────────────────────
def main():
    """命令行入口：解析参数 -> 整理版本号/用户名列表 -> 调用 run() 执行主流程。"""
    p = argparse.ArgumentParser(description="Jira 版本工作任务统计工具")
    p.add_argument("--versions", "-v", required=True)   # 必填，逗号分隔的版本号，如 v6.18,v6.20
    p.add_argument("--users", "-u")                      # 可选，逗号分隔的姓名；不填则用 DEFAULT_USERS 里的全部人
    p.add_argument("--send-to-lark", action="store_true")  # 加上这个 flag 才会真正发飞书消息/图片
    p.add_argument("--lark-group", default=DEFAULT_LARK_GROUP)  # 目标飞书群名称
    p.add_argument("--chat-id", default="")               # 也可以直接指定 chat_id，跳过按群名搜索
    args = p.parse_args()

    # 按逗号拆分版本号，并去除空白；至少要有一个版本，否则直接报错退出
    versions = [v.strip() for v in args.versions.split(",") if v.strip()]
    if not versions:
        print("❌ 请至少指定一个版本", file=sys.stderr)
        sys.exit(1)

    # 没传 --users 就用默认的全部人；传了就按逗号拆分
    users = ([u.strip() for u in args.users.split(",") if u.strip()]
             if args.users else list(DEFAULT_USERS.keys()))

    run(versions, users, send_lark=args.send_to_lark,
        lark_group=args.lark_group, chat_id=args.chat_id)


if __name__ == "__main__":
    main()
