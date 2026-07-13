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
    # 兼容从技能安装目录下（.agents/skills/jira_fix_version_time/）加载 .env
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
    return "%s %s" % (dt.strftime("%Y-%m-%d"), base_title)

'''
- SETTINGS["MESSAGE_TYPE"] = "interactive" ：卡片
- SETTINGS["MESSAGE_TYPE"] = "post" ：富文本
'''
SETTINGS: Dict[str, Any] = {
    "JIRA_BASE_URL": "https://rd-project.fuseinsurtech.com",
    "JIRA_USERNAME": "huxuesong",
    "JIRA_PASSWORD": "Qq12345678=",
    "LARK_WEBHOOK_URL": "https://open.larksuite.com/open-apis/bot/v2/hook/955ef15f-edf5-413f-9f49-322703b6aa45",
    # 测试用
    # "LARK_WEBHOOK_URL": "https://open.larksuite.com/open-apis/bot/v2/hook/addf0fe2-d59a-4797-beff-ea836606e398",
    
    "REPORT_JQL": 'project in (CS, MP) AND issuetype in (Story, Improvement)',
    # 版本号与过滤配置
    "FIX_VERSION": "AUTO", # 可以固定如 "v6.16" 或设为 "AUTO" 动态获取
    "DYNAMIC_VERSION_BOARD_ID": "1", # 当 FIX_VERSION 为 AUTO 时，从该 board 获取版本周期
    "EXCLUDE_STATUSES": ["SIT Done", "IN SIT", "UAT Done", "IN UAT", "Open", "Closed", "Done", "On Hold"],
    "TIMEZONE": "Asia/Shanghai",
    "LOG_LEVEL": "INFO",
    "MESSAGE_TYPE": "interactive",
    "REPORT_TOP_N": 20,
    "MAX_RESULTS": 100,
    "ENABLE_LINKS": True,
    "QA_FIELD_NAME": "QAs",
    "QA_FIELD_PATH": "customfield_10700",
    "TARGET_START_FIELD_NAME": "Target start",
    "TARGET_START_FIELD_PATH": "customfield_10109",
    "TARGET_END_FIELD_NAME": "Target end",
    "TARGET_END_FIELD_PATH": "customfield_10110",
    "APPLICABLE_COUNTRIES_FIELD_PATH": "customfield_10206",
    "ENABLE_APPROVAL_CHECK": True,
    "APPROVAL_API_PATH_TEMPLATE": "/rest/workflow-wise/latest/approval/issue-panel/{issue_id}/approval",
    "ONLY_MENTION_PENDING_QA": False,
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
    "DEV_MAP_INLINE": {
        "罗恒(Loren Luo)": "6985397642436018181",
        "赵志国(Vito Zhao)": "7050270687382011909",
        "张界(Magee Zhang)": "7080360017798381574",
        "王正鑫(Tanya)": "7050091635010437126",
        "肖宝(Carlos Xiao)": "7050283542877569030",
        "郑子龙(Stark)": "7246212856302026758",
        "陆嘉冠(Gavin)": "7050283891210338310",
        "陈凡(Frank)": "6953497492818231302",
        "黄欣(Simba)": "6943875503438692357",
        "黄嘉权(Hurley)": "7050282599079493637",
        "刘在欢(Murphy Liu)": "7050293754636304389",
        "刘广平(levi.liu)": "7094811934456971269",
        "何方远(Hector He)": "7050095903511674886",
        "陈涛(Ann)": "7050286631751811078",
        "黄福财(Simon)": "7050283517887905797",
        "黄瑞忠(Akira)": "6953529589742190598",
        "梁益森(Thompson)": "7256971338462527494",
        "Joseph": "6916687679249711110",
        "Nabilah Ulfah Aulia": "7248861203471024133",
        "Fadel Attar Chazalie": "7332047100271214597",
        "Ari Aliansah": "7364304065999290373",
        "Ardiansyah Fuse": "7274822459042299910",
    },
    "ROW_PREFIX_EMOJI": "-",
    "COUNT_EMOJI": "COUNT",
    "STATUS_EMOJI": "Status",
    "DEV_START_EMOJI": "DevStartTime",
    "DEV_END_EMOJI": "DevEndTime",
    "SUMMARY_EMOJI": "Summary",
    "SHOW_LIMIT": 15,
}

