from formatter import format_text_report, format_post_report

# 构造示例 issues（无需访问 Jira）
issues = [
    {
        "key": "ABC-101",
        "fields": {
            "summary": "修复登录失败的异常处理",
            "status": {"name": "In Progress"},
            "assignee": {"displayName": "Alice"},
        },
    },
    {
        "key": "ABC-102",
        "fields": {
            "summary": "优化报表导出性能",
            "status": {"name": "Done"},
            "assignee": {"displayName": "Bob"},
        },
    },
    {
        "key": "XYZ-7",
        "fields": {
            "summary": "接入第三方支付测试环境",
            "status": {"name": "To Do"},
            "assignee": {"displayName": "未指派"},
        },
    },
]

# 以纯文本格式打印
print("===== TEXT 报告 =====")
print(format_text_report(issues))

# 以 Lark post 富文本内容打印（包含状态分组与链接）
print("\n===== POST 报告结构 =====")
title, content = format_post_report(
    issues,
    project_keys=["ABC", "XYZ"],
    top_n=10,
    base_url_for_links="https://your-domain.atlassian.net",
)
print("标题:", title)
print("内容块数量:", len(content))
for i, block in enumerate(content, 1):
    print(f"-- Block {i} --")
    for elem in block:
        if elem.get("tag") == "a":
            print(f"  链接: [{elem.get('text')}] -> {elem.get('href')}")
        else:
            print("  文本:", elem.get("text"))