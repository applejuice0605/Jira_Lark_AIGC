import logging
import sys
import time
from typing import Dict, Any, List, Optional, Set
import requests
import json
from datetime import datetime
import pytz
from urllib.parse import quote_plus
import os
# 尝试加载 .env 配置文件
try:
    from dotenv import load_dotenv
    # 优先加载当前工作目录下的 .env
    load_dotenv()
    # 兼容从技能安装目录下（.agents/skills/jira_issue_status_monitor/）加载 .env
    script_dir = os.path.dirname(os.path.abspath(__file__))
    skill_dir = os.path.dirname(script_dir)
    skill_env = os.path.join(skill_dir, ".env")
    if os.path.exists(skill_env):
        load_dotenv(skill_env, override=True)
except ImportError:
    pass

# 标题日期前缀（按时区）
def _today_title(base_title: str, tz_name: str) -> str:
    try:
        tz = pytz.timezone(tz_name)
        dt = datetime.now(tz)
    except Exception:
        dt = datetime.now()
    return "%s %s" % (dt.strftime('%Y-%m-%d'), base_title)

# 基于python3已上版本, 卡片推送不带icon
SETTINGS: Dict[str, Any] = {
    "JIRA_BASE_URL": "https://rd-project.fuseinsurtech.com",
    "JIRA_USERNAME": "huxuesong",
    "JIRA_PASSWORD": "Qq12345678=",
    "LARK_WEBHOOK_URL": "https://open.larksuite.com/open-apis/bot/v2/hook/442dc5a2-6eef-41e5-85fe-da97d21eccff",
    "REPORT_PROJECT_KEYS": ["CS"],
    "REPORT_JQL": "project = MP AND issuetype = Bug AND status in (Open) AND Env in (UAT, SIT)",
    "TIMEZONE": "Asia/Shanghai",
    "LOG_LEVEL": "INFO",
    "MESSAGE_TYPE": "interactive",
    "REPORT_TOP_N": 10,
    "MAX_RESULTS": 100,
    "ENABLE_LINKS": True,
    "ASSIGNEE_FIELD_PATH": "assignee.displayName",
    "ENV_FIELD_PATH": "customfield_10701.value",
    "ROW_PREFIX_EMOJI": "-",
    "COUNT_EMOJI": "COUNT",
    "AT_ASSIGNEE_PLAIN": False,
    "AT_ASSIGNEE_MENTION": True,
    "AT_TOP_LIMIT": 10,

    "ASSIGNEE_MAP_INLINE": {
        "罗恒(Loren Luo)": "6985397642436018181",
        "赵志国(Vito Zhao)": "7050270687382011909",
        "张界(Magee Zhang)": "7080360017798381574",
        "Azis Setiawan": "7217663305542795269",
        "Faris Harun Ahmad": "7556829471928516646",
        "Winda Natalia Sianipar": "7298201363240992774",
        "王正鑫(Tanya)": "7050091635010437126",
        "Joshua Dika": "7137161637517066245",
        "吴维(Shirley)": "7050275950939865093",
        "Joshua Kevin Christian": "7537209808038936608",
        "Chintia Uli Br Panggabean": "7264406897271291909",
    },
    "CARD_LAYOUT": "single_column",
    "KEY_EMOJI": "Key",
    "ENV_EMOJI": "Env",
    "QA_EMOJI": "QAs",
    "PRIORITY_EMOJI": "Priority",
    "SUMMARY_EMOJI": "Summary",
    "LINK_EMOJI": "Link",
    "SHOW_LIMIT": 15,
}

# 优先读取系统环境变量覆盖默认设置（如 .env 加载的配置）
for key in ["JIRA_BASE_URL", "JIRA_USERNAME", "JIRA_PASSWORD", "LARK_WEBHOOK_URL"]:
    env_val = os.environ.get(key)
    if env_val:
        SETTINGS[key] = env_val.strip().strip('"').strip("'")


