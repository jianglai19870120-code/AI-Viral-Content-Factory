"""Shared V3 final-copy contract helpers."""
from __future__ import annotations

import re

WRITING_METHODS = {
    "案例", "故事", "举例", "对比", "反证", "机制", "机制解释", "小技巧",
    "步骤验证", "数据证据", "情境", "结果", "条件限定", "反问", "因果推演", "对照", "其他",
}
METHOD_PATTERNS = {
    "对比": r"同样|相比|前者|后者|另一|却|不如|而",
    "对照": r"对照|一边|另一边|一方面|另一方面|前者|后者",
    "反证": r"如果|一旦|只会|导致|最后|反而|无法|不会",
    "案例": r"案例|客户|团队|公司|项目|有人|一个人",
    "故事": r"起初|一开始|后来|最后|当时|有一次",
    "举例": r"比如|例如|举个例子",
    "机制": r"因为|所以|导致|使得|决定|说明|只有",
    "机制解释": r"因为|所以|导致|使得|决定|说明|只有",
    "小技巧": r"先|每次|每周|只要|记录|测试|核对|把",
    "步骤验证": r"第一步|第二步|先|再|随后|完成|验证|检查",
    "数据证据": r"\d|百分之|成|倍|率",
    "情境": r"当你|场景|时候|正在|刚刚|面对",
    "结果": r"结果|最后|因此|于是|带来|变成",
    "条件限定": r"前提|只有|除非|条件|不是所有|取决于",
    "反问": r"[？?]",
    "因果推演": r"因为|所以|导致|如果|那么|就会",
}
PUNCTUATION = frozenset("，。！？；：,.!?;:")


def method_matches(method: str, text: str) -> bool:
    if method == "其他":
        return True
    pattern = METHOD_PATTERNS.get(method)
    return bool(pattern and re.search(pattern, text))


def punctuation_lines(text: str) -> str:
    """Render browsing lines after every supported sentence or clause marker."""
    lines: list[str] = []
    buffer: list[str] = []
    for char in str(text).replace("\r\n", "\n"):
        buffer.append(char)
        if char in PUNCTUATION:
            value = "".join(buffer).strip()
            if value:
                lines.append(value)
            buffer = []
        elif char == "\n":
            value = "".join(buffer).strip()
            if value:
                lines.append(value)
            buffer = []
    value = "".join(buffer).strip()
    if value:
        lines.append(value)
    return "\n".join(lines)


def is_punctuation_rendered(text: str) -> bool:
    rendered = punctuation_lines(text)
    return str(text).strip() == rendered.strip()
