from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class OtherTopicRecord:
    raw_line: str
    account: str
    title: str
    suspected_category: str
    reason: str


GROWTH_KEYWORDS = [
    "成长",
    "成事",
    "做事",
    "做成",
    "执行力",
    "专注力",
    "时间管理",
    "上班",
    "打工",
    "不上班",
    "面试",
    "空窗期",
    "方向",
    "习惯",
    "行动力",
    "解决问题",
    "超级个体",
    "个人提升",
    "感兴趣",
    "喜欢的事",
]

IP_KEYWORDS = [
    "卖课",
    "自媒体",
    "起号",
    "涨粉",
    "账号",
    "赛道",
    "内容",
    "粉丝",
    "女粉",
    "博主",
    "ip",
    "个人品牌",
]

WEALTH_KEYWORDS = [
    "赚钱",
    "收入",
    "副业",
    "搞钱",
    "财务",
    "财富",
    "投资",
    "理财",
    "保险",
    "买房",
    "房价",
    "基金",
    "股票",
    "经济",
    "成交",
    "销售",
]

AI_KEYWORDS = [
    "ai",
    "agent",
    "gpt",
    "claude",
    "prompt",
    "自动化",
    "工作流",
    "模型",
    "token",
    "应用",
    "编程",
    "代码",
]

SCIENCE_BUSINESS_KEYWORDS = [
    "创业",
    "商业",
    "生意",
    "产品",
    "增长",
    "转化",
    "定价",
    "验证",
    "团队",
    "经营",
]


def infer_category(title: str, account: str) -> tuple[str, str]:
    text = f"{account} {title}".lower()

    def has_any(words: list[str]) -> bool:
        return any(word in text for word in words)

    if has_any(AI_KEYWORDS):
        return "AI科技", "含 AI / 模型 / 自动化 / 工作流 等关键词"
    if has_any(IP_KEYWORDS):
        return "个人IP", "含 卖课 / 自媒体 / 起号 / 涨粉 / 赛道 等关键词"
    if has_any(GROWTH_KEYWORDS):
        return "能力成长", "含 成事 / 做事 / 个人提升 / 上班打工 / 执行力 等关键词"
    if has_any(WEALTH_KEYWORDS):
        return "赚钱财富", "含 赚钱 / 收入 / 投资 / 房产 / 保险 / 成交 等关键词"
    if has_any(SCIENCE_BUSINESS_KEYWORDS):
        return "科学创业", "含 创业 / 商业 / 产品 / 增长 / 经营 等关键词"
    return "待补规则", "当前未命中稳定规则，需要继续补充通用分类口径"


def parse_other_lines(audit_text: str) -> list[OtherTopicRecord]:
    marker = "## 其他类型原因"
    if marker not in audit_text:
        return []

    section = audit_text.split(marker, 1)[1]
    next_heading = re.search(r"\n##\s+", section)
    if next_heading:
        section = section[: next_heading.start()]

    records: list[OtherTopicRecord] = []
    for raw_line in section.splitlines():
        line = raw_line.strip()
        if not line.startswith("- "):
            continue

        body = line[2:]
        account = "未知账号"
        title = body

        if " - " in body:
            account, title = body.split(" - ", 1)
        elif "： " in body:
            account, title = body.split("： ", 1)
        elif ": " in body:
            account, title = body.split(": ", 1)

        suspected_category, reason = infer_category(title.strip(), account.strip())
        records.append(
            OtherTopicRecord(
                raw_line=line,
                account=account.strip(),
                title=title.strip(),
                suspected_category=suspected_category,
                reason=reason,
            )
        )
    return records


def build_report(records: list[OtherTopicRecord], audit_path: Path) -> str:
    lines = [
        "# 99_其他类型回收建议",
        "",
        f"- 来源审核文件：`{audit_path}`",
        f"- 待回收条目数：`{len(records)}`",
        "",
        "| 账号 | 选题 | 当前分类 | 疑似应归类 | 原因 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in records:
        lines.append(
            f"| {item.account} | {item.title} | 99_其他类型 | {item.suspected_category} | {item.reason} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="为 99_其他类型 审核结果补充疑似正式分类。")
    parser.add_argument("--audit-path", required=True, help="爆款选题分类审核 Markdown 文件路径")
    parser.add_argument("--output-path", help="输出 Markdown 路径；默认写到审核文件同目录")
    args = parser.parse_args()

    audit_path = Path(args.audit_path)
    audit_text = audit_path.read_text(encoding="utf-8")
    records = parse_other_lines(audit_text)

    if args.output_path:
        output_path = Path(args.output_path)
    else:
        output_path = audit_path.with_name(audit_path.stem + "_99类回收建议.md")

    output_path.write_text(build_report(records, audit_path), encoding="utf-8")
    print(str(output_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
