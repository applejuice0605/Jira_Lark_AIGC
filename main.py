import logging
import json
from config import load_config
from jira_client import JiraClient
from lark_client import LarkClient
from formatter import format_text_report, format_post_report
from card_main import build_interactive_card
from utils import setup_logger


def run_once() -> None:
    config = load_config()
    setup_logger(level=config.log_level)
    logger = logging.getLogger(__name__)

    logger.info("开始生成日报：jql=%s", config.report_jql)
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
        msg_type = config.message_type.lower()
        if msg_type == "post":
            title, content = format_post_report(
                issues,
                config.report_project_keys,
                top_n=config.report_top_n,
                base_url_for_links=(config.jira_base_url if config.enable_links else None),
                qa_field_path=config.qa_field_path,
                env_field_path=config.env_field_path,
                row_prefix_emoji=config.row_prefix_emoji,
                count_emoji=config.count_emoji,
                at_qa_plain=config.at_qa_plain,
            )
            resp = lark.send_post_content(title, content)
            logger.info("Lark响应: %s", resp)
        elif msg_type == "interactive":
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
            # Optional: send a Post message to @ QAs with real mentions
            try:
                if getattr(config, "at_qa_mention", False):
                    # Collect unique QA names and emails (fallback)
                    qa_names: set[str] = set()
                    qa_emails: set[str] = set()
                    for issue in issues:
                        fields = issue.get("fields") or {}
                        assignee = (fields.get("assignee") or {})
                        name = assignee.get("displayName") or ""
                        email = assignee.get("emailAddress") or ""
                        if not name:
                            # fallback to custom path
                            try:
                                from formatter import _get_by_path
                                name = _get_by_path(fields, config.qa_field_path)
                            except Exception:
                                name = ""
                        if name and name != "未指派":
                            qa_names.add(name)
                        if email:
                            qa_emails.add(email)
                    # Load mapping file (supports name->id or email->id)
                    mapping: dict[str, str] = {}
                    try:
                        with open(config.qa_map_path, "r", encoding="utf-8") as f:
                            mapping = json.load(f)
                    except FileNotFoundError:
                        logger.warning("QA映射文件未找到：%s，跳过 @ 提醒", config.qa_map_path)
                    except Exception as e:
                        logger.warning("读取 QA 映射失败：%s，跳过 @ 提醒", e)

                    user_ids: list[str] = []
                    # Try mapping by display name first
                    for name in sorted(qa_names):
                        uid = mapping.get(name)
                        if uid:
                            user_ids.append(uid)
                    # Fallback: map by emails
                    for email in sorted(qa_emails):
                        uid = mapping.get(email)
                        if uid:
                            user_ids.append(uid)
                    # Deduplicate while preserving order
                    seen = set()
                    user_ids = [u for u in user_ids if not (u in seen or seen.add(u))]

                    if user_ids:
                        content_row: list[dict] = [{"tag": "text", "text": "涉及人员："}]
                        content_row.extend([{"tag": "at", "user_id": uid} for uid in user_ids])
                        post_content: list[list[dict]] = [content_row]
                        resp_at = lark.send_post_content("今日涉及人员提醒", post_content)
                        logger.info("@QAs Post 响应: %s", resp_at)
                    else:
                        # Fallback: send plain @ if configured
                        if getattr(config, "at_qa_plain", False) and qa_names:
                            # Compose a text with plain @names
                            plain_line = "涉及人员：" + " ".join([f"@{n}" for n in sorted(qa_names)])
                            content = [[{"tag": "text", "text": plain_line}]]
                            resp_plain = lark.send_post_content("今日涉及人员提醒(纯文本)", content)
                            logger.info("@QAs 纯文本 Post 响应: %s", resp_plain)
                        else:
                            logger.info("无可用的 QA 映射，且未启用纯文本 @，未发送提醒。")
            except Exception as e:
                logger.warning("发送 @QAs 提醒失败：%s", e)
        else:
            message = format_text_report(issues)
            resp = lark.send_text(message)
            logger.info("Lark响应: %s", resp)
        logger.info("报告已推送，条目数=%s，类型=%s", len(issues), config.message_type)
    except Exception as e:
        logger.exception("推送飞书消息失败: %s", e)


if __name__ == "__main__":
    run_once()