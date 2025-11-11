import logging
from typing import List, Dict, Tuple
from urllib.parse import quote_plus

from config import load_config
from jira_client import JiraClient
from lark_client import LarkClient
from utils import setup_logger
from formatter import _get_by_path, _summarize_by_custom_field
from datetime import datetime
import re
import pytz


def _format_created(created: str, tz_name: str | None = None) -> str:
    """Format Jira created time to 'YYYY-MM-DD HH:MM:SS' with optional timezone conversion.

    Known Jira formats:
    - 2025-11-08T09:24:46.123+0800
    - 2025-11-08T09:24:46+0800
    - 2025-11-08T09:24:46.123 (no tz)
    - 2025-11-08T09:24:46 (no tz)
    If parsing fails, return original string.
    """
    if not created:
        return ""
    target_tz = None
    if tz_name:
        try:
            target_tz = pytz.timezone(tz_name)
        except Exception:
            target_tz = None
    # Formats with explicit timezone
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            dt = datetime.strptime(created, fmt)
            if target_tz:
                dt = dt.astimezone(target_tz)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass
    # Formats without timezone: assume UTC then convert if target_tz
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


def _priority_rank(name: str | None) -> int:
    """Map priority name to order: P0<P1<P2<P3, unknown last."""
    if not name:
        return 999
    n = str(name).strip().upper()
    mapping = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    if n in mapping:
        return mapping[n]
    # Try to parse patterns like 'P2 - High'
    m = re.search(r"\bP(\d)\b", n)
    if m:
        try:
            v = int(m.group(1))
            return v
        except Exception:
            pass
    # Common Jira synonyms
    synonyms = {"HIGHEST": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    if n in synonyms:
        return synonyms[n]
    return 999


def _created_sort_val(created: str | None) -> float:
    """Return a sortable timestamp for created time; unknown goes last."""
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
            # Assume UTC for naive timestamps
            dt = pytz.utc.localize(naive)
            return dt.timestamp()
        except Exception:
            pass
    return float("inf")


def build_interactive_card(
    issues: List[Dict],
    title: str,
    base_url_for_links: str | None,
    qa_field_path: str,
    env_field_path: str,
    count_emoji: str,
    row_prefix_emoji: str,
    show_limit: int = 20,
    jira_base_url: str | None = None,
    jql: str | None = None,
    layout: str = "two_columns",
    key_emoji: str = "🏷️",
    env_emoji: str = "🧪",
    qa_emoji: str = "👤",
    priority_emoji: str = "⚠️",
    summary_emoji: str = "📝",
    link_emoji: str = "🔗",
    target_tz: str | None = None,
) -> Dict:
    total = len(issues)

    # Header
    card: Dict = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": title},
        },
        "elements": [],
    }

    elements = card["elements"]

    # Overview count
    overview = f"{count_emoji} 【待更新数量 Pending update amount】：{total}"
    elements.append({"tag": "div", "text": {"tag": "lark_md", "content": overview}})

    # QA Top（加 emoji 更醒目）
    qa_counts = _summarize_by_custom_field(issues, qa_field_path)
    top_qas = list(qa_counts.items())[:10]
    if top_qas:
        top_line = "🏆 TOP QA PIC：" + ", ".join([f"{name}:{cnt}" for name, cnt in top_qas])
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": top_line}})

    elements.append({"tag": "hr"})

    # Issue list：按 Priority(P0→P1→P2→P3) 优先，再按创建时间升序，超过 show_limit 折叠
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
        qa_val = _get_by_path(fields, qa_field_path) or "未指派"
        env_val = _get_by_path(fields, env_field_path)
        priority = _get_by_path(fields, "priority.name")
        summary = fields.get("summary", "")
        created = fields.get("created", "")
        created_fmt = _format_created(created, target_tz)

        # Left column: Key link + Env
        if base_url_for_links and key:
            # Key 前只保留行前缀 🔹，链接前加 🔗
            key_md = f"{row_prefix_emoji} **Key**: {link_emoji} [{key}]({base_url_for_links.rstrip('/')}/browse/{key})"
        else:
            key_md = f"{row_prefix_emoji} **Key**: {key}"
        left_lines = [key_md]
        if env_val:
            left_lines.append(f"{env_emoji} **Env**: {env_val}")

        # Right column: QAs + Priority
        right_lines = [f"{qa_emoji} **QAs**: {qa_val}"]
        if priority:
            right_lines.append(f"{priority_emoji} **Priority**: {priority}")

        if layout == "single_column":
            # 单列：所有字段整合为一个 markdown 段落
            lines = []
            lines.extend(left_lines)
            lines.extend(right_lines)
            if created_fmt:
                lines.append(f"🕒 **Created**: {created_fmt}")
            if summary:
                lines.append(f"{summary_emoji} {summary}")
            elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(lines)}})
        elif layout == "three_columns":
            # 三列（注意卡片字段通常两列一行，第三列会自动换行显示）
            fields_block = {
                "tag": "div",
                "fields": [
                    {"is_short": True, "text": {"tag": "lark_md", "content": "\n".join(left_lines)}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": "\n".join(right_lines)}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"🕒 **Created**: {created_fmt}"}},
                ],
            }
            elements.append(fields_block)
            if summary:
                elements.append({"tag": "note", "elements": [{"tag": "plain_text", "content": f"{summary_emoji} {summary}"}]})
        else:
            # 默认两列布局
            elements.append(
                {
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": True,
                            "text": {"tag": "lark_md", "content": "\n".join(left_lines)},
                        },
                        {
                            "is_short": True,
                            "text": {"tag": "lark_md", "content": "\n".join(right_lines + ([f"🕒 **Created**: {created_fmt}"] if created_fmt else []))},
                        },
                    ],
                }
            )
            if summary:
                elements.append({"tag": "note", "elements": [{"tag": "plain_text", "content": f"{summary_emoji} {summary}"}]})

    # 折叠提示与“查看全部”链接（英文文案）
    if hidden_count > 0:
        elements.append({"tag": "hr"})
        tip = f"Remaining {hidden_count} items collapsed"
        if jira_base_url and jql:
            # 构造查看全部链接到 Jira 搜索页
            jql_url = f"{jira_base_url.rstrip('/')}/issues/?jql={quote_plus(jql)}"
            tip = tip + f", [View All]({jql_url})"
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": f"ℹ️ {tip}"}})

    return card