# 优先读取系统环境变量覆盖默认设置（如 .env 加载的配置）
for key in ["JIRA_BASE_URL", "JIRA_USERNAME", "JIRA_PASSWORD", "LARK_WEBHOOK_URL"]:
    env_val = os.environ.get(key)
    if env_val:
        SETTINGS[key] = env_val.strip().strip('"').strip("'")



def _build_report_jql() -> str:
    base = str(SETTINGS.get("REPORT_JQL", "")).strip()
    fix_version = str(SETTINGS.get("FIX_VERSION", "")).strip()
    exclude_statuses = SETTINGS.get("EXCLUDE_STATUSES") or []
    status_filter = ""
    if isinstance(exclude_statuses, list):
        cleaned = [str(s).strip() for s in exclude_statuses if str(s).strip()]
        if cleaned:
            status_filter = "status not in (%s)" % ", ".join(['"%s"' % s.replace('"', '\\"') for s in cleaned])
    if fix_version:
        versions = [v.strip() for v in fix_version.split(",") if v.strip()]
        if len(versions) == 1:
            version_condition = 'fixVersion = "%s"' % versions[0]
        else:
            version_list_str = ", ".join('"%s"' % v for v in versions)
            version_condition = 'fixVersion in (%s)' % version_list_str
            
        if base:
            base = '%s AND %s' % (base, version_condition)
        else:
            base = version_condition
    if status_filter:
        if base:
            return "%s AND %s" % (base, status_filter)
        return status_filter
    return base


def _report_title() -> str:
    fix_version = str(SETTINGS.get("FIX_VERSION", "")).strip()
    if fix_version:
        return "Version %s Estimated Dev Finish Time Track" % fix_version
    return "Version Estimated Dev Finish Time Track"
    
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

    def search_issues(self, jql: str, max_results: int = 50, fields: Optional[List[str]] = None, retries: int = 3) -> List[Dict[str, Any]]:
        url = "%s/rest/api/%s/search" % (self.base_url, self.api_version)
        params: Dict[str, Any] = {"jql": jql, "maxResults": max_results}
        if fields:
            params["fields"] = ",".join([str(x).strip() for x in fields if str(x).strip()])
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

    def get_issue(self, issue_key: str, fields: Optional[List[str]] = None, retries: int = 3) -> Dict[str, Any]:
        url = "%s/rest/api/%s/issue/%s" % (self.base_url, self.api_version, str(issue_key).strip())
        params: Dict[str, Any] = {}
        if fields:
            params["fields"] = ",".join([str(x).strip() for x in fields if str(x).strip()])
        last_exc = None
        for attempt in range(1, retries + 1):
            try:
                resp = self.session.get(url, params=params, timeout=20)
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

    def get_approval_panel(self, issue_id: str, retries: int = 3) -> Dict[str, Any]:
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

    def send_post_content(self, title: str, content: List[List[Dict[str, Any]]]) -> Dict[str, Any]:
        payload = {"msg_type": "post", "content": {"post": {"zh_cn": {"title": title, "content": content}}}}
        return self._post(payload)

    def send_interactive_card(self, card: Dict[str, Any]) -> Dict[str, Any]:
        payload = {"msg_type": "interactive", "card": card}
        return self._post(payload)


def _extract_display_names(val: Any) -> List[str]:
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
    if not path:
        return []
    parts = [p for p in path.split(".") if p]
    cur_items: List[Any] = [fields]
    for p in parts:
        next_items: List[Any] = []
        for cur in cur_items:
            if type(cur) is dict:
                next_items.append(cur.get(p))
            elif type(cur) is list:
                for item in cur:
                    if type(item) is dict:
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


