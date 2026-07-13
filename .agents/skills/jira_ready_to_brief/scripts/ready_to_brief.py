import logging
import sys
import time
from typing import Dict, Any, List, Optional, Set, Tuple
import json
import os
from datetime import datetime
from urllib.parse import quote_plus

import pytz
import requests

# 尝试加载 .env 配置文件
try:
    from dotenv import load_dotenv
    # 优先加载当前工作目录下的 .env
    load_dotenv()
    # 兼容从技能安装目录下（.agents/skills/jira_ready_to_brief/）加载 .env
    script_dir = os.path.dirname(os.path.abspath(__file__))
    skill_dir = os.path.dirname(script_dir)
    skill_env = os.path.join(skill_dir, ".env")
    if os.path.exists(skill_env):
        load_dotenv(skill_env, override=True)
except ImportError:
    pass

def _today_title(base_title: str, tz_name: str) -> str:
    """
    根据给定的时区生成包含当前日期的标题字符串。
    格式如：'2026-05-28 基础标题'。若解析时区失败，则降级使用本地系统时间。
    """
    try:
        tz = pytz.timezone(tz_name)
        dt = datetime.now(tz)
    except Exception:
        dt = datetime.now()
    return "%s %s" % (dt.strftime("%Y-%m-%d"), base_title)


# 全局配置字典，用于控制脚本的各项核心行为，包括：
# Jira 凭证、Lark Webhook 地址、查询 JQL、日志级别、人员映射以及各种格式化选项。
SETTINGS: Dict[str, Any] = {
    "JIRA_BASE_URL": "https://rd-project.fuseinsurtech.com",
    "JIRA_USERNAME": "huxuesong",
    "JIRA_PASSWORD": "Qq12345678=",
    "LARK_WEBHOOK_URL": "https://open.larksuite.com/open-apis/bot/v2/hook/868b9ee7-4a12-4032-88b1-c79ee08d5541",
    # 测试用
    # "LARK_WEBHOOK_URL": "https://open.larksuite.com/open-apis/bot/v2/hook/addf0fe2-d59a-4797-beff-ea836606e398",
    "REPORT_PROJECT_KEYS": ["CS", "MP"],
    "REPORT_JQL": 'project in (CS, MP) AND issuetype in (Story, Improvement) AND status = "Ready to Brief"',
    "FIX_VERSION": "AUTO",
    "DYNAMIC_VERSION_BOARD_ID": "1",
    "TIMEZONE": "Asia/Shanghai",
    "LOG_LEVEL": "INFO",
    "MESSAGE_TYPE": "interactive",
    # "MESSAGE_TYPE": "post",
    "REPORT_TOP_N": 10,
    "MAX_RESULTS": 100,
    "ENABLE_LINKS": True,
    "QA_FIELD_NAME": "QAs",
    "QA_FIELD_PATH": "AUTO",
    "ENABLE_APPROVAL_CHECK": True,
    "APPROVAL_API_PATH_TEMPLATE": "/rest/workflow-wise/latest/approval/issue-panel/{issue_id}/approval",
    "ONLY_MENTION_PENDING_QA": True,
    "ROW_PREFIX_EMOJI": "-",
    "COUNT_EMOJI": "COUNT",
    "AT_QA_PLAIN": False,
    "AT_QA_MENTION": True,
    "AT_TOP_LIMIT": 10,
    "QA_MAP_PATH": "qa_map.json",
    "QA_MAP_INLINE": {
        "Faris Harun Ahmad": "7556829471928516646",
        "Winda Natalia Sianipar": "7298201363240992774",
        "aaron": "6920048781270450182",
        "Nanda Caesar": "7280016497504747525",
        "吴维(Shirley)": "7050275950939865093",
        "蔡淑彬(Nora)": "7340092567356211205",
        "Muhammad Fandly Fadlurachman": "7290409388383191046",
        "胡雪松(Malcolm)": "7050282576732274694",
        "冯明明(Jerry)": "6943876384087343110",
        "Thikumporn Homeaw": "7556103654416072743",
        "Nguyen Tin": "7347529059997401094",
        "李飞(Bruce)": "6953542404913758214",
        "Atho Isnanthyo Abyan": "7300802997502656518",
    },
    "CARD_LAYOUT": "single_column",
    "KEY_EMOJI": "Key",
    "QA_EMOJI": "QAs",
    "PRIORITY_EMOJI": "Priority",
    "STATUS_EMOJI": "Status",
    "SUMMARY_EMOJI": "Summary",
    "LINK_EMOJI": "Link",
    "SHOW_LIMIT": 15,
}

