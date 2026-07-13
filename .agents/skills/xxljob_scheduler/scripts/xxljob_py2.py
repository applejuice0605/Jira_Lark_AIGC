# -*- coding: utf-8 -*-
from __future__ import print_function
import logging
import sys
import time
import os
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

import requests
from datetime import datetime
import pytz
try:
    from urllib.parse import quote_plus
except Exception:
    from urllib import quote_plus

# 基于python2版本, 卡片推送不带icon
SETTINGS = {
    "JIRA_BASE_URL": "https://rd-project.fuseinsurtech.com",
    "JIRA_USERNAME": "huxuesong",
    "JIRA_PASSWORD": "Qq12345678=",
    "LARK_WEBHOOK_URL": "https://open.larksuite.com/open-apis/bot/v2/hook/addf0fe2-d59a-4797-beff-ea836606e398",
    "REPORT_PROJECT_KEYS": ["CS"],
    "REPORT_JQL": "project = CS AND issuetype = Bug AND status = Resolved AND Env in (SIT, UAT)",
    "TIMEZONE": "Asia/Shanghai",
    "LOG_LEVEL": "INFO",
    "MESSAGE_TYPE": "interactive",
    "REPORT_TOP_N": 10,
    "MAX_RESULTS": 100,
    "ENABLE_LINKS": True,
    "QA_FIELD_PATH": "reporter.displayName",
    "ENV_FIELD_PATH": "customfield_10701.value",
    "ROW_PREFIX_EMOJI": "-",
    "COUNT_EMOJI": "COUNT",
    "AT_QA_PLAIN": False,
    "AT_QA_MENTION": False,
    "QA_MAP_PATH": "qa_map.json",
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


def _today_title(base_title, tz_name):
    try:
        tz = pytz.timezone(tz_name)
        dt = datetime.now(tz)
    except Exception:
        dt = datetime.now()
    return "%s %s" % (dt.strftime('%Y-%m-%d'), base_title)

def setup_logger(level):
    try:
        os.makedirs("logs")
    except Exception:
        pass
    logger = logging.getLogger()
    logger.setLevel(level)
    fmt = logging.Formatter("%Y-%m-%d %H:%M:%S %(levelname)s %(name)s: %(message)s")
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.handlers = []
    logger.addHandler(ch)
    try:
        fh = logging.FileHandler(os.path.join("logs", "app.log"))
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except Exception:
        pass
    return logger

class JiraClient(object):
    def __init__(self, base_url, username=None, password=None, api_version="2"):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        self.api_version = (api_version or "2").strip()
        self.session.auth = (username or "", password or "")

    def search_issues(self, jql, max_results=50, retries=3):
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

class LarkClient(object):
    def __init__(self, webhook_url):
        self.webhook_url = webhook_url

    def _post(self, payload, retries=3, backoff_sec=1.0):
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

    def send_text(self, text):
        payload = {"msg_type": "text", "content": {"text": text}}
        return self._post(payload)

    def send_post_content(self, title, content):
        payload = {"msg_type": "post", "content": {"post": {"zh_cn": {"title": title, "content": content}}}}
        return self._post(payload)

    def send_interactive_card(self, card):
        payload = {"msg_type": "interactive", "card": card}
        return self._post(payload)

def _get_by_path(fields, path):
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

def _priority_rank(name):
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

def _created_sort_val(created):
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

def _summarize_by_custom_field(issues, field_path):
    counts = {}
    for issue in issues:
        fields = issue.get("fields") or {}
        val = _get_by_path(fields, field_path) if field_path else ""
        name = val or "Unassigned"
        counts[name] = counts.get(name, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: (-x[1], x[0])))

def format_post_report(issues, project_keys=None, top_n=10, base_url_for_links=None, qa_field_path="assignee.displayName", env_field_path="", row_prefix_emoji="-", count_emoji="COUNT", at_qa_plain=False):
    total = len(issues)
    title = _today_title("SIT/UAT Pending Resolved Bugs(Daily Push)", SETTINGS.get("TIMEZONE", "Asia/Shanghai"))
    content = [[{"tag": "text", "text": "%s Pending update amount: %d\n" % (count_emoji, total)}]]
    qa_counts = _summarize_by_custom_field(issues, qa_field_path)
    top_qas = list(qa_counts.items())[:10]
    if top_qas:
        top_line = "TOP QA PIC: " + ", ".join(["%s:%d" % (name, cnt) for name, cnt in top_qas])
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
        elements = []
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
            if at_qa_plain:
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