def _get_by_path(fields: Dict[str, Any], path: str) -> str:
    if not path:
        return ""
    parts = [p for p in path.split(".") if p]
    cur: Any = fields
    for p in parts:
        if type(cur) is dict:
            cur = cur.get(p)
        elif type(cur) is list:
            cur = cur[0] if cur else None
        else:
            cur = None
        if cur is None:
            return ""
    if type(cur) is dict:
        return cur.get("displayName") or cur.get("name") or ""
    return str(cur) if cur is not None else ""


def _parse_jira_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    v = str(s)
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(v, fmt)
        except Exception:
            pass
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(v, fmt)
        except Exception:
            pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(v, fmt)
        except Exception:
            pass
    try:
        dt = datetime.strptime(v, "%Y-%m-%d")
        try:
            tz = pytz.timezone(str(SETTINGS.get("TIMEZONE", "Asia/Shanghai")))
            return tz.localize(dt)
        except Exception:
            return dt
    except Exception:
        pass
    return None


def _format_dt(dt: Optional[datetime], tz_name: str) -> str:
    if not dt:
        return ""
    try:
        tz = pytz.timezone(tz_name)
    except Exception:
        tz = None
    if tz:
        if dt.tzinfo is None:
            try:
                dt = pytz.utc.localize(dt)
            except Exception:
                pass
        try:
            dt = dt.astimezone(tz)
        except Exception:
            pass
    try:
        if dt.hour == 0 and dt.minute == 0 and dt.second == 0:
            return dt.strftime("%Y-%m-%d")
    except Exception:
        pass
    return dt.strftime("%Y-%m-%d %H:%M")


def _parse_approved_display_names(panel: Any) -> Set[str]:
    if type(panel) is not dict:
        return set()
    approved = panel.get("approved")
    if type(approved) is not list:
        return set()
    names: Set[str] = set()
    for item in approved:
        if type(item) is dict:
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
    if not qa_names:
        return ""
    parts: List[str] = []
    for n in qa_names:
        s = str(n).strip()
        if not s:
            continue
        if s in approved_names:
            parts.append("%s" % s)
        else:
            parts.append("%s" % s)
    return ", ".join(parts)


def _load_map(path: str) -> Dict[str, str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items() if v}
    except Exception:
        pass
    return {}


def _get_qa_map(path: str) -> Dict[str, str]:
    inline = SETTINGS.get("QA_MAP_INLINE") or {}
    if isinstance(inline, dict) and inline:
        return {str(k): str(v) for k, v in inline.items() if v}
    return _load_map(path)


def _get_dev_name_set() -> Set[str]:
    m = SETTINGS.get("DEV_MAP_INLINE") or {}
    if m and type(m) is dict:
        return set((str(k).strip() for k in m.keys() if str(k).strip()))
    if m and type(m) is list:
        return set((str(x).strip() for x in m if str(x).strip()))
    return set()

def _resolve_field_path_by_name(jira: "JiraClient", configured_path: str, field_name: str, fallback_path: str) -> str:
    configured = str(configured_path or "").strip()
    if configured and configured.upper() != "AUTO":
        return configured
    name = str(field_name or "").strip()
    if name:
        all_fields = jira.get_fields()
        for f in all_fields:
            if str(f.get("name", "")).strip() == name:
                fid = str(f.get("id", "")).strip()
                if fid:
                    return fid
    if configured and configured.upper() != "AUTO":
        return configured
    return str(fallback_path or "").strip()

def _resolve_qa_field_path(jira: "JiraClient") -> str:
    configured = str(SETTINGS.get("QA_FIELD_PATH", "")).strip()
    if configured and configured.upper() != "AUTO" and configured != "reporter.displayName":
        return configured
    return _resolve_field_path_by_name(
        jira,
        configured_path=str(SETTINGS.get("QA_FIELD_PATH", "")).strip(),
        field_name=str(SETTINGS.get("QA_FIELD_NAME", "QAs")).strip() or "QAs",
        fallback_path="reporter.displayName",
    )