# 优先读取系统环境变量覆盖默认设置（如 .env 加载的配置）
for key in ["JIRA_BASE_URL", "JIRA_USERNAME", "JIRA_PASSWORD", "LARK_WEBHOOK_URL"]:
    env_val = os.environ.get(key)
    if env_val:
        SETTINGS[key] = env_val.strip().strip('"').strip("'")


def _build_report_jql() -> str:
    """
    根据配置项动态构建用于查询 Jira 数据的 JQL 语句。
    会自动拼接上 FIX_VERSION 进行过滤。支持逗号分隔的多版本号。
    """
    base = str(SETTINGS.get("REPORT_JQL", "")).strip()
    fix_version = str(SETTINGS.get("FIX_VERSION", "")).strip()
    
    if fix_version:
        versions = [v.strip() for v in fix_version.split(",") if v.strip()]
        if len(versions) == 1:
            version_condition = 'fixVersion = "%s"' % versions[0]
        else:
            version_list_str = ", ".join('"%s"' % v for v in versions)
            version_condition = 'fixVersion in (%s)' % version_list_str
            
        if base:
            return '%s AND %s' % (base, version_condition)
        else:
            return version_condition
    return base

def _report_title() -> str:
    """
    根据是否有指定版本号，生成推送报告的基础标题名称。
    """
    fix_version = str(SETTINGS.get("FIX_VERSION", "")).strip()
    if fix_version:
        return "Ready to Brief Story/Improvement %s " % fix_version
    return "Ready to Brief Story/Improvement"


def setup_logger(level: str = "INFO") -> logging.Logger:
    """
    配置并初始化全局日志记录器。
    同时将日志输出到控制台和本地 `logs/app.log` 文件。
    """
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
    """
    Jira API 客户端，封装了与 Jira 交互的核心方法。
    包含：根据 JQL 搜索 Issue、获取字段列表、获取工作流审批状态面板等。
    """
    def __init__(self, base_url: str, username: Optional[str] = None, password: Optional[str] = None, api_version: str = "2") -> None:
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        self.api_version = (api_version or "2").strip()
        self.session.auth = (username or "", password or "")

    def search_issues(self, jql: str, max_results: int = 50, retries: int = 3) -> List[Dict[str, Any]]:
        """
        根据指定的 JQL 语句查询 Jira 问题列表。
        带有自动重试机制以应对网络抖动。
        """
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

    def get_fields(self, retries: int = 3) -> List[Dict[str, Any]]:
        """
        获取 Jira 系统中所有字段（Field）的定义信息。
        常用于将自定义字段名（如 QAs）反向解析为 customfield_xxx ID。
        """
        url = "%s/rest/api/%s/field" % (self.base_url, self.api_version)
        last_exc = None
        for attempt in range(1, retries + 1):
            try:
                resp = self.session.get(url, timeout=20)
                resp.raise_for_status()
                data = resp.json()
                return data if isinstance(data, list) else []
            except Exception as e:
                last_exc = e
                if attempt < retries:
                    time.sleep(1.0 * attempt)
        if last_exc:
            raise last_exc
        return []

    def get_approval_panel(self, issue_id: str, retries: int = 3) -> Dict[str, Any]:
        """
        调用 Workflow-wise Approval API 获取指定 Issue 的审批面板数据。
        用于判断 QA 是否已经点过了 Approve。
        """
        path_tpl = str(SETTINGS.get("APPROVAL_API_PATH_TEMPLATE", "")).strip() or "/rest/workflow-wise/latest/approval/issue-panel/{issue_id}/approval"
        url = "%s%s" % (self.base_url, path_tpl.format(issue_id=str(issue_id).strip()))
        last_exc = None
        for attempt in range(1, retries + 1):
            try:
                resp = self.session.get(url, timeout=20)
                resp.raise_for_status()
                data = resp.json()
                return data if isinstance(data, dict) else {}
            except Exception as e:
                last_exc = e
                if attempt < retries:
                    time.sleep(1.0 * attempt)
        if last_exc:
            raise last_exc
        return {}


class LarkClient:
    """
    飞书群机器人 Webhook 客户端，封装了各类消息类型的推送方法。
    """
    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url

    def _post(self, payload: Dict[str, Any], retries: int = 3, backoff_sec: float = 1.0) -> Dict[str, Any]:
        """
        底层 HTTP POST 请求封装，带有指数退避重试策略。
        """
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
        """推送普通文本消息"""
        payload = {"msg_type": "text", "content": {"text": text}}
        return self._post(payload)

    def send_post_content(self, title: str, content: List[List[Dict[str, Any]]]) -> Dict[str, Any]:
        """推送富文本（Post）消息"""
        payload = {"msg_type": "post", "content": {"post": {"zh_cn": {"title": title, "content": content}}}}
        return self._post(payload)

    def send_interactive_card(self, card: Dict[str, Any]) -> Dict[str, Any]:
        """推送交互式卡片（Interactive Card）消息"""
        payload = {"msg_type": "interactive", "card": card}
        return self._post(payload)


