def format_text_report(issues: list[dict]) -> str:
    count = len(issues)
    lines: list[str] = [f"今日 Jira 更新：共 {count} 条。"]
    for issue in issues[:10]:
        key = issue.get("key", "")
        fields = issue.get("fields") or {}
        summary = fields.get("summary", "")
        status_name = (fields.get("status") or {}).get("name", "")
        lines.append(f"- {key} [{status_name}] {summary}")
    return "\n".join(lines) if lines else "今日暂无更新。"


def summarize_by_status(issues: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for issue in issues:
        fields = issue.get("fields") or {}
        status_name = (fields.get("status") or {}).get("name", "Unknown")
        counts[status_name] = counts.get(status_name, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: x[0]))


def summarize_by_assignee(issues: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for issue in issues:
        fields = issue.get("fields") or {}
        assignee = (fields.get("assignee") or {}).get("displayName", "未指派")
        counts[assignee] = counts.get(assignee, 0) + 1
    # 按数量降序
    return dict(sorted(counts.items(), key=lambda x: (-x[1], x[0])))


def group_by_status(issues: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for issue in issues:
        fields = issue.get("fields") or {}
        status_name = (fields.get("status") or {}).get("name", "Unknown")
        groups.setdefault(status_name, []).append(issue)
    # 保持键排序稳定
    return dict(sorted(groups.items(), key=lambda x: x[0]))


def _get_by_path(fields: dict, path: str) -> str:
    if not path:
        return ""
    parts = [p for p in path.split(".") if p]
    cur: object = fields
    for p in parts:
        if isinstance(cur, dict):
            cur = cur.get(p)
        elif isinstance(cur, list):
            # 如果是列表，取第一个元素的该键
            cur = cur[0] if cur else None
        else:
            cur = None
        if cur is None:
            return ""
    # 最终值可能是 dict（如用户对象），尝试常见显示名
    if isinstance(cur, dict):
        return cur.get("displayName") or cur.get("name") or ""
    return str(cur) if cur is not None else ""


def _summarize_by_custom_field(issues: list[dict], field_path: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for issue in issues:
        fields = issue.get("fields") or {}
        val = _get_by_path(fields, field_path) if field_path else ""
        name = val or "未指派"
        counts[name] = counts.get(name, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: (-x[1], x[0])))


def format_post_report(
    issues: list[dict],
    project_keys: list[str] | None = None,
    top_n: int = 10,
    base_url_for_links: str | None = None,
    qa_field_path: str = "assignee.displayName",
    env_field_path: str = "",
    row_prefix_emoji: str = "🔹",
    count_emoji: str = "📌",
    at_qa_plain: bool = False,
) -> tuple[str, list[list[dict]]]:
    total = len(issues)
    # 标题改为固定值
    title = "Pending Resolved Bugs(Daily Push)"

    # 概览：仅展示待更新数量（Feishu Post 不支持样式，这里用括号强调）
    overview_text = f"{count_emoji} 【待更新数量 Pending update amount】：{total}\n"
    content: list[list[dict]] = [
        [{"tag": "text", "text": overview_text}]
    ]

    # 经办人Top：按 QA 字段路径聚合
    qa_counts = _summarize_by_custom_field(issues, qa_field_path)
    top_qas = list(qa_counts.items())[:10]
    if top_qas:
        top_line = "经办人Top：" + ", ".join([f"{name}:{cnt}" for name, cnt in top_qas])
        content.append([[{"tag": "text", "text": top_line}]][0])

    # 列表：按指定列顺序输出（不展示原先的明细与状态分布）
    for issue in issues[:top_n]:
        key = issue.get("key", "")
        fields = issue.get("fields") or {}
        qa_val = _get_by_path(fields, qa_field_path)
        priority = _get_by_path(fields, "priority.name")
        env_val = _get_by_path(fields, env_field_path)
        summary = fields.get("summary", "")

        elements: list[dict] = []
        # Key：支持链接
        prefix = f"{row_prefix_emoji} " if row_prefix_emoji else "- "
        if base_url_for_links and key:
            elements.append({"tag": "text", "text": prefix})
            elements.append({"tag": "a", "text": key, "href": f"{base_url_for_links.rstrip('/')}/browse/{key}"})
        else:
            elements.append({"tag": "text", "text": f"{prefix}{key}"})

        # Env：紧随 Key 后面
        if env_val:
            elements.append({"tag": "text", "text": f" {env_val}"})

        # QA（强调显示，用中文书名号）
        if qa_val:
            elements.append({"tag": "text", "text": f" 《{qa_val}》"})
            if at_qa_plain:
                elements.append({"tag": "text", "text": f" @{qa_val}"})
        else:
            elements.append({"tag": "text", "text": " 《未指派》"})

        # 其余字段：Priority Summary（移除 Created，并且 Env 已在 Key 后展示）
        tail = " " + " ".join([v for v in [priority, summary] if v])
        if tail.strip():
            elements.append({"tag": "text", "text": tail})

        content.append(elements)

    return title, content