def _enrich_issue_with_qa_display(jira: "JiraClient", issue: Dict[str, Any], qa_field_path: str) -> None:
    if not SETTINGS.get("ENABLE_APPROVAL_CHECK"):
        fields = issue.get("fields") or {}
        qa_names = _get_display_names_by_path(fields, qa_field_path) if qa_field_path else []
        if qa_names:
            issue["_qa_display"] = ", ".join(qa_names)
        return
    fields = issue.get("fields") or {}
    qa_names = _get_display_names_by_path(fields, qa_field_path) if qa_field_path else []
    issue_id = str(issue.get("id", "")).strip()
    approved_names: Set[str] = set()
    if issue_id:
        panel = jira.get_approval_panel(issue_id)
        approved_names = _parse_approved_display_names(panel)
    issue["_qa_display"] = _format_qas_with_approval(qa_names, approved_names) if qa_names else ""


def _calc_dev_time_range(
    jira: "JiraClient",
    parent_issue: Dict[str, Any],
    target_start_field_path: str,
    target_end_field_path: str,
) -> Tuple[Optional[datetime], Optional[datetime], List[str]]:
    dev_names = _get_dev_name_set()
    fields = parent_issue.get("fields") or {}
    subtasks = fields.get("subtasks") or []
    if type(subtasks) is not list or not subtasks:
        return None, None, []
    start_dts: List[datetime] = []
    end_dts: List[datetime] = []
    dev_pics: List[str] = []

    def _extract_best_dt(val: Any) -> Optional[datetime]:
        if val is None:
            return None
        if type(val) is list:
            dts = [d for d in (_extract_best_dt(x) for x in val) if d]
            if not dts:
                return None
            return max(dts, key=lambda x: x.timestamp() if x.tzinfo else x.replace(tzinfo=pytz.utc).timestamp())
        if type(val) is dict:
            # Try to extract a value from the dict (e.g. from {"value": "2026-05-14"})
            for k in ("value", "name", "id"):
                v = val.get(k)
                if v is not None:
                    dt = _parse_jira_dt(str(v))
                    if dt:
                        return dt
            return None
        return _parse_jira_dt(str(val))

    for st in subtasks:
        if type(st) is not dict:
            continue
        st_key = str(st.get("key", "")).strip()
        if not st_key:
            continue
        st_issue = jira.get_issue(
            st_key,
            fields=[
                "assignee",
                "status",
                "resolutiondate",
                "updated",
                "summary",
                str(target_start_field_path).strip(),
                str(target_end_field_path).strip(),
            ],
        )
        st_fields = st_issue.get("fields") or {}
        assignee = st_fields.get("assignee") or {}
        assignee_name = ""
        if type(assignee) is dict:
            assignee_name = str(assignee.get("displayName") or assignee.get("name") or "").strip()
        if not assignee_name or assignee_name not in dev_names:
            continue
        if assignee_name not in dev_pics:
            dev_pics.append(assignee_name)
        start_dt = None
        if str(target_start_field_path).strip():
            start_val_raw = st_fields.get(str(target_start_field_path).strip())
            if start_val_raw is not None:
                start_dt = _extract_best_dt(start_val_raw)
        if start_dt:
            start_dts.append(start_dt)

        end_dt = None
        if str(target_end_field_path).strip():
            end_val_raw = st_fields.get(str(target_end_field_path).strip())
            if end_val_raw is not None:
                end_dt = _extract_best_dt(end_val_raw)
        
        if not end_dt:
            end_dt = _parse_jira_dt(st_fields.get("resolutiondate"))
        if not end_dt:
            status_cat = (((st_fields.get("status") or {}).get("statusCategory") or {}).get("name") or "")
            if str(status_cat).strip().lower() == "done":
                end_dt = _parse_jira_dt(st_fields.get("updated"))
        if end_dt:
            end_dts.append(end_dt)
    start_val: Optional[datetime] = None
    end_val: Optional[datetime] = None
    if start_dts:
        start_val = min(start_dts, key=lambda x: x.timestamp() if x.tzinfo else x.replace(tzinfo=pytz.utc).timestamp())
    if end_dts:
        end_val = max(end_dts, key=lambda x: x.timestamp() if x.tzinfo else x.replace(tzinfo=pytz.utc).timestamp())
    return start_val, end_val, dev_pics