def _get_by_path(fields: Dict[str, Any], path: str) -> str:
    """
    通过点分路径（如 status.name）从嵌套字典中安全提取对应的值。
    如果遇到列表，则默认取第一个元素的属性。
    """
    if not path:
        return ""
    parts = [p for p in path.split(".") if p]
    cur: Any = fields
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

def _extract_display_names(val: Any) -> List[str]:
    """
    递归从多层嵌套结构（列表或字典）中提取人员的名字或显示名（displayName / name / value）。
    常用于处理 Jira 返回的多人字段数组。
    """
    if val is None:
        return []
    if isinstance(val, list):
        names: List[str] = []
        for item in val:
            names.extend(_extract_display_names(item))
        return names
    if isinstance(val, dict):
        for k in ("displayName", "name", "value"):
            v = val.get(k)
            if v is not None:
                s = str(v).strip()
                return [s] if s else []
        return []
    s = str(val).strip()
    return [s] if s else []


def _get_display_names_by_path(fields: Dict[str, Any], path: str) -> List[str]:
    """
    结合点分路径和显示名提取逻辑，从复杂字段（如 customfield_xxx）中获取去重后的名称列表。
    """
    if not path:
        return []
    parts = [p for p in path.split(".") if p]
    cur_items: List[Any] = [fields]
    for p in parts:
        next_items: List[Any] = []
        for cur in cur_items:
            if isinstance(cur, dict):
                next_items.append(cur.get(p))
            elif isinstance(cur, list):
                for item in cur:
                    if isinstance(item, dict):
                        next_items.append(item.get(p))
        cur_items = [x for x in next_items if x is not None]
        if not cur_items:
            return []
    names: List[str] = []
    for cur in cur_items:
        names.extend(_extract_display_names(cur))
    deduped: List[str] = []
    seen: Set[str] = set()
    for n in names:
        s = str(n).strip()
        if not s:
            continue
        if s not in seen:
            seen.add(s)
            deduped.append(s)
    return deduped


def _qa_display(fields: Dict[str, Any], qa_field_path: str) -> str:
    """
    辅助函数：通过指定路径从字段数据中提取出 QA 的显示名称，以逗号分隔返回。
    """
    names = _get_display_names_by_path(fields, qa_field_path)
    return ", ".join(names)

def _qa_display_for_issue(issue: Dict[str, Any], qa_field_path: str) -> str:
    """
    为单个 Issue 获取用于展示的 QA 人员字符串。
    优先读取已解析好并携带审批状态（如已 Approve）的缓存字段 `_qa_display`。
    """
    v = issue.get("_qa_display")
    if isinstance(v, str) and v.strip():
        return v
    fields = issue.get("fields") or {}
    return _qa_display(fields, qa_field_path)

def _get_issue_people_names(issue: Dict[str, Any], field_path: str) -> List[str]:
    """
    根据配置策略提取问题单中需要统计或艾特的人员名单列表。
    如果开启了 ONLY_MENTION_PENDING_QA，则只提取未 Approve 的 QA 名单。
    """
    if SETTINGS.get("ONLY_MENTION_PENDING_QA") and isinstance(issue.get("_qa_pending_names"), list):
        return [str(x).strip() for x in (issue.get("_qa_pending_names") or []) if str(x).strip()]
    if isinstance(issue.get("_qa_names"), list):
        return [str(x).strip() for x in (issue.get("_qa_names") or []) if str(x).strip()]
    fields = issue.get("fields") or {}
    return _get_display_names_by_path(fields, field_path) if field_path else []

def _parse_approved_display_names(panel: Any) -> Set[str]:
    """
    解析 Workflow-wise 审批面板响应，提取出已经点击 Approve 的人员名单。
    """
    if not isinstance(panel, dict):
        return set()
    approved = panel.get("approved")
    if not isinstance(approved, list):
        return set()
    names: Set[str] = set()
    for item in approved:
        if isinstance(item, dict):
            dn = item.get("displayName") or item.get("name") or item.get("value")
            if dn is not None:
                s = str(dn).strip()
                if s:
                    names.add(s)
        elif item is not None:
            s = str(item).strip()
            if s:
                names.add(s)
    return names

def _format_qas_with_approval(qa_names: List[str], approved_names: Set[str]) -> str:
    """
    根据 QA 列表和已审批的人员集合，为 QA 名字追加 "(Already approved)" 或 "(Pending approval)" 状态。
    """
    if not qa_names:
        return ""
    parts: List[str] = []
    for n in qa_names:
        s = str(n).strip()
        if not s:
            continue
        if s in approved_names:
            parts.append("%s(Already approved)" % s)
        else:
            parts.append("%s(Pending approval)" % s)
    return ", ".join(parts)


