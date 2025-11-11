from dataclasses import dataclass
import os
from dotenv import load_dotenv


@dataclass
class Config:
    jira_base_url: str
    jira_email: str
    jira_api_token: str
    jira_username: str
    jira_password: str
    auth_method: str
    api_version: str
    lark_webhook_url: str
    report_project_keys: list
    report_jql: str
    timezone: str
    report_cron: str
    log_level: str
    message_type: str
    report_top_n: int
    max_results: int
    enable_links: bool
    qa_field_path: str
    env_field_path: str
    row_prefix_emoji: str
    count_emoji: str
    at_qa_plain: bool
    at_qa_mention: bool
    qa_map_path: str
    card_layout: str
    key_emoji: str
    env_emoji: str
    qa_emoji: str
    priority_emoji: str
    summary_emoji: str
    link_emoji: str
    show_limit: int


def load_config() -> Config:
    load_dotenv()

    def get(name: str, default: str | None = None, required: bool = False) -> str:
        value = os.getenv(name, default)
        if required and not value:
            raise ValueError(f"Missing required environment variable: {name}")
        return value

    def get_int(name: str, default: int) -> int:
        raw = os.getenv(name)
        try:
            return int(raw) if raw is not None else default
        except Exception:
            return default

    def get_bool(name: str, default: bool) -> bool:
        raw = os.getenv(name)
        if raw is None:
            return default
        return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}

    keys_raw = get("REPORT_PROJECT_KEYS", "").strip()
    keys = [k.strip() for k in keys_raw.split(",") if k.strip()]

    auth_method = get("JIRA_AUTH_METHOD", "token").strip().lower()  # token 或 basic

    # 根据认证方式要求不同的必填项
    if auth_method == "basic":
        jira_username = get("JIRA_USERNAME", required=True)
        jira_password = get("JIRA_PASSWORD", required=True)
        jira_email = get("JIRA_EMAIL", "")  # 非必填
        jira_api_token = get("JIRA_API_TOKEN", "")  # 非必填
    else:
        jira_email = get("JIRA_EMAIL", required=True)
        jira_api_token = get("JIRA_API_TOKEN", required=True)
        jira_username = get("JIRA_USERNAME", "")
        jira_password = get("JIRA_PASSWORD", "")

    # Jira API 版本：Cloud 默认 3，自建 Server/DC 默认 2，可通过环境变量覆盖
    default_api_version = "2" if auth_method == "basic" else "3"
    api_version = get("JIRA_API_VERSION", default_api_version)

    return Config(
        jira_base_url=get("JIRA_BASE_URL", required=True),
        jira_email=jira_email,
        jira_api_token=jira_api_token,
        jira_username=jira_username,
        jira_password=jira_password,
        auth_method=auth_method,
        api_version=api_version,
        lark_webhook_url=get("LARK_WEBHOOK_URL", required=True),
        report_project_keys=keys,
        report_jql=get("REPORT_JQL", "updated >= -1d ORDER BY updated DESC"),
        timezone=get("TIMEZONE", "Asia/Shanghai"),
        report_cron=get("REPORT_CRON", "0 9 * * *"),
        log_level=get("LOG_LEVEL", "INFO"),
        message_type=get("MESSAGE_TYPE", "post"),
        report_top_n=get_int("REPORT_TOP_N", 10),
        max_results=get_int("MAX_RESULTS", 100),
        enable_links=get_bool("ENABLE_LINKS", True),
        qa_field_path=get("QA_FIELD_PATH", "assignee.displayName"),
        env_field_path=get("ENV_FIELD_PATH", ""),
        row_prefix_emoji=get("ROW_PREFIX_EMOJI", "🔹"),
        count_emoji=get("COUNT_EMOJI", "📌"),
        at_qa_plain=get_bool("AT_QA_PLAIN", False),
        at_qa_mention=get_bool("AT_QA_MENTION", False),
        qa_map_path=get("QA_MAP_PATH", "qa_map.json"),
        card_layout=get("CARD_LAYOUT", "two_columns"),
        key_emoji=get("KEY_EMOJI", "🏷️"),
        env_emoji=get("ENV_EMOJI", "🧪"),
        qa_emoji=get("QA_EMOJI", "👤"),
        priority_emoji=get("PRIORITY_EMOJI", "⚠️"),
        summary_emoji=get("SUMMARY_EMOJI", "📝"),
        link_emoji=get("LINK_EMOJI", "🔗"),
        show_limit=get_int("SHOW_LIMIT", 20),
    )