def _dev_end_sort_key(issue: Dict[str, Any]) -> Tuple[int, float, str]:
    key = str(issue.get("key", ""))
    dt = issue.get("_dev_end_dt")
    if type(dt) is datetime:
        ts = dt.timestamp() if dt.tzinfo else dt.replace(tzinfo=pytz.utc).timestamp()
        return (0, ts, key)
    s = str(issue.get("_dev_end") or "").strip()
    dt2 = _parse_jira_dt(s) if s else None
    if dt2:
        ts = dt2.timestamp() if dt2.tzinfo else dt2.replace(tzinfo=pytz.utc).timestamp()
        return (0, ts, key)
    return (1, float("inf"), key)


def _qa_display(issue: Dict[str, Any], qa_field_path: str) -> str:
    v = issue.get("_qa_display")
    if v is not None and type(v) is str:
        return v
    fields = issue.get("fields") or {}
    names = _get_display_names_by_path(fields, qa_field_path)
    return ", ".join(names)


def _summarize_by_people_field(issues: List[Dict[str, Any]], field_path: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for issue in issues:
        fields = issue.get("fields") or {}
        names = _get_display_names_by_path(fields, field_path) if field_path else []
        if not names:
            counts["Unassigned"] = counts.get("Unassigned", 0) + 1
            continue
        for n in names:
            counts[n] = counts.get(n, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: (-x[1], x[0])))


def _send_mentions(lark: "LarkClient", issues: List[Dict[str, Any]], qa_field_path: str, qa_map_path: str) -> None:
    if not SETTINGS.get("AT_QA_MENTION"):
        return
    qa_map = _get_qa_map(qa_map_path)
    counts = _summarize_by_people_field(issues, qa_field_path)
    top = list(counts.items())[:max(0, int(SETTINGS.get("AT_TOP_LIMIT", 10)))]
    names = [name for name, _ in top if str(name).strip()]
    logger = logging.getLogger(__name__)
    user_ids: List[str] = []
    for n in names:
        uid = qa_map.get(n)
        if uid and uid not in user_ids:
            user_ids.append(str(uid))
    if not user_ids:
        logger.info("未发送提及：无可用user_id")
        return
    content: List[List[Dict[str, Any]]] = [[{"tag": "text", "text": "Please Pay Attention To The Dev Done Time："}]]
    for uid in user_ids:
        content[0].append({"tag": "at", "user_id": uid})
    
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


def format_post_report(issues: List[Dict[str, Any]], top_n: int, base_url_for_links: Optional[str], qa_field_path: str, applicable_countries_path: str, count_emoji: str) -> Tuple[str, List[List[Dict[str, Any]]]]:
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
        content.append([{"tag": "text", "text": f"There's no ticket meet the condition in version {current_version}", "style": ["bold"]}])
        return title, content
    
    issues_sorted = sorted(issues, key=_dev_end_sort_key)
    for issue in issues_sorted[:top_n]:
        key = issue.get("key", "")
        fields = issue.get("fields") or {}
        status = _get_by_path(fields, "status.name")
        applicable_countries_list = _get_display_names_by_path(fields, applicable_countries_path)
        applicable_countries = ", ".join(applicable_countries_list) if applicable_countries_list else "N/A"
        qa_val = _qa_display(issue, qa_field_path)
        dev_start = str(issue.get("_dev_start") or "").strip()
        dev_end = str(issue.get("_dev_end") or "").strip()
        dev_pics = issue.get("_dev_pics") or []
        dev_pic_text = ", ".join([str(x) for x in dev_pics if str(x).strip()])
        summary = str(fields.get("summary", "") or "")

        elements: List[Dict[str, Any]] = []
        jira_ticket_text = "%s: %s" % (key, summary) if summary else key
        
        if base_url_for_links and key:
            elements.append({"tag": "a", "text": jira_ticket_text, "href": "%s/browse/%s" % (base_url_for_links.rstrip("/"), key)})
        else:
            elements.append({"tag": "text", "text": "%s" % jira_ticket_text})
            
        if status:
            elements.append({"tag": "text", "text": " [%s]" % status})
        elements.append({"tag": "text", "text": " [Applicable Countries:%s]" % applicable_countries})
        if dev_pic_text:
            elements.append({"tag": "text", "text": " [Dev:%s]" % dev_pic_text})
        if dev_start:
            elements.append({"tag": "text", "text": " [DevStartTime:%s]" % dev_start})
        else:
            elements.append({"tag": "text", "text": " [DevStartTime:N/A]"})
        if dev_end:
            elements.append({"tag": "text", "text": " [DevEndTime:%s]" % dev_end})
        else:
            elements.append({"tag": "text", "text": " [DevEndTime:N/A]"})
        if qa_val:
            elements.append({"tag": "text", "text": " [QAs:%s]" % qa_val})
        content.append(elements)
    return title, content