def _priority_rank(name: Optional[str]) -> int:
    """
    计算优先级的排序权重，数字越小优先级越高。
    支持 P0/P1/P2/P3 和 Highest/High/Medium/Low 等不同格式的同义词转换。
    """
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
    """
    将 Jira 返回的 created 字符串时间转换为用于排序的 UNIX 时间戳（float）。
    兼容处理带时区和不带时区的多种 ISO 时间格式。
    """
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
    """
    按通用自定义字段对 Issue 列表进行分组统计（如：按状态或模块统计数量）。
    返回降序排列后的名称到数量的字典映射。
    """
    counts: Dict[str, int] = {}
    for issue in issues:
        fields = issue.get("fields") or {}
        val = _get_by_path(fields, field_path) if field_path else ""
        name = val or "Unassigned"
        counts[name] = counts.get(name, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: (-x[1], x[0])))

def _summarize_by_people_field(issues: List[Dict[str, Any]], field_path: str) -> Dict[str, int]:
    """
    专门针对人员字段（如 QAs 列表）进行分组聚合统计。
    处理了一对多（一条 issue 有多个 QA）的拆分计数逻辑，返回降序排列的字典。
    """
    counts: Dict[str, int] = {}
    for issue in issues:
        names = _get_issue_people_names(issue, field_path)
        if not names:
            counts["Unassigned"] = counts.get("Unassigned", 0) + 1
            continue
        for n in names:
            counts[n] = counts.get(n, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: (-x[1], x[0])))


def _collect_top_qas_by_counts(issues: List[Dict[str, Any]], qa_field_path: str, top_limit: int) -> List[str]:
    """
    获取参与数量排名前 N 的 QA 人员名称列表。
    常用于构建摘要报告头部的 "TOP Pending QA PIC"。
    """
    counts = _summarize_by_people_field(issues, qa_field_path)
    top = list(counts.items())[:max(0, top_limit)]
    return [name for name, _ in top if str(name).strip()]