def setup_logger(level: str = "INFO") -> logging.Logger:
    os.makedirs("logs", exist_ok=True)
    logger = logging.getLogger()
    logger.setLevel(level)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.handlers = []
    logger.addHandler(ch)
    fh = logging.FileHandler(os.path.join("logs", "app.log"), encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    return logger

class JiraClient:
    def __init__(self, base_url: str, username: Optional[str] = None, password: Optional[str] = None, api_version: str = "2") -> None:
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        self.api_version = (api_version or "2").strip()
        self.session.auth = (username or "", password or "")

    def search_issues(self, jql: str, max_results: int = 50, retries: int = 3) -> List[Dict[str, Any]]:
        url = "%s/rest/api/%s/search" % (self.base_url, self.api_version)
        params = {"jql": jql, "maxResults": max_results}
        last_exc = None
        for attempt in range(1, retries + 1):
            try:
                resp = self.session.get(url, params=params, timeout=20)
                resp.raise_for_status()
                data = resp.json()
                return data.get("issues", [])
            except Exception as e:
                last_exc = e
                if attempt < retries:
                    time.sleep(1.0 * attempt)
        if last_exc:
            raise last_exc
        return []

class LarkClient:
    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url

    def _post(self, payload: Dict[str, Any], retries: int = 3, backoff_sec: float = 1.0) -> Dict[str, Any]:
        last_exc = None
        for attempt in range(1, retries + 1):
            try:
                resp = requests.post(self.webhook_url, json=payload, timeout=15)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                last_exc = e
                if attempt < retries:
                    time.sleep(backoff_sec * attempt)
        if last_exc:
            raise last_exc
        return {}

    def send_text(self, text: str) -> Dict[str, Any]:
        payload = {"msg_type": "text", "content": {"text": text}}
        return self._post(payload)

    def send_post_content(self, title: str, content: List[List[Dict[str, Any]]]) -> Dict[str, Any]:
        payload = {"msg_type": "post", "content": {"post": {"zh_cn": {"title": title, "content": content}}}}
        return self._post(payload)

    def send_interactive_card(self, card: Dict[str, Any]) -> Dict[str, Any]:
        payload = {"msg_type": "interactive", "card": card}
        return self._post(payload)

def _get_by_path(fields: Dict[str, Any], path: str) -> str:
    if not path:
        return ""
    parts = [p for p in path.split(".") if p]
    cur = fields
    for p in parts:
        if isinstance(cur, dict):
            cur = cur.get(p)
        elif isinstance(cur, list):
            cur = cur[0] if cur else None
        else:
            cur = None
        if cur is None:
            return ""
    if isinstance(cur, dict):
        return cur.get("displayName") or cur.get("name") or ""
    return str(cur) if cur is not None else ""

def _priority_rank(name: Optional[str]) -> int:
    if not name:
        return 999
    n = str(name).strip().upper()
    mapping = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    if n in mapping:
        return mapping[n]
    import re
    m = re.search(r"\bP(\d)\b", n)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            pass
    synonyms = {"HIGHEST": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    if n in synonyms:
        return synonyms[n]
    return 999

def _created_sort_val(created: Optional[str]) -> float:
    if not created:
        return float("inf")
    s = str(created)
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.timestamp()
        except Exception:
            pass
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            naive = datetime.strptime(s, fmt)
            dt = pytz.utc.localize(naive)
            return dt.timestamp()
        except Exception:
            pass
    return float("inf")

def _summarize_by_custom_field(issues: List[Dict[str, Any]], field_path: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for issue in issues:
        fields = issue.get("fields") or {}
        val = _get_by_path(fields, field_path) if field_path else ""
        name = (val or "Unassigned").strip()
        counts[name] = counts.get(name, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: (-x[1], x[0])))

def format_post_report(issues: List[Dict[str, Any]], project_keys: Optional[List[str]] = None, top_n: int = 10, base_url_for_links: Optional[str] = None, assignee_field_path: str = "assignee.displayName", env_field_path: str = "", row_prefix_emoji: str = "-", count_emoji: str = "COUNT", AT_ASSIGNEE_PLAIN: bool = False) -> tuple:
    total = len(issues)
    title = _today_title("Micro SIT Pending Open Bugs(Daily Push)", SETTINGS.get("TIMEZONE", "Asia/Shanghai"))
    content: List[List[Dict[str, Any]]] = [[{"tag": "text", "text": "%s Pending update amount: %d\n" % (count_emoji, total)}]]
    qa_counts = _summarize_by_custom_field(issues, assignee_field_path)
    top_qas = list(qa_counts.items())[:10]
    if top_qas:
        top_line = "TOP Assignee PIC: " + ", ".join(["%s:%d" % (name, cnt) for name, cnt in top_qas])
        content.append([{"tag": "text", "text": top_line}])
    issues_sorted = sorted(
        issues,
        key=lambda i: (
            _priority_rank(_get_by_path((i.get("fields") or {}), "priority.name")),
            _created_sort_val((i.get("fields") or {}).get("created", "")),
        ),
    )
    for issue in issues_sorted[:top_n]:
        key = issue.get("key", "")
        fields = issue.get("fields") or {}
        qa_val = _get_by_path(fields, assignee_field_path)
        priority = _get_by_path(fields, "priority.name")
        env_val = _get_by_path(fields, env_field_path)
        summary = fields.get("summary", "")
        elements: List[Dict[str, Any]] = []
        prefix = ("%s " % row_prefix_emoji) if row_prefix_emoji else "- "
        if base_url_for_links and key:
            elements.append({"tag": "text", "text": prefix})
            elements.append({"tag": "a", "text": key, "href": "%s/browse/%s" % (base_url_for_links.rstrip('/'), key)})
        else:
            elements.append({"tag": "text", "text": "%s%s" % (prefix, key)})
        if env_val:
            elements.append({"tag": "text", "text": " %s" % env_val})
        if qa_val:
            elements.append({"tag": "text", "text": " [%s]" % qa_val})
            if AT_ASSIGNEE_PLAIN:
                elements.append({"tag": "text", "text": " @%s" % qa_val})
        else:
            elements.append({"tag": "text", "text": " [Unassigned]"})
        tail_parts = []
        if priority:
            tail_parts.append(priority)
        if summary:
            tail_parts.append(summary)
        if tail_parts:
            elements.append({"tag": "text", "text": " " + " ".join(tail_parts)})
        content.append(elements)
    return title, content

def _collect_assignee_names(issues: List[Dict[str, Any]], assignee_field_path: str) -> Set[str]:
    names: Set[str] = set()
    for issue in issues:
        fields = issue.get("fields") or {}
        val = _get_by_path(fields, assignee_field_path)
        if val and str(val).strip():
            names.add(str(val).strip())
    return names

def _collect_top_assignees_by_counts(issues: List[Dict[str, Any]], assignee_field_path: str, top_limit: int) -> List[str]:
    counts = _summarize_by_custom_field(issues, assignee_field_path)
    top = list(counts.items())[:max(0, top_limit)]
    return [name for name, _ in top if str(name).strip()]

def _load_qa_map(path: str) -> Dict[str, str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items() if v}
    except Exception:
        pass
    return {}

def _get_qa_map(path: str) -> Dict[str, str]:
    inline = SETTINGS.get("ASSIGNEE_MAP_INLINE") or {}
    if isinstance(inline, dict) and inline:
        return {str(k): str(v) for k, v in inline.items() if v}
    return _load_qa_map(path)

def _send_mentions(lark: "LarkClient", issues: List[Dict[str, Any]], assignee_field_path: str, qa_map_path: str) -> None:
    qa_map = _get_qa_map(qa_map_path)
    names = _collect_top_assignees_by_counts(issues, assignee_field_path, int(SETTINGS.get("AT_TOP_LIMIT", 10)))
    logger = logging.getLogger(__name__)
    try:
        logger.info("提及候选数=%d, 候选=%s", len(names), ", ".join(names))
    except Exception:
        logger.info("提及候选数=%d", len(names))
    user_ids: List[str] = []
    missing: List[str] = []
    for n in names:
        uid = qa_map.get(n)
        if uid:
            if uid not in user_ids:
                user_ids.append(str(uid))
        else:
            missing.append(n)
    if missing:
        try:
            logger.warning("未匹配到user_id的人员=%s", ", ".join(missing))
        except Exception:
            logger.warning("未匹配到user_id人数=%d", len(missing))
    if not user_ids:
        logger.info("未发送提及：无可用user_id，AT_ASSIGNEE_MENTION=%s", SETTINGS.get("AT_ASSIGNEE_MENTION"))
        return
    content: List[List[Dict[str, Any]]] = [[{"tag": "text", "text": "请相关方及时跟进 Please kindly follow up in time："}]]
    for uid in user_ids:
        content[0].append({"tag": "at", "user_id": uid})
    try:
        logger.info("发送提及数=%d", len(user_ids))
        resp = lark.send_post_content(_today_title("Mention", SETTINGS.get("TIMEZONE", "Asia/Shanghai")), content)
        logger.info("提及响应=%s", resp)
    except Exception as e:
        logger.error("提及失败=%s", e)

def _format_created(created: str, tz_name: Optional[str] = None) -> str:
    if not created:
        return ""
    target_tz = None
    if tz_name:
        try:
            target_tz = pytz.timezone(tz_name)
        except Exception:
            target_tz = None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            dt = datetime.strptime(created, fmt)
            if target_tz:
                dt = dt.astimezone(target_tz)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            naive = datetime.strptime(created, fmt)
            if target_tz:
                dt = pytz.utc.localize(naive).astimezone(target_tz)
            else:
                dt = naive
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass
    return created

def build_interactive_card(issues: List[Dict[str, Any]], title: str, base_url_for_links: Optional[str], assignee_field_path: str, env_field_path: str, count_emoji: str, row_prefix_emoji: str, show_limit: int, jira_base_url: str, jql: str, layout: str, key_emoji: str, env_emoji: str, qa_emoji: str, priority_emoji: str, summary_emoji: str, link_emoji: str, target_tz: str) -> Dict[str, Any]:
    total = len(issues)
    card: Dict[str, Any] = {"config": {"wide_screen_mode": True}, "header": {"title": {"tag": "plain_text", "content": title}}, "elements": []}
    elements = card["elements"]
    overview = "%s Pending update amount: %d" % (count_emoji, total)
    elements.append({"tag": "div", "text": {"tag": "lark_md", "content": overview}})
    qa_counts = _summarize_by_custom_field(issues, assignee_field_path)
    top_qas = list(qa_counts.items())[:10]
    if top_qas:
        top_line = "TOP Assignee PIC: " + ", ".join(["%s:%d" % (name, cnt) for name, cnt in top_qas])
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": top_line}})
    elements.append({"tag": "hr"})
    issues_sorted = sorted(
        issues,
        key=lambda i: (
            _priority_rank(_get_by_path((i.get("fields") or {}), "priority.name")),
            _created_sort_val((i.get("fields") or {}).get("created", "")),
        ),
    )
    show_items = issues_sorted[:show_limit]
    hidden_count = max(0, len(issues_sorted) - len(show_items))
    for issue in show_items:
        key = issue.get("key", "")
        fields = issue.get("fields") or {}
        val = _get_by_path(fields, assignee_field_path)
        qa_val = val.strip() if val else "Unassigned"
        env_val = _get_by_path(fields, env_field_path)
        priority = _get_by_path(fields, "priority.name")
        summary = fields.get("summary", "")
        created = fields.get("created", "")
        created_fmt = _format_created(created, target_tz)
        if base_url_for_links and key:
            key_md = "%s **Key**: [%s](%s/browse/%s)" % (row_prefix_emoji, key, base_url_for_links.rstrip('/'), key)
        else:
            key_md = "%s **Key**: %s" % (row_prefix_emoji, key)
        left_lines = [key_md]
        if env_val:
            left_lines.append("**Env**: %s" % (env_val))
        right_lines = ["**Assignee**: %s" % (qa_val)]
        if priority:
            right_lines.append("**Priority**: %s" % (priority))
        if layout == "single_column":
            lines = []
            lines.extend(left_lines)
            lines.extend(right_lines)
            if created_fmt:
                lines.append("**Created**: %s" % created_fmt)
            if summary:
                lines.append("%s %s" % (summary_emoji, summary))
            elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(lines)}})
        elif layout == "three_columns":
            fields_block = {"tag": "div", "fields": [{"is_short": True, "text": {"tag": "lark_md", "content": "\n".join(left_lines)}}, {"is_short": True, "text": {"tag": "lark_md", "content": "\n".join(right_lines)}}, {"is_short": True, "text": {"tag": "lark_md", "content": "**Created**: %s" % created_fmt}}]}
            elements.append(fields_block)
            if summary:
                elements.append({"tag": "note", "elements": [{"tag": "plain_text", "content": "%s %s" % (summary_emoji, summary)}]})
        else:
            elements.append({"tag": "div", "fields": [{"is_short": True, "text": {"tag": "lark_md", "content": "\n".join(left_lines)}}, {"is_short": True, "text": {"tag": "lark_md", "content": "\n".join(right_lines + (["**Created**: %s" % created_fmt] if created_fmt else []))}}]})
            if summary:
                elements.append({"tag": "note", "elements": [{"tag": "plain_text", "content": "%s %s" % (summary_emoji, summary)}]})
    if hidden_count > 0:
        elements.append({"tag": "hr"})
        tip = "Remaining %d items collapsed" % hidden_count
        if jira_base_url and jql:
            jql_url = "%s/issues/?jql=%s" % (jira_base_url.rstrip('/'), quote_plus(jql))
            tip = tip + ", [View All](%s)" % jql_url
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "Info: %s" % tip}})
    return card