def build_interactive_card(issues: List[Dict[str, Any]], title: str, base_url_for_links: Optional[str], qa_field_path: str, applicable_countries_path: str, count_emoji: str, show_limit: int, jira_base_url: str, jql: str) -> Dict[str, Any]:
    total = len(issues)
    card: Dict[str, Any] = {"config": {"wide_screen_mode": True}, "header": {"title": {"tag": "plain_text", "content": title}}, "elements": []}
    elements = card["elements"]
    elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "%s Total: %d" % (count_emoji, total)}})
    
    current_version = str(SETTINGS.get("FIX_VERSION", "")).strip() or "N/A"
    elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "Query Version: %s" % current_version}})

    # 无数据时的默认兜底文案
    if total == 0:
        elements.append({"tag": "hr"})
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": f"**There's no ticket meet the condition in version {current_version}**"}})
        return card

    elements.append({"tag": "hr"})

    issues_sorted = sorted(issues, key=_dev_end_sort_key)
    show_items = issues_sorted[:show_limit]
    hidden_count = max(0, len(issues_sorted) - len(show_items))
    for issue in show_items:
        key = issue.get("key", "")
        fields = issue.get("fields") or {}
        qa_val = _qa_display(issue, qa_field_path) or "Unassigned"
        status = _get_by_path(fields, "status.name")
        applicable_countries_list = _get_display_names_by_path(fields, applicable_countries_path)
        applicable_countries = ", ".join(applicable_countries_list) if applicable_countries_list else "N/A"
        summary = str(fields.get("summary", "") or "")
        dev_start = str(issue.get("_dev_start") or "").strip() or "N/A"
        dev_end = str(issue.get("_dev_end") or "").strip() or "N/A"
        dev_pics = issue.get("_dev_pics") or []
        dev_pic_text = ", ".join([str(x) for x in dev_pics if str(x).strip()])
        
        jira_ticket_text = "%s: %s" % (key, summary) if summary else key
        key_md = "**Jira Ticket**: %s" % jira_ticket_text
        if base_url_for_links and key:
            key_md = "**Jira Ticket**: [%s](%s/browse/%s)" % (jira_ticket_text, base_url_for_links.rstrip("/"), key)

        right_lines = ["**QAs**: %s" % qa_val]
        if status:
            right_lines.append("**Status**: %s" % status)
        if dev_pic_text:
            right_lines.append("**DevPIC**: %s" % dev_pic_text)
        right_lines.append("**DevStartTime**: %s" % dev_start)
        right_lines.append("**DevEndTime**: %s" % dev_end)

        lines = [key_md]
        lines.append("**Applicable Countries**: %s" % applicable_countries)
        lines.extend(right_lines)
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(lines)}})

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

    qa_field_path = _resolve_qa_field_path(jira)
    target_start_field_path = _resolve_field_path_by_name(
        jira,
        configured_path=str(SETTINGS.get("TARGET_START_FIELD_PATH", "")).strip(),
        field_name=str(SETTINGS.get("TARGET_START_FIELD_NAME", "Target start")).strip() or "Target start",
        fallback_path="",
    )
    target_end_field_path = _resolve_field_path_by_name(
        jira,
        configured_path=str(SETTINGS.get("TARGET_END_FIELD_PATH", "")).strip(),
        field_name=str(SETTINGS.get("TARGET_END_FIELD_NAME", "Target end")).strip() or "Target end",
        fallback_path="",
    )
    applicable_countries_path = str(SETTINGS.get("APPLICABLE_COUNTRIES_FIELD_PATH", "")).strip()
    logger.info("字段解析 qa_field=%s target_start=%s target_end=%s app_countries=%s", qa_field_path, target_start_field_path, target_end_field_path, applicable_countries_path)
    try:
        fields_for_search = ["summary", "status", "subtasks", "fixVersions", qa_field_path]
        if applicable_countries_path:
            fields_for_search.append(applicable_countries_path)
        issues = jira.search_issues(jql, max_results=int(SETTINGS["MAX_RESULTS"]), fields=fields_for_search)
        logger.info("从 Jira 获取到 %d 条结果", len(issues))
    except Exception as e:
        print("Jira 请求失败: %s" % e, file=sys.stderr)
        return

    exclude_statuses = SETTINGS.get("EXCLUDE_STATUSES") or []
    exclude_set = set((str(s).strip() for s in exclude_statuses if str(s).strip())) if isinstance(exclude_statuses, list) else set()
    if exclude_set:
        issues = [i for i in issues if _get_by_path((i.get("fields") or {}), "status.name") not in exclude_set]

    for issue in issues:
        try:
            _enrich_issue_with_qa_display(jira, issue, qa_field_path)
        except Exception as e:
            logger.warning("解析QA失败 key=%s err=%s", issue.get("key", ""), e)
        try:
            start_dt, end_dt, dev_pics = _calc_dev_time_range(jira, issue, target_start_field_path, target_end_field_path)
            if isinstance(start_dt, datetime):
                issue["_dev_start_dt"] = start_dt
                issue["_dev_start"] = _format_dt(start_dt, str(SETTINGS.get("TIMEZONE", "Asia/Shanghai")))
            if isinstance(end_dt, datetime):
                issue["_dev_end_dt"] = end_dt
                issue["_dev_end"] = _format_dt(end_dt, str(SETTINGS.get("TIMEZONE", "Asia/Shanghai")))
            if dev_pics:
                issue["_dev_pics"] = dev_pics
        except Exception as e:
            logger.warning("计算开发结束时间失败 key=%s err=%s", issue.get("key", ""), e)

    webhook = str(SETTINGS.get("LARK_WEBHOOK_URL", "")).strip()
    if not webhook:
        print("未配置 LARK_WEBHOOK_URL，打印到控制台，条目数=%d" % len(issues))
        return

    try:
        lark = LarkClient(webhook)
        if str(SETTINGS["MESSAGE_TYPE"]).strip().lower() == "post":
            title, content = format_post_report(
                issues,
                top_n=int(SETTINGS["REPORT_TOP_N"]),
                base_url_for_links=(SETTINGS["JIRA_BASE_URL"] if SETTINGS["ENABLE_LINKS"] else None),
                qa_field_path=qa_field_path,
                applicable_countries_path=applicable_countries_path,
                count_emoji=SETTINGS["COUNT_EMOJI"],
            )
            resp = lark.send_post_content(title, content)
            logger.info("Lark响应: %s", resp)
        else:
            title = _today_title(_report_title(), SETTINGS.get("TIMEZONE", "Asia/Shanghai"))
            card = build_interactive_card(
                issues,
                title,
                base_url_for_links=(SETTINGS["JIRA_BASE_URL"] if SETTINGS["ENABLE_LINKS"] else None),
                qa_field_path=qa_field_path,
                applicable_countries_path=applicable_countries_path,
                count_emoji=SETTINGS["COUNT_EMOJI"],
                show_limit=int(SETTINGS["SHOW_LIMIT"]),
                jira_base_url=SETTINGS["JIRA_BASE_URL"],
                jql=jql,
            )
            resp = lark.send_interactive_card(card)
            logger.info("Lark响应: %s", resp)
        
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