def _load_qa_map(path: str) -> Dict[str, str]:
    """
    从本地 JSON 文件中加载 QA 名字到飞书 user_id 的映射表。
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items() if v}
    except Exception:
        pass
    return {}


def _get_qa_map(path: str) -> Dict[str, str]:
    """
    获取 QA 映射表。
    优先使用脚本代码内置（内联）的 `QA_MAP_INLINE` 配置字典，如果为空则尝试读取外部 JSON 文件。
    """
    inline = SETTINGS.get("QA_MAP_INLINE") or {}
    if isinstance(inline, dict) and inline:
        return {str(k): str(v) for k, v in inline.items() if v}
    return _load_qa_map(path)

def _resolve_qa_field_path(jira: "JiraClient", issues: List[Dict[str, Any]]) -> str:
    """
    动态解析 QA 对应的自定义字段 ID（如 customfield_10700）。
    优先使用配置的显式 ID，否则通过 API 查询字段定义列表进行匹配，
    最后还会通过对 Issue 数据进行启发式分析推断 QA 字段的可能路径。
    """
    logger = logging.getLogger(__name__)
    configured = str(SETTINGS.get("QA_FIELD_PATH", "")).strip()
    if configured and configured.upper() != "AUTO" and configured != "reporter.displayName":
        return configured

    field_name = str(SETTINGS.get("QA_FIELD_NAME", "QAs")).strip() or "QAs"
    try:
        all_fields = jira.get_fields()
        for f in all_fields:
            if str(f.get("name", "")).strip() == field_name:
                fid = str(f.get("id", "")).strip()
                if fid:
                    logger.info("已自动解析QA字段：name=%s id=%s", field_name, fid)
                    return fid
    except Exception as e:
        logger.warning("自动解析QA字段失败（/field）：%s", e)

    qa_map_keys = set((str(k).strip() for k in (_get_qa_map(SETTINGS.get("QA_MAP_PATH", "qa_map.json")) or {}).keys()))
    best_key = ""
    best_score = 0
    for issue in issues[:50]:
        fields = issue.get("fields") or {}
        for k, v in fields.items():
            names = _extract_display_names(v)
            score = 0
            for n in names:
                if n in qa_map_keys:
                    score += 1
            if score > best_score:
                best_score = score
                best_key = str(k)
    if best_key and best_score > 0:
        logger.info("已启用QA字段启发式推断：field=%s score=%d", best_key, best_score)
        return best_key

    if configured and configured.upper() != "AUTO":
        return configured
    logger.warning("未能解析QA字段，继续使用默认 reporter.displayName（可能不等于页面的 QAs 字段）")
    return "reporter.displayName"

def _enrich_issues_with_qa_approval(jira: "JiraClient", issues: List[Dict[str, Any]], qa_field_path: str) -> None:
    """
    为获取到的 Issue 列表并行（这里通过遍历）注入 QA 审批状态数据。
    调用 approval panel 接口检查 QAs 中人员是否已审批，并将最终用于展示的字符串组装回 issue 字典。
    """
    if not SETTINGS.get("ENABLE_APPROVAL_CHECK"):
        return
    logger = logging.getLogger(__name__)
    cache: Dict[str, Set[str]] = {}
    for issue in issues:
        fields = issue.get("fields") or {}
        qa_names = _get_display_names_by_path(fields, qa_field_path) if qa_field_path else []
        issue["_qa_names"] = qa_names
        issue_id = str(issue.get("id", "")).strip()
        approved_names: Set[str] = set()
        if issue_id:
            if issue_id in cache:
                approved_names = cache[issue_id]
            else:
                try:
                    panel = jira.get_approval_panel(issue_id)
                    approved_names = _parse_approved_display_names(panel)
                except Exception as e:
                    logger.warning("获取approval失败 issue_id=%s key=%s err=%s", issue_id, issue.get("key", ""), e)
                    approved_names = set()
                cache[issue_id] = approved_names
        issue["_qa_approved_names"] = [n for n in qa_names if n in approved_names]
        issue["_qa_pending_names"] = [n for n in qa_names if n not in approved_names]
        display = _format_qas_with_approval(qa_names, approved_names)
        if display:
            issue["_qa_display"] = display


def _send_mentions(lark: "LarkClient", issues: List[Dict[str, Any]], qa_field_path: str, qa_map_path: str) -> None:
    """
    负责在飞书群中单独发送 Mention（艾特）提醒消息。
    根据 QA 名字映射其对应的飞书 user_id 并执行艾特。
    """
    qa_map = _get_qa_map(qa_map_path)
    names = _collect_top_qas_by_counts(issues, qa_field_path, int(SETTINGS.get("AT_TOP_LIMIT", 10)))
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
        logger.info("未发送提及：无可用user_id，AT_QA_MENTION=%s", SETTINGS.get("AT_QA_MENTION"))
        return
    content: List[List[Dict[str, Any]]] = [[{"tag": "text", "text": "Please kindly approve the ticket in time if you have no further questions: "}]]
    for uid in user_ids:
        content[0].append({"tag": "at", "user_id": uid})
    try:
        logger.info("发送提及数=%d", len(user_ids))
        # 提取所有期望查询的版本范围集合
        query_version_str = str(SETTINGS.get("FIX_VERSION", "")).strip()
        query_versions_set = {v.strip() for v in query_version_str.split(",") if v.strip()}
        
        # 提取实际存在的数据所属的 fixVersion 并集
        actual_versions_set: Set[str] = set()
        for issue in issues:
            fields = issue.get("fields") or {}
            fix_versions = fields.get("fixVersions") or []
            if type(fix_versions) is list:
                for fv in fix_versions:
                    if type(fv) is dict:
                        v_name = fv.get("name")
                        if v_name:
                            actual_versions_set.add(str(v_name).strip())
        
        # 取查询范围与实际返回范围的交集
        intersect_versions = query_versions_set.intersection(actual_versions_set)
        
        if intersect_versions:
            display_version = ", ".join(sorted(list(intersect_versions)))
        else:
            display_version = query_version_str

        mention_title = "%s Mention" % display_version if display_version else "Mention"
        resp = lark.send_post_content(_today_title(mention_title, SETTINGS.get("TIMEZONE", "Asia/Shanghai")), content)
        logger.info("提及响应=%s", resp)
    except Exception as e:
        logger.error("提及失败=%s", e)


def format_post_report(issues: List[Dict[str, Any]], top_n: int, base_url_for_links: Optional[str], qa_field_path: str, row_prefix_emoji: str, count_emoji: str, at_qa_plain: bool) -> Tuple[str, List[List[Dict[str, Any]]]]:
    """
    格式化富文本（Post）格式的推送报告。
    当数据为 0 时，将展示 f-string 构造的默认无数据文案。
    """
    total = len(issues)
    title = _today_title(_report_title(), SETTINGS.get("TIMEZONE", "Asia/Shanghai"))
    
    current_version = str(SETTINGS.get("FIX_VERSION", "")).strip() or "N/A"
    content: List[List[Dict[str, Any]]] = [
        [{"tag": "text", "text": "%s Total: %d" % (count_emoji, total)}],
        [{"tag": "text", "text": "Query Version: %s\n" % current_version}]
    ]
    
    # 无数据时的默认兜底文案
    if total == 0:
        content.append([{"tag": "text", "text": "-----------------------------\n"}])
        content.append([{"tag": "text", "text": f"There's no Ready to Brief Story/Improvement pending from QA in version {current_version}", "style": ["bold"]}])
        return title, content

    qa_counts = _summarize_by_people_field(issues, qa_field_path)
    top_qas = list(qa_counts.items())[:10]
    if top_qas:
        top_label = "TOP Pending QA PIC" if SETTINGS.get("ONLY_MENTION_PENDING_QA") else "TOP QA PIC"
        top_line = top_label + ": " + ", ".join(["%s:%d" % (name, cnt) for name, cnt in top_qas])
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
        qa_val = _qa_display_for_issue(issue, qa_field_path)
        priority = _get_by_path(fields, "priority.name")
        status = _get_by_path(fields, "status.name")
        summary = fields.get("summary", "")
        elements: List[Dict[str, Any]] = []
        jira_ticket_text = "%s: %s" % (key, summary) if summary else key
        if base_url_for_links and key:
            elements.append({"tag": "a", "text": jira_ticket_text, "href": "%s/browse/%s" % (base_url_for_links.rstrip("/"), key)})
        else:
            elements.append({"tag": "text", "text": "%s" % jira_ticket_text})
        if qa_val:
            elements.append({"tag": "text", "text": " [%s]" % qa_val})
            if at_qa_plain:
                elements.append({"tag": "text", "text": " @%s" % qa_val})
        else:
            elements.append({"tag": "text", "text": " [Unassigned]"})
        tail_parts = []
        if priority:
            tail_parts.append(priority)
        if status:
            tail_parts.append(status)
        if tail_parts:
            elements.append({"tag": "text", "text": " " + " ".join(tail_parts)})
        content.append(elements)
    return title, content


def build_interactive_card(issues: List[Dict[str, Any]], title: str, base_url_for_links: Optional[str], qa_field_path: str, count_emoji: str, row_prefix_emoji: str, show_limit: int, jira_base_url: str, jql: str, layout: str, summary_emoji: str, target_tz: str) -> Dict[str, Any]:
    """
    构建交互式卡片（Interactive Card）格式的推送报告。
    当数据为 0 时，将展示 f-string 构造的默认无数据文案。
    """
    total = len(issues)
    card: Dict[str, Any] = {"config": {"wide_screen_mode": True}, "header": {"title": {"tag": "plain_text", "content": title}}, "elements": []}
    elements = card["elements"]
    elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "%s Total: %d" % (count_emoji, total)}})
    
    current_version = str(SETTINGS.get("FIX_VERSION", "")).strip() or "N/A"
    elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "Query Version: %s" % current_version}})

    # 无数据时的默认兜底文案
    if total == 0:
        elements.append({"tag": "hr"})
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": f"**There's no Ready to Brief Story/Improvement pending from QA in version {current_version}**"}})
        return card

    qa_counts = _summarize_by_people_field(issues, qa_field_path)
    top_qas = list(qa_counts.items())[:10]
    if top_qas:
        top_label = "TOP Pending QA PIC" if SETTINGS.get("ONLY_MENTION_PENDING_QA") else "TOP QA PIC"
        top_line = top_label + ": " + ", ".join(["%s:%d" % (name, cnt) for name, cnt in top_qas])
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

    def _format_created(created: str, tz_name: Optional[str] = None) -> str:
        if not created:
            return ""
        target = None
        if tz_name:
            try:
                target = pytz.timezone(tz_name)
            except Exception:
                target = None
        for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
            try:
                dt = datetime.strptime(created, fmt)
                if target:
                    dt = dt.astimezone(target)
                return dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                pass
        for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
            try:
                naive = datetime.strptime(created, fmt)
                if target:
                    dt = pytz.utc.localize(naive).astimezone(target)
                else:
                    dt = naive
                return dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                pass
        return created

    for issue in show_items:
        key = issue.get("key", "")
        fields = issue.get("fields") or {}
        qa_val = _qa_display_for_issue(issue, qa_field_path) or "Unassigned"
        priority = _get_by_path(fields, "priority.name")
        status = _get_by_path(fields, "status.name")
        summary = fields.get("summary", "")
        created_fmt = _format_created(fields.get("created", ""), target_tz)

        jira_ticket_text = "%s: %s" % (key, summary) if summary else key
        key_md = "**Jira Ticket**: %s" % jira_ticket_text
        if base_url_for_links and key:
            key_md = "**Jira Ticket**: [%s](%s/browse/%s)" % (jira_ticket_text, base_url_for_links.rstrip("/"), key)

        right_lines = ["**QAs**: %s" % qa_val]
        if priority:
            right_lines.append("**Priority**: %s" % priority)
        if status:
            right_lines.append("**Status**: %s" % status)

        if layout == "single_column":
            lines = [key_md]
            lines.extend(right_lines)
            if created_fmt:
                lines.append("**Created**: %s" % created_fmt)
            elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(lines)}})
        elif layout == "three_columns":
            fields_block = {
                "tag": "div",
                "fields": [
                    {"is_short": True, "text": {"tag": "lark_md", "content": key_md}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": "\n".join(right_lines)}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": "**Created**: %s" % created_fmt}},
                ],
            }
            elements.append(fields_block)
        else:
            fields_block = {
                "tag": "div",
                "fields": [
                    {"is_short": True, "text": {"tag": "lark_md", "content": key_md}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": "\n".join(right_lines + (["**Created**: %s" % created_fmt] if created_fmt else []))}},
                ],
            }
            elements.append(fields_block)

    if hidden_count > 0:
        elements.append({"tag": "hr"})
        tip = "Remaining %d items collapsed" % hidden_count
        if jira_base_url and jql:
            jql_url = "%s/issues/?jql=%s" % (jira_base_url.rstrip("/"), quote_plus(jql))
            tip = tip + ", [View All](%s)" % jql_url
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "Info: %s" % tip}})
    return card


def _apply_odd_even_version_logic(current_version: str, all_versions: List[Tuple[str, str, str]]) -> str:
    """
    根据版本号奇偶性决定是否包含下一个版本
    奇数版本：返回 "当前版本, 下一版本"
    偶数版本：返回 "当前版本"
    """
    try:
        parts = current_version.split(".")
        if not parts:
            return current_version
        
        last_num_str = parts[-1]
        import re
        match = re.search(r'\d+', last_num_str)
        if not match:
            return current_version
            
        last_num = int(match.group())
        
        if last_num % 2 != 0:
            next_version = ""
            if all_versions:
                for i, (_, _, v_name) in enumerate(all_versions):
                    if v_name == current_version and i + 1 < len(all_versions):
                        next_version = all_versions[i+1][2]
                        break
            if not next_version:
                prefix = current_version[:current_version.rfind(str(last_num))]
                next_version = f"{prefix}{last_num + 1}"
            
            logger = logging.getLogger(__name__)
            logger.info("捕获当前版本号: %s (奇数版本，包含下一版本 %s)", current_version, next_version)
            return f"{current_version}, {next_version}"
        else:
            logger = logging.getLogger(__name__)
            logger.info("捕获当前版本号: %s (偶数版本)", current_version)
            return current_version
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.warning("解析版本号奇偶性失败: %s, 退回单版本查询", e)
        return current_version


def run_job() -> None:
    """
    主调度函数，串联整体业务流程：
    1. 初始化并检查环境及配置。
    2. 动态匹配当前版本的版本号。
    3. 调用 Jira 接口查询符合条件的 issues 数据。
    4. 对数据进行多维度解析、组装（如解析审批状态）。
    5. 根据配置选择推送卡片格式或富文本格式到飞书。
    6. 执行补充的提及提醒（Mention）功能。
    """
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

    try:
        jira = JiraClient(
            SETTINGS["JIRA_BASE_URL"],
            username=(SETTINGS.get("JIRA_USERNAME") or None),
            password=(SETTINGS.get("JIRA_PASSWORD") or None),
            api_version="2",
        )
    except Exception as e:
        print("JiraClient 初始化失败: %s" % e, file=sys.stderr)
        return

    # 动态版本解析
    if str(SETTINGS.get("FIX_VERSION", "")).strip().upper() == "AUTO":
        board_id = str(SETTINGS.get("DYNAMIC_VERSION_BOARD_ID", "1")).strip()
        try:
            url = "%s/rest/release-management/1.0/board/%s?onlyUnarchived=true&reduce=description%%2Cparagraph" % (jira.base_url, board_id)
            resp = jira.session.get(url, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            versions = data.get("versions", {})
            all_versions = []
            if type(versions) is dict:
                for k, v_list in versions.items():
                    if type(v_list) is list:
                        for v in v_list:
                            name = v.get("name")
                            start = v.get("startDate")
                            release = v.get("releaseDate")
                            if name and release and name.startswith("v"):
                                all_versions.append((release, start, name))
            all_versions.sort() # Sorts by release date ascending
            
            today = datetime.now().date().isoformat()
            matched_version = ""
            
            # 找到第一个 releaseDate >= 当前时间的版本
            for release, start, name in all_versions:
                if today <= release:
                    matched_version = name
                    break

            if matched_version:
                SETTINGS["FIX_VERSION"] = _apply_odd_even_version_logic(matched_version, all_versions)
            else:
                logger.warning("未找到匹配时间区间的版本，将使用空字符串进行搜索")
                SETTINGS["FIX_VERSION"] = ""
        except Exception as e:
            logger.error("动态解析 FIX_VERSION 失败: %s", e)
            SETTINGS["FIX_VERSION"] = ""
    else:
        current_fixed = str(SETTINGS.get("FIX_VERSION", "")).strip()
        if current_fixed and current_fixed.upper() != "AUTO":
            SETTINGS["FIX_VERSION"] = _apply_odd_even_version_logic(current_fixed, [])

    jql = _build_report_jql()
    logger.info("开始生成日报 jql=%s", jql)
    
    try:
        # 默认获取所有字段（包含 summary, status, fixVersions 等）
        issues = jira.search_issues(jql, max_results=int(SETTINGS["MAX_RESULTS"]))
        logger.info("从 Jira 获取到 %d 条结果", len(issues))
    except Exception as e:
        print("Jira 请求失败: %s" % e, file=sys.stderr)
        return

    qa_field_path = _resolve_qa_field_path(jira, issues)
    _enrich_issues_with_qa_approval(jira, issues, qa_field_path)

    webhook = str(SETTINGS.get("LARK_WEBHOOK_URL", "")).strip()
    if not webhook:
        print("未配置 LARK_WEBHOOK_URL，打印到控制台，条目数=%d" % len(issues))
        return

    try:
        # 初始化 Lark 客户端，准备执行推送操作
        lark = LarkClient(webhook)
        if str(SETTINGS["MESSAGE_TYPE"]).strip().lower() == "post":
            # 如果配置为富文本（post）模式，构建标题与内容
            title, content = format_post_report(
                issues,
                top_n=int(SETTINGS["REPORT_TOP_N"]),
                base_url_for_links=(SETTINGS["JIRA_BASE_URL"] if SETTINGS["ENABLE_LINKS"] else None),
                qa_field_path=qa_field_path,
                row_prefix_emoji=SETTINGS["ROW_PREFIX_EMOJI"],
                count_emoji=SETTINGS["COUNT_EMOJI"],
                at_qa_plain=SETTINGS["AT_QA_PLAIN"],
            )
            if SETTINGS.get("AT_QA_MENTION"):
                # 将 Mention 逻辑内嵌到富文本消息中
                qa_map = _get_qa_map(SETTINGS.get("QA_MAP_PATH", "qa_map.json"))
                names = _collect_top_qas_by_counts(issues, qa_field_path, int(SETTINGS.get("AT_TOP_LIMIT", 10)))
                user_ids: List[str] = []
                for n in names:
                    uid = qa_map.get(n)
                    if uid and uid not in user_ids:
                        user_ids.append(uid)
                if user_ids:
                    content.insert(1, [{"tag": "text", "text": "Please kindly approve the ticket in time if you have no further questions: "}] + [{"tag": "at", "user_id": uid} for uid in user_ids])
            resp = lark.send_post_content(title, content)
            logger.info("Lark响应: %s", resp)
        else:
            # 如果配置为交互式卡片（interactive）模式，构建卡片对象
            title = _today_title(_report_title(), SETTINGS.get("TIMEZONE", "Asia/Shanghai"))
            card = build_interactive_card(
                issues,
                title,
                base_url_for_links=(SETTINGS["JIRA_BASE_URL"] if SETTINGS["ENABLE_LINKS"] else None),
                qa_field_path=qa_field_path,
                count_emoji=SETTINGS["COUNT_EMOJI"],
                row_prefix_emoji=SETTINGS["ROW_PREFIX_EMOJI"],
                show_limit=int(SETTINGS["SHOW_LIMIT"]),
                jira_base_url=SETTINGS["JIRA_BASE_URL"],
                jql=jql,
                layout=SETTINGS["CARD_LAYOUT"],
                summary_emoji=SETTINGS["SUMMARY_EMOJI"],
                target_tz=SETTINGS["TIMEZONE"],
            )
            resp = lark.send_interactive_card(card)
            logger.info("Lark响应: %s", resp)
            if SETTINGS.get("AT_QA_MENTION"):
                # 卡片模式下，Mention 需要通过独立的一条文本消息发送
                _send_mentions(lark, issues, qa_field_path, SETTINGS.get("QA_MAP_PATH", "qa_map.json"))
        logger.info("报告已推送，条目数=%s，类型=%s", len(issues), SETTINGS["MESSAGE_TYPE"])
    except Exception as e:
        print("Lark 推送失败: %s" % e, file=sys.stderr)


if __name__ == "__main__":
    try:
        run_job()
    except Exception as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
