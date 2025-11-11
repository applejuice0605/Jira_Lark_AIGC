import os
import sys
import json
import argparse
from typing import List, Dict

import requests
from dotenv import load_dotenv

'''
使用自动脚本获取 open_id(自动化)需要
- 填写 .env 的 LARK_APP_ID 和 LARK_APP_SECRET ，并为应用开通联系人读取权限（如 contact:user:readonly ）。
- 脚本 fetch_open_ids.py 会用应用凭据获取租户令牌，按邮箱批量查询 open_id ，生成/更新 qa_map.json
'''
BASE_URL = "https://open.feishu.cn/open-apis"


def get_tenant_access_token(app_id: str, app_secret: str) -> str:
    url = f"{BASE_URL}/auth/v3/tenant_access_token/internal"
    resp = requests.post(url, json={"app_id": app_id, "app_secret": app_secret}, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") == 0 and data.get("tenant_access_token"):
        return data["tenant_access_token"]
    raise RuntimeError(f"获取tenant_access_token失败: {data}")


def batch_get_open_ids_by_emails(token: str, emails: List[str]) -> Dict[str, str]:
    """Return mapping of email -> open_id using contact v3 batch_get_id.

    API: POST /contact/v3/users/batch_get_id?user_id_type=open_id
    Body: {"emails": ["a@x", "b@y"]}
    """
    url = f"{BASE_URL}/contact/v3/users/batch_get_id?user_id_type=open_id"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    resp = requests.post(url, headers=headers, json={"emails": emails}, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"batch_get_id 失败: {data}")
    # 兼容不同返回结构
    result_map: Dict[str, str] = {}
    # 常见结构: data -> user_list -> [{email, open_id, user_id, ...}]
    user_list = (data.get("data") or {}).get("user_list") or []
    for u in user_list:
        email = u.get("email") or u.get("enterprise_email")
        open_id = u.get("open_id")
        if email and open_id:
            result_map[email] = open_id
    # 有的环境可能返回 data -> items
    items = (data.get("data") or {}).get("items") or []
    for u in items:
        email = u.get("email") or u.get("enterprise_email")
        open_id = u.get("open_id")
        if email and open_id:
            result_map[email] = open_id
    return result_map


def get_user_name_by_open_id(token: str, open_id: str) -> str:
    """Get user's display name by open_id.

    API: GET /contact/v3/users/{open_id}?user_id_type=open_id
    """
    url = f"{BASE_URL}/contact/v3/users/{open_id}?user_id_type=open_id"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        return ""
    user = (data.get("data") or {}).get("user") or {}
    # 兼容 name/display_name
    return user.get("name") or user.get("display_name") or ""


def generate_mapping(app_id: str, app_secret: str, emails: List[str]) -> Dict[str, str]:
    token = get_tenant_access_token(app_id, app_secret)
    email_to_open = batch_get_open_ids_by_emails(token, emails)
    mapping: Dict[str, str] = {}
    for email, open_id in email_to_open.items():
        name = get_user_name_by_open_id(token, open_id)
        key = name or email  # 优先使用显示名，缺失则回退邮箱
        mapping[key] = open_id
    return mapping


def read_emails_from_file(path: str) -> List[str]:
    emails: List[str] = []
    if not os.path.exists(path):
        return emails
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            e = line.strip()
            if e:
                emails.append(e)
    return emails


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Fetch Feishu open_id by emails and generate qa_map.json")
    parser.add_argument("--emails", type=str, default="", help="Comma-separated emails, e.g., a@x.com,b@y.com")
    parser.add_argument("--input", type=str, default=os.getenv("QA_EMAILS_PATH", "qa_emails.txt"), help="Path to a file with one email per line")
    parser.add_argument("--out", type=str, default=os.getenv("QA_MAP_PATH", "qa_map.json"), help="Output mapping file path")
    args = parser.parse_args()

    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        print("[ERROR] 缺少应用凭据 LARK_APP_ID / LARK_APP_SECRET，请在 .env 中配置。", file=sys.stderr)
        sys.exit(1)

    emails: List[str] = []
    if args.emails:
        emails = [e.strip() for e in args.emails.split(",") if e.strip()]
    else:
        emails = read_emails_from_file(args.input)

    if not emails:
        print(f"[ERROR] 没有可用邮箱，请通过 --emails 或在文件 {args.input} 中提供。", file=sys.stderr)
        sys.exit(1)

    try:
        mapping = generate_mapping(app_id, app_secret, emails)
    except Exception as e:
        print(f"[ERROR] 获取 open_id 失败: {e}", file=sys.stderr)
        sys.exit(2)

    # 合并到已有 qa_map（如果存在）
    out_path = args.out
    merged: Dict[str, str] = {}
    if os.path.exists(out_path):
        try:
            with open(out_path, "r", encoding="utf-8") as f:
                merged = json.load(f)
        except Exception:
            merged = {}
    merged.update(mapping)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    print(f"[OK] 已生成/更新 {out_path}，合计 {len(merged)} 条映射。")


if __name__ == "__main__":
    main()