def run_once_card() -> None:
    config = load_config()
    setup_logger(level=config.log_level)
    logger = logging.getLogger(__name__)

    logger.info("开始生成交互卡片：jql=%s", config.report_jql)
    jira = JiraClient(
        config.jira_base_url,
        email=config.jira_email or None,
        api_token=config.jira_api_token or None,
        username=config.jira_username or None,
        password=config.jira_password or None,
        auth_method=config.auth_method,
        api_version=config.api_version,
    )

    try:
        issues = jira.search_issues(config.report_jql, max_results=config.max_results)
        logger.info("从 Jira 获取到 %d 条结果", len(issues))
    except Exception as e:
        logger.exception("获取 Jira 数据失败: %s", e)
        return

    lark = LarkClient(config.lark_webhook_url)

    try:
        title = "Pending Resolved Bugs(Daily Push)"
        card = build_interactive_card(
            issues,
            title,
            base_url_for_links=(config.jira_base_url if config.enable_links else None),
            qa_field_path=config.qa_field_path,
            env_field_path=config.env_field_path,
            count_emoji=config.count_emoji,
            row_prefix_emoji=config.row_prefix_emoji,
            show_limit=config.show_limit,
            jira_base_url=config.jira_base_url,
            jql=config.report_jql,
            layout=config.card_layout,
            key_emoji=config.key_emoji,
            env_emoji=config.env_emoji,
            qa_emoji=config.qa_emoji,
            priority_emoji=config.priority_emoji,
            summary_emoji=config.summary_emoji,
            link_emoji=config.link_emoji,
            target_tz=config.timezone,
        )
        resp = lark.send_interactive_card(card)
        logger.info("Lark响应: %s", resp)
        logger.info("交互卡片已推送，条目数=%s", len(issues))
    except Exception as e:
        logger.exception("推送交互卡片失败: %s", e)


if __name__ == "__main__":
    run_once_card()