def _format_created(created, tz_name=None):
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

def build_interactive_card(issues, title, base_url_for_links, qa_field_path, env_field_path, count_emoji, row_prefix_emoji, show_limit, jira_base_url, jql, layout, key_emoji, env_emoji, qa_emoji, priority_emoji, summary_emoji, link_emoji, target_tz):
    total = len(issues)
    card = {"config": {"wide_screen_mode": True}, "header": {"title": {"tag": "plain_text", "content": title}}, "elements": []}
    elements = card["elements"]
    overview = "%s Pending update amount: %d" % (count_emoji, total)
    elements.append({"tag": "div", "text": {"tag": "lark_md", "content": overview}})
    qa_counts = _summarize_by_custom_field(issues, qa_field_path)
    top_qas = list(qa_counts.items())[:10]
    if top_qas:
        top_line = "TOP QA PIC: " + ", ".join(["%s:%d" % (name, cnt) for name, cnt in top_qas])
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
            key_md = "%s **Key**: %s [%s](%s/browse/%s)" % (row_prefix_emoji, link_emoji, key, base_url_for_links.rstrip('/'), key)
        else:
            key_md = "%s **Key**: %s" % (row_prefix_emoji, key)
        left_lines = [key_md]
        if env_val:
            left_lines.append("%s **Env**: %s" % (env_emoji, env_val))
        right_lines = ["%s **QAs**: %s" % (qa_emoji, qa_val)]
        if priority:
            right_lines.append("%s **Priority**: %s" % (priority_emoji, priority))
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

