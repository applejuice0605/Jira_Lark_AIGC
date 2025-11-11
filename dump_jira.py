import json
import logging
from typing import Dict, List

from config import load_config
from jira_client import JiraClient
from utils import setup_logger


def run_dump() -> None:
    config = load_config()
    setup_logger(level=config.log_level)
    logger = logging.getLogger(__name__)

    jira = JiraClient(
        config.jira_base_url,
        email=config.jira_email or None,
        api_token=config.jira_api_token or None,
        username=config.jira_username or None,
        password=config.jira_password or None,
        auth_method=config.auth_method,
        api_version=config.api_version,
    )

    logger.info("开始抓取 Jira 原始数据用于定位 Env 字段")
    try:
        fields_meta = jira.list_fields()
        logger.info("获取到字段元数据 %d 条", len(fields_meta))
    except Exception as e:
        logger.exception("获取字段元数据失败: %s", e)
        return

    try:
        issues = jira.search_issues(config.report_jql, max_results=min(config.max_results, 50))
        logger.info("获取到 issue %d 条（最多50条用于示例）", len(issues))
    except Exception as e:
        logger.exception("获取 Jira issues 失败: %s", e)
        return

    # 生成 id->name 映射
    id_to_name: Dict[str, str] = {}
    for f in fields_meta:
        fid = f.get("id")
        name = f.get("name")
        if isinstance(fid, str) and isinstance(name, str):
            id_to_name[fid] = name

    # 候选 Env 字段：名字包含 env 或 environment 的字段
    candidates = [
        (fid, name) for fid, name in id_to_name.items()
        if name and ("env" in name.lower() or "environment" in name.lower())
    ]

    # 准备导出内容
    dump = {
        "jql": config.report_jql,
        "fields_meta_count": len(fields_meta),
        "field_name_map_candidates": candidates,
        "issues_sample": issues[:3],  # 仅导出前三条完整数据，避免过大
    }

    with open("logs/jira_dump.json", "w", encoding="utf-8") as f:
        json.dump(dump, f, ensure_ascii=False, indent=2)
    logger.info("已导出 Jira 原始数据到 logs/jira_dump.json")

    # 在日志中打印候选 Env 字段及其在样例 issue 中是否有值
    if issues:
        fields = issues[0].get("fields", {})
        logger.info("样例 issue 的字段键数量: %d", len(fields.keys()))
        for fid, name in candidates:
            val = fields.get(fid)
            logger.info("候选 Env 字段: id=%s, name=%s, 示例值=%s", fid, name, val)


if __name__ == "__main__":
    run_dump()