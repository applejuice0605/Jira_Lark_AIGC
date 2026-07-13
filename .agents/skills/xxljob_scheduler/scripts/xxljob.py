import logging
import sys
import time
from typing import Dict, Any, List
import requests
from datetime import datetime
import pytz
from urllib.parse import quote_plus

# 尝试加载 .env 配置文件
try:
    from dotenv import load_dotenv
    # 优先加载当前工作目录下的 .env
    load_dotenv()
    # 兼容从技能安装目录下（.agents/skills/xxljob_scheduler/）加载 .env
    script_dir = os.path.dirname(os.path.abspath(__file__))
    skill_dir = os.path.dirname(script_dir)
    skill_env = os.path.join(skill_dir, ".env")
    if os.path.exists(skill_env):
        load_dotenv(skill_env, override=True)
except ImportError:
    pass


def _today_title(base_title: str, tz_name: str) -> str:
    try:
        tz = pytz.timezone(tz_name)
        dt = datetime.now(tz)
    except Exception:
        dt = datetime.now()
    return f"{dt.strftime('%Y-%m-%d')} {base_title}"

# 基于python3已上版本, 卡片推送带icon
SETTINGS: Dict[str, Any] = {
    "JIRA_BASE_URL": "https://rd-project.fuseinsurtech.com",
    "JIRA_USERNAME": "huxuesong",
    "JIRA_PASSWORD": "Qq12345678=",
    "LARK_WEBHOOK_URL": "https://open.larksuite.com/open-apis/bot/v2/hook/addf0fe2-d59a-4797-beff-ea836606e398",
    "REPORT_PROJECT_KEYS": ["CS"],
    "REPORT_JQL": "project = CS AND issuetype = Bug AND status in (Open, Resolved) AND Env in (UAT, SIT) AND created >= 2025-01-01 AND created <= 2029-12-31",
    "TIMEZONE": "Asia/Shanghai",
    "LOG_LEVEL": "INFO",
    "MESSAGE_TYPE": "interactive",
    "REPORT_TOP_N": 10,
    "MAX_RESULTS": 100,
    "ENABLE_LINKS": True,
    "QA_FIELD_PATH": "reporter.displayName",
    "ENV_FIELD_PATH": "customfield_10701.value",
    "ROW_PREFIX_EMOJI": "\U0001F539",
    "COUNT_EMOJI": "\U0001F4CC",
    "AT_QA_PLAIN": False,
    "AT_QA_MENTION": False,
    "QA_MAP_PATH": "qa_map.json",
    "CARD_LAYOUT": "single_column",
    "KEY_EMOJI": "\U0001F517",
    "ENV_EMOJI": "\U0001F310",
    "QA_EMOJI": "\U0001F464",
    "PRIORITY_EMOJI": "\U0001F6A9",
    "SUMMARY_EMOJI": "\U0001F4DD",
    "LINK_EMOJI": "\U0001F517",
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
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.handlers = []
    logger.addHandler(ch)
    fh = logging.FileHandler(os.path.join("logs", "app.log"), encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    return logger

class JiraClient:
    def __init__(self, base_url: str, username: str | None = None, password: str | None = None, api_version: str = "2") -> None:
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        self.api_version = (api_version or "2").strip()
        self.session.auth = (username or "", password or "")

    def search_issues(self, jql: str, max_results: int = 50, retries: int = 3) -> List[dict]:
        url = f"{self.base_url}/rest/api/{self.api_version}/search"
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

    def _post(self, payload: dict, retries: int = 3, backoff_sec: float = 1.0) -> dict:
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

    def send_text(self, text: str) -> dict:
        payload = {"msg_type": "text", "content": {"text": text}}
        return self._post(payload)

    def send_post_content(self, title: str, content: List[List[dict]]) -> dict:
        payload = {"msg_type": "post", "content": {"post": {"zh_cn": {"title": title, "content": content}}}}
        return self._post(payload)

    def send_interactive_card(self, card: dict) -> dict:
        payload = {"msg_type": "interactive", "card": card}
        return self._post(payload)

def _get_by_path(fields: dict, path: str) -> str:
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

def _priority_rank(name: str | None) -> int:
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

def _created_sort_val(created: str | None) -> float:
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

def _summarize_by_custom_field(issues: List[dict], field_path: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for issue in issues:
        fields = issue.get("fields") or {}
        val = _get_by_path(fields, field_path) if field_path else ""
        name = val or "Unassigned"
        counts[name] = counts.get(name, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: (-x[1], x[0])))

def format_post_report(issues: List[dict], project_keys: List[str] | None = None, top_n: int = 10, base_url_for_links: str | None = None, qa_field_path: str = "assignee.displayName", env_field_path: str = "", row_prefix_emoji: str = "-", count_emoji: str = "COUNT", at_qa_plain: bool = False) -> tuple[str, List[List[dict]]]:
    total = len(issues)
    title = _today_title("SIT/UAT Pending Resolved Bugs(Daily Push)", SETTINGS.get("TIMEZONE", "Asia/Shanghai"))
    content: List[List[dict]] = [[{"tag": "text", "text": f"{count_emoji} 【待更新数量 Pending update amount】：{total}\n"}]]
    qa_counts = _summarize_by_custom_field(issues, qa_field_path)
    top_qas = list(qa_counts.items())[:10]
    if top_qas:
        top_line = "\U0001F3C6 TOP QA PIC：" + ", ".join([f"{name}:{cnt}" for name, cnt in top_qas])
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
        qa_val = _get_by_path(fields, qa_field_path)
        priority = _get_by_path(fields, "priority.name")
        env_val = _get_by_path(fields, env_field_path)
        summary = fields.get("summary", "")
        elements: List[dict] = []
        prefix = f"{row_prefix_emoji} " if row_prefix_emoji else "- "
        if base_url_for_links and key:
            elements.append({"tag": "text", "text": prefix})
            elements.append({"tag": "a", "text": key, "href": f"{base_url_for_links.rstrip('/')}/browse/{key}"})
        else:
            elements.append({"tag": "text", "text": f"{prefix}{key}"})
        if env_val:
            elements.append({"tag": "text", "text": f" {env_val}"})
        if qa_val:
            elements.append({"tag": "text", "text": f" [{qa_val}]"})
            if at_qa_plain:
                elements.append({"tag": "text", "text": f" @{qa_val}"})
        else:
            elements.append({"tag": "text", "text": " [Unassigned]"})
        tail = " " + " ".join([v for v in [priority, summary] if v])
        if tail.strip():
            elements.append({"tag": "text", "text": tail})
        content.append(elements)
    return title, content

def _format_created(created: str, tz_name: str | None = None) -> str:
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

def build_interactive_card(issues: List[dict], title: str, base_url_for_links: str | None, qa_field_path: str, env_field_path: str, count_emoji: str, row_prefix_emoji: str, show_limit: int, jira_base_url: str, jql: str, layout: str, key_emoji: str, env_emoji: str, qa_emoji: str, priority_emoji: str, summary_emoji: str, link_emoji: str, target_tz: str) -> dict:
    total = len(issues)
    card: Dict = {"config": {"wide_screen_mode": True}, "header": {"title": {"tag": "plain_text", "content": title}}, "elements": []}
    elements = card["elements"]
    overview = f"{count_emoji} 【待更新数量 Pending update amount】：{total}"
    elements.append({"tag": "div", "text": {"tag": "lark_md", "content": overview}})
    qa_counts = _summarize_by_custom_field(issues, qa_field_path)
    top_qas = list(qa_counts.items())[:10]
    if top_qas:
        top_line = "\U0001F3C6 TOP QA PIC：" + ", ".join([f"{name}:{cnt}" for name, cnt in top_qas])
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
        qa_val = _get_by_path(fields, qa_field_path) or "Unassigned"
        env_val = _get_by_path(fields, env_field_path)
        priority = _get_by_path(fields, "priority.name")
        summary = fields.get("summary", "")
        created = fields.get("created", "")
        created_fmt = _format_created(created, target_tz)
        if base_url_for_links and key:
            key_md = f"{row_prefix_emoji} **Key**: {link_emoji} [{key}]({base_url_for_links.rstrip('/')}/browse/{key})"
        else:
            key_md = f"{row_prefix_emoji} **Key**: {key}"
        left_lines = [key_md]
        if env_val:
            left_lines.append(f"{env_emoji} **Env**: {env_val}")
        right_lines = [f"{qa_emoji} **QAs**: {qa_val}"]
        if priority:
            right_lines.append(f"{priority_emoji} **Priority**: {priority}")
        if layout == "single_column":
            lines = []
            lines.extend(left_lines)
            lines.extend(right_lines)
            if created_fmt:
                lines.append(f"\U0001F552 **Created**: {created_fmt}")
            if summary:
                lines.append(f"{summary_emoji} {summary}")
            elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(lines)}})
        elif layout == "three_columns":
            fields_block = {"tag": "div", "fields": [{"is_short": True, "text": {"tag": "lark_md", "content": "\n".join(left_lines)}}, {"is_short": True, "text": {"tag": "lark_md", "content": "\n".join(right_lines)}}, {"is_short": True, "text": {"tag": "lark_md", "content": f"\U0001F552 **Created**: {created_fmt}"}}]}
            elements.append(fields_block)
            if summary:
                elements.append({"tag": "note", "elements": [{"tag": "plain_text", "content": f"{summary_emoji} {summary}"}]})
        else:
            elements.append({"tag": "div", "fields": [{"is_short": True, "text": {"tag": "lark_md", "content": "\n".join(left_lines)}}, {"is_short": True, "text": {"tag": "lark_md", "content": "\n".join(right_lines + ([f"\U0001F552 **Created**: {created_fmt}"] if created_fmt else []))}}]})
            if summary:
                elements.append({"tag": "note", "elements": [{"tag": "plain_text", "content": f"{summary_emoji} {summary}"}]})
    if hidden_count > 0:
        elements.append({"tag": "hr"})
        tip = f"Remaining {hidden_count} items collapsed"
        if jira_base_url and jql:
            jql_url = f"{jira_base_url.rstrip('/')}/issues/?jql={quote_plus(jql)}"
            tip = tip + f", [View All]({jql_url})"
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": f"\u2139\ufe0f {tip}"}})
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
        print(f"Jira 请求失败: {e}", file=sys.stderr)
        return

    webhook = SETTINGS.get("LARK_WEBHOOK_URL", "").strip()
    if not webhook:
        print(f"未配置 LARK_WEBHOOK_URL，打印到控制台，条目数={len(issues)}")
        if SETTINGS["MESSAGE_TYPE"].strip().lower() == "post":
            title, content = format_post_report(
                issues,
                SETTINGS["REPORT_PROJECT_KEYS"],
                top_n=int(SETTINGS["REPORT_TOP_N"]),
                base_url_for_links=(SETTINGS["JIRA_BASE_URL"] if SETTINGS["ENABLE_LINKS"] else None),
                qa_field_path=SETTINGS["QA_FIELD_PATH"],
                env_field_path=SETTINGS["ENV_FIELD_PATH"],
                row_prefix_emoji=SETTINGS["ROW_PREFIX_EMOJI"],
                count_emoji=SETTINGS["COUNT_EMOJI"],
                at_qa_plain=SETTINGS["AT_QA_PLAIN"],
            )
            print(title)
            for block in content:
                for elem in block:
                    if "text" in elem:
                        print(elem["text"])
        else:
            title = _today_title("SIT/UAT Pending Resolved Bugs(Daily Push)", SETTINGS["TIMEZONE"])
            card = build_interactive_card(
                issues,
                title,
                base_url_for_links=(SETTINGS["JIRA_BASE_URL"] if SETTINGS["ENABLE_LINKS"] else None),
                qa_field_path=SETTINGS["QA_FIELD_PATH"],
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
        if SETTINGS["MESSAGE_TYPE"].strip().lower() == "post":
            title, content = format_post_report(
                issues,
                SETTINGS["REPORT_PROJECT_KEYS"],
                top_n=int(SETTINGS["REPORT_TOP_N"]),
                base_url_for_links=(SETTINGS["JIRA_BASE_URL"] if SETTINGS["ENABLE_LINKS"] else None),
                qa_field_path=SETTINGS["QA_FIELD_PATH"],
                env_field_path=SETTINGS["ENV_FIELD_PATH"],
                row_prefix_emoji=SETTINGS["ROW_PREFIX_EMOJI"],
                count_emoji=SETTINGS["COUNT_EMOJI"],
                at_qa_plain=SETTINGS["AT_QA_PLAIN"],
            )
            resp = lark.send_post_content(title, content)
            logger.info("Lark响应: %s", resp)
        else:
            title = _today_title("SIT/UAT Pending Resolved Bugs(Daily Push)", SETTINGS["TIMEZONE"])
            card = build_interactive_card(
                issues,
                title,
                base_url_for_links=(SETTINGS["JIRA_BASE_URL"] if SETTINGS["ENABLE_LINKS"] else None),
                qa_field_path=SETTINGS["QA_FIELD_PATH"],
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
        logger.info("报告已推送，条目数=%s，类型=%s", len(issues), SETTINGS["MESSAGE_TYPE"])
    except Exception as e:
        print(f"Lark 推送失败: {e}", file=sys.stderr)

if __name__ == "__main__":
    try:
        run_job()
    except Exception as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)