def run_job() -> None:
    setup_logger(level=SETTINGS["LOG_LEVEL"])
    logger = logging.getLogger(__name__)
    if not SETTINGS.get("JIRA_BASE_URL"):
        print("JIRA_BASE_URL missing", file=sys.stderr)
        return
    if not SETTINGS.get("JIRA_USERNAME"):
        print("JIRA_USERNAME missing", file=sys.stderr)
        return
    if not SETTINGS.get("JIRA_PASSWORD"):
        print("JIRA_PASSWORD missing", file=sys.stderr)
        return
    api_version = "2"
    logger.info("开始生成日报 jql=%s", SETTINGS["REPORT_JQL"])
    try:
        jira = JiraClient(
            SETTINGS["JIRA_BASE_URL"],
            username=(SETTINGS.get("JIRA_USERNAME") or None),
            password=(SETTINGS.get("JIRA_PASSWORD") or None),
            api_version=api_version,
        )
        issues = jira.search_issues(SETTINGS["REPORT_JQL"], max_results=int(SETTINGS["MAX_RESULTS"]))
        logger.info("从 Jira 获取到 %d 条结果", len(issues))
    except Exception as e:
        print("Jira 请求失败: %s" % e, file=sys.stderr)
        return

    webhook = str(SETTINGS.get("LARK_WEBHOOK_URL", "")).strip()
    if not webhook:
        print("未配置 LARK_WEBHOOK_URL，打印到控制台，条目数=%d" % len(issues))
        if str(SETTINGS["MESSAGE_TYPE"]).strip().lower() == "post":
            title, content = format_post_report(
                issues,
                SETTINGS["REPORT_PROJECT_KEYS"],
                top_n=int(SETTINGS["REPORT_TOP_N"]),
                base_url_for_links=(SETTINGS["JIRA_BASE_URL"] if SETTINGS["ENABLE_LINKS"] else None),
                assignee_field_path=SETTINGS["ASSIGNEE_FIELD_PATH"],
                env_field_path=SETTINGS["ENV_FIELD_PATH"],
                row_prefix_emoji=SETTINGS["ROW_PREFIX_EMOJI"],
                count_emoji=SETTINGS["COUNT_EMOJI"],
                AT_ASSIGNEE_PLAIN=SETTINGS["AT_ASSIGNEE_PLAIN"],
            )
            print(title)
            for block in content:
                for elem in block:
                    if "text" in elem:
                        print(elem["text"])
        else:
            title = _today_title("Micro SIT Pending Open Bugs(Daily Push)", SETTINGS.get("TIMEZONE", "Asia/Shanghai"))
            card = build_interactive_card(
                issues,
                title,
                base_url_for_links=(SETTINGS["JIRA_BASE_URL"] if SETTINGS["ENABLE_LINKS"] else None),
                assignee_field_path=SETTINGS["ASSIGNEE_FIELD_PATH"],
                env_field_path=SETTINGS["ENV_FIELD_PATH"],
                count_emoji=SETTINGS["COUNT_EMOJI"],
                row_prefix_emoji=SETTINGS["ROW_PREFIX_EMOJI"],
                show_limit=int(SETTINGS["SHOW_LIMIT"]),
                jira_base_url=SETTINGS["JIRA_BASE_URL"],
                jql=SETTINGS["REPORT_JQL"],
                layout=SETTINGS["CARD_LAYOUT"],
                key_emoji=SETTINGS["KEY_EMOJI"],
                env_emoji=SETTINGS["ENV_EMOJI"],
                qa_emoji=SETTINGS["QA_EMOJI"],
                priority_emoji=SETTINGS["PRIORITY_EMOJI"],
                summary_emoji=SETTINGS["SUMMARY_EMOJI"],
                link_emoji=SETTINGS["LINK_EMOJI"],
                target_tz=SETTINGS["TIMEZONE"],
            )
            print(card.get("header", {}).get("title", ""))
            for el in card.get("elements", []):
                content = el.get("content")
                if isinstance(content, str):
                    print(content)
        return

    try:
        lark = LarkClient(webhook)
        if str(SETTINGS["MESSAGE_TYPE"]).strip().lower() == "post":
            title, content = format_post_report(
                issues,
                SETTINGS["REPORT_PROJECT_KEYS"],
                top_n=int(SETTINGS["REPORT_TOP_N"]),
                base_url_for_links=(SETTINGS["JIRA_BASE_URL"] if SETTINGS["ENABLE_LINKS"] else None),
                assignee_field_path=SETTINGS["ASSIGNEE_FIELD_PATH"],
                env_field_path=SETTINGS["ENV_FIELD_PATH"],
                row_prefix_emoji=SETTINGS["ROW_PREFIX_EMOJI"],
                count_emoji=SETTINGS["COUNT_EMOJI"],
                AT_ASSIGNEE_PLAIN=SETTINGS["AT_ASSIGNEE_PLAIN"],
            )
            if SETTINGS.get("AT_ASSIGNEE_MENTION"):
                qa_map = _get_qa_map(SETTINGS.get("QA_MAP_PATH", "qa_map.json"))
                names = _collect_top_assignees_by_counts(issues, SETTINGS["ASSIGNEE_FIELD_PATH"], int(SETTINGS.get("AT_TOP_LIMIT", 10)))
                user_ids: List[str] = []
                for n in names:
                    uid = qa_map.get(n)
                    if uid and uid not in user_ids:
                        user_ids.append(uid)
                if user_ids:
                    content.insert(1, [{"tag": "text", "text": "请相关方及时跟进 Please kindly follow up in time："}] + [{"tag": "at", "user_id": uid} for uid in user_ids])
            resp = lark.send_post_content(title, content)
            logger.info("Lark响应: %s", resp)
        else:
            title = _today_title("Micro SIT Pending Open Bugs(Daily Push)", SETTINGS.get("TIMEZONE", "Asia/Shanghai"))
            card = build_interactive_card(
                issues,
                title,
                base_url_for_links=(SETTINGS["JIRA_BASE_URL"] if SETTINGS["ENABLE_LINKS"] else None),
                assignee_field_path=SETTINGS["ASSIGNEE_FIELD_PATH"],
                env_field_path=SETTINGS["ENV_FIELD_PATH"],
                count_emoji=SETTINGS["COUNT_EMOJI"],
                row_prefix_emoji=SETTINGS["ROW_PREFIX_EMOJI"],
                show_limit=int(SETTINGS["SHOW_LIMIT"]),
                jira_base_url=SETTINGS["JIRA_BASE_URL"],
                jql=SETTINGS["REPORT_JQL"],
                layout=SETTINGS["CARD_LAYOUT"],
                key_emoji=SETTINGS["KEY_EMOJI"],
                env_emoji=SETTINGS["ENV_EMOJI"],
                qa_emoji=SETTINGS["QA_EMOJI"],
                priority_emoji=SETTINGS["PRIORITY_EMOJI"],
                summary_emoji=SETTINGS["SUMMARY_EMOJI"],
                link_emoji=SETTINGS["LINK_EMOJI"],
                target_tz=SETTINGS["TIMEZONE"],
            )
            resp = lark.send_interactive_card(card)
            logger.info("Lark响应: %s", resp)
            if SETTINGS.get("AT_ASSIGNEE_MENTION"):
                _send_mentions(lark, issues, SETTINGS["ASSIGNEE_FIELD_PATH"], SETTINGS.get("QA_MAP_PATH", "qa_map.json"))
        logger.info("报告已推送，条目数=%s，类型=%s", len(issues), SETTINGS["MESSAGE_TYPE"])
    except Exception as e:
        print("Lark 推送失败: %s" % e, file=sys.stderr)

if __name__ == "__main__":
    try:
        run_job()
    except Exception as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