def run_job():
    setup_logger(level=SETTINGS.get("LOG_LEVEL", "INFO"))
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
    logger.info("Start report: jql=%s", SETTINGS.get("REPORT_JQL", ""))
    try:
        jira = JiraClient(
            SETTINGS.get("JIRA_BASE_URL", ""),
            username=SETTINGS.get("JIRA_USERNAME"),
            password=SETTINGS.get("JIRA_PASSWORD"),
            api_version=api_version,
        )
        issues = jira.search_issues(SETTINGS.get("REPORT_JQL", ""), max_results=int(SETTINGS.get("MAX_RESULTS", 100)))
        logger.info("Fetched %d issues from Jira", len(issues))
    except Exception as e:
        print("Jira request failed: %s" % e, file=sys.stderr)
        return

    webhook = str(SETTINGS.get("LARK_WEBHOOK_URL", "")).strip()
    if not webhook:
        print("LARK_WEBHOOK_URL not set, printing to console; count=%d" % len(issues))
        if str(SETTINGS.get("MESSAGE_TYPE", "post")).strip().lower() == "post":
            title, content = format_post_report(
                issues,
                SETTINGS.get("REPORT_PROJECT_KEYS", []),
                top_n=int(SETTINGS.get("REPORT_TOP_N", 10)),
                base_url_for_links=(SETTINGS.get("JIRA_BASE_URL") if SETTINGS.get("ENABLE_LINKS") else None),
                qa_field_path=SETTINGS.get("QA_FIELD_PATH", "assignee.displayName"),
                env_field_path=SETTINGS.get("ENV_FIELD_PATH", ""),
                row_prefix_emoji=SETTINGS.get("ROW_PREFIX_EMOJI", "-"),
                count_emoji=SETTINGS.get("COUNT_EMOJI", "COUNT"),
                at_qa_plain=SETTINGS.get("AT_QA_PLAIN", False),
            )
            print(title)
            for block in content:
                for elem in block:
                    if "text" in elem:
                        print(elem["text"])
        else:
            title = _today_title("SIT/UAT Pending Resolved Bugs(Daily Push)", SETTINGS.get("TIMEZONE", "Asia/Shanghai"))
            card = build_interactive_card(
                issues,
                title,
                base_url_for_links=(SETTINGS.get("JIRA_BASE_URL") if SETTINGS.get("ENABLE_LINKS") else None),
                qa_field_path=SETTINGS.get("QA_FIELD_PATH", "assignee.displayName"),
                env_field_path=SETTINGS.get("ENV_FIELD_PATH", ""),
                count_emoji=SETTINGS.get("COUNT_EMOJI", "COUNT"),
                row_prefix_emoji=SETTINGS.get("ROW_PREFIX_EMOJI", "-"),
                show_limit=int(SETTINGS.get("SHOW_LIMIT", 15)),
                jira_base_url=SETTINGS.get("JIRA_BASE_URL"),
                jql=SETTINGS.get("REPORT_JQL", ""),
                layout=SETTINGS.get("CARD_LAYOUT", "two_columns"),
                key_emoji=SETTINGS.get("KEY_EMOJI", "Key"),
                env_emoji=SETTINGS.get("ENV_EMOJI", "Env"),
                qa_emoji=SETTINGS.get("QA_EMOJI", "QAs"),
                priority_emoji=SETTINGS.get("PRIORITY_EMOJI", "Priority"),
                summary_emoji=SETTINGS.get("SUMMARY_EMOJI", "Summary"),
                link_emoji=SETTINGS.get("LINK_EMOJI", "Link"),
                target_tz=SETTINGS.get("TIMEZONE", "Asia/Shanghai"),
            )
            header = card.get("header", {}).get("title", {})
            if isinstance(header, dict):
                print(header.get("content", ""))
            for el in card.get("elements", []):
                content = el.get("text", {}).get("content")
                if isinstance(content, str):
                    print(content)
        return

    try:
        lark = LarkClient(webhook)
        if str(SETTINGS.get("MESSAGE_TYPE", "post")).strip().lower() == "post":
            title, content = format_post_report(
                issues,
                SETTINGS.get("REPORT_PROJECT_KEYS", []),
                top_n=int(SETTINGS.get("REPORT_TOP_N", 10)),
                base_url_for_links=(SETTINGS.get("JIRA_BASE_URL") if SETTINGS.get("ENABLE_LINKS") else None),
                qa_field_path=SETTINGS.get("QA_FIELD_PATH", "assignee.displayName"),
                env_field_path=SETTINGS.get("ENV_FIELD_PATH", ""),
                row_prefix_emoji=SETTINGS.get("ROW_PREFIX_EMOJI", "-"),
                count_emoji=SETTINGS.get("COUNT_EMOJI", "COUNT"),
                at_qa_plain=SETTINGS.get("AT_QA_PLAIN", False),
            )
            resp = lark.send_post_content(title, content)
            logger.info("Lark response: %s", resp)
        else:
            title = _today_title("SIT/UAT Pending Resolved Bugs(Daily Push)", SETTINGS.get("TIMEZONE", "Asia/Shanghai"))
            card = build_interactive_card(
                issues,
                title,
                base_url_for_links=(SETTINGS.get("JIRA_BASE_URL") if SETTINGS.get("ENABLE_LINKS") else None),
                qa_field_path=SETTINGS.get("QA_FIELD_PATH", "assignee.displayName"),
                env_field_path=SETTINGS.get("ENV_FIELD_PATH", ""),
                count_emoji=SETTINGS.get("COUNT_EMOJI", "COUNT"),
                row_prefix_emoji=SETTINGS.get("ROW_PREFIX_EMOJI", "-"),
                show_limit=int(SETTINGS.get("SHOW_LIMIT", 15)),
                jira_base_url=SETTINGS.get("JIRA_BASE_URL"),
                jql=SETTINGS.get("REPORT_JQL", ""),
                layout=SETTINGS.get("CARD_LAYOUT", "two_columns"),
                key_emoji=SETTINGS.get("KEY_EMOJI", "Key"),
                env_emoji=SETTINGS.get("ENV_EMOJI", "Env"),
                qa_emoji=SETTINGS.get("QA_EMOJI", "QAs"),
                priority_emoji=SETTINGS.get("PRIORITY_EMOJI", "Priority"),
                summary_emoji=SETTINGS.get("SUMMARY_EMOJI", "Summary"),
                link_emoji=SETTINGS.get("LINK_EMOJI", "Link"),
                target_tz=SETTINGS.get("TIMEZONE", "Asia/Shanghai"),
            )
            resp = lark.send_interactive_card(card)
            logger.info("Lark response: %s", resp)
        logger.info("Report pushed; count=%s; type=%s", len(issues), SETTINGS.get("MESSAGE_TYPE", "post"))
    except Exception as e:
        print("Lark push failed: %s" % e, file=sys.stderr)

if __name__ == "__main__":
    try:
        run_job()
    except Exception as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)