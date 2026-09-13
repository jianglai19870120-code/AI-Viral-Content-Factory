#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
from collections import Counter
import copy
import hashlib
import importlib.util
import json
import math
import pathlib
import re
import shutil
import sys
from typing import Any

from PIL import Image
from pptx import Presentation

from common import (
    PROJECT_ROOT,
    SKILL_ROOT,
    ensure_dir,
    load_character,
    load_config,
    resolve_default_character,
    sanitize_windows_name,
    write_json,
    write_text,
)


ODD_BG = "#fcb537"
EVEN_BG = "#122142"
ODD_LINE = "black"
EVEN_LINE = "white"
SKIN_TONE_BASE = "#e8a668"
COVER_BG = ODD_BG
# Covers may only use title/source labels.  Never fall back to decorative English.
DEFAULT_COVER_SUPPORT_LABELS: list[str] = []
DEFAULT_COVER_ENGLISH_LABELS: list[str] = []
COVER_ACCENT_BLOCKS_MIN = 1
COVER_ACCENT_BLOCKS_MAX = 2
FACE_ANCHOR_FILENAME = "ip-face-anchor-top-left.png"
CONTRACT_VERSION = "4.1.0"
RENDER_PLAN_VERSION = "render-plan-v4.1"
VISUAL_BLUEPRINT_VERSION = "visual-blueprint-v4.1"
TEXT_OVERLAY_VERSION = "model-integrated-text-layout-v1"
ATTEMPT_LEDGER_FILENAME = "attempt-ledger.json"
QUALITY_REFERENCE_IMAGE = SKILL_ROOT / "assets" / "quality-reference" / "approved-visual-note-page-01.png"
# v4.1 cards must carry every source-rooted main card and evidence node in the
# native image prompt.  3,800 truncated valid dense pages before preflight.
BODY_PROMPT_MAX_CHARS = 5000
COVER_PROMPT_MAX_CHARS = 1800
KEYWORD_VISUAL_MAPPING_MIN = 2
# Four source cards plus the title preserve a single integrated scene; five
# repeatedly squeezed the central visual into a card wall even though v4.1
# permits up to five when a source genuinely needs it.
KEYWORD_VISUAL_MAPPING_MAX = 5
KEYWORD_VISUAL_MAPPING_FIELDS = (
    "keyword",
    "source_quote",
    "source_field",
    "source_label",
    "concept",
    "semantic_role",
    "visual_form",
    "expected_visual_module",
    "visual_module_id",
    "visual_objects",
    "action_or_relation",
    "page_slot",
    "prompt_fragment",
    "priority",
    "evidence_nodes",
)
EVIDENCE_NODE_FIELDS = (
    "evidence_id",
    "text",
    "source_quote",
    "source_field",
    "parent_visual_module_id",
    "visual_module_id",
    "visual_objects",
    "action_or_relation",
)
EVIDENCE_NODE_MIN_PER_MAIN = 1
EVIDENCE_NODE_MAX_PER_MAIN = 3
GENERIC_VISUAL_ACTIONS = {
    "讲解",
    "说明",
    "展示",
    "表达",
    "推进",
    "演示",
    "嵌入结构并演示",
    "人物讲解",
    "人物指向",
}
GENERIC_VISUAL_OBJECTS = {
    "问题",
    "事情",
    "内容",
    "东西",
    "方法",
    "结构",
    "概念",
    "画面",
    "概念卡",
    "通用图标",
    "抽象节点",
}
FORBIDDEN_VISUAL_OBJECT_PLACEHOLDERS = {
    "具体手绘场景",
    "关系节点",
    "通用图标",
    "占位",
    "抽象节点",
}
VISUAL_FORM_TO_MODULE = {
    "formula": "formula-board",
    "contrast": "contrast-bridge",
    "causal": "causal-chain",
    "action": "action-node",
    "question": "question-ladder",
    "object": "component-map",
    "conclusion": "concept-anchor",
}
INFO_TYPE_TO_VISUAL_FORM = {
    "formula": "formula",
    "contrast": "contrast",
    "causal": "causal",
    "action": "action",
    "question-chain": "question",
    "supporting-object": "object",
    "conclusion": "conclusion",
}
# Each rule supplies an actual drawable translation.  Labels still come only
# from the source; these objects exist solely in the illustration layer.
VISUAL_TRANSLATION_RULES: list[tuple[tuple[str, ...], tuple[str, ...], str]] = [
    (("塞满任务", "排满日程"), ("塞满的日历格", "堆叠待办卡"), "用被任务卡塞满的日历格表现日程过载"),
    (("彻底摆烂", "最后摆烂"), ("倒扣时钟", "散落任务单"), "让时钟倒扣、任务单散落，表现彻底失去执行节奏"),
    (("专注时长不同",), ("深度专注刻度", "安静工作块"), "用专注刻度对照安静工作块，表现同样时间的有效投入不同"),
    (("回复消息和刷手机",), ("消息气泡", "手机屏幕"), "让消息气泡把注意力拉向手机，表现外部打断"),
    (("恢复心力",), ("回升电量条", "充电心力电池"), "让心力电量回升，表现休息后的恢复结果"),
    (("唯一任务置顶",), ("置顶任务卡", "聚焦光束"), "把唯一任务卡置顶并用聚焦光束隔离其他事项"),
    (("分段时间轴",), ("分段时间轴", "高亮专注区"), "用分段时间轴标出深度思考与恢复的安排"),
    (("重要成果",), ("完成印章", "成果展示板"), "让完成印章落到成果展示板，表现持续完成的重要结果"),
    (("底层逻辑",), ("逻辑根基图", "双向验证箭头"), "用根基图连接两条验证箭头，表现底层逻辑而非泛化收益"),
    (("不为清单",), ("红色不为清单", "筛除任务卡"), "用不为清单筛除不适合的机会，表现先排除再选择"),
    (("做对的事和把事情做对", "做对的事情和把事情做对"), ("方向指南针", "执行验收清单"), "用指南针确定方向，再用验收清单表现执行到位"),
    (("持续在一个点上犯错",), ("同一靶点上的连续红叉", "停滞循环箭头"), "让红叉反复落在同一靶点，表现错误没有变化"),
    (("坚决不做", "什么不能做", "不能做", "不该做"), ("红色停止清单", "被划掉的任务卡"), "用停止清单划掉不做的任务，表现明确排除"),
    (("哪个机会最适合现在的我", "懂取舍", "什么该做", "什么不该做", "不能做", "判断", "机会最适合"), ("分岔选择路牌", "勾叉判断卡"), "用分岔路牌和勾叉卡表现判断、保留与舍弃"),
    (("长期稳定", "长期来看", "长期", "系统"), ("多年时间轴", "循环运转齿轮"), "用多年时间轴连接持续运转的齿轮，表现长期成立的系统"),
    (("发现错了", "马上改", "允许自己犯错", "犯错", "试错"), ("带红叉的试错稿", "即时改正铅笔"), "让红叉稿被铅笔立即改正，表现允许试错并及时调整"),
    (("定义结果", "结果是什么"), ("终点靶心", "结果验收单"), "先钉住终点靶心，再用验收单明确结果标准"),
    (("什么叫做成", "爆款视频", "粉丝", "客户"), ("爆款视频卡", "粉丝与客户目标板"), "把视频、粉丝或客户写入目标板，表现结果定义而非前期投入"),
    (("找高手学", "高手"), ("高手示范台", "跟练步骤板"), "让高手在示范台演示，学习者沿步骤板跟练"),
    (("自我迭代", "迭代"), ("迭代循环箭头", "逐版升级稿"), "用循环箭头连接逐版升级的稿件，表现持续迭代"),
    (("做对的事情是道", "做对的事就是道", "做对的事情", "做对的事"), ("方向指南针", "路线地图"), "用指南针和路线地图表现先确定正确方向"),
    (("把事情做对是术", "把事情做对"), ("执行工具箱", "结果验收清单"), "用工具箱执行，并由验收清单确认事情做对"),
    (("修炼道", "有道无术", "有术无道", "止于术"), ("方向罗盘", "工具箱分岔路"), "让方向罗盘决定工具箱的去向，表现道与术的先后关系"),
    (("自律", "习惯"), ("习惯打卡表", "连续勾选格"), "用连续勾选的打卡表表现自律习惯"),
    (("压力", "压垮"), ("压力表盘", "层层堆高的重物"), "让压力表升高并让重物逐层压下"),
    (("专注",), ("聚焦光束", "深度工作块"), "用聚焦光束只照亮一个深度工作块"),
    (("耗能", "消耗电量"), ("快速掉电电池", "能量流失刻度"), "用快速下降的电池和流失刻度表现耗能"),
    (("留白",), ("空白日历格", "呼吸间隔带"), "在拥挤日程中保留清晰的空白格和间隔带"),
    (("暂时放下", "放下"), ("侧边暂存托盘", "暂停任务卡"), "把非当前任务卡移入暂存托盘并标记暂停"),
    (("节奏",), ("起伏节奏线", "工作休息交替块"), "用起伏节奏线串联工作与休息的交替区块"),
    (("心力", "精力", "注意力"), ("电量刻度", "可充电电池"), "用电量高低和充电状态表现可用心力"),
    (("时间", "小时", "分钟", "24小时"), ("并列时钟", "时间刻度条"), "用并列时钟和长度不同的时间条表现时间差异"),
    (("切换", "一心二用", "回复微信", "刷会手机"), ("分叉任务箭头", "掉电电池"), "让任务在分叉箭头间切换，并让电量同步下降"),
    (("放松", "休息", "恢复"), ("休息椅", "充电插头"), "让人物从休息椅获得充电，连接到恢复刻度"),
    (("日程", "排满", "待办"), ("塞满的日历格", "拥挤任务卡"), "用被任务卡塞满的日历格表现排满日程"),
    (("意志力", "硬抗", "扛住"), ("拉紧绳索", "摇晃重物"), "让人物拉紧绳索硬扛重物，体现用力对抗"),
    (("破窗", "摆烂", "放弃"), ("裂开的窗格", "下坠任务卡"), "从裂开的窗格让任务卡连续下坠，表现破窗效应"),
    (("深度思考", "安静"), ("安静房间", "思考台灯"), "在安静房间中用台灯聚焦一张思考图"),
    (("战略", "战术"), ("路线地图", "执行传送带"), "将路线地图与重复运转的执行传送带并列对照"),
    (("循环", "正向"), ("闭环箭头", "循环齿轮"), "用首尾相接的箭头和齿轮呈现正向循环"),
    (("最重要", "只有一件"), ("唯一置顶卡", "聚光灯"), "把唯一任务卡置顶并用聚光灯隔离其他卡片"),
    (("选择", "挑出来", "筛选"), ("筛选漏斗", "保留任务卡"), "让多张任务卡经过漏斗，只留下被选中的一张"),
    (("文案", "写文案"), ("书写稿纸", "铅笔"), "让人物在稿纸上书写，并把文案卡放在主节点"),
    (("AI", "自动", "内容工厂"), ("自动化齿轮", "传送带"), "用齿轮驱动传送带，承接重复工作自动流转"),
    (("分块", "时间段", "高效时间"), ("分段时间轴", "高亮时间块"), "把一天分成时间块，并高亮专注时段"),
    (("成果", "衡量标准"), ("完成印章", "结果账本"), "将完成印章落到结果账本，而不是工时刻度"),
    (("装修",), ("店铺施工图", "油漆滚筒"), "用施工图和滚筒表现实体装修投入"),
    (("员工",), ("员工排班表", "服务柜台"), "用排班表连接服务柜台，表现人员投入"),
    (("餐饮", "开店"), ("餐饮店铺", "后厨设备"), "用店铺门面和后厨设备表现餐饮实体投入"),
    (("电商", "囤货", "投流", "选品", "运营"), ("库存货箱", "投流与选品面板"), "用货箱和运营面板表现电商投入与操作链"),
    (("技能", "设计", "摄影", "短视频", "培训"), ("个人技能工具箱", "客户订单"), "用技能工具箱连接客户订单，表现先验证技能需求"),
    (("客户", "成交"), ("客户人群", "成交订单"), "用客户人群与订单表现实际需求验证"),
    (("省多少时间", "省时"), ("省时沙漏", "时间刻度"), "用沙漏与时间刻度表现原文明确提到的省时关系"),
    (("赚钱", "收入", "收益"), ("价值交换卡", "结果账本"), "用价值交换卡与结果账本表现原文明确提到的收入或收益关系"),
]
MICRO_VISUAL_STYLE = "handdrawn-card-icon-module"
MICRO_VISUAL_STYLE_LABEL = "手绘卡片式图标模块"
MICRO_VISUAL_STYLE_COMPONENTS = [
    "handdrawn-card-or-node-container",
    "semantic-handdrawn-icon-or-mini-scene",
    "source-rooted-short-label",
    "restrained-flat-color-accent",
]
PPT_PAGE_HEIGHT_CM = 19.05
RESERVED_ZONE_SIZE_CM = [3, 3]
RESERVED_ZONE_SIDE_RATIO_OF_HEIGHT = round(RESERVED_ZONE_SIZE_CM[1] / PPT_PAGE_HEIGHT_CM, 5)
PRE_RENDER_AUDIT_FILENAME = "visual-preflight-audit.json"
SEMANTIC_REVIEW_FILENAME = "visual-semantic-review.json"
PREFLIGHT_BLOCK_START = "<pre-render-audit-status>"
PREFLIGHT_BLOCK_END = "</pre-render-audit-status>"
SINGLE_ROLE_PAGE_INDEXES = {1}
SINGLE_ROLE_COVER_TYPES = {"cover-3x4", "cover-4x3"}
MAX_MIC_POSE_PER_DECK = 1
SUMMARY_EXCEPTION_TITLE_CANDIDATES = {"结尾", "结语", "总结", "总结页", "最后", "最后总结"}
ACTION_FAMILY_REFERENCE_MAP = {
    # 讲解页默认以提问/指向动作承载结构；话筒只允许由正文显式话筒语义触发。
    "explaining": ("ip-ref-04-questioning.png", "ip-ref-06-pointing.png"),
    "thinking": ("ip-ref-03-thinking.png",),
    "questioning": ("ip-ref-04-questioning.png",),
    "blocking": ("ip-ref-05-stop-pose.png",),
    "pointing": ("ip-ref-06-pointing.png",),
    "shocked": ("ip-ref-07-shocked.png",),
    "confused": ("ip-ref-08-confused.png",),
    "idea": ("ip-ref-09-idea.png",),
}
ACTION_FAMILY_ALLOWED_FRAMINGS = {
    "explaining": ["three-quarter", "half-body", "full-body"],
    "thinking": ["three-quarter", "half-body", "full-body"],
    "questioning": ["three-quarter", "half-body", "full-body"],
    "blocking": ["full-body", "three-quarter"],
    "pointing": ["three-quarter", "half-body", "full-body"],
    "shocked": ["half-body", "three-quarter", "full-body"],
    "confused": ["half-body", "three-quarter", "full-body"],
    "idea": ["three-quarter", "half-body", "full-body"],
}
ACTION_FAMILY_RULES = [
    ("blocking", ("误区", "阻挡", "别急", "警示", "警告", "停止", "风险", "做不大")),
    ("shocked", ("震惊", "踩坑", "强提醒", "偷走", "危险", "代价")),
    ("confused", ("困惑", "卡点", "不理解", "迷茫", "会不会", "为什么做不到")),
    ("questioning", ("提问", "追问", "会不会", "到底", "为什么", "疑问")),
    ("thinking", ("思考", "判断", "分析", "拆解", "理解", "判断感")),
    ("idea", ("结尾", "总结", "结论", "顿悟", "从0到1", "想明白", "所以")),
    ("pointing", ("指向", "号召", "结果", "产品", "信任", "卖产品")),
    ("explaining", ("推进", "讲解", "步骤", "流程", "第1步", "第2步", "第3步", "服务", "内容", "系统")),
]

MIC_PROP_SIGNATURES = {"mic", "speaking-mic"}
EXPRESSION_FAMILY_RULES = [
    ("shocked", ("震惊", "踩坑", "强提醒", "危险")),
    ("confused", ("困惑", "卡点", "迷茫", "会不会", "不理解")),
    ("questioning", ("提问", "追问", "疑问", "为什么", "到底")),
    ("blocking", ("阻挡", "警示", "停止", "误区")),
    ("thinking", ("思考", "判断", "分析", "拆解")),
    ("idea", ("总结", "结论", "顿悟", "想明白")),
    ("pointing", ("号召", "结果", "指向", "产品")),
    ("explaining", ("讲解", "推进", "说明", "步骤", "流程")),
]
ACTION_REFERENCE_BY_INTENT = [
    # "讲解"是一个动作语义，而不是默认拿麦主持。避免结构/步骤页在
    # 没有明确话筒需求时回退为 speaking-mic，触发整套姿态重复。
    (("讲解", "推进", "说明", "流程", "操作", "演示"), ("ip-ref-04-questioning.png", "ip-ref-06-pointing.png")),
    (("思考", "判断", "分析", "拆解"), ("ip-ref-03-thinking.png",)),
    (("强调", "阻挡", "误区", "提醒"), ("ip-ref-05-stop-pose.png",)),
    (("指向", "号召", "结论", "总结", "顿悟"), ("ip-ref-06-pointing.png", "ip-ref-09-idea.png")),
    (("震惊", "踩坑", "强提醒", "惊讶"), ("ip-ref-07-shocked.png",)),
    (("困惑", "卡点", "不理解", "质疑"), ("ip-ref-08-confused.png",)),
]
DEFAULT_LAYOUT_CONSTRAINTS = [
    "标题区优先",
    "说明文案小字号",
    "配图和配字分离",
    "文字原文锚定，只允许少量源自原文的结构词",
    "正文页左下角 3cm × 3cm 纯底色禁绘区域",
    "正文页小模块统一使用手绘卡片式图标模块风格",
    "左下角不要出现任何文字",
    "左下角不要出现人物、图标、线条、箭头、坑位边缘和装饰符号",
    "左下 3cm × 3cm 禁绘区的每一个像素必须与本页主背景 RGB 完全一致；这不是近色留白，不得单独绘制浅色或深色色块、边框、阴影或残影",
]

STEP_LABEL_RE = re.compile(
    r"^\s*(?P<label>(?:第[一二三四五六七八九十百千万0-9]+[点步])|(?:[一二三四五六七八九十]+、)|(?:\d+[\.、]))"
)
EXPLICIT_STEP_TITLE_RE = re.compile(
    r"(?:第[一二三四五六七八九十百千万0-9]+(?:层|步|点|条)|认知[一二三四五六七八九十百千万0-9]+)"
)
STEP_TITLE_ENTRY_RE = re.compile(
    r"(?P<entry>(?:第[一二三四五六七八九十百千万0-9]+(?:层|步|点|条)|认知[一二三四五六七八九十百千万0-9]+)(?:[：:，,、 ]*[^。！？；\n]+)?)"
)
GUIDE_TITLE_PREFIX_RE = re.compile(
    r"^\s*(?P<prefix>(?:第[一二三四五六七八九十百千万0-9]+(?:点|步|条|讲|课|章|节|部分|阶段))|(?:认知[一二三四五六七八九十百千万0-9]+)|(?:误区[一二三四五六七八九十百千万0-9]+)|(?:步骤[一二三四五六七八九十百千万0-9]+)|(?:方法[一二三四五六七八九十百千万0-9]+)|(?:模块[一二三四五六七八九十百千万0-9]+))"
)
SUMMARY_SENTENCE_RE = re.compile(r"^(所以|总之|最后|说到底|归根结底|真正厉害的人|记住)")
INTRO_BREAK_RE = re.compile(r"(今天我就|先别|接下来|你最该|真正该补的是)")
PAGE_BREAK_RE = re.compile(r"(所以|但是|因为|真正该补的是|正确顺序是|也就是说|我见过|尤其在)")
PAGE_REF_RE = re.compile(r"^\s*(\d+)(?:\s*-\s*(\d+))?\s*$")
DECK_TITLE_RE = re.compile(r"^\s*选题[：:]\s*(.+?)\s*$")
WRAPPER_HEADING_RE = re.compile(r"^\s*#+\s*.+生成结果\s*$")
WRAPPER_META_RE = re.compile(r"^\s*(调用结构编号|调用结构文件名|生成时间)[：:].*$")
RESERVED_ZONE = {
    "position": "bottom-left",
    "size_cm": "3 x 3",
    "size_cm_array": RESERVED_ZONE_SIZE_CM,
    "side_ratio_of_height": RESERVED_ZONE_SIDE_RATIO_OF_HEIGHT,
    "pixel_formula": "side_px = round(image_height * 3 / 19.05)",
    "pixel_zone_formula": "zone = [0, image_height - side_px, side_px, image_height]",
    "fill_mode": "pure-background-no-draw",
}
RESERVED_ZONE_RULES = [
    "no_text",
    "no_icons",
    "no_character",
    "no_lines",
    "no_shapes",
    "no_scene_overlap",
    "background_only",
    "no_frame",
    "no_border",
    "no_placeholder_box",
]
BOLD_TEXT_RE = re.compile(r"\*\*(.+?)\*\*")
FORMULA_RE = re.compile(r"^[^=\n]{1,80}=[^=\n]{1,160}$")
TRANSITION_PREFIX_RE = re.compile(
    r"^(?:今天来聊聊|我就发现|其实你只要懂|刚刚我们讲了|你会发现|"
    r"原因很简单|那我是应该先|那怎么|那如何|要想|我教你|比如|第一步|具体做法是|"
    r"光找到本质还不够|后来我总结了下|我总结了|还记得最开始我说的)[，,：:\s]*"
)
NON_VISUAL_SOURCE_FRAGMENTS = {
    "而是", "但是", "可是", "所以", "因此", "然后", "同时",
    "我举个例子啊", "最后我想说的是", "其实也非常简单", "我想说的是",
    # These are grammatical lead-ins or time context, not independently
    # drawable labels.  Keeping them out prevents cards such as “考虑的不是”.
    "考虑的不是", "这些年创业",
}
WEAK_FRAGMENT_RE = re.compile(
    r"(?:只要懂|沉迷于找|应该先|必须有明确的|才能实现真正|我总结了\d+个|"
    r"那我是应该先|还是去找|还是应该先|我就发现|而这些人都有|"
    r"其实很简单|原因很简单|只有写出来|还记得最开始我说的)$"
)
KEY_INFORMATION_MARKERS = (
    "=", "本质", "判断", "误区", "必须", "不能", "只有", "结论", "条件", "失效",
    "反例", "承重墙", "脚手架", "目标", "变量", "为什么", "伪逻辑", "核心客户",
    "原样写下来", "正在服从什么", "连续追问", "清空", "找条件", "定方向",
    "小群人", "一个问题", "超出预期", "客户", "经验和案例", "更新服务",
    "信任", "功能竞争", "容易被复制", "没办法复制", "个人IP", "护城河",
    "靠IP信任", "任何产品",
)

COVER_OUTPUT_SPECS = [
    {
        "cover_type": "cover-3x4",
        "aspect_ratio": "3:4",
        "filename": "cover-3x4.png",
        "title_zone": "top-centered",
        "composition_guidance": "人物居中或偏下居中，标题在上方主标题区，标签围绕人物点缀",
    },
    {
        "cover_type": "cover-4x3",
        "aspect_ratio": "4:3",
        "filename": "cover-4x3.png",
        "title_zone": "left-or-top-horizontal",
        "composition_guidance": "人物偏一侧，标题与标签形成横向信息区，整体更像横版主视觉卡面",
    },
]


def unique_preserve_order(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def pose_digest(*parts: str) -> str:
    payload = "||".join((part or "").strip() for part in parts)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


def infer_prop_signature(*parts: str) -> str:
    haystack = "\n".join(part for part in parts if part)
    # A prohibition such as “不要主持姿态” is not a microphone request.
    mic_matches = list(re.finditer(r"(话筒|麦克风|演讲|主持|播报)", haystack))
    mic_requested = any(
        not re.search(r"(?:不要|别|禁止|避免|不做|非)\s*$", haystack[max(0, match.start() - 8):match.start()])
        for match in mic_matches
    )
    if mic_requested:
        return "mic"
    if re.search(r"(笔记本|电脑|键盘|屏幕|鼠标|系统|工具)", haystack):
        return "tool"
    if re.search(r"(纸|写|笔|清单|文档)", haystack):
        return "writing"
    return "none"


def file_sha256(path_value: str | pathlib.Path | None) -> str:
    """Return an immutable reference fingerprint without loading image bytes into prompts."""
    if not path_value:
        return ""
    path = pathlib.Path(path_value)
    if not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable_choice(values: list[str], seed: str) -> str:
    if not values:
        return ""
    return values[int(hashlib.sha256(seed.encode("utf-8")).hexdigest(), 16) % len(values)]


def _source_contains_fragment(source_quote: str, source_label: str) -> bool:
    quote_key = normalize_source_lookup(source_quote)
    label_key = normalize_source_lookup(source_label)
    return bool(quote_key and label_key and label_key in quote_key)


def is_drawable_source_concept(value: str) -> bool:
    """Reject connective or delivery-only fragments before they become visual labels."""
    normalized = normalize_source_lookup(value)
    if not normalized or normalized in {normalize_source_lookup(item) for item in NON_VISUAL_SOURCE_FRAGMENTS}:
        return False
    if re.match(r"^第[一二三四五六七八九十百0-9]+(?:步|个)", value.strip()):
        return True
    return not bool(TRANSITION_PREFIX_RE.match(value.strip()))


def _mapping_action_is_generic(action_or_relation: str) -> bool:
    normalized = re.sub(r"[\s，,\u3002！！？?;；:：“”'\"]+", "", action_or_relation)
    return normalized in {re.sub(r"\s+", "", item) for item in GENERIC_VISUAL_ACTIONS}


def _concept_core(value: str) -> str:
    """Normalize spoken wrappers so one idea cannot occupy two visual cards."""
    return re.sub(
        r"^(?:就是|也就是|其实|所谓|真正|你要|我们要|我想说的是)",
        "",
        normalize_source_lookup(value),
    )


def _concepts_are_near_duplicates(left: str, right: str) -> bool:
    left_core, right_core = _concept_core(left), _concept_core(right)
    return bool(
        left_core
        and right_core
        and (
            left_core == right_core
            or (min(len(left_core), len(right_core)) >= 4 and (left_core in right_core or right_core in left_core))
        )
    )


def _is_redundant_with_title(value: str, title: str) -> bool:
    value_key = _concept_core(value)
    title_key = re.sub(
        r"^(?:第[一二三四五六七八九十百0-9]+点)[，,、:：\s]*",
        "",
        _concept_core(title),
    )
    if not value_key or not title_key:
        return False
    if value_key == title_key:
        return True
    return value_key in title_key and len(value_key) >= 4 and len(value_key) / len(title_key) >= 0.8


def validate_keyword_visual_mappings(
    mappings: list[dict[str, Any]] | None,
    title: str,
    body: str,
    *,
    context: str = "page",
) -> list[dict[str, Any]]:
    """Validate the one canonical keyword-to-visual contract.

    A mapping must name a concrete drawable unit.  Merely storing a keyword in
    JSON is not sufficient: the same mapping is later copied into the prompt
    and independently checked by the visual preflight audit.
    """
    items = list(mappings or [])
    if not KEYWORD_VISUAL_MAPPING_MIN <= len(items) <= KEYWORD_VISUAL_MAPPING_MAX:
        raise ValueError(
            f"{context} keyword_visual_mappings 必须为 "
            f"{KEYWORD_VISUAL_MAPPING_MIN}-{KEYWORD_VISUAL_MAPPING_MAX} 条，当前为 {len(items)} 条"
        )
    page_source = "\n".join(part for part in (title, body) if part)
    page_source_key = normalize_source_lookup(page_source)
    title_key = normalize_source_lookup(title)
    seen: set[tuple[str, str, str]] = set()
    seen_concepts: list[str] = []
    seen_visual_combinations: set[tuple[str, ...]] = set()
    seen_evidence_ids: set[str] = set()
    seen_evidence_texts: set[str] = set()
    has_specific_mapping = False
    normalized_items: list[dict[str, Any]] = []
    for index, raw in enumerate(items, start=1):
        missing = [field for field in KEYWORD_VISUAL_MAPPING_FIELDS if field not in raw]
        if missing:
            raise ValueError(f"{context} keyword_visual_mappings[{index}] 缺少字段: {', '.join(missing)}")
        item = dict(raw)
        for field in (
            "keyword",
            "source_quote",
            "source_field",
            "source_label",
            "concept",
            "semantic_role",
            "visual_form",
            "expected_visual_module",
            "visual_module_id",
            "action_or_relation",
            "page_slot",
            "prompt_fragment",
        ):
            item[field] = str(item.get(field) or "").strip()
            if not item[field]:
                raise ValueError(f"{context} keyword_visual_mappings[{index}].{field} 不得为空")
        objects = [str(value).strip() for value in (item.get("visual_objects") or []) if str(value).strip()]
        if not objects:
            raise ValueError(f"{context} keyword_visual_mappings[{index}].visual_objects 不得为空")
        if any(
            placeholder in visual_object
            for visual_object in objects
            for placeholder in FORBIDDEN_VISUAL_OBJECT_PLACEHOLDERS
        ):
            raise ValueError(
                f"{context} keyword_visual_mappings[{index}].visual_objects 含占位描述，"
                "必须改成可直接画出的具体对象"
            )
        item["visual_objects"] = unique_preserve_order(objects)[:4]
        evidence_nodes = list(item.get("evidence_nodes") or [])
        if not EVIDENCE_NODE_MIN_PER_MAIN <= len(evidence_nodes) <= EVIDENCE_NODE_MAX_PER_MAIN:
            raise ValueError(
                f"{context} keyword_visual_mappings[{index}].evidence_nodes 必须为 "
                f"{EVIDENCE_NODE_MIN_PER_MAIN}-{EVIDENCE_NODE_MAX_PER_MAIN} 条"
            )
        normalized_evidence: list[dict[str, Any]] = []
        for evidence_index, raw_evidence in enumerate(evidence_nodes, start=1):
            missing_evidence = [field for field in EVIDENCE_NODE_FIELDS if field not in raw_evidence]
            if missing_evidence:
                raise ValueError(
                    f"{context} keyword_visual_mappings[{index}].evidence_nodes[{evidence_index}] 缺少字段: "
                    f"{', '.join(missing_evidence)}"
                )
            evidence = dict(raw_evidence)
            for field in (
                "evidence_id", "text", "source_quote", "source_field", "parent_visual_module_id",
                "visual_module_id", "action_or_relation",
            ):
                evidence[field] = str(evidence.get(field) or "").strip()
                if not evidence[field]:
                    raise ValueError(
                        f"{context} keyword_visual_mappings[{index}].evidence_nodes[{evidence_index}].{field} 不得为空"
                    )
            evidence_objects = unique_preserve_order(
                [str(value).strip() for value in (evidence.get("visual_objects") or []) if str(value).strip()]
            )[:4]
            if not evidence_objects or any(
                placeholder in visual_object
                for visual_object in evidence_objects
                for placeholder in FORBIDDEN_VISUAL_OBJECT_PLACEHOLDERS
            ):
                raise ValueError(
                    f"{context} keyword_visual_mappings[{index}].evidence_nodes[{evidence_index}].visual_objects 必须为具体对象"
                )
            if evidence["source_field"] not in {"source_title_full", "page_body"}:
                raise ValueError(f"{context} evidence_nodes[{evidence_index}].source_field 非法")
            if normalize_source_lookup(evidence["source_quote"]) not in page_source_key:
                raise ValueError(f"{context} evidence_nodes[{evidence_index}].source_quote 无法在当前页原文中定位")
            if not _source_contains_fragment(evidence["source_quote"], evidence["text"]):
                raise ValueError(f"{context} evidence_nodes[{evidence_index}].text 必须直接来自 source_quote")
            if evidence["parent_visual_module_id"] != item["visual_module_id"]:
                raise ValueError(f"{context} evidence_nodes[{evidence_index}] 必须归属当前主卡")
            if evidence["evidence_id"] in seen_evidence_ids or evidence["visual_module_id"] in seen_evidence_ids:
                raise ValueError(f"{context} evidence_nodes 的唯一标识不得重复")
            text_key = normalize_source_lookup(evidence["text"])
            if text_key in seen_evidence_texts or text_key == normalize_source_lookup(item["source_label"]):
                raise ValueError(f"{context} evidence_nodes 不能重复主卡或其他证据短句")
            seen_evidence_ids.update({evidence["evidence_id"], evidence["visual_module_id"]})
            seen_evidence_texts.add(text_key)
            evidence["visual_objects"] = evidence_objects
            normalized_evidence.append(evidence)
        item["evidence_nodes"] = normalized_evidence
        try:
            item["priority"] = int(item.get("priority"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{context} keyword_visual_mappings[{index}].priority 必须是整数") from exc
        if not 1 <= item["priority"] <= KEYWORD_VISUAL_MAPPING_MAX:
            raise ValueError(
                f"{context} keyword_visual_mappings[{index}].priority 必须在 1-{KEYWORD_VISUAL_MAPPING_MAX} 之间"
            )
        quote_key = normalize_source_lookup(item["source_quote"])
        if not quote_key or quote_key not in page_source_key:
            raise ValueError(
                f"{context} keyword_visual_mappings[{index}].source_quote 无法在当前页原文中定位: "
                f"{item['source_quote']}"
            )
        if not _source_contains_fragment(item["source_quote"], item["source_label"]):
            raise ValueError(
                f"{context} keyword_visual_mappings[{index}].source_label 必须直接来自 source_quote: "
                f"{item['source_label']}"
            )
        if normalize_source_lookup(item["keyword"]) not in quote_key:
            raise ValueError(f"{context} keyword_visual_mappings[{index}].keyword 必须来自 source_quote")
        if normalize_source_lookup(item["source_label"]) == title_key or _is_redundant_with_title(item["source_label"], title):
            raise ValueError(
                f"{context} keyword_visual_mappings[{index}].source_label 与页面标题重复，"
                "标题已单独渲染，映射卡必须选择其他原文关键词或短语"
            )
        if item["source_field"] not in {"source_title_full", "page_body"}:
            raise ValueError(f"{context} keyword_visual_mappings[{index}].source_field 非法")
        if item["expected_visual_module"] != VISUAL_FORM_TO_MODULE.get(item["visual_form"]):
            raise ValueError(f"{context} keyword_visual_mappings[{index}] 的 visual_form 与模块不匹配")
        signature = (
            normalize_source_lookup(item["source_quote"]),
            normalize_source_lookup(item["keyword"]),
            item["semantic_role"],
        )
        if signature in seen:
            raise ValueError(f"{context} keyword_visual_mappings[{index}] 与前面映射重复")
        if any(_concepts_are_near_duplicates(item["concept"], prior) for prior in seen_concepts):
            raise ValueError(
                f"{context} keyword_visual_mappings[{index}] 与前面映射表达同一概念，"
                "不得用口语前缀或长短句重复占用版面"
            )
        seen.add(signature)
        seen_concepts.append(item["concept"])
        visual_combination = tuple(normalize_source_lookup(value) for value in item["visual_objects"])
        if visual_combination in seen_visual_combinations:
            raise ValueError(
                f"{context} keyword_visual_mappings[{index}] 与前面映射使用同一组图形对象，"
                "同一页必须按各自原文语义改用不同具体对象"
            )
        seen_visual_combinations.add(visual_combination)
        non_generic_objects = [
            value for value in item["visual_objects"]
            if normalize_source_lookup(value) not in {normalize_source_lookup(generic) for generic in GENERIC_VISUAL_OBJECTS}
        ]
        if not _mapping_action_is_generic(item["action_or_relation"]) and non_generic_objects:
            has_specific_mapping = True
        normalized_items.append(item)
    if not has_specific_mapping:
        raise ValueError(
            f"{context} keyword_visual_mappings 不得只使用‘讲解/说明/展示/推进’类泛化动作，"
            "至少一条必须把原文概念落到具体对象、动作或关系"
        )
    return sorted(normalized_items, key=lambda item: item["priority"])


def _visual_mapping_role(information_type: str) -> str:
    return {
        "formula": "formula-relation",
        "contrast": "contrast",
        "causal": "cause-effect",
        "action": "action",
        "question-chain": "question",
        "conclusion": "result",
        "supporting-object": "object",
    }.get(information_type, "context-link")


def infer_visual_form(information_type: str, concept: str, source_quote: str) -> str:
    if information_type == "formula":
        return "formula"
    if re.search(r"(对比|不同|区别|而不是|不是.+而是|却|比.+更)", source_quote):
        return "contrast"
    # A source-native "from manual repetition to repeatable operation" is a
    # transformation mechanism, even when its short card label is a concrete
    # noun such as “赚钱” or “系统”.  Classify only this explicit before/after
    # relation as causal; ordinary object cards remain component maps.
    if re.search(r"从.+(?:重新来一遍|每次都靠自己).*(?:变成|到).*(?:重复运转|不再依赖)", source_quote):
        return "causal"
    if re.search(r"(消耗|恢复|导致|不然|破坏|越.+越|才能)", source_quote):
        return "causal"
    if any(term in concept for term in ("放松", "休息", "恢复", "切换", "选择", "筛选", "写文案", "分块")):
        return "action"
    if information_type == "question-chain":
        return "question"
    if information_type in {"supporting-object", "conclusion", "context"}:
        return "object"
    return INFO_TYPE_TO_VISUAL_FORM.get(information_type, "object")


def _visual_mapping_action(information_type: str, concept: str, visual_description: str) -> str:
    if information_type == "formula":
        return f"{visual_description}，并将“{concept}”放入同一公式板保持关系"
    if information_type == "contrast":
        return f"{visual_description}，将“{concept}”的两种条件或结果并排对照"
    if information_type == "causal":
        return f"{visual_description}，沿“{concept}”建立单向因果箭头"
    if information_type == "action":
        return f"{visual_description}，让人物或对象执行“{concept}”并落到下一节点"
    if information_type == "question-chain":
        return f"{visual_description}，把“{concept}”拆成逐层下钻的问题节点"
    if information_type == "conclusion":
        return f"{visual_description}，让前置依据汇聚到“{concept}”的结论锚点"
    if information_type == "supporting-object":
        return f"{visual_description}，把“{concept}”作为可操作对象嵌入主结构"
    return f"{visual_description}，把“{concept}”与本页主判断建立明确关系"


def _visual_mapping_slot(visual_form: str, position: int) -> str:
    preferred = {
        "conclusion": "primary-center",
        "formula": "primary-center",
        "contrast": "primary-split",
        "causal-chain": "flow-center",
        "action-node": "flow-node",
        "question": "vertical-center",
        "object": "support-side",
    }.get(visual_form)
    if preferred and position == 0:
        return preferred
    return ["upper-left", "upper-right", "lower-center", "side-support", "center-support"][position % 5]


def translate_visual_concept(concept: str, source_quote: str, information_type: str) -> tuple[list[str], str]:
    # Translate the selected concept, not every word in its source sentence.
    # Otherwise a long sentence containing “心力” turns every keyword into a
    # battery, which is exactly the generic-repetition failure this contract
    # is intended to prevent.
    haystack = concept
    source_key = normalize_source_lookup(source_quote)
    if "没流量不是因为你讲干货" in haystack:
        return ["干货视频卡", "讲课黑板", "专业能力工具箱", "下滑播放曲线"], "把干货视频卡和讲课黑板放在下滑播放曲线旁划掉，再将箭头指向专业能力工具箱，呈现流量问题不在讲干货或太专业"
    if "素人" in haystack and "不是明星" in source_key and "不是企业家" in source_key:
        return ["素人头像", "明星聚光灯", "企业家名片", "空白标签牌"], "把素人头像与明星聚光灯、企业家名片对照，并把空白标签牌挂在素人一侧，呈现素人缺少已有标签"
    if "用干货型视频建立IP信任" in haystack or ("干货型视频" in haystack and "IP信任" in source_key):
        return ["干货型视频播放卡", "IP信任握手徽章", "需要你的人头像"], "让干货型视频播放卡连接IP信任握手徽章，再指向需要你的人头像，呈现用干货型视频建立IP信任"
    if "认出你理解他的处境" in haystack:
        return ["需要你的人头像", "自身处境镜面", "理解对勾"], "让需要你的人头像在自身处境镜面前得到理解对勾，呈现先认出你理解他的处境"
    if "认可你提出的一套解决方案" in haystack:
        return ["解决方案卡", "认可印章", "需要你的人头像"], "让需要你的人头像给解决方案卡盖认可印章，呈现认可你提出的一套解决方案"
    if "知道客户想听什么" in haystack:
        return ["客户提问气泡", "倾听耳朵", "需求清单"], "让客户提问气泡进入倾听耳朵，再归入需求清单，呈现理解客户想听、恐惧和需要什么"
    # The card label may legitimately be the same short source word on two
    # pages.  For “系统”, retain the selected word but let the source sentence
    # determine whether it means a missing operating mechanism or a built
    # content-production mechanism.  This gives the cross-page gate distinct
    # source-rooted object/relation combinations without weakening its check
    # for truly identical motifs.
    if "系统" in haystack:
        if "系统思维驱动赚钱" in source_key:
            return ["系统思维方向盘", "价值传动连杆"], "让系统思维方向盘带动价值传动连杆，表现用系统思维驱动赚钱"
        if "做事不会构建系统" in source_key:
            return ["散落技巧卡", "断开的传动齿轮"], "让散落技巧卡无法咬合断开的传动齿轮，表现做事没有形成系统"
        if "持续稳定产出内容的生产系统" in source_key:
            return ["内容排产日历", "稳定输出传送带"], "让内容排产日历流向稳定输出传送带，表现持续稳定地产出内容"
        if "内容生产系统" in source_key:
            return ["内容排程看板", "自动化生产传送带"], "让内容排程看板流向自动化生产传送带，表现内容持续稳定产出"
        if "每次都靠自己重新来一遍" in source_key and "重复运转的系统" in source_key:
            return ["手工重来循环箭头", "自动运转齿轮"], "让手工重来循环箭头切换为自动运转齿轮，表现赚钱不再依赖每次重新开始"
        if "系统卡点" in source_key:
            return ["系统瓶颈卡", "逐项修复扳手"], "让系统瓶颈卡依次经过修复扳手，表现找到卡点后一个一个解决"
    # “客户” can recur across a dry-goods article, but the source may mean
    # listening to demand, winning a transaction, or a buyer recognizing their
    # own problem. Keep the same source label only when the source-rooted
    # objects and relation change with that meaning; otherwise the deck would
    # repeat an identical client/target-board motif across pages.
    if normalize_source_lookup(concept) == "客户" or "充分的理解客户需求" in haystack:
        if "充分的理解客户需求" in source_key:
            return ["客户需求便签", "倾听耳朵", "问题清单"], "让倾听耳朵收集客户需求便签并归入问题清单，表现先理解客户真正需要什么"
        if "获得客户并成交" in source_key:
            return ["评论追问气泡", "目标客户头像", "成交订单"], "让评论追问气泡连到目标客户头像和成交订单，表现以客户追问验证是否能获得客户并成交"
        if "客户最先识别" in source_key and "自己的问题" in source_key:
            return ["客户头像", "自身问题镜像", "方案判断量尺"], "让客户头像先在自身问题镜像中识别处境，再用方案判断量尺评估专业是否有用"
    matched_rules: list[tuple[int, tuple[str, ...], str]] = []
    for terms, objects, description in VISUAL_TRANSLATION_RULES:
        matched_lengths = [len(term) for term in terms if term in haystack]
        if matched_lengths:
            matched_rules.append((max(matched_lengths), objects, description))
    if matched_rules:
        _length, objects, description = max(matched_rules, key=lambda item: item[0])
        return list(objects), description
    # Do not infer investment from another clause in a long source quote.  A
    # restaurant's “一年能赚100万” and a result target “1万粉丝” are outcome
    # statements, even if that same paragraph later mentions an investment.
    if re.search(r"(?:先拿|投入|本金|囤货)", concept):
        return ["前期投入单", "风险刻度"], "用前期投入单和风险刻度表现原文明确提到的资金投入"
    fallback = {
        "formula": (["等式天平", "变量卡片"], "用天平和变量卡片保持原文中的等式关系"),
        "contrast": (["左右对照刻度", "分叉箭头"], "用左右刻度和分叉箭头呈现两端差异"),
        "causal": (["因果骨牌", "单向箭头"], "用连续骨牌和单向箭头呈现因果传递"),
        "action": (["步骤脚印", "操作工具"], "让步骤脚印指向被实际操作的工具"),
        "question-chain": (["放大镜", "问题阶梯"], "让放大镜沿问题阶梯逐层下钻"),
        "conclusion": (["聚光结论牌", "汇聚箭头"], "让多条依据沿箭头汇聚到结论牌"),
    }
    if information_type in fallback:
        return fallback[information_type]
    # Unknown context nouns do not get a fabricated generic card. The caller
    # tries another source candidate and fails closed if fewer than two
    # concrete mappings remain.
    return [], ""


def extract_visual_concepts(source_quote: str, fallback: str) -> list[str]:
    """Prefer short, source-native concepts that have a drawable translation.

    This prevents a whole spoken sentence from becoming a fake “keyword” and
    gives one page genuinely different objects/relations instead of five cards
    all carrying the same generic topic.
    """
    matches: list[tuple[int, int, str]] = []
    for terms, _objects, _description in VISUAL_TRANSLATION_RULES:
        for term in terms:
            position = source_quote.find(term)
            if position >= 0:
                matches.append((-len(term), position, term))
    result = unique_preserve_order([term for _length, _position, term in sorted(matches)])
    short_source_phrases = []
    for raw in re.split(r"[，,。；;：:！？!?\n]+", source_quote):
        phrase = strip_step_label(raw).strip()
        compact_phrase = re.sub(
            r"^(?:(?:但|不过|而且|然后|所以|其实)[，,\s]*)?"
            r"(?:(?:你要|我要|我们要)[，,\s]*)?(?:先)?",
            "",
            phrase,
            count=1,
        ).strip()
        if compact_phrase and _source_contains_fragment(phrase, compact_phrase):
            phrase = compact_phrase
        is_structural_label = bool(re.fullmatch(r"(?:原因|误区|第)?\d+[点步条个]?", phrase))
        contains_known_term = any(term in phrase for terms, _objects, _description in VISUAL_TRANSLATION_RULES for term in terms)
        if 2 <= len(phrase) <= 12 and not is_structural_label and not contains_known_term:
            short_source_phrases.append(phrase)
    result = unique_preserve_order(result + short_source_phrases)
    if result:
        return result[:KEYWORD_VISUAL_MAPPING_MAX]
    inferred = [term for term in extract_source_terms(source_quote, limit=3, max_len=10) if term]
    if inferred:
        return inferred[:3]
    fallback = trim_source_fragment(fallback)
    return [fallback] if fallback else []


PARALLEL_BRANCH_RE = re.compile(r"(?m)^\s*第\s*(?P<index>[0-9一二三四五六七八九十]+)\s*个[，,、:：]?")
NUMBERED_STEP_RE = re.compile(r"(?m)^\s*第\s*(?P<index>[0-9一二三四五六七八九十]+)\s*步[，,、:：]?")
DATA_TO_PRODUCTION_SYSTEM_RE = re.compile(
    r"(?P<data>我从来不看视频数据)\s*[，,、]?\s*"
    r"(?P<viral>更不关心一条视频爆没爆)\s*[，,、]?\s*"
    r"而是\s*(?P<system>先去搭建一套持续稳定产出内容的生产系统)"
)


def _numbered_branch_blocks(body: str) -> list[dict[str, str]]:
    """Return source-native blocks for a `第1个/第2个/第3个` choice page."""
    matches = list(PARALLEL_BRANCH_RE.finditer(body or ""))
    blocks: list[dict[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        text = str(body[match.start():end]).strip()
        if text:
            blocks.append({"branch_id": f"branch-{match.group('index')}", "source_quote": text})
    return blocks


def _numbered_step_blocks(body: str) -> list[dict[str, str]]:
    """Return source-native blocks for a `第1步/第2步/第3步` procedure page."""
    matches = list(NUMBERED_STEP_RE.finditer(body or ""))
    blocks: list[dict[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        text = str(body[match.start():end]).strip()
        if text:
            blocks.append({"step_id": f"step-{match.group('index')}", "source_quote": text})
    return blocks


def _build_data_to_production_system_mappings(body: str) -> list[dict[str, Any]]:
    """Freeze the explicit metrics-to-production-system contrast as two cards.

    The source itself must say that the speaker ignores both video data and
    whether a video went viral *and then* builds a stable production system.
    This prevents a generic allocator from splitting the one causal turn into
    bare cards and borrowing evidence from the next sentence.
    """
    compact_body = "\n".join(line.strip() for line in (body or "").splitlines() if line.strip())
    match = DATA_TO_PRODUCTION_SYSTEM_RE.search(compact_body)
    if not match:
        return []
    data, viral, system = (match.group(name).strip() for name in ("data", "viral", "system"))
    source_quote = f"{data}，{viral}，而是{system}"
    cards = [
        {
            "keyword": data, "source_quote": source_quote, "source_field": "page_body",
            "source_label": data, "concept": "不看数据转向内容生产系统", "semantic_role": "contrast",
            "visual_form": "contrast", "expected_visual_module": "contrast-bridge",
            "visual_module_id": "metrics-to-production-system-data",
            "visual_objects": ["视频数据仪表盘", "爆款火焰标签", "转向内容生产看板"],
            "visual_description": "把视频数据仪表盘和爆款火焰标签划掉，再用转向箭头指向内容生产看板",
            "action_or_relation": "将视频数据仪表盘和爆款火焰标签划掉，转向内容生产看板，表现不看数据、不关心爆没爆而先搭生产系统",
            "page_slot": "primary-split",
            "prompt_fragment": (
                f"对照主卡「{data}」使用contrast-bridge模块：画出视频数据仪表盘、爆款火焰标签、转向内容生产看板；"
                "将前两者划掉并经转向箭头连到生产看板，表现不看数据、不关心爆没爆而先搭生产系统；"
                "在同一手绘模块内直接填入精确原文中文标签。"
            ),
            "priority": 1,
            "evidence_nodes": [{
                "evidence_id": "metrics-to-production-system-data-evidence-01", "text": viral,
                "source_quote": source_quote, "source_field": "page_body",
                "parent_visual_module_id": "metrics-to-production-system-data",
                "visual_module_id": "metrics-to-production-system-data-evidence-01",
                "visual_objects": ["爆款火焰标签", "划线符号", "转向箭头"],
                "action_or_relation": "把爆款火焰标签划掉并接入转向箭头，作为不看数据主卡的内部佐证",
            }],
        },
        {
            "keyword": "持续稳定产出内容的生产系统", "source_quote": source_quote, "source_field": "page_body",
            "source_label": "持续稳定产出内容的生产系统", "concept": "先搭持续内容生产系统", "semantic_role": "contrast",
            "visual_form": "contrast", "expected_visual_module": "contrast-bridge",
            "visual_module_id": "metrics-to-production-system-build",
            "visual_objects": ["被划线的视频数据仪表盘", "内容生产看板", "稳定输出传送带"],
            "visual_description": "从被划线的视频数据仪表盘转向内容生产看板，再接到稳定输出传送带",
            "action_or_relation": "从被划线的视频数据仪表盘转向内容生产看板与稳定输出传送带，表现先搭系统而非追逐数据和爆款",
            "page_slot": "upper-right",
            "prompt_fragment": (
                "对照主卡「持续稳定产出内容的生产系统」使用contrast-bridge模块：画出被划线的视频数据仪表盘、内容生产看板、稳定输出传送带；"
                "从被划线的仪表盘经转向箭头连到看板和传送带，表现先搭系统而非追逐数据和爆款；"
                "在同一手绘模块内直接填入精确原文中文标签。"
            ),
            "priority": 2,
            "evidence_nodes": [{
                "evidence_id": "metrics-to-production-system-build-evidence-01", "text": "而是先去搭建一套",
                "source_quote": source_quote, "source_field": "page_body",
                "parent_visual_module_id": "metrics-to-production-system-build",
                "visual_module_id": "metrics-to-production-system-build-evidence-01",
                "visual_objects": ["搭建扳手", "内容生产看板", "稳定输出传送带"],
                "action_or_relation": "用搭建扳手连接内容生产看板和稳定输出传送带，作为先搭系统主卡的内部动作证据",
            }],
        },
    ]
    ensure_final_visible_text_contract(cards, "")
    return cards


def _build_system_income_mappings(body: str, title: str = "") -> list[dict[str, Any]]:
    """Freeze five source-native system/income mechanisms before generic ranking.

    These are deliberately conjunction-gated.  They cover mechanisms which a
    keyword allocator can otherwise split across unrelated cards (or reduce to
    a generic account/time icon): skill collection causing overload, income
    tied to labour time, durable system outcomes, repeatable operation, and a
    product-to-reinvestment loop.  Do not loosen the predicates: this is a
    narrow repair for explicit source relations, not a new generic theme rule.
    """
    source = re.sub(r"[，,、。；;：:“”\"'（）()\s]+", "", normalize_source_lookup(body))

    def card(
        card_id: str,
        label: str,
        quote: str,
        objects: list[str],
        relation: str,
        evidence: list[tuple[str, str, list[str], str]],
        position: int,
        form: str = "causal",
        evidence_source_field: str = "page_body",
    ) -> dict[str, Any]:
        module = VISUAL_FORM_TO_MODULE[form]
        return {
            "keyword": label,
            "source_quote": quote,
            "source_field": "page_body",
            "source_label": label,
            "concept": label,
            "semantic_role": _visual_mapping_role({
                "causal": "causal", "action": "action", "contrast": "contrast",
                "conclusion": "conclusion", "supporting-object": "supporting-object",
            }.get(form, "causal")),
            "visual_form": form,
            "expected_visual_module": module,
            "visual_module_id": card_id,
            "visual_objects": objects,
            "visual_description": relation,
            "action_or_relation": relation,
            "page_slot": _visual_mapping_slot(form, position),
            "prompt_fragment": (
                f"原文机制主卡「{label}」使用{module}模块：画出{'、'.join(objects)}；"
                f"{relation}；主卡与每条内部证据均直接写入同一手绘模块。"
            ),
            "priority": position + 1,
            "evidence_nodes": [{
                "evidence_id": f"{card_id}-evidence-{number:02d}",
                "text": text,
                "source_quote": evidence_quote,
                "source_field": evidence_source_field,
                "parent_visual_module_id": card_id,
                "visual_module_id": f"{card_id}-evidence-{number:02d}",
                "visual_objects": evidence_objects,
                "action_or_relation": evidence_relation,
            } for number, (text, evidence_quote, evidence_objects, evidence_relation) in enumerate(evidence, start=1)],
        }

    if all(fragment in source for fragment in (
        "总把赚钱当成收集技巧", "你掌握了越多技巧", "你就越忙", "就越混乱", "每个技巧都在争夺你的时间",
    )):
        return [
            card(
                "skill-collection-overload", "总把赚钱当成收集技巧", "总把赚钱当成收集技巧。",
                ["散落技巧卡堆", "断开的系统齿轮", "拥挤任务时钟"],
                "让不断堆叠的技巧卡堵住断开的系统齿轮，明确呈现收集技巧而非构建系统的起点",
                [("你掌握了越多技巧", "学个开头钩子，学个剪辑技巧，你掌握了越多技巧，", ["叠高技巧卡", "超载红色刻度"], "用叠高技巧卡压过超载刻度，表现技巧越多的累积")],
                0,
            ),
            card(
                "skill-overload-chaos", "你就越忙，越不知道在哪个点发力才有用，就越混乱", "你就越忙，越不知道在哪个点发力才有用，就越混乱。",
                ["多向任务箭头", "失焦发力靶盘", "混乱日程表"],
                "让多向技巧任务箭头同时冲向失焦靶盘并挤乱日程表，呈现技巧越多导致越忙越乱且缺少系统发力点",
                [("每个技巧都在争夺你的时间", "每个技巧都在争夺你的时间，", ["拉扯时间绳", "多个技巧卡"], "让多个技巧卡拉扯同一根时间绳，作为忙乱因果的内部证据")],
                1,
            ),
        ]

    if all(fragment in source for fragment in (
        "收入是不是还和你的时间绑定", "只要你停下来收入就停了", "没有构建好系统", "拿命换钱",
    )):
        return [
            card(
                "income-time-binding", "你的收入是不是还和你的时间绑定", "你的收入是不是还和你的时间绑定。",
                ["收入账单", "工时钟表", "捆绑绳结"],
                "把收入账单与工时钟表用捆绑绳结锁在一起，呈现收入仍依赖本人时间投入",
                [("只要你停下来，收入就停了", "只要你停下来，收入就停了，", ["暂停按钮", "停摆收入流水"], "按下暂停按钮后收入流水立即停摆，呈现停下即无收入的因果")],
                0,
            ),
            card(
                "life-for-income", "就等于拿命换钱", "就等于拿命换钱",
                ["生命能量电池", "换钱传送带", "警示沙漏"],
                "让生命能量电池被换钱传送带持续消耗，并以警示沙漏标出没有系统的代价",
                [("没有构建好系统", "那其实就是没有构建好系统，", ["断开齿轮", "未完成流程板"], "用断开齿轮和未完成流程板证明收入停摆来自系统尚未构建")],
                1,
            ),
        ]

    if all(fragment in source for fragment in (
        "一次构建持续收益", "有闲有钱又松弛", "想好选题20分钟就拍完了", "打造一套自己的内容生产系统",
    )):
        return [
            card(
                "build-once-durable-return", "一次构建，持续收益", "一次构建，持续收益。",
                ["一次搭建扳手", "持续收益流水", "循环系统齿轮"],
                "让一次搭建扳手启动循环系统齿轮并持续输出收益流水，呈现一次构建而非一次性劳作",
                [("一次学习，终身可用", "就是一次学习，终身可用。", ["学习笔记卡", "长期使用时间轴"], "让学习笔记卡沿长期时间轴持续被调用，作为一次构建的长期基础")],
                0,
            ),
            card(
                "wealth-and-leisure", "有闲有钱，又松弛", "他们的典型特征就是，有闲有钱，又松弛。",
                ["闲置时间躺椅", "充足现金罐", "放松姿态人物"],
                "让时间躺椅、现金罐和放松人物并列，呈现系统带来的闲钱与松弛状态",
                [("我身边有很多这样的老板", "我身边有很多这样的老板，", ["经营者人物", "稳定系统看板"], "让经营者站在稳定系统看板旁，说明闲钱松弛来自可复用经营系统")],
                1,
            ),
            card(
                "content-system-twenty-minutes", "想好选题20分钟就拍完了", "想好选题20分钟就拍完了。",
                ["选题便签", "二十分钟沙漏", "拍摄手机"],
                "让选题便签经过二十分钟沙漏直接连到拍摄手机，呈现内容拍摄耗时被系统压缩",
                [("去打造一套自己的内容生产系统", "就是因为我在前面已经花了时间，去打造一套自己的内容生产系统", ["内容排程看板", "自动化生产传送带"], "用内容排程看板连接自动化生产传送带，证明二十分钟完成拍摄来自前置内容系统")],
                2,
            ),
        ]

    if all(fragment in source for fragment in (
        "把赚钱这件事", "每次都靠自己重新来一遍", "变成一套可以重复运转的系统",
    )):
        # Keep source evidence as exact fragments.  Both quoted and unquoted
        # source manuscripts occur in the library, so do not normalize away a
        # quote mark and then claim the altered string is the source quote.
        title_source_quote = title.rstrip("？?。！!").strip()
        manual_restart_match = re.search(r"从[“\"]?每次都靠自己重新来一遍[”\"]?[，,。]?", body)
        manual_restart_quote = manual_restart_match.group(0) if manual_restart_match else "每次都靠自己重新来一遍"
        return [
            card(
                "income-manual-restart", "把赚钱这件事", "说白了，就是把赚钱这件事，",
                ["手工重来箭头", "单次收入工位", "重复劳动人物"],
                "让重复劳动人物在单次收入工位不断沿手工重来箭头返回起点，呈现赚钱每次都要本人重新开始",
                [("每次都靠自己重新来一遍", manual_restart_quote, ["回到起点的循环箭头", "人工操作台"], "用回到起点的循环箭头连接人工操作台，作为手工重来模式的可见证据")],
                0,
            ),
            card(
                "income-repeatable-system", "变成一套可以重复运转的系统", "变成一套可以重复运转的系统。",
                ["闭环运转齿轮", "自动收入流水", "无需重启的流程环"],
                "让闭环运转齿轮持续带动自动收入流水和无需重启的流程环，呈现可重复运转的赚钱系统",
                [("用系统思维帮我们赚钱", title_source_quote, ["系统思维方向盘", "价值传动连杆"], "让系统思维方向盘驱动价值传动连杆，说明该重复系统服务于赚钱")],
                1,
                evidence_source_field="source_title_full",
            ),
        ]

    if all(fragment in source for fragment in (
        "先把它变成产品", "稳定找到客户完成成交做好交付", "继续投入到最影响收入的那个环节", "不断找到系统卡点", "一个一个解决",
    )):
        return [
            card(
                "bottleneck-one-by-one", "不断找到系统卡点，一个一个解决", "所以系统思维不是让你一次把所有事情都做好，而是不断找到系统卡点，一个一个解决。",
                ["系统瓶颈卡", "逐项修复扳手", "前进齿轮轨道"],
                "让系统瓶颈卡逐一经过修复扳手并推动前进齿轮轨道，呈现卡点不是一次做完而是一个一个解决",
                [("不是让你一次把所有事情都做好", "所以系统思维不是让你一次把所有事情都做好，而是不断找到系统卡点，一个一个解决。", ["一次做完叉号", "待修复瓶颈卡"], "划掉一次做完的堆叠任务，突出逐个修复系统卡点")],
                0,
            ),
            card(
                "product-customer-deal-delivery", "稳定找到客户、完成成交、做好交付", "再想办法稳定找到客户、完成成交、做好交付；",
                ["产品盒", "客户人群", "成交订单", "交付清单"],
                "让产品盒依次流向客户人群、成交订单和交付清单，完整呈现产品到客户、成交、交付的业务链条",
                [("先把它变成产品", "先把它变成产品；", ["能力工具", "产品盒"], "让能力工具装入产品盒，作为客户成交交付链条的起点")],
                1,
                "action",
            ),
            card(
                "income-reinvest-loop", "最后把赚到的钱和时间，继续投入到最影响收入的那个环节", "最后把赚到的钱和时间，继续投入到最影响收入的那个环节。",
                ["收益钱袋", "时间沙漏", "高影响环节靶盘", "再投入箭头"],
                "让收益钱袋和时间沙漏沿再投入箭头回到高影响环节靶盘，呈现赚钱系统的再投入闭环",
                [("你每解决掉一个瓶颈，整个赚钱系统就会往前走一步", "你每解决掉一个瓶颈，整个赚钱系统就会往前走一步。", ["被修复的瓶颈卡", "前进一步的齿轮"], "让每张被修复的瓶颈卡推动齿轮前进一步，证明再投入后系统持续前行")],
                2,
            ),
        ]
    return []


def _build_comment_validation_mappings(body: str) -> list[dict[str, Any]]:
    """Freeze the source-native comment-to-customer validation loop.

    This is not a generic metrics page. The source explicitly separates a
    target customer's follow-up question, the corrective rewrite after three
    misses, the customer-and-deal objective, and growth/play/update as merely
    process signals. Each relationship needs its own complete text card and
    drawable objects; a short “不要把涨粉” shard cannot stand in for that
    source decision.
    """
    source = re.sub(r"[\s，,、。！？；;]+", "", normalize_source_lookup(body))
    required = (
        "评论和私信里有没有目标客户追问",
        "连续三条都没有这类追问",
        "停止沿用这套开头",
        "重写人群和痛苦",
        "不要把涨粉流量持续更新当成目标",
        "获得客户并成交当成唯一目标",
        "涨粉播放和更新频率可以记录",
        "它们只是过程信号不是最终结果",
    )
    if not all(fragment in source for fragment in required):
        return []

    def card(
        card_id: str,
        label: str,
        quote: str,
        objects: list[str],
        relation: str,
        evidence_text: str,
        evidence_quote: str,
        evidence_objects: list[str],
        evidence_relation: str,
        position: int,
        visual_form: str = "causal",
    ) -> dict[str, Any]:
        module = VISUAL_FORM_TO_MODULE[visual_form]
        return {
            "keyword": label,
            "source_quote": quote,
            "source_field": "page_body",
            "source_label": label,
            "concept": label,
            "semantic_role": _visual_mapping_role("causal" if visual_form == "causal" else "action"),
            "visual_form": visual_form,
            "expected_visual_module": module,
            "visual_module_id": card_id,
            "visual_objects": objects,
            "visual_description": relation,
            "action_or_relation": relation,
            "page_slot": _visual_mapping_slot(visual_form, position),
            "prompt_fragment": f"评论验证主卡「{label}」使用{module}模块：画出{'、'.join(objects)}；{relation}；主卡与内部证据必须在同一手绘模块中填入精确原文。",
            "priority": position + 1,
            "evidence_nodes": [{
                "evidence_id": f"{card_id}-evidence-01",
                "text": evidence_text,
                "source_quote": evidence_quote,
                "source_field": "page_body",
                "parent_visual_module_id": card_id,
                "visual_module_id": f"{card_id}-evidence-01",
                "visual_objects": evidence_objects,
                "action_or_relation": evidence_relation,
            }],
        }

    comment_quote = "评论和私信里有没有目标客户追问。\n连续三条都没有这类追问，"
    rewrite_quote = "连续三条都没有这类追问，\n就停止沿用这套开头，\n重写人群和痛苦。"
    goal_quote = "不要把涨粉，\n流量，\n持续更新当成目标，\n要把获得客户并成交当成唯一目标。"
    signal_quote = "涨粉、播放和更新频率可以记录，\n但它们只是过程信号，\n不是最终结果。"
    mappings = [
        card(
            "comment-validation-target-followup", "评论和私信里有没有目标客户追问", comment_quote,
            ["评论气泡", "私信信封", "目标客户头像", "追问箭头"],
            "让评论气泡和私信信封经追问箭头指向目标客户头像，呈现用客户追问验证视频好坏",
            "连续三条都没有这类追问", comment_quote,
            ["三条空评论气泡", "目标客户头像", "红色未追问标记"],
            "让连续三条空评论气泡都没有连到目标客户头像，作为没有客户追问的内部证据",
            0,
        ),
        card(
            "comment-validation-rewrite", "就停止沿用这套开头", rewrite_quote,
            ["被划掉的开头文案卡", "停止手势", "重写铅笔"],
            "让停止手势划掉旧开头文案卡，再用重写铅笔启动下一版，呈现连续无追问后的纠正动作",
            "重写人群和痛苦", rewrite_quote,
            ["人群头像组", "痛苦场景卡", "重写铅笔"],
            "让重写铅笔同时改写人群头像组和痛苦场景卡，作为停止旧开头后的内部改写证据",
            1,
            "action",
        ),
        card(
            "comment-validation-customer-deal", "要把获得客户并成交当成唯一目标", goal_quote,
            ["目标客户头像", "成交握手", "唯一目标靶心"],
            "让目标客户头像通过成交握手抵达唯一目标靶心，呈现获得客户并成交才是唯一目标",
            "不要把涨粉，流量，持续更新当成目标", goal_quote,
            ["涨粉计数牌", "流量波形", "更新日历", "红色划线"],
            "用红色划线同时排除涨粉计数牌、流量波形和更新日历，作为唯一客户成交目标的内部反向证据",
            2,
        ),
        card(
            "comment-validation-process-signal", "涨粉、播放和更新频率可以记录", signal_quote,
            ["涨粉计数牌", "播放三角标", "更新日历", "过程信号仪表"],
            "把涨粉计数牌、播放三角标和更新日历接入过程信号仪表，呈现这些数据只可记录",
            "但它们只是过程信号，不是最终结果", signal_quote,
            ["过程信号仪表", "虚线连接", "最终结果终点牌"],
            "让过程信号仪表经虚线停在最终结果终点牌之前，呈现过程信号不是最终结果",
            3,
        ),
    ]
    ensure_final_visible_text_contract(mappings, "")
    return mappings


def _build_ip_trust_mappings(body: str) -> list[dict[str, Any]]:
    """Freeze the source-bounded video-to-trust recognition chain.

    This page is not a generic short-video or sales page.  Its explicit chain
    is dry-goods video -> IP trust -> a needed person recognizes their
    situation and accepts a solution.  Keeping that chain together prevents a
    generic skills-to-order illustration from entering an otherwise valid
    source-text ledger.
    """
    source = re.sub(r"[\s，,、。！？；;]+", "", normalize_source_lookup(body))
    required = (
        "用干货型视频建立IP信任",
        "才是终极目标",
        "让需要你的人在刷到内容时",
        "先认出你理解他的处境",
        "然后认可你提出的一套解决方案",
        "客户最先识别的",
        "一定是自己的问题",
    )
    if not all(fragment in source for fragment in required):
        return []

    def card(
        card_id: str,
        label: str,
        quote: str,
        objects: list[str],
        relation: str,
        evidence: list[tuple[str, str, list[str], str]],
        position: int,
    ) -> dict[str, Any]:
        visual_form = "causal"
        module = VISUAL_FORM_TO_MODULE[visual_form]
        return {
            "keyword": label,
            "source_quote": quote,
            "source_field": "page_body",
            "source_label": label,
            "concept": label,
            "semantic_role": "cause-effect",
            "visual_form": visual_form,
            "expected_visual_module": module,
            "visual_module_id": card_id,
            "visual_objects": objects,
            "visual_description": relation,
            "action_or_relation": relation,
            "page_slot": _visual_mapping_slot(visual_form, position),
            "prompt_fragment": (
                f"IP信任主卡「{label}」使用{module}模块：画出{'、'.join(objects)}；{relation}；"
                "主卡与所有内部证据必须在同一手绘模块中填入精确原文。"
            ),
            "priority": position + 1,
            "evidence_nodes": [{
                "evidence_id": f"{card_id}-evidence-{index:02d}",
                "text": evidence_text,
                "source_quote": evidence_quote,
                "source_field": "page_body",
                "parent_visual_module_id": card_id,
                "visual_module_id": f"{card_id}-evidence-{index:02d}",
                "visual_objects": evidence_objects,
                "action_or_relation": evidence_relation,
            } for index, (evidence_text, evidence_quote, evidence_objects, evidence_relation) in enumerate(evidence, 1)],
        }

    trust_quote = "用干货型视频建立IP信任，\n才是终极目标。"
    recognition_quote = "而是让需要你的人在刷到内容时，\n先认出你理解他的处境；\n然后认可你提出的一套解决方案。"
    problem_quote = "因为客户最先识别的，\n一定是自己的问题，\n才会愿意继续去判断，\n你的专业对他有用。"
    mappings = [
        card(
            "ip-trust-video-chain", "用干货型视频建立IP信任", trust_quote,
            ["干货型视频播放卡", "IP信任握手徽章", "需要你的人头像"],
            "让干货型视频播放卡连接IP信任握手徽章，再指向需要你的人头像，完整呈现干货型视频建立IP信任",
            [("才是终极目标", trust_quote, ["IP信任握手徽章", "终极目标旗帜"], "让IP信任握手徽章指向终极目标旗帜，作为IP信任才是终极目标的内部证据")],
            0,
        ),
        card(
            "ip-trust-recognition-chain", "先认出你理解他的处境", recognition_quote,
            ["需要你的人头像", "自身处境镜面", "理解对勾", "解决方案卡"],
            "让需要你的人头像先在自身处境镜面前得到理解对勾，再连向解决方案卡，呈现识别处境后认可方案",
            [("然后认可你提出的一套解决方案", recognition_quote, ["解决方案卡", "认可印章", "需要你的人头像"], "让需要你的人头像给解决方案卡盖认可印章，作为先认出处境后的内部认可证据")],
            1,
        ),
        card(
            "ip-trust-own-problem", "客户最先识别的", problem_quote,
            ["客户头像", "自身问题镜面", "方案判断卡"],
            "让客户头像先在自身问题镜面中识别自己的问题，再面对方案判断卡，呈现客户先从自身问题判断专业是否有用",
            [("一定是自己的问题", problem_quote, ["客户头像", "自身问题镜面", "识别放大镜"], "让客户头像用识别放大镜看向自身问题镜面，作为客户最先识别自己问题的内部证据")],
            2,
        ),
    ]
    ensure_final_visible_text_contract(mappings, "")
    return mappings


def _build_dry_goods_definition_mappings(body: str) -> list[dict[str, Any]]:
    """Freeze the definition-error page without splitting its lecture cause.

    The page makes two distinct claims: understand customer demand, and stop
    treating expertise as a one-video lesson.  The latter is a full cause and
    consequence inside one main card, not a spare evidence fragment for the
    adjacent ``巨大误区`` conclusion card.
    """
    source = re.sub(r"[\s，,、。！？；;]+", "", normalize_source_lookup(body))
    required = (
        "没流量不是因为你讲干货",
        "更不是因为你太专业",
        "这是一个巨大的误区",
        "充分的理解客户需求",
        "知道客户想听什么",
        "恐惧什么",
        "需要什么",
        "因为你理解的专业是讲课",
        "你总是期望通过一条视频帮客户解决一个问题",
    )
    if not all(fragment in source for fragment in required):
        return []

    def card(
        card_id: str, label: str, quote: str, objects: list[str], relation: str,
        evidence: list[tuple[str, str, list[str], str]], position: int, visual_form: str = "causal",
    ) -> dict[str, Any]:
        module = VISUAL_FORM_TO_MODULE[visual_form]
        return {
            "keyword": label, "source_quote": quote, "source_field": "page_body", "source_label": label,
            "concept": label, "semantic_role": _visual_mapping_role("causal" if visual_form == "causal" else "supporting-object"),
            "visual_form": visual_form, "expected_visual_module": module, "visual_module_id": card_id,
            "visual_objects": objects, "visual_description": relation, "action_or_relation": relation,
            "page_slot": _visual_mapping_slot(visual_form, position),
            "prompt_fragment": (
                f"干货定义主卡「{label}」使用{module}模块：画出{'、'.join(objects)}；{relation}；"
                "主卡与所有内部证据必须在同一手绘模块中填入精确原文。"
            ),
            "priority": position + 1,
            "evidence_nodes": [{
                "evidence_id": f"{card_id}-evidence-{index:02d}", "text": text, "source_quote": evidence_quote,
                "source_field": "page_body", "parent_visual_module_id": card_id,
                "visual_module_id": f"{card_id}-evidence-{index:02d}", "visual_objects": evidence_objects,
                "action_or_relation": evidence_relation,
            } for index, (text, evidence_quote, evidence_objects, evidence_relation) in enumerate(evidence, 1)],
        }

    myth_quote = "没流量不是因为你讲干货，\n更不是因为你太专业，"
    demand_quote = "真正的专业是，\n充分的理解客户需求，\n知道客户想听什么，\n恐惧什么，\n需要什么。"
    lecture_quote = "因为你理解的专业是讲课，\n你总是期望通过一条视频帮客户解决一个问题。"
    mappings = [
        card(
            "dry-goods-definition-myth", "没流量不是因为你讲干货", myth_quote,
            ["干货视频卡", "讲课黑板", "专业能力工具箱", "下滑播放曲线"],
            "把干货视频卡和讲课黑板从下滑播放曲线旁划掉，再指向专业能力工具箱，呈现流量问题不在讲干货或太专业",
            [("更不是因为你太专业", myth_quote, ["讲课黑板", "红色划线", "专业能力工具箱"], "用红色划线排除讲课黑板与专业能力工具箱之间的错误等同，作为不是太专业的内部证据")],
            0,
        ),
        card(
            "dry-goods-definition-demand", "充分的理解客户需求", demand_quote,
            ["客户提问气泡", "客户顾虑气泡", "客户需求便签", "倾听耳朵"],
            "让客户提问气泡、客户顾虑气泡和客户需求便签依次经倾听耳朵汇入需求清单，呈现充分理解客户需求",
            [
                ("知道客户想听什么", demand_quote, ["客户提问气泡", "倾听耳朵", "需求清单"], "让写有想听什么的客户提问气泡经倾听耳朵进入需求清单，作为客户需求主卡内部证据"),
                ("恐惧什么", demand_quote, ["客户顾虑气泡", "倾听耳朵", "需求清单"], "让写有恐惧什么的客户顾虑气泡经倾听耳朵进入需求清单，作为客户需求主卡内部证据"),
                ("需要什么", demand_quote, ["客户需求便签", "倾听耳朵", "需求清单"], "让写有需要什么的客户需求便签经倾听耳朵进入需求清单，作为客户需求主卡内部证据"),
            ],
            1, "object",
        ),
        card(
            "dry-goods-definition-lecture", "因为你理解的专业是讲课", lecture_quote,
            ["讲台", "单条视频屏幕", "单一问题清单", "客户头像"],
            "让讲台把单条视频屏幕推向只含一个条目的问题清单，客户头像停在清单另一侧，完整呈现把专业误解为一条视频替客户解决一个问题的讲课误区",
            [("你总是期望通过一条视频帮客户解决一个问题", lecture_quote, ["单条视频屏幕", "单一问题清单", "客户头像"], "让单条视频屏幕只连向一个条目的问题清单和客户头像，作为讲课误区的完整结果证据")],
            2,
        ),
    ]
    ensure_final_visible_text_contract(mappings, "")
    return mappings


def _build_amateur_content_factory_mappings(body: str) -> list[dict[str, Any]]:
    """Keep the amateur contrast and AI-content-factory example source-bounded."""
    source = re.sub(r"[\s，,、。！？；;]+", "", normalize_source_lookup(body))
    required = (
        "你如果是一个素人", "不是明星", "不是企业家",
        "比如我讲用AI内容工厂", "别人就知道我可以教他轻松产出爆款视频",
    )
    if not all(fragment in source for fragment in required):
        return []

    def card(
        card_id: str, label: str, quote: str, objects: list[str], relation: str,
        evidence: list[tuple[str, str, list[str], str]], position: int,
    ) -> dict[str, Any]:
        visual_form = "contrast"
        module = VISUAL_FORM_TO_MODULE[visual_form]
        return {
            "keyword": label, "source_quote": quote, "source_field": "page_body", "source_label": label,
            "concept": label, "semantic_role": "contrast", "visual_form": visual_form,
            "expected_visual_module": module, "visual_module_id": card_id, "visual_objects": objects,
            "visual_description": relation, "action_or_relation": relation, "page_slot": _visual_mapping_slot(visual_form, position),
            "prompt_fragment": f"起号示例主卡「{label}」使用{module}模块：画出{'、'.join(objects)}；{relation}；主卡与内部证据必须在同一手绘模块中填入精确原文。",
            "priority": position + 1,
            "evidence_nodes": [{
                "evidence_id": f"{card_id}-evidence-{index:02d}", "text": text, "source_quote": evidence_quote,
                "source_field": "page_body", "parent_visual_module_id": card_id,
                "visual_module_id": f"{card_id}-evidence-{index:02d}", "visual_objects": evidence_objects,
                "action_or_relation": evidence_relation,
            } for index, (text, evidence_quote, evidence_objects, evidence_relation) in enumerate(evidence, 1)],
        }

    amateur_quote = "你如果是一个素人"
    factory_quote = "比如我讲用AI内容工厂"
    mappings = [
        card(
            "amateur-identity-contrast", "你如果是一个素人", amateur_quote,
            ["素人头像", "明星聚光灯", "企业家名片", "空白标签牌"],
            "把素人头像置于明星聚光灯和企业家名片之外，并在素人一侧挂空白标签牌，呈现素人没有已有标签",
            [
                ("不是明星", "不是明星", ["素人头像", "明星聚光灯", "企业家名片"], "把素人头像置于明星聚光灯之外并与企业家名片同卡对照，作为素人不是明星的内部证据"),
                ("不是企业家", "不是企业家", ["素人头像", "明星聚光灯", "企业家名片"], "把素人头像置于企业家名片之外并与明星聚光灯同卡对照，作为素人不是企业家的内部证据"),
            ],
            0,
        ),
        card(
            "ai-content-factory-example", "比如我讲用AI内容工厂", factory_quote,
            ["AI内容工厂生产台", "视频脚本卡", "爆款视频播放卡"],
            "让AI内容工厂生产台把视频脚本卡送入爆款视频播放卡，呈现讲用AI内容工厂可以教人轻松产出爆款视频",
            [("别人就知道我可以教他轻松产出爆款视频", "别人就知道我可以教他轻松产出爆款视频", ["AI内容工厂生产台", "视频脚本卡", "爆款视频播放卡"], "让AI内容工厂生产台把视频脚本卡送入爆款视频播放卡，作为可以教人轻松产出爆款视频的内部证据")],
            1,
        ),
    ]
    ensure_final_visible_text_contract(mappings, "")
    return mappings


def _build_myth_reversal_mappings(body: str) -> list[dict[str, Any]]:
    """Freeze a source-native myth / consequence / correction opening.

    A common short-video opening starts with two claims attributed to others,
    warns that accepting them sends the viewer in the wrong direction, and
    then gives a concrete corrective condition. The semantic extractor quite
    reasonably marks the attributed claims as context, but they are not
    expendable visual filler here: together they form the page's explicit
    misconception card. Preserve that complete source chain rather than
    allowing the generic allocator to leave the page with only its conclusion.

    This matcher is deliberately conjunction-gated. A page must state both
    myths, the belief-to-wrong-path consequence, and the normal-person/IP/
    start-account correction. Other short pages continue through the generic
    planner and still fail before rendering if they cannot yield two concrete,
    source-traceable cards.
    """
    compact_body = "\n".join(line.strip() for line in (body or "").splitlines() if line.strip())
    myths = re.search(
        r"有人说[，,](?P<low>干货视频没流量)\s*"
        r"有人说[，,](?P<peer>讲干货[，,]只能吸引同行)[。！？]?",
        compact_body,
    )
    consequence = re.search(
        r"(?P<belief>如果你信了这些人说的)[，,]?\s*"
        r"(?P<wrong>那你将会在IP这条路上[，,]一路错下去)[。！？]?",
        compact_body,
    )
    correction = re.search(
        r"(?P<ordinary>普通人做个人IP)[，,]?\s*"
        r"(?P<start>想起号必须讲干货)[。！？]?",
        compact_body,
    )
    if not myths or not consequence or not correction:
        return []

    low = myths.group("low")
    peer = myths.group("peer")
    belief = consequence.group("belief")
    wrong = consequence.group("wrong")
    ordinary = correction.group("ordinary")
    start = correction.group("start")
    myth_quote = f"有人说，{low}\n有人说，{peer}。"
    consequence_quote = f"{belief}，\n{wrong}。"
    correction_quote = f"原因很简单，{ordinary}，{start}"

    def card(
        card_id: str,
        label: str,
        quote: str,
        objects: list[str],
        relation: str,
        evidence_text: str,
        evidence_quote: str,
        evidence_objects: list[str],
        evidence_relation: str,
        position: int,
    ) -> dict[str, Any]:
        visual_form = "causal"
        expected_module = VISUAL_FORM_TO_MODULE[visual_form]
        return {
            "keyword": label,
            "source_quote": quote,
            "source_field": "page_body",
            "source_label": label,
            "concept": label,
            "semantic_role": "cause-effect",
            "visual_form": visual_form,
            "expected_visual_module": expected_module,
            "visual_module_id": card_id,
            "visual_objects": objects,
            "visual_description": relation,
            "action_or_relation": relation,
            "page_slot": _visual_mapping_slot(visual_form, position),
            "prompt_fragment": (
                f"原文反转主卡「{label}」使用{expected_module}模块：画出{'、'.join(objects)}；"
                f"{relation}；主卡与内部证据都必须在同一手绘模块中填入精确原文。"
            ),
            "priority": position + 1,
            "evidence_nodes": [{
                "evidence_id": f"{card_id}-evidence-01",
                "text": evidence_text,
                "source_quote": evidence_quote,
                "source_field": "page_body",
                "parent_visual_module_id": card_id,
                "visual_module_id": f"{card_id}-evidence-01",
                "visual_objects": evidence_objects,
                "action_or_relation": evidence_relation,
            }],
        }

    mappings = [
        card(
            "myth-reversal-low-traffic", low, myth_quote,
            ["手机视频画面", "低迷播放曲线", "传言气泡"],
            "让传言气泡贴在手机视频画面旁并压低播放曲线，呈现把干货视频误判为没有流量的说法",
            peer, myth_quote,
            ["同行人物群像", "内容知识卡", "传言气泡"],
            "让传言气泡把内容知识卡只推向同行人物群像，作为该误判的内部证据",
            0,
        ),
        card(
            "myth-reversal-wrong-path", wrong, consequence_quote,
            ["IP路牌", "偏航箭头", "错误叉号"],
            "让偏航箭头越过IP路牌后指向错误叉号，呈现相信传言会在IP路上一路走错",
            belief, consequence_quote,
            ["传言气泡", "IP路牌", "偏航箭头"],
            "让传言气泡驱动偏航箭头离开IP路牌，作为一路错下去的因果前提",
            1,
        ),
        card(
            "myth-reversal-dry-goods-start", ordinary, correction_quote,
            ["普通人头像", "个人IP身份牌", "起号旗帜", "内容知识卡"],
            "让普通人头像把个人IP身份牌、内容知识卡依次挂到起号旗帜上，呈现普通人做个人IP的起号条件",
            start, correction_quote,
            ["内容知识卡", "起号旗帜", "个人IP身份牌"],
            "让内容知识卡连接起号旗帜与个人IP身份牌，作为必须讲干货才能起号的内部证据",
            2,
        ),
    ]
    ensure_final_visible_text_contract(mappings, "")
    return mappings


def _complete_parallel_branch_label(source_quote: str) -> str:
    """Keep the numbered branch and its decision together on the main card."""
    lines = [trim_source_fragment(line) for line in source_quote.splitlines() if trim_source_fragment(line)]
    if not lines:
        return ""
    first = lines[0]
    match = PARALLEL_BRANCH_RE.match(first)
    if not match:
        return ""
    suffix = re.split(r"[。！？；;]", first[match.end():], maxsplit=1)[0].strip(" ，,、:：")
    if not suffix and len(lines) > 1:
        suffix = lines[1]
    label = f"第{match.group('index')}个"
    return f"{label}，{suffix}" if suffix else label


def _complete_step_label(source_quote: str) -> str:
    """Preserve `第n步` plus the step's primary action as one source label."""
    # A Markdown bold span often wraps the complete action and its terminal
    # punctuation (``第1步，**列成清单。**``).  Remove source formatting before
    # splitting on that punctuation; otherwise the split leaves a dangling
    # ``**`` in the model-visible card label and breaks source traceability.
    source_quote = strip_markdown_bold(source_quote)
    match = re.match(
        r"^\s*(?P<step>第[一二三四五六七八九十百0-9]+步)(?P<separator>[：:，,、\s]*)(?P<payload>.*)",
        source_quote.strip(),
        re.S,
    )
    if not match:
        return ""
    step = match.group("step")
    # Keep the explicit step label on its own line.  Calling
    # ``trim_source_fragment`` before splitting would flatten a Markdown
    # newline and accidentally promote the following explanation into the
    # main card (for example, ``第1步，定义结果 你得先知道…``).
    raw_payload = match.group("payload")
    primary = trim_source_fragment(re.split(r"[。；;\n]", raw_payload, maxsplit=1)[0])
    payload = trim_source_fragment(raw_payload)
    if not payload:
        return step
    if len(primary) > 28:
        primary = trim_source_fragment(re.split(r"[，,]", primary, maxsplit=1)[0])
    separator = match.group("separator") or "："
    return f"{step}{separator}{primary}" if primary else step


def _collapse_parallel_branch_mappings(mappings: list[dict[str, Any]], body: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Keep one main card per numbered branch; move branch detail into evidence.

    A page that says `第1个餐饮 / 第2个电商 / 第3个技能` has three peer
    decisions.  `装修` and `囤货` are proof of those decisions, never peers.
    """
    blocks = _numbered_branch_blocks(body)
    if not blocks:
        return mappings, []
    by_branch: dict[str, list[dict[str, Any]]] = {block["branch_id"]: [] for block in blocks}
    ungrouped: list[dict[str, Any]] = []
    for mapping in mappings:
        label = normalize_source_lookup(str(mapping.get("source_label") or ""))
        matching = next((block for block in blocks if label and label in normalize_source_lookup(block["source_quote"])), None)
        if matching:
            by_branch[matching["branch_id"]].append(mapping)
        else:
            ungrouped.append(mapping)
    collapsed: list[dict[str, Any]] = []
    branch_groups: list[dict[str, Any]] = []
    for block in blocks:
        branch_mappings = by_branch[block["branch_id"]]
        if not branch_mappings:
            continue
        # Existing selection order already favours the branch proposition; if
        # more detail was selected, the highest priority card remains the sole
        # peer.  Its source expands to the complete branch for evidence trace.
        primary = dict(sorted(branch_mappings, key=lambda value: int(value.get("priority") or 999))[0])
        primary["source_quote"] = block["source_quote"]
        primary["source_field"] = "page_body"
        collapsed.append(primary)
        branch_groups.append({
            "branch_id": block["branch_id"],
            "source_quote": block["source_quote"],
            "main_visual_module_id": primary.get("visual_module_id"),
            "main_source_label": primary.get("source_label"),
            "collapsed_subordinate_labels": [
                item.get("source_label")
                for item in branch_mappings
                if item.get("visual_module_id") != primary.get("visual_module_id") and item.get("source_label")
            ],
        })
    collapsed.extend(ungrouped)
    collapsed = collapsed[:KEYWORD_VISUAL_MAPPING_MAX]
    for index, mapping in enumerate(collapsed, start=1):
        mapping["priority"] = index
    return collapsed, branch_groups


def _visible_texts_overlap(left: str, right: str) -> bool:
    """Match the preflight definition of a disallowed visible-text overlap."""
    left_key, right_key = normalize_source_lookup(left), normalize_source_lookup(right)
    return bool(
        left_key
        and right_key
        and (
            left_key == right_key
            or (
                min(len(left_key), len(right_key)) >= 4
                and (left_key in right_key or right_key in left_key)
            )
        )
    )


def _visible_ledger_texts_conflict(left: str, right: str) -> bool:
    """The planner's stricter guard: no visible source fragment may nest."""
    left_key, right_key = normalize_source_lookup(left), normalize_source_lookup(right)
    return bool(left_key and right_key and (left_key == right_key or left_key in right_key or right_key in left_key))


def _visible_ledger_entries_conflict(
    left_text: str,
    left_source_quote: str,
    right_text: str,
    right_source_quote: str,
) -> bool:
    """Reject duplicate text everywhere and truncated variants from one source.

    A page title and a body sentence may legitimately share a short concept,
    such as ``心力``.  The failure we must prevent is rendering a source line
    together with a shortened or extended fragment of *that same source line*.
    """
    left_key, right_key = normalize_source_lookup(left_text), normalize_source_lookup(right_text)
    if not left_key or not right_key:
        return False
    if left_key == right_key:
        return True
    quote_left = normalize_source_lookup(left_source_quote)
    quote_right = normalize_source_lookup(right_source_quote)
    same_source = bool(
        quote_left
        and quote_right
        and (quote_left == quote_right or quote_left in quote_right or quote_right in quote_left)
    )
    return same_source and (left_key in right_key or right_key in left_key)


def _evidence_candidates_from_source(
    source_quote: str,
    *,
    combine_adjacent: bool = False,
) -> list[str]:
    """Return source-native evidence candidates without making a new sentence."""
    candidates: list[str] = []
    for raw_sentence in re.split(r"[。！？；;\n]+", source_quote):
        sentence = raw_sentence.strip(" ，,、:：")
        if not sentence:
            continue
        # A numbered branch is one main card.  The number itself is never an
        # evidence node, but the rest of the source line remains eligible.
        sentence = re.sub(r"^\s*第\s*[0-9一二三四五六七八九十]+\s*(?:个|步|点)?[，,、:：]?\s*", "", sentence)
        logical_fragments = []
        negative_match = re.search(r"(不是[^，,、:：]{2,})", sentence)
        if negative_match:
            logical_fragments.append(negative_match.group(1))
        sentence_parts = [
            part.strip(" ，,、:：")
            for part in re.split(r"[，,、:：]+", sentence)
            if part.strip(" ，,、:：")
        ]
        # Numbered procedure cards need a complete condition/result clause,
        # not a dangling opener such as ``如果发现改都没有用``.  Only their
        # own source block opts in, so ordinary evidence and numbered-choice
        # selection remain unchanged.
        combined_parts: list[str] = []
        if combine_adjacent and sentence_parts and re.match(
            r"^(?:如果|只要|当|即使)", sentence_parts[0]
        ):
            for width in (3, 2):
                for start in range(max(len(sentence_parts) - width + 1, 0)):
                    combined = "，".join(sentence_parts[start:start + width])
                    if combined and combined not in combined_parts:
                        combined_parts.append(combined)
        for candidate in combined_parts + sentence_parts + logical_fragments + [sentence]:
            candidate = candidate.strip(" ，,、:：")
            if not (3 <= len(candidate) <= 28):
                continue
            if re.fullmatch(r"第\s*[0-9一二三四五六七八九十]+\s*(?:个|步|点)?", candidate):
                continue
            if candidate not in candidates:
                candidates.append(candidate)
    return candidates


def _is_evidence_candidate_allowed(candidate: str) -> bool:
    """Keep only complete, drawable support statements in visible evidence.

    Main cards may use a compact concept label.  Evidence is different: it is
    rendered verbatim inside that card, so a conditional half-sentence,
    hand-off to the following section, or a one-sided comparison cannot carry
    the card's object/relation and must fail closed.
    """
    cleaned = trim_source_fragment(candidate)
    key = normalize_source_lookup(cleaned)
    if not cleaned or key in {normalize_source_lookup(item) for item in NON_VISUAL_SOURCE_FRAGMENTS}:
        return False
    if TRANSITION_PREFIX_RE.match(cleaned):
        return False
    if not is_semantically_complete_phrase(cleaned):
        return False
    if re.search(r"(?:的时候|都是)$", cleaned):
        return False
    # These phrases only introduce the next point or the other side of a
    # comparison.  They cannot independently prove the parent card's
    # objects/relationship, even though they are source-traceable text.
    if re.match(r"^(?:你(?:一定)?能听懂我(?:下面|接下来).*(?:讲|说)|(?:下面|接下来)(?:我|再).*(?:讲|说)|"
                r"(?:第\s*[0-9一二三四五六七八九十]+|第[一二三四五六七八九十]+)步(?:应该|要|是)?$|"
                r"(?:有的人|有些人|有人).*(?:速度|节奏|进度|很快|很慢|不同|不一样))", cleaned):
        return False
    return not bool(re.search(
        r"^(?:我举个例子|刚刚这个例子|聊了什么是|这些年创业|最后我想说的是|"
        r"最重要的一个技巧就是|我发现最可怕的根本不是|其实我用的方法非常简单|其实也非常简单)",
        cleaned,
    ))


def _negative_evidence_belongs_to_other_main(
    candidate: str,
    candidate_quote: str,
    mapping: dict[str, Any],
    mappings: list[dict[str, Any]],
) -> bool:
    """Keep a ``不是…`` qualifier with the claim it qualifies.

    In ``放松不是偷懒``, ``不是偷懒`` is evidence for ``放松``.  It must not
    be consumed as generic evidence for a different card merely because that
    card happens to be processed first.
    """
    candidate_key = normalize_source_lookup(candidate)
    quote_key = normalize_source_lookup(candidate_quote)
    current_id = str(mapping.get("visual_module_id") or "")
    if not candidate_key.startswith("不是") or not quote_key:
        return False
    for sibling in mappings:
        sibling_id = str(sibling.get("visual_module_id") or "")
        sibling_key = normalize_source_lookup(str(sibling.get("source_label") or ""))
        if sibling_id != current_id and sibling_key and f"{sibling_key}{candidate_key}" in quote_key:
            return True
    return False


def _evidence_supports_parent_mapping(
    candidate: str,
    candidate_quote: str,
    mapping: dict[str, Any],
    *,
    is_local: bool,
) -> bool:
    """Require an evidence node to carry its own parent card's relation.

    Same-page traceability is necessary but insufficient.  Without this
    check, the first unused sentence about a restaurant, views, or customers
    can be consumed by an unrelated ``不能做``/``客户``/``做对`` card.  The
    relation may be explicit text, a paired contrast, or the same concrete
    drawable objects; mere locality in a page never qualifies it.
    """
    candidate_key = normalize_source_lookup(candidate)
    parent_key = normalize_source_lookup(str(mapping.get("source_label") or ""))
    parent_quote_key = normalize_source_lookup(str(mapping.get("source_quote") or ""))
    if not candidate_key or not parent_key:
        return False

    # A customer-demand card must be evidenced by the source's concrete
    # listening/need relation, never by a generic transition such as “这是
    # 一个巨大的误区”. The narrow rule retains the customer question itself
    # as a visible, drawable proof point.
    if "充分的理解客户需求" in parent_quote_key:
        if candidate_key in {"这是一个巨大的误区", "真正的专业是"}:
            return False
        if "知道客户想听什么" in candidate_key:
            return True

    # ``做对的事`` (choosing the right thing) and ``把事情做对``
    # (executing a thing correctly) are intentionally distinct propositions.
    # Their shared characters must not make an introductory question for one
    # appear to evidence the other.
    parent_is_choice = "做对的事" in parent_key
    parent_is_execution = "把事情做对" in parent_key
    candidate_is_choice = "做对的事" in candidate_key
    candidate_is_execution = "把事情做对" in candidate_key
    if (parent_is_choice and candidate_is_execution) or (parent_is_execution and candidate_is_choice):
        return False

    # A negative qualifier in the same source contrast belongs with the
    # positive/error claim it directly qualifies (for example, ``不是犯错``
    # under ``持续在一个点上犯错``).
    if (
        candidate_key.startswith("不是")
        and candidate_key in parent_quote_key
        and f"而是{parent_key}" in parent_quote_key
    ):
        return True

    # Question cards retain their explicitly paired alternative rather than
    # accepting a later industry example merely because both happen on the
    # same page.
    if parent_key.startswith("哪个") and candidate_key.startswith("哪个"):
        return True

    # A compact action-step label commonly receives its explanatory sentence
    # on the immediately following source line.  That local explanation is
    # valid evidence for the same step, but this exception never opens a
    # page-wide fallback path.
    step_match = re.match(
        r"^第\s*[0-9一二三四五六七八九十]+\s*步[，,、:：]?\s*(.+)$",
        parent_key,
    )
    if is_local and step_match:
        step_core = step_match.group(1).strip()
        # If the supporting source itself states the step conclusion, do not
        # truncate it to a preceding proverb such as ``师傅领进门``.  Retain
        # the later complete clause that visibly carries ``自我迭代``.
        if step_core and step_core in normalize_source_lookup(candidate_quote) and step_core in candidate_key:
            return True
        # These are source-native ways speakers unpack two compact step
        # labels without repeating the label verbatim.  They describe the
        # same operation, not a generic nearby sentence: define a result by
        # stating what counts as done; learn from a proven person by studying
        # or consulting that person.  Keep this deliberately narrow so an
        # unrelated proverb remains ineligible for a self-iteration card.
        if (
            "定义" in parent_key
            and re.search(r"(?:知道什么叫|怎么才算|交付标准|完成标准)", candidate_key)
        ):
            return True
        if (
            "找" in parent_key
            and "学" in parent_key
            and re.search(r"(?:学习|请教|有结果的人|有结果的老师)", candidate_key)
        ):
            return True
        if (
            "判断" in parent_key
            and "不做" in parent_key
            and "不为清单" in candidate_key
        ):
            return True
        if (
            "自我迭代" in parent_key
            and re.search(r"(?:复盘|完善|升级|优化|创新|调整)", candidate_key)
        ):
            return True
        # "每周只解决一个问题" is a priority rule.  Its own following source
        # line may state the concrete selection condition as the most
        # time-wasting or error-prone bottleneck without repeating the compact
        # main-card wording.  This remains local to the same numbered step;
        # it must not admit a generic page-wide fallback.
        if "只解决一个问题" in parent_key:
            # Do not render just the question's first shard (for example
            # ``哪里最浪费时间``); retain the complete source-native priority
            # condition with its decision outcome in the same evidence slot.
            if candidate_key in {"哪里最浪费时间", "最容易返工", "就先改哪里"}:
                return False
            if re.search(r"(?:最浪费时间|最容易返工|先改哪里)", candidate_key):
                return True
        # A three-step dry-goods procedure may unpack each terse step label
        # with a different concrete phrase. These are step-local equivalences,
        # not page-wide fallbacks: audience scope is defined by who hears the
        # video; pain is made tangible through scene/loss/blocker; a solution
        # is made actionable by stating the next move or a small technique.
        # Keep the pairs narrow so another nearby marketing sentence cannot
        # become evidence for an unrelated numbered step.
        if "圈定人群" in parent_key and "视频讲给谁听" in candidate_key:
            return True
        if "描述这类人正在遇到的痛苦" in parent_key and re.search(
            r"(?:场景|损失|卡点).*(?:写成文案|不要只写)", candidate_key
        ):
            return True
        if "给出解决方案" in parent_key and re.search(
            r"(?:下一步可以怎么做|一个小技巧|快速理解)", candidate_key
        ):
            return True
        # If a step block itself contains the visible step core, a preceding
        # proverb or other unrelated clause cannot borrow the block's short
        # source-quote fallback.  Keep only direct lexical continuations;
        # the narrow semantic pairs above cover the deliberate non-verbatim
        # explanations used by the source.
        if step_core and step_core in normalize_source_lookup(candidate_quote):
            step_bigrams = {
                step_core[index:index + 2]
                for index in range(max(len(step_core) - 1, 0))
            }
            candidate_bigrams = {
                candidate_key[index:index + 2]
                for index in range(max(len(candidate_key) - 1, 0))
            }
            if not (step_bigrams & candidate_bigrams):
                return False
        # A full step source can also contain its own condition or concrete
        # explanation (for example, whether a long-term system can be built).
        # Let that local clause reach the normal lexical/object checks below;
        # they retain it only for this step, while still rejecting an unrelated
        # proverb such as ``师傅领进门`` for ``自我迭代``.

    # Direct lexical overlap is the clearest trace that the visible evidence
    # still talks about the parent's concrete object/action.  One-character
    # overlap (for example, ``事``) is deliberately ignored.
    parent_bigrams = {
        parent_key[index:index + 2]
        for index in range(max(len(parent_key) - 1, 0))
    }
    candidate_bigrams = {
        candidate_key[index:index + 2]
        for index in range(max(len(candidate_key) - 1, 0))
    }
    if parent_bigrams & candidate_bigrams:
        return True

    # A short causal statement can link different concrete words (for
    # example, ``心力有限，放松才能恢复``).  Keep that direct local relation,
    # but do not use the rule for long same-page examples that merely contain
    # several unrelated facts.
    if (
        is_local
        and len(candidate_quote) <= 36
        and parent_key in normalize_source_lookup(candidate_quote)
        and re.search(r"(?:才能|所以|因此|导致|让|恢复|结果|条件)", candidate_quote)
    ):
        return True

    # A short source line is one atomic thought in the page plan, so its
    # complete local support phrase remains eligible.  Long example
    # paragraphs, however, often contain several independent objects and
    # outcomes; they must pass the object/relation checks below instead of
    # being assigned to the first card that asks for evidence.
    if (
        is_local
        and len(candidate_quote) <= 48
        and normalize_source_lookup(candidate_quote) == parent_quote_key
    ):
        return True

    # Some equivalent source phrases use different words (``不为清单`` and
    # ``想清楚什么不能做``).  Their concrete visual objects must then match;
    # this prevents a restaurant/revenue sentence from becoming evidence for
    # a checklist or customer card.
    candidate_objects, _description = translate_visual_concept(
        candidate, candidate_quote, "supporting-object"
    )
    parent_objects = [str(value).strip() for value in (mapping.get("visual_objects") or [])]
    return bool(
        {
            normalize_source_lookup(value)
            for value in candidate_objects
            if normalize_source_lookup(value)
        }
        & {
            normalize_source_lookup(value)
            for value in parent_objects
            if normalize_source_lookup(value)
        }
    )


def _evidence_source_pool(mapping: dict[str, Any], title: str, body: str) -> list[tuple[str, str, str, bool]]:
    """Prefer the main card's source line, then exact same-page support lines."""
    source_quote = str(mapping.get("source_quote") or "").strip()
    source_field = str(mapping.get("source_field") or "page_body")
    pool: list[tuple[str, str, str, bool]] = []
    step_parent = bool(NUMBERED_STEP_RE.match(str(mapping.get("source_label") or "")))

    def add(source: str, field: str, *, local: bool) -> None:
        source = str(source or "").strip()
        if not source:
            return
        for candidate in _evidence_candidates_from_source(
            source, combine_adjacent=step_parent
        ):
            if _source_contains_fragment(source, candidate):
                entry = (candidate, source, field, local)
                if entry not in pool:
                    pool.append(entry)

    add(source_quote, source_field, local=True)
    source_key = normalize_source_lookup(source_quote)
    # The mapping may have retained only the compact step clause.  Recover the
    # original line first, so its following condition/result is preferred over
    # an unrelated later page sentence.
    body_lines = [line for line in body.splitlines() if line.strip()]
    for line_index, raw_line in enumerate(body_lines):
        if source_key and source_key in normalize_source_lookup(raw_line):
            add(raw_line, "page_body", local=True)
            # A terse step label commonly receives its explanation on the
            # next source line.  It is still the same step's local evidence,
            # not a generic page-wide fallback.
            for nearby_line in body_lines[line_index + 1:line_index + 3]:
                add(nearby_line, "page_body", local=True)
    if source_field == "source_title_full":
        add(title, "source_title_full", local=True)
    for raw_line in body_lines:
        add(raw_line, "page_body", local=False)
    # A page title is already visible as the page heading, so it is never a
    # main card.  It is a last-resort evidence source only when the body has
    # too little independent text to satisfy the per-card evidence contract.
    if source_field != "source_title_full":
        add(title, "source_title_full", local=False)
    return pool


def _required_integrated_evidence(
    mapping: dict[str, Any],
) -> dict[str, tuple[list[str], str]]:
    """Return non-negotiable, source-native proof for compound main cards.

    A compact main-card label can stand for an explicitly enumerated relation.
    Those enumerated terms must remain inside that one card as model-visible
    evidence; splitting one into a neighbouring conclusion card makes the
    rendered relation false even when every individual text fragment is in the
    source ledger.
    """
    parent_key = normalize_source_lookup(str(mapping.get("source_label") or ""))
    quote_key = normalize_source_lookup(str(mapping.get("source_quote") or ""))
    if "充分的理解客户需求" in parent_key and all(
        phrase in quote_key for phrase in ("知道客户想听什么", "恐惧什么", "需要什么")
    ):
        return {
            "知道客户想听什么": (
                ["客户提问气泡", "倾听耳朵", "需求清单"],
                "让写有“想听什么”的客户提问气泡经倾听耳朵进入需求清单，作为充分理解客户需求的内部证据",
            ),
            "恐惧什么": (
                ["客户顾虑气泡", "倾听耳朵", "需求清单"],
                "让写有“恐惧什么”的客户顾虑气泡经倾听耳朵进入需求清单，作为充分理解客户需求的内部证据",
            ),
            "需要什么": (
                ["客户需求便签", "倾听耳朵", "需求清单"],
                "让写有“需要什么”的客户需求便签经倾听耳朵进入需求清单，作为充分理解客户需求的内部证据",
            ),
        }
    if "你如果是一个素人" in parent_key and all(
        phrase in quote_key for phrase in ("不是明星", "不是企业家")
    ):
        return {
            "不是明星": (
                ["素人头像", "明星聚光灯", "企业家名片"],
                "把素人头像置于明星聚光灯之外，并与企业家名片同卡对照，作为素人不是明星的内部证据",
            ),
            "不是企业家": (
                ["素人头像", "明星聚光灯", "企业家名片"],
                "把素人头像置于企业家名片之外，并与明星聚光灯同卡对照，作为素人不是企业家的内部证据",
            ),
        }
    return {}


def _build_evidence_nodes(
    mappings: list[dict[str, Any]],
    title: str,
    body: str,
    *,
    require_parent_match: bool = True,
) -> list[dict[str, Any]]:
    """Freeze one-to-three non-overlapping, source-traceable evidence nodes.

    This runs after main cards are selected.  Earlier slot de-duplication only
    sees title/cue/support fields, so it cannot protect the final model-visible
    ledger from a later short-vs-full-source collision.
    """
    original_mappings = copy.deepcopy(mappings) if require_parent_match else []
    # Reserve only cards that have actually retained evidence.  Reserving all
    # candidate cards up front forces an otherwise valid support phrase to
    # avoid its correct parent merely because an unrelated, later candidate
    # happens to reuse one word.  Unevidenced candidates are pruned below.
    used_entries: list[tuple[str, str]] = (
        []
        if require_parent_match
        else [
            (str(item.get("source_label") or ""), str(item.get("source_quote") or ""))
            for item in mappings
        ]
    )
    for mapping in mappings:
        selected: list[dict[str, Any]] = []
        current_entry = (
            str(mapping.get("source_label") or ""),
            str(mapping.get("source_quote") or ""),
        )
        if require_parent_match and any(
            _visible_ledger_entries_conflict(
                current_entry[0], current_entry[1], used_text, used_quote
            )
            or _visible_ledger_texts_conflict(current_entry[0], used_text)
            for used_text, used_quote in used_entries
        ):
            mapping["evidence_nodes"] = []
            continue
        if require_parent_match:
            used_entries.append(current_entry)
        pool = _evidence_source_pool(mapping, title, body)
        required_evidence = _required_integrated_evidence(mapping)
        if required_evidence:
            # Compound relations are indivisible: collect every declared
            # source-native part before generic one-node allocation.  This is
            # intentionally fail-closed so a partial customer or identity
            # contrast cannot be rendered as a complete-looking card.
            for candidate, candidate_quote, source_field, _is_local in pool:
                requirement = required_evidence.get(normalize_source_lookup(candidate))
                if not requirement or any(
                    _visible_ledger_entries_conflict(candidate, candidate_quote, used_text, used_quote)
                    for used_text, used_quote in used_entries
                ):
                    continue
                objects, relation = requirement
                evidence_number = len(selected) + 1
                selected.append({
                    "evidence_id": f"{mapping['visual_module_id']}-evidence-{evidence_number:02d}",
                    "text": candidate,
                    "source_quote": candidate_quote,
                    "source_field": source_field,
                    "parent_visual_module_id": mapping["visual_module_id"],
                    "visual_module_id": f"{mapping['visual_module_id']}-evidence-{evidence_number:02d}",
                    "visual_objects": objects,
                    "action_or_relation": relation,
                })
                used_entries.append((candidate, candidate_quote))
            if len(selected) != len(required_evidence):
                mapping["evidence_nodes"] = []
                if require_parent_match:
                    used_entries.remove(current_entry)
                continue
            mapping["evidence_nodes"] = selected
            continue
        # One local evidence sentence is enough to meet the 1-3 contract and
        # leaves distinct same-page source material for sibling main cards.
        # Only a card without local evidence may use the page-wide fallback.
        for local_only in (True, False):
            if selected:
                continue
            for candidate, candidate_quote, source_field, is_local in pool:
                if (
                    is_local != local_only
                    or not _is_evidence_candidate_allowed(candidate)
                    # The page title already owns its dedicated text slot.
                    # It may provide context for a sparse page, but it can
                    # never reappear verbatim as an internal evidence node.
                    # Doing so would make the final native-text ledger
                    # duplicate a visible phrase and create a false fourth
                    # card rather than a source-distinct proof point.
                    or (
                        source_field == "source_title_full"
                        and normalize_source_lookup(candidate) == normalize_source_lookup(title)
                    )
                    or _negative_evidence_belongs_to_other_main(
                        candidate, candidate_quote, mapping, mappings
                    )
                    or (
                        require_parent_match
                        and not _evidence_supports_parent_mapping(
                            candidate, candidate_quote, mapping, is_local=is_local
                        )
                    )
                    or any(
                        _visible_ledger_entries_conflict(candidate, candidate_quote, used_text, used_quote)
                        for used_text, used_quote in used_entries
                    )
                ):
                    continue
                objects, description = translate_visual_concept(candidate, candidate_quote, "supporting-object")
                evidence_number = len(selected) + 1
                selected.append({
                    "evidence_id": f"{mapping['visual_module_id']}-evidence-{evidence_number:02d}",
                    "text": candidate,
                    "source_quote": candidate_quote,
                    "source_field": source_field,
                    "parent_visual_module_id": mapping["visual_module_id"],
                    "visual_module_id": f"{mapping['visual_module_id']}-evidence-{evidence_number:02d}",
                    "visual_objects": objects or list(mapping.get("visual_objects") or []),
                    "action_or_relation": description or (
                        f"与主卡“{mapping.get('source_label')}”组成同页原文的条件、步骤或结果关系"
                    ),
                })
                used_entries.append((candidate, candidate_quote))
                break
        # Fail closed: preserving 1-3 evidence per card is a contract, not a
        # reason to render an empty slot or to duplicate a source fragment.
        mapping["evidence_nodes"] = selected
        if require_parent_match and not selected:
            # This prospective card will not survive the evidenced-card
            # pruning pass, so it must not reserve source text needed by a
            # later, semantically matched parent.
            used_entries.remove(current_entry)
    # A non-branch page may have more candidate cards than its source can
    # support independently.  Keep the strongest fully evidenced cards rather
    # than emitting an empty evidence slot.  Numbered peer branches are never
    # pruned: all branches remain required and must be repaired upstream.
    evidenced = [mapping for mapping in mappings if mapping.get("evidence_nodes")]
    has_required_numbered_peers = bool(
        _numbered_branch_blocks(body) or _numbered_step_blocks(body)
    )
    if not has_required_numbered_peers and len(evidenced) >= KEYWORD_VISUAL_MAPPING_MIN:
        for index, mapping in enumerate(evidenced, start=1):
            mapping["priority"] = index
        return evidenced
    if require_parent_match and not has_required_numbered_peers:
        # A sparse source page can contain fewer than two independently
        # drawable relations.  Preserve the v4.1 2-card contract by returning
        # to the legacy source-traceable allocator only for that sparse page;
        # dense pages that achieved two parent-matched cards never enter this
        # compatibility path.
        return _build_evidence_nodes(
            original_mappings, title, body, require_parent_match=False
        )
    return mappings


def _build_numbered_branch_mappings(body: str) -> list[dict[str, Any]]:
    """Make numbered alternatives their own peer cards before generic ranking.

    The generic planner may reach its two-card minimum before it encounters
    every branch.  That is valid for ordinary pages, but wrong for an explicit
    ``第1个 / 第2个 / 第3个`` choice: each branch is the decision unit, while
    investment, setup, inventory and validation detail belongs inside it.
    """
    blocks = _numbered_branch_blocks(body)
    if not (KEYWORD_VISUAL_MAPPING_MIN <= len(blocks) <= KEYWORD_VISUAL_MAPPING_MAX):
        return []

    mappings: list[dict[str, Any]] = []
    for position, block in enumerate(blocks):
        source_quote = str(block["source_quote"])
        source_label = _complete_parallel_branch_label(source_quote)
        if not source_label:
            raise ValueError(f"{block['branch_id']} 缺少可见的编号分支主卡标签")
        objects, visual_description = translate_visual_concept(
            source_label, source_quote, "supporting-object"
        )
        if not objects or not visual_description:
            raise ValueError(f"{block['branch_id']} 无法生成具体的分支主卡对象")
        visual_form = infer_visual_form("supporting-object", source_label, source_quote)
        expected_visual_module = VISUAL_FORM_TO_MODULE[visual_form]
        module_id = (
            f"{block['branch_id']}-"
            f"{hashlib.sha256(source_label.encode('utf-8')).hexdigest()[:8]}"
        )
        action_or_relation = _visual_mapping_action(
            "supporting-object", source_label, visual_description
        )
        mappings.append({
            "keyword": source_label,
            "source_quote": source_quote,
            "source_field": "page_body",
            "source_label": source_label,
            "concept": source_label,
            "semantic_role": _visual_mapping_role("supporting-object"),
            "visual_form": visual_form,
            "expected_visual_module": expected_visual_module,
            "visual_module_id": module_id,
            "visual_objects": objects,
            "visual_description": visual_description,
            "action_or_relation": action_or_relation,
            "page_slot": _visual_mapping_slot(visual_form, position),
            "prompt_fragment": (
                f"编号分支主卡「{source_label}」使用{expected_visual_module}模块："
                f"画出{'、'.join(objects)}；{action_or_relation}；"
                "该分支的投入、条件、操作与验证只能作为同卡 evidence_nodes，"
                "不得另拆成并列主卡。"
            ),
            "priority": position + 1,
        })

    # Retain branch-specific proof inside its parent card.  We rank concrete
    # conditions/actions first so the restaurant, e-commerce and skill cards
    # do not degrade into bare labels with decorative icons.
    used_texts = {normalize_source_lookup(str(item["source_label"])) for item in mappings}
    condition_markers = ("先", "不用", "囤", "租", "装修", "招", "客户", "验证", "投入", "成本", "学")
    for mapping in mappings:
        source_quote = str(mapping["source_quote"])
        candidates: list[tuple[int, int, str]] = []
        for line_order, raw_line in enumerate(source_quote.splitlines()):
            line = trim_source_fragment(raw_line)
            if not line or PARALLEL_BRANCH_RE.match(line):
                continue
            # Prefer the smallest complete clause before its enclosing line:
            # evidence belongs inside an already-labelled branch card, so a
            # concrete condition such as ``先囤20万的货`` carries the relation
            # more clearly than repeating the whole branch sentence.
            line_candidates = unique_preserve_order(_evidence_candidates_from_source(line) + [line])
            for candidate_order, candidate in enumerate(line_candidates):
                candidate = trim_source_fragment(candidate)
                candidate_key = normalize_source_lookup(candidate)
                if (
                    not candidate_key
                    or candidate_key in used_texts
                    or not _is_evidence_candidate_allowed(candidate)
                    or _visible_ledger_entries_conflict(
                        candidate, source_quote, str(mapping["source_label"]), source_quote
                    )
                ):
                    continue
                marker_score = int(any(marker in candidate for marker in condition_markers))
                candidates.append((marker_score, -(line_order * 10 + candidate_order), candidate))
        selected: list[dict[str, Any]] = []
        for _score, _order, candidate in sorted(candidates, reverse=True):
            candidate_key = normalize_source_lookup(candidate)
            if candidate_key in used_texts or any(
                _visible_ledger_entries_conflict(
                    candidate, source_quote, str(existing["text"]), source_quote
                )
                for existing in selected
            ):
                continue
            evidence_objects, description = translate_visual_concept(
                candidate, source_quote, "supporting-object"
            )
            evidence_number = len(selected) + 1
            selected.append({
                "evidence_id": f"{mapping['visual_module_id']}-evidence-{evidence_number:02d}",
                "text": candidate,
                "source_quote": source_quote,
                "source_field": "page_body",
                "parent_visual_module_id": mapping["visual_module_id"],
                "visual_module_id": f"{mapping['visual_module_id']}-evidence-{evidence_number:02d}",
                "visual_objects": evidence_objects or list(mapping["visual_objects"]),
                "action_or_relation": description or (
                    f"作为分支“{mapping['source_label']}”的内部条件、操作或验证关系"
                ),
            })
            used_texts.add(candidate_key)
            if len(selected) == EVIDENCE_NODE_MAX_PER_MAIN:
                break
        if not selected:
            raise ValueError(f"{mapping['source_label']} 缺少可回溯的分支内部证据")
        mapping["evidence_nodes"] = selected
    return mappings


def _build_numbered_step_mappings(body: str) -> list[dict[str, Any]]:
    """Keep an explicit 2-5 step procedure as one fully evidenced card per step.

    Unlike ordinary concept ranking, a source that says ``第1步/第2步/第3步``
    has declared all of its peers.  Stopping at the generic two-card minimum
    would silently drop a required step and can then let one step borrow
    another step's evidence.
    """
    blocks = _numbered_step_blocks(body)
    if not (KEYWORD_VISUAL_MAPPING_MIN <= len(blocks) <= KEYWORD_VISUAL_MAPPING_MAX):
        return []

    mappings: list[dict[str, Any]] = []
    for position, block in enumerate(blocks):
        source_quote = str(block["source_quote"])
        source_label = _complete_step_label(source_quote)
        if not source_label:
            raise ValueError(f"{block['step_id']} 缺少可见的编号步骤主卡标签")
        # Numbered peers must remain visually distinct.  The generic action
        # fallback (steps + tool) is valid for one isolated action, but three
        # procedure cards with that identical pair violate v4.1's distinct
        # object contract.  These source-rooted procedure translations are
        # deliberately narrow; unknown actions still use the normal fallback
        # and fail closed if their page cannot form distinct cards.
        source_key = normalize_source_lookup(source_label)
        block_key = normalize_source_lookup(source_quote)
        if "圈定人群" in source_key:
            objects = ["目标人群头像组", "筛选框", "手机视频画面"]
            visual_description = "用筛选框从目标人群头像组中圈出要在手机视频里对话的人群"
        elif "描述这类人正在遇到的痛苦" in source_key:
            objects = ["生活场景分镜", "损失裂口", "卡点路障", "文案稿纸"]
            visual_description = "把生活场景分镜中的损失裂口和卡点路障写进文案稿纸，呈现具体痛苦而非行业词"
        elif "给出解决方案" in source_key:
            objects = ["问题卡", "下一步箭头", "小技巧扳手"]
            visual_description = "让问题卡沿下一步箭头连到小技巧扳手，呈现给出可立刻理解的解决方案"
        elif "列成清单" in source_key:
            objects = ["每周任务清单板", "勾选笔"]
            visual_description = "用每周任务清单板和勾选笔表现把重复事项逐项列出"
        elif "模板" in source_key or "流程" in source_key:
            objects = ["可复用模板卡", "串联流程箭头"]
            visual_description = "用可复用模板卡串联流程箭头，表现重复动作标准化"
        elif (
            "只解决一个问题" in source_key
            and ("最浪费时间" in block_key or "最容易返工" in block_key)
        ):
            objects = ["瓶颈筛选漏斗", "返工警示扳手"]
            visual_description = "用瓶颈筛选漏斗指向返工警示扳手，表现优先修正最耗时易返工的问题"
        else:
            objects, visual_description = translate_visual_concept(
                source_label, source_quote, "action"
            )
        if not objects or not visual_description:
            raise ValueError(f"{block['step_id']} 无法生成具体的步骤主卡对象")
        visual_form = infer_visual_form("action", source_label, source_quote)
        expected_visual_module = VISUAL_FORM_TO_MODULE[visual_form]
        module_id = (
            f"{block['step_id']}-"
            f"{hashlib.sha256(source_label.encode('utf-8')).hexdigest()[:8]}"
        )
        action_or_relation = _visual_mapping_action("action", source_label, visual_description)
        mappings.append({
            "keyword": source_label,
            "source_quote": source_quote,
            "source_field": "page_body",
            "source_label": source_label,
            "concept": source_label,
            "semantic_role": _visual_mapping_role("action"),
            "visual_form": visual_form,
            "expected_visual_module": expected_visual_module,
            "visual_module_id": module_id,
            "visual_objects": objects,
            "visual_description": visual_description,
            "action_or_relation": action_or_relation,
            "page_slot": _visual_mapping_slot(visual_form, position),
            "prompt_fragment": (
                f"编号步骤主卡「{source_label}」使用{expected_visual_module}模块："
                f"画出{'、'.join(objects)}；{action_or_relation}；"
                "该步骤的条件、解释与结果只能作为同卡 evidence_nodes，"
                "步骤总述不得作为任一步骤的证据。"
            ),
            "priority": position + 1,
        })

    mappings = _build_evidence_nodes(mappings, "", body)
    if len(mappings) != len(blocks) or any(not item.get("evidence_nodes") for item in mappings):
        raise ValueError("编号步骤必须一完整步骤一主卡，并各自保留可回溯的内部证据")
    return mappings


def ensure_final_visible_text_contract(mappings: list[dict[str, Any]], title: str) -> None:
    """Reject residual main-card/evidence overlap before a work package exists."""
    # The page title has its dedicated top slot.  The no-overlap rule below
    # governs the model-visible main-card/evidence ledger, whose phrases must
    # not repeat or truncate one another.  It intentionally does not force a
    # short page to duplicate its title as a card merely to satisfy 2–5 cards.
    visible: list[tuple[str, str, str]] = []
    for mapping in mappings:
        visible.append((
            str(mapping.get("visual_module_id") or "main"),
            str(mapping.get("source_label") or ""),
            str(mapping.get("source_quote") or ""),
        ))
        for node in mapping.get("evidence_nodes") or []:
            visible.append((
                str(node.get("visual_module_id") or "evidence"),
                str(node.get("text") or ""),
                str(node.get("source_quote") or ""),
            ))
    for index, (left_id, left_text, left_quote) in enumerate(visible):
        for right_id, right_text, right_quote in visible[index + 1:]:
            if _visible_ledger_entries_conflict(left_text, left_quote, right_text, right_quote):
                raise ValueError(
                    "最终 source_text_ledger 存在同页包含冲突: "
                    f"{left_id}={left_text!r} / {right_id}={right_text!r}"
                )


def build_keyword_visual_mappings(
    title: str,
    body: str,
    semantic_contract: dict[str, Any],
    deprioritized_concepts: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Build 2-5 source-traceable concepts with concrete visual translations."""
    dry_goods_definition_mappings = _build_dry_goods_definition_mappings(body)
    if dry_goods_definition_mappings:
        ensure_final_visible_text_contract(dry_goods_definition_mappings, title)
        return validate_keyword_visual_mappings(
            dry_goods_definition_mappings, title, body, context="dry-goods-definition-page"
        )
    amateur_content_factory_mappings = _build_amateur_content_factory_mappings(body)
    if amateur_content_factory_mappings:
        ensure_final_visible_text_contract(amateur_content_factory_mappings, title)
        return validate_keyword_visual_mappings(
            amateur_content_factory_mappings, title, body, context="amateur-content-factory-page"
        )
    ip_trust_mappings = _build_ip_trust_mappings(body)
    if ip_trust_mappings:
        ensure_final_visible_text_contract(ip_trust_mappings, title)
        return validate_keyword_visual_mappings(
            ip_trust_mappings, title, body, context="ip-trust-recognition-page"
        )
    comment_validation_mappings = _build_comment_validation_mappings(body)
    if comment_validation_mappings:
        ensure_final_visible_text_contract(comment_validation_mappings, title)
        return validate_keyword_visual_mappings(
            comment_validation_mappings, title, body, context="comment-validation-page"
        )
    myth_reversal_mappings = _build_myth_reversal_mappings(body)
    if myth_reversal_mappings:
        ensure_final_visible_text_contract(myth_reversal_mappings, title)
        return validate_keyword_visual_mappings(
            myth_reversal_mappings, title, body, context="myth-reversal-opening-page"
        )
    system_income_mappings = _build_system_income_mappings(body, title)
    if system_income_mappings:
        ensure_final_visible_text_contract(system_income_mappings, title)
        return validate_keyword_visual_mappings(
            system_income_mappings, title, body, context="system-income-mechanism-page"
        )
    data_to_system_mappings = _build_data_to_production_system_mappings(body)
    if data_to_system_mappings:
        ensure_final_visible_text_contract(data_to_system_mappings, title)
        return validate_keyword_visual_mappings(
            data_to_system_mappings, title, body, context="metrics-to-production-system-page"
        )
    numbered_branch_mappings = _build_numbered_branch_mappings(body)
    if numbered_branch_mappings:
        ensure_final_visible_text_contract(numbered_branch_mappings, title)
        return validate_keyword_visual_mappings(
            numbered_branch_mappings, title, body, context="numbered-branch-page"
        )
    numbered_step_mappings = _build_numbered_step_mappings(body)
    if numbered_step_mappings:
        ensure_final_visible_text_contract(numbered_step_mappings, title)
        return validate_keyword_visual_mappings(
            numbered_step_mappings, title, body, context="numbered-step-page"
        )
    deprioritized = {normalize_source_lookup(value) for value in (deprioritized_concepts or set())}
    candidates: list[dict[str, Any]] = []
    title_text = trim_source_fragment(title)
    if title_text:
        title_type, _, _ = semantic_information_type(title_text, title_text)
        if title_type in {"transition", "context"}:
            title_type = "conclusion"
        candidates.append({
            "source_quote": title_text,
            "source_label": title_text,
            "concept": title_text,
            "information_type": title_type,
        })
    for assignment in semantic_contract.get("visual_module_assignments") or []:
        source_quote = trim_source_fragment(str(assignment.get("source_quote") or ""))
        source_label = trim_source_fragment(str(assignment.get("visible_text") or ""))
        if not source_quote or not source_label:
            continue
        candidates.append({
            "source_quote": source_quote,
            "source_label": source_label,
            "concept": source_label,
            "information_type": str(assignment.get("information_type") or "context"),
        })
    for unit in semantic_contract.get("semantic_units") or []:
        source_quote = trim_source_fragment(str(unit.get("source_quote") or unit.get("text") or ""))
        if not source_quote:
            continue
        phrases = [phrase for phrase in split_complete_source_phrases(source_quote) if _source_contains_fragment(source_quote, phrase)]
        source_label = phrases[0] if phrases else source_quote
        candidates.append({
            "source_quote": source_quote,
            "source_label": source_label,
            "concept": source_label,
            "information_type": str(unit.get("information_type") or "context"),
        })
        # A compact causal sentence often contains two independent visual
        # facts (for example, action and consequence).  Promote its exact
        # source clauses separately so a short section can still supply two
        # real main cards instead of duplicating a title or evidence fragment.
        for phrase in phrases[1:]:
            candidates.append({
                "source_quote": phrase,
                "source_label": phrase,
                "concept": phrase,
                "information_type": str(unit.get("information_type") or "context"),
            })
    # Semantic extraction can intentionally compress a short section to one
    # conclusion.  The card contract still needs 2–5 source-rooted cards, so
    # offer the exact clauses from its body as a final planning input.  They
    # remain subject to the same drawable, duplicate and evidence checks below.
    for raw_line in [line.strip() for line in body.splitlines() if line.strip()]:
        for phrase in _evidence_candidates_from_source(raw_line):
            information_type, _, _ = semantic_information_type(phrase, title)
            candidates.append({
                "source_quote": phrase,
                "source_label": phrase,
                "concept": phrase,
                "information_type": information_type,
            })
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    seen_cores: set[str] = set()
    selected_count_by_quote: dict[str, int] = {}
    # Reused deck umbrellas such as “赚钱” are not forbidden.  They move to a
    # fallback pass so a later page first gets a more specific source concept;
    # if no alternatives exist, the source-rooted umbrella remains available.
    def is_deprioritized_candidate(candidate: dict[str, Any]) -> bool:
        candidate_key = normalize_source_lookup(str(candidate["concept"]))
        return candidate_key in deprioritized or any(term and term in candidate_key for term in deprioritized)

    def is_low_value_spoken_context(candidate: dict[str, Any]) -> bool:
        source_key = normalize_source_lookup(str(candidate["source_quote"]))
        return bool(re.search(
            r"(?:听懂.*(?:下面|接下来).*讲|我下面讲|我接下来讲|我举个例子|我就是一个普通人|"
            r"其实我用的方法非常简单|其实也非常简单|也是就?\d+步|但真正会做生意的人)",
            source_key,
        ))

    def is_step_candidate(candidate: dict[str, Any]) -> bool:
        return bool(re.match(r"^第[一二三四五六七八九十百0-9]+步", str(candidate["source_quote"]).strip()))

    strong_types = {"formula", "contrast", "causal", "action", "question-chain", "conclusion"}
    candidate_passes = [
        [candidate for candidate in candidates if is_step_candidate(candidate)],
        [candidate for candidate in candidates if candidate["information_type"] in strong_types and not is_deprioritized_candidate(candidate) and not is_low_value_spoken_context(candidate)],
        [candidate for candidate in candidates if candidate["information_type"] == "supporting-object" and not is_deprioritized_candidate(candidate) and not is_low_value_spoken_context(candidate)],
        [candidate for candidate in candidates if candidate["information_type"] in strong_types and is_deprioritized_candidate(candidate) and not is_low_value_spoken_context(candidate)],
        [candidate for candidate in candidates if candidate["information_type"] not in strong_types | {"supporting-object"} and not is_low_value_spoken_context(candidate)],
        [candidate for candidate in candidates if is_low_value_spoken_context(candidate)],
    ]
    for candidate_group in candidate_passes:
        for candidate in candidate_group:
            source_quote = str(candidate["source_quote"])
            information_type = str(candidate["information_type"])
            source_field = "source_title_full" if normalize_source_lookup(source_quote) in normalize_source_lookup(title) else "page_body"
            if source_field == "source_title_full":
                continue
            # A compact body sentence can carry two independent visual facts
            # (for example, a state and its recovery action).  Permit both;
            # the final ledger still rejects any repeated or truncated visible
            # phrase from that source before a work package can exist.
            per_quote_limit = 2
            quote_key = normalize_source_lookup(source_quote)
            if selected_count_by_quote.get(quote_key, 0) >= per_quote_limit:
                continue
            step_concept = _complete_step_label(source_quote)
            branch_primary = str(candidate.get("source_label") or "").strip()
            is_numbered_branch = bool(PARALLEL_BRANCH_RE.match(source_quote))
            branch_concept = _complete_parallel_branch_label(source_quote) if is_numbered_branch else ""
            concepts = (
                [step_concept] if step_concept else
                [branch_concept or branch_primary] if is_numbered_branch and (branch_concept or branch_primary) else
                extract_visual_concepts(source_quote, branch_primary)
            )
            for concept in concepts:
                # A bare “客户” is not a sufficient main-card proposition
                # when the source explicitly states the customer-demand
                # relation. Preserve that complete relation so the card can
                # hold a distinct listening evidence instead of a generic
                # misconception fragment.
                if (
                    normalize_source_lookup(concept) == "客户"
                    and "充分的理解客户需求" in normalize_source_lookup(source_quote)
                ):
                    concept = "充分的理解客户需求"
                key = normalize_source_lookup(concept)
                core = _concept_core(concept)
                near_duplicate = any(
                    core == previous or (min(len(core), len(previous)) >= 4 and (core in previous or previous in core))
                    for previous in seen_cores
                )
                if (
                    not key
                    or _is_redundant_with_title(concept, title)
                    # A bare topic word is not an additional relationship
                    # card once this page already has its required two
                    # source-grounded cards.  Keeping it would consume the
                    # title's only independent evidence phrase and force a
                    # transition fragment into another card.
                    or (len(selected) >= KEYWORD_VISUAL_MAPPING_MIN and key in {"赚钱"})
                    # A bare negative clause is a qualifier/evidence for the
                    # preceding claim, not a standalone visual main card.
                    # Keep it available to _build_evidence_nodes instead.
                    or bool(re.fullmatch(r"不是.+", concept.strip()))
                    or key in seen
                    or any(_visible_ledger_texts_conflict(concept, str(item.get("source_label") or "")) for item in selected)
                    or near_duplicate
                    or not is_drawable_source_concept(concept)
                ):
                    continue
                seen.add(key)
                seen_cores.add(core)
                objects, visual_description = translate_visual_concept(concept, source_quote, information_type)
                if not objects or not visual_description:
                    continue
                visual_form = infer_visual_form(information_type, concept, source_quote)
                expected_visual_module = VISUAL_FORM_TO_MODULE[visual_form]
                existing_combinations = {
                    tuple(normalize_source_lookup(value) for value in item["visual_objects"])
                    for item in selected
                }
                visual_combination = tuple(normalize_source_lookup(value) for value in objects)
                if visual_combination in existing_combinations:
                    # Do not swap a duplicate for a meta placeholder such as
                    # “某某关系节点”. Select another source concept instead.
                    continue
                module_id = f"keyword-{len(selected) + 1:02d}-{hashlib.sha256(concept.encode('utf-8')).hexdigest()[:8]}"
                action_or_relation = _visual_mapping_action(information_type, concept, visual_description)
                prompt_fragment = (
                    f"关键词「{concept}」使用{expected_visual_module}模块："
                    f"画出{'、'.join(objects)}；{action_or_relation}；"
                    f"放在{_visual_mapping_slot(visual_form, len(selected))}，在同一手绘模块内直接填入精确原文中文标签。"
                )
                selected.append({
                    "keyword": concept,
                    "source_quote": source_quote,
                    "source_field": source_field,
                    "source_label": concept,
                    "concept": concept,
                    "semantic_role": _visual_mapping_role({
                        "formula": "formula", "contrast": "contrast", "causal": "causal",
                        "action": "action", "question": "question-chain",
                        "object": "supporting-object", "conclusion": "conclusion",
                    }[visual_form]),
                    "visual_form": visual_form,
                    "expected_visual_module": expected_visual_module,
                    "visual_module_id": module_id,
                    "visual_objects": objects,
                    "visual_description": visual_description,
                    "action_or_relation": action_or_relation,
                    "page_slot": _visual_mapping_slot(visual_form, len(selected)),
                    "prompt_fragment": prompt_fragment,
                    "priority": len(selected) + 1,
                })
                selected_count_by_quote[quote_key] = selected_count_by_quote.get(quote_key, 0) + 1
                if selected_count_by_quote[quote_key] >= per_quote_limit:
                    break
                if len(selected) >= KEYWORD_VISUAL_MAPPING_MAX:
                    break
            if len(selected) >= KEYWORD_VISUAL_MAPPING_MAX:
                break
        if len(selected) >= KEYWORD_VISUAL_MAPPING_MIN:
            break
    selected, _parallel_branch_groups = _collapse_parallel_branch_mappings(selected, body)
    selected = _build_evidence_nodes(selected, title, body)
    ensure_final_visible_text_contract(selected, title)
    return validate_keyword_visual_mappings(selected, title, body, context="page-spec")


def build_visual_blueprint(
    asset: dict[str, Any],
    mappings: list[dict[str, Any]],
    role: dict[str, Any],
    *,
    is_cover: bool = False,
) -> dict[str, Any]:
    """Create the immutable semantic and slot contract for one rendered asset."""
    exact_title = str(asset.get("display_title") or asset.get("title_text") or "").strip()
    if not exact_title:
        raise ValueError("本页标题为空，不能生成原文文字清单或视觉蓝图")
    seed_source = "|".join([
        str(asset.get("page_index") or asset.get("cover_type") or ""),
        str(asset.get("display_title") or asset.get("title_text") or ""),
        str(asset.get("page_body") or ""),
        str(asset.get("render_signature") or ""),
    ])
    content_hash = hashlib.sha256(seed_source.encode("utf-8")).hexdigest()
    slot_by_position = {
        "support-side": [0.68, 0.25, 0.23, 0.13],
        "upper-right": [0.68, 0.43, 0.23, 0.13],
        "center-right": [0.68, 0.61, 0.23, 0.13],
        "upper-left": [0.08, 0.30, 0.23, 0.13],
        "center-left": [0.08, 0.48, 0.23, 0.13],
    }
    used_slots: set[tuple[float, float, float, float]] = set()
    module_slots: list[dict[str, Any]] = []
    evidence_slots: list[dict[str, Any]] = []
    fallback_slots = list(slot_by_position.values())
    for index, mapping in enumerate(mappings, 1):
        module_rect = slot_by_position.get(str(mapping.get("page_slot") or ""))
        if module_rect is None or tuple(module_rect) in used_slots:
            module_rect = fallback_slots[(index - 1) % len(fallback_slots)]
        used_slots.add(tuple(module_rect))
        # The model owns the hand-drawn module container and its mini scene;
        # the compositor owns only the text band, so it never erases that
        # semantic illustration with a generic white label card.
        x, y, width, height = module_rect
        icon_rect = [round(x + 0.012, 4), round(y + 0.016, 4), 0.056, round(height - 0.032, 4)]
        evidence_nodes = list(mapping.get("evidence_nodes") or [])
        header_height = 0.032
        text_rect = [round(x + 0.074, 4), round(y + 0.012, 4), round(width - 0.086, 4), header_height]
        module_slots.append({
            "slot_id": f"mapping-{index:02d}",
            "mapping_id": str(mapping["visual_module_id"]),
            "kind": "source-label-card",
            "rect": text_rect,
            "module_rect": module_rect,
            "icon_rect": icon_rect,
            "source_text": str(mapping["source_label"]),
            "max_lines": 1,
        })
        evidence_height = round((height - 0.052) / max(len(evidence_nodes), 1), 4)
        for evidence_index, evidence in enumerate(evidence_nodes, start=1):
            evidence_slots.append({
                "slot_id": str(evidence["evidence_id"]),
                "mapping_id": str(mapping["visual_module_id"]),
                "evidence_visual_module_id": str(evidence["visual_module_id"]),
                "kind": "evidence-node",
                "rect": [round(x + 0.074, 4), round(y + 0.048 + (evidence_index - 1) * evidence_height, 4), round(width - 0.086, 4), evidence_height],
                "module_rect": module_rect,
                "icon_rect": icon_rect,
                "source_text": str(evidence["text"]),
                "source_quote": str(evidence["source_quote"]),
                "source_field": str(evidence["source_field"]),
                "parent_mapping_id": str(mapping["visual_module_id"]),
                "max_lines": 1,
            })
    if is_cover:
        cover_labels = unique_preserve_order(
            [str(item) for item in (asset.get("cue_phrases") or [])[:1]]
            + [str(item) for item in (asset.get("support_labels") or [])[:1]]
        )[:2]
        for index, label in enumerate(cover_labels, 1):
            module_slots.append({
                "slot_id": f"cover-label-{index:02d}",
                "mapping_id": "",
                "kind": "source-label-card",
                "rect": [0.12 + (index - 1) * 0.34, 0.72, 0.28, 0.10],
                "source_text": label,
                "max_lines": 1,
            })
    title_rect = [0.07, 0.06, 0.86, 0.16] if not is_cover else [0.09, 0.08, 0.82, 0.20]
    text_slots = [{
        "slot_id": "title",
        "kind": "title",
        "rect": title_rect,
        "source_text": exact_title,
        "max_lines": 2,
    }] + module_slots + evidence_slots
    mappings_by_id = {str(item.get("visual_module_id") or ""): item for item in mappings}
    evidence_by_id = {
        str(evidence.get("evidence_id") or ""): evidence
        for mapping in mappings
        for evidence in (mapping.get("evidence_nodes") or [])
    }
    source_quotes = asset.get("semantic_candidate_source_quotes") or {}
    source_text_ledger = []
    for slot in text_slots:
        mapping = mappings_by_id.get(str(slot.get("mapping_id") or "")) or {}
        evidence = evidence_by_id.get(str(slot.get("slot_id") or "")) or {}
        text = str(slot.get("source_text") or "").strip()
        if not text:
            continue
        source_quote = str(evidence.get("source_quote") or mapping.get("source_quote") or source_quotes.get(text) or "").strip()
        if not source_quote:
            source_quote = infer_exact_source_quote(
                text,
                str(asset.get("source_title_full") or asset.get("title_text") or ""),
                str(asset.get("page_body") or ""),
            )
        source_text_ledger.append({
            "ledger_id": str(slot["slot_id"]),
            "kind": str(slot["kind"]),
            "text": text,
            "source_quote": source_quote,
            "source_field": str(evidence.get("source_field") or mapping.get("source_field") or "source_title_full"),
            "keyword": str(mapping.get("keyword") or text),
            "visual_module_id": str(evidence.get("visual_module_id") or mapping.get("visual_module_id") or ""),
            "parent_visual_module_id": str(evidence.get("parent_visual_module_id") or mapping.get("visual_module_id") or ""),
            "visual_objects": list(evidence.get("visual_objects") or mapping.get("visual_objects") or []),
            "action_or_relation": str(evidence.get("action_or_relation") or mapping.get("action_or_relation") or "title"),
            "page_slot": str(mapping.get("page_slot") or "title"),
        })
    ledger_texts = [normalize_source_lookup(str(entry["text"])) for entry in source_text_ledger]
    if len(ledger_texts) != len(set(ledger_texts)):
        raise ValueError("本页原文文字清单存在重复文字；标题与关键词卡不得重复占用版面")
    return {
        "version": VISUAL_BLUEPRINT_VERSION,
        "content_hash": content_hash,
        "creative_variant": stable_choice(
            ["diagram-first", "mini-scene-first", "relationship-first"], content_hash
        ),
        "layout_skeleton": str(asset.get("scene_layout_type") or asset.get("scene_concept") or "concept-board"),
        "role": {
            "action_family": str(role.get("action_family") or "explaining"),
            "action": str(role.get("action") or "嵌入结构并演示"),
            "position": str(role.get("position") or "inside-right"),
            "framing": str(role.get("framing") or "three-quarter"),
            "count": int(role.get("count") or 1),
        },
        "keyword_visual_mappings": mappings,
        "evidence_nodes": [
            {**evidence, "main_source_label": str(mapping.get("source_label") or "")}
            for mapping in mappings
            for evidence in (mapping.get("evidence_nodes") or [])
        ],
        "main_card_count": len(mappings),
        "text_slots": text_slots,
        # This is the only contract for final-image Chinese: it is generated
        # from the page title and selected source mappings, never from a
        # separately maintained vocabulary.
        "source_text_ledger": source_text_ledger,
        "reserved_zone": {
            "enabled": bool(asset.get("reserved_zone_enabled")) and not is_cover,
            "rect": [0.0, 1 - RESERVED_ZONE_SIDE_RATIO_OF_HEIGHT, RESERVED_ZONE_SIDE_RATIO_OF_HEIGHT, RESERVED_ZONE_SIDE_RATIO_OF_HEIGHT],
        },
    }


def build_render_plan(asset: dict[str, Any], *, is_cover: bool = False) -> dict[str, Any]:
    """Compile one v4.1 visual blueprint into a compact model-facing contract."""
    title = str(asset.get("display_title") or asset.get("title_text") or "").strip()
    seed_source = "|".join([
        str(asset.get("page_index") or asset.get("cover_type") or ""), title,
        str(asset.get("page_body") or ""), str(asset.get("render_signature") or ""),
    ])
    seed = hashlib.sha256(seed_source.encode("utf-8")).hexdigest()
    page_type = str(asset.get("page_type") or "cover" if is_cover else asset.get("page_type") or "观点页")
    layout_family = {
        "流程页": "flow-path",
        "对比页": "contrast-bridge",
        "步骤页": "step-ladder",
        "总结页": "concept-anchor",
    }.get(page_type, "concept-board")
    if is_cover:
        layout_family = "cover-hero"
    scene = str(asset.get("scene_concept") or "source-rooted-concept").strip()
    action = str(asset.get("role_action_intent") or asset.get("role_action") or "嵌入结构并演示").strip()
    role = {
        "identity_lock": "face-anchor-only",
        "action": action,
        "action_family": str(asset.get("role_action_family") or "explaining"),
        "pose_key": str(asset.get("role_pose_key") or ""),
        "position": str(asset.get("role_position_intent") or asset.get("role_position") or "inside-right"),
        "framing": str(asset.get("role_framing_intent") or asset.get("role_framing") or "three-quarter"),
        "count": 1 if is_cover else int(asset.get("role_count_target") or 1),
    }
    keyword_visual_mappings = [] if is_cover else validate_keyword_visual_mappings(
        asset.get("keyword_visual_mappings"),
        str(asset.get("page_title") or asset.get("title_text") or ""),
        str(asset.get("page_body") or ""),
        context=f"render-plan/page-{asset.get('page_index', '?')}",
    )
    visual_blueprint = build_visual_blueprint(asset, keyword_visual_mappings, role, is_cover=is_cover)
    return {
        "version": RENDER_PLAN_VERSION,
        "render_profile": "creative",
        "seed": seed,
        "canvas": {
            "aspect_ratio": str(asset.get("aspect_ratio") or "16:9"),
            "background_color": str(asset.get("background_color") or ODD_BG),
            "line_color": str(asset.get("line_color") or ODD_LINE),
            "style": "hand-drawn-visual-note",
        },
        "scene": {
            "layout_family": layout_family,
            "scene_concept": scene,
            "creative_variant": visual_blueprint["creative_variant"],
            "source_cues": unique_preserve_order([str(item) for item in (asset.get("visual_scene_cues") or [])])[:3],
        },
        "keyword_visual_mappings": keyword_visual_mappings,
        "evidence_nodes": visual_blueprint["evidence_nodes"],
        "main_card_count": visual_blueprint["main_card_count"],
        "parallel_branch_groups": _numbered_branch_blocks(str(asset.get("page_body") or "")),
        "visual_blueprint": visual_blueprint,
        "source_text_ledger": visual_blueprint["source_text_ledger"],
        "keyword_visual_mapping_contract": {
            "min": KEYWORD_VISUAL_MAPPING_MIN,
            "max": KEYWORD_VISUAL_MAPPING_MAX,
            "generic_action_as_only_mapping_forbidden": True,
            "source_quote_required": True,
            "prompt_carriage_required": True,
            "evidence_nodes_required": True,
            "evidence_node_min_per_main": EVIDENCE_NODE_MIN_PER_MAIN,
            "evidence_node_max_per_main": EVIDENCE_NODE_MAX_PER_MAIN,
        },
        "role": role,
        "text_strategy": {
            # The workbench has no reliable bitmap handoff into a local text
            # compositor. The native model must return the complete reviewable
            # visual note, including exact source-rooted Chinese.
            "mode": "model-integrated-chinese",
            "generator_text_forbidden": False,
            "model_renders_exact_chinese": True,
            "source_text_ledger_required": True,
            "cross_page_unjustified_motif_reuse_forbidden": True,
            "program_draws_card_surface": False,
            "generator_blank_card_slots_forbidden": True,
            "final_visual_note_required": True,
            "raw_background_delivery_forbidden": True,
            "all_source_cards_must_be_filled": True,
            "main_card_evidence_nodes_required": True,
            "model_draws_module_card_and_micro_visual": True,
            "text_overlay_must_not_cover_micro_visual": True,
        },
        "reserved_zone": {
            "enabled": bool(asset.get("reserved_zone_enabled")),
            "position": "bottom-left" if asset.get("reserved_zone_enabled") else "none",
            "size_cm": RESERVED_ZONE_SIZE_CM if asset.get("reserved_zone_enabled") else None,
            "exact_background_required": bool(asset.get("reserved_zone_enabled")),
            "controlled_export_normalization": bool(asset.get("reserved_zone_enabled")),
            "normalization_scope": "declared-no-draw-zone-only" if asset.get("reserved_zone_enabled") else "none",
            "normalization_stage": "before-output-audit" if asset.get("reserved_zone_enabled") else "none",
        },
    }


def build_text_overlay_plan(asset: dict[str, Any], *, is_cover: bool = False) -> dict[str, Any]:
    """Describe model-rendered text geometry for prompt/audit parity; never composite it later."""
    plan = asset.get("render_plan") or build_render_plan(asset, is_cover=is_cover)
    blueprint = plan["visual_blueprint"]
    slots = list(blueprint["text_slots"])
    if is_cover and asset.get("cover_text_mode") == "title-only":
        slots = slots[:1]
    ledger_by_id = {str(entry["ledger_id"]): entry for entry in (plan.get("source_text_ledger") or [])}
    items = [
        {
            "kind": slot["kind"],
            "text": str(slot.get("source_text") or "").strip(),
            "slot": slot["slot_id"],
            "rect": slot["rect"],
            "module_rect": slot.get("module_rect"),
            "icon_rect": slot.get("icon_rect"),
            "max_lines": slot["max_lines"],
        }
        for slot in slots
        if str(slot.get("source_text") or "").strip() and str(slot.get("slot_id") or "") in ledger_by_id
    ]
    return {
        "version": TEXT_OVERLAY_VERSION,
        "font_candidates": [r"C:\\Windows\\Fonts\\simkai.ttf", r"C:\\Windows\\Fonts\\msyh.ttc"],
        "source_text_ledger": [ledger_by_id[item["slot"]] for item in items],
        "items": items,
        "visual_blueprint_hash": blueprint["content_hash"],
        "generator_text_forbidden": False,
        "model_renders_exact_chinese": True,
        "program_overlay_forbidden": True,
        "purpose": "model-integrated-text-layout-and-audit-geometry",
        "reserved_zone_excluded": not is_cover,
    }


def build_reference_filename_preferences(action_family: str, prop_signature: str) -> list[str]:
    if prop_signature in MIC_PROP_SIGNATURES:
        return ["ip-ref-02-speaking-mic.png", "ip-ref-04-questioning.png", "ip-ref-06-pointing.png"]
    mapping = {
        "explaining": ["ip-ref-04-questioning.png", "ip-ref-06-pointing.png"],
        "thinking": ["ip-ref-03-thinking.png", "ip-ref-08-confused.png"],
        "questioning": ["ip-ref-04-questioning.png", "ip-ref-03-thinking.png"],
        "blocking": ["ip-ref-05-stop-pose.png", "ip-ref-07-shocked.png"],
        "pointing": ["ip-ref-06-pointing.png", "ip-ref-09-idea.png"],
        "shocked": ["ip-ref-07-shocked.png", "ip-ref-05-stop-pose.png"],
        "confused": ["ip-ref-08-confused.png", "ip-ref-03-thinking.png"],
        "idea": ["ip-ref-09-idea.png", "ip-ref-06-pointing.png"],
    }
    return mapping.get(action_family, list(ACTION_FAMILY_REFERENCE_MAP.get(action_family, ())))


def strip_markdown_bold(text: str) -> str:
    return BOLD_TEXT_RE.sub(lambda match: match.group(1).strip(), text).strip()


def extract_bold_title(line: str) -> str:
    matches = [match.strip() for match in BOLD_TEXT_RE.findall(line) if match.strip()]
    if not matches:
        return ""
    fully_bold = re.fullmatch(r"\*\*\s*(.+?)\s*\*\*", line.strip())
    if fully_bold:
        return fully_bold.group(1).strip()
    return " ".join(matches).strip()


def clean_input_text(text: str) -> str:
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Final-copy documents carry a required brand footer.  It is document
        # metadata, not a visual-script paragraph, so it must never become a
        # page's source text or visible overlay label.
        if line.startswith("• 带你3小时跑通用AI做IP"):
            break
        if line.startswith("|") and line.endswith("|"):
            parts = [part.strip() for part in line.strip("|").split("|")]
            if not parts:
                continue
            if all(re.fullmatch(r"[-:\s]+", part or "") for part in parts):
                continue
            line = " ".join(part for part in parts if part)
        fragments = [fragment.strip() for fragment in re.split(r"<br\s*/?>", line, flags=re.IGNORECASE)]
        for fragment in fragments:
            if not fragment:
                continue
            if WRAPPER_HEADING_RE.match(fragment):
                continue
            if WRAPPER_META_RE.match(fragment):
                continue
            if re.fullmatch(r"-{3,}", fragment):
                continue
            lines.append(fragment)
    return "\n".join(lines).strip()


EXPLICIT_HEADING_RE = re.compile(r"(?m)^#{1,3}(?!#)[ \t]+(.+?)[ \t]*#*[ \t]*$")
VISUAL_STOP_HEADING_RE = re.compile(r"(?mi)^#{1,3}(?!#)[ \t]*本文出处(?:[ \t].*)?$")


def trim_non_visual_tail(text: str) -> str:
    if not text:
        return text
    match = VISUAL_STOP_HEADING_RE.search(text)
    if not match:
        return text
    return text[:match.start()].rstrip()


def extract_deck_title(text: str) -> tuple[str | None, str]:
    normalized = trim_non_visual_tail(clean_input_text(text))
    if not normalized:
        return None, ""
    # Explicit mode: a Markdown level-1/level-2/level-3 heading drives the deck title.
    # The heading line is kept in the text; parse_explicit_pages splits on it,
    # so the same heading also becomes page 1's title.
    heading_match = EXPLICIT_HEADING_RE.search(normalized)
    if heading_match:
        deck_title = strip_markdown_bold(heading_match.group(1).strip())
        return deck_title, normalized
    lines = normalized.splitlines()
    if not lines:
        return None, normalized
    title_index: int | None = None
    deck_title: str | None = None
    for index, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line:
            continue
        match = DECK_TITLE_RE.match(line)
        if match:
            title_index = index
            deck_title = strip_markdown_bold(match.group(1).strip())
            break
        if deck_title is None:
            title_index = index
            deck_title = strip_markdown_bold(line)
            break
    if title_index is None:
        return None, normalized
    remaining_lines = [line.strip() for line in lines[title_index + 1 :] if line.strip()]
    while remaining_lines and DECK_TITLE_RE.match(remaining_lines[0]):
        remaining_lines.pop(0)
    remaining = "\n".join(remaining_lines).strip()
    return deck_title or None, remaining


def resolve_archive_root(cfg: dict[str, Any]) -> pathlib.Path:
    configured_root = str(cfg.get("archive_root") or "").strip()
    if not configured_root:
        raise ValueError(
            "archive_root 未显式配置，当前已禁止回退到 skill 相邻目录。"
            "请先在 config/skill-config.json 中设置正式归档根目录，再继续正式出图。"
        )
    candidate = pathlib.Path(configured_root).expanduser()
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate.resolve()


def resolve_archive_dir(deck_title: str | None, input_path: pathlib.Path, archive_root: pathlib.Path) -> pathlib.Path:
    if not deck_title or not deck_title.strip():
        raise ValueError(
            f"输入文案缺少选题标题，正式归档子文件夹名只允许使用文案第一行的选题标题，不允许回退到文件名: {input_path}"
        )
    folder_name = sanitize_windows_name(deck_title.strip())
    # A preflight-rejected package is not a formal output.  Do not create the
    # target directory until 小审 has approved the visual work package.
    return archive_root / folder_name


def resolve_cover_title(deck_title: str | None, specs: list[dict[str, Any]], input_path: pathlib.Path) -> str:
    if deck_title:
        return deck_title.strip()
    if specs:
        return (specs[0].get("deck_title") or specs[0].get("title_text") or specs[0].get("page_title") or "").strip()
    raise ValueError(f"输入文案缺少选题标题，封面标题只允许使用文案第一行的选题标题: {input_path}")


def resolve_title_folder_name(deck_title: str | None, input_path: pathlib.Path) -> str:
    if not deck_title or not deck_title.strip():
        raise ValueError(
            f"输入文案缺少选题标题，正式归档子文件夹名只允许使用文案第一行的选题标题，不允许回退到文件名: {input_path}"
        )
    return sanitize_windows_name(deck_title.strip())


def build_pre_render_audit_block(
    status: str,
    receipt_path: pathlib.Path | None,
    issues: list[str] | None = None,
) -> str:
    receipt_text = str(receipt_path) if receipt_path else ""
    issue_text = "；".join((issues or [])[:3]) if issues else ""
    blocked = status != "approved"
    reason = issue_text or ("等待小审工作包预审放行" if blocked else "工作包预审已通过，可以进入正式生图阶段")
    lines = [
        PREFLIGHT_BLOCK_START,
        f"预审状态：{status}",
        f"预审回执：{receipt_text}",
        f"未通过前禁止生图：{blocked}",
        f"阻塞说明：{reason}",
        PREFLIGHT_BLOCK_END,
    ]
    return "\n".join(lines) + "\n"


def ensure_visual_semantic_review_scaffold(workdir: pathlib.Path, specs_path: pathlib.Path, specs: list[dict[str, Any]]) -> pathlib.Path:
    review_path = workdir / SEMANTIC_REVIEW_FILENAME
    subject_hash = hashlib.sha256(specs_path.read_bytes()).hexdigest()
    if review_path.exists():
        existing = json.loads(review_path.read_text(encoding="utf-8"))
        if existing.get("subject_hash") == subject_hash:
            return review_path
    review = {
        "schema": "ip-visual-semantic-review-v4.1",
        "auditor": "xiaoshen",
        "reviewer": "xiaoshen",
        "review_stage": "pre-render",
        "independent_review": True,
        "subject": {},
        "subject_hash": subject_hash,
        "status": "needs-review",
        "checks": {
            "key_information_selection": "needs-review",
            "formula_preservation": "needs-review",
            "semantic_completeness": "needs-review",
            "transition_text_exclusion": "needs-review",
            "semantic_priority": "needs-review",
            "visual_module_mapping": "needs-review",
            "source_text_ledger_traceability": "needs-review",
            "evidence_node_traceability": "needs-review",
            "parallel_branch_integrity": "needs-review",
        },
        "pages": [
            {"page_index": int(spec["page_index"]), "status": "needs-review", "issues": []}
            for spec in specs
        ],
        "issues": [],
    }
    write_json(review_path, review)
    return review_path


def refresh_visual_semantic_review_scaffold(
    workdir: pathlib.Path,
    specs_path: pathlib.Path,
    handoff_path: pathlib.Path,
    specs: list[dict[str, Any]],
    prompt_paths: list[pathlib.Path],
) -> pathlib.Path:
    """Populate reviewer evidence without making any semantic approval.

    The generator may prepare source, mapping and prompt evidence, but only
    小审 may replace `needs-review` with an approved assessment.
    """
    review_path = workdir / SEMANTIC_REVIEW_FILENAME
    review = json.loads(review_path.read_text(encoding="utf-8")) if review_path.is_file() else {}
    if review.get("status") == "approved":
        return review_path
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    selected_indexes = {
        int(item.get("page_index", 0))
        for item in handoff.get("pages") or []
        if int(item.get("page_index", 0))
    }
    review_specs = [spec for spec in specs if int(spec["page_index"]) in selected_indexes]
    prompt_by_index = {index + 1: path for index, path in enumerate(prompt_paths)}
    review.update({
        "schema": "ip-visual-semantic-review-v4.1",
        "auditor": "xiaoshen",
        "reviewer": "xiaoshen",
        "review_stage": "pre-render",
        "independent_review": True,
        "status": "needs-review",
        "subject": {
            "pages_spec_sha256": file_sha256(specs_path),
            "handoff_sha256": file_sha256(handoff_path),
            "prompt_sha256_by_page": {
                f"page-{int(spec['page_index']):02d}": file_sha256(prompt_by_index[int(spec["page_index"])])
                for spec in review_specs if int(spec["page_index"]) in prompt_by_index
            },
        },
        "checks": {
            "key_information_selection": "needs-review",
            "formula_preservation": "needs-review",
            "semantic_completeness": "needs-review",
            "transition_text_exclusion": "needs-review",
            "semantic_priority": "needs-review",
            "visual_module_mapping": "needs-review",
            "source_text_ledger_traceability": "needs-review",
            "evidence_node_traceability": "needs-review",
            "parallel_branch_integrity": "needs-review",
        },
        "pages": [
            {
                "page_index": int(spec["page_index"]),
                "visual_blueprint_hash": (spec.get("render_plan") or {}).get("visual_blueprint", {}).get("content_hash", ""),
                "source_text_ledger": (spec.get("render_plan") or {}).get("source_text_ledger", []),
                "status": "needs-review",
                "issues": [],
                "keyword_visual_reviews": [
                    {
                        "keyword": mapping["keyword"],
                        "source_quote": mapping["source_quote"],
                        "expected_visual_module": mapping["expected_visual_module"],
                        "actual_visual_module": mapping["expected_visual_module"],
                        "prompt_evidence": mapping["prompt_fragment"],
                        "status": "needs-review",
                        "assessment": "",
                    }
                    for mapping in spec.get("keyword_visual_mappings") or []
                ],
                "evidence_node_reviews": [
                    {
                        "evidence_id": evidence["evidence_id"],
                        "text": evidence["text"],
                        "source_quote": evidence["source_quote"],
                        "parent_visual_module_id": evidence["parent_visual_module_id"],
                        "expected_visual_module": evidence["visual_module_id"],
                        "prompt_evidence": evidence["text"],
                        "status": "needs-review",
                        "assessment": "",
                    }
                    for mapping in spec.get("keyword_visual_mappings") or []
                    for evidence in (mapping.get("evidence_nodes") or [])
                ],
                "non_poster_review": {"status": "needs-review", "evidence": "", "assessment": ""},
            }
            for spec in review_specs
        ],
        "issues": [],
    })
    write_json(review_path, review)
    return review_path


def replace_pre_render_audit_block(text: str, block: str) -> str:
    pattern = re.compile(
        rf"{re.escape(PREFLIGHT_BLOCK_START)}.*?{re.escape(PREFLIGHT_BLOCK_END)}\n?",
        re.S,
    )
    if pattern.search(text):
        return pattern.sub(lambda _match: block, text, count=1)
    return block + "\n" + text


def load_visual_preflight_audit_module() -> Any:
    module_path = PROJECT_ROOT / "01_Agent系统" / "02_小审-质量审核Agent" / "scripts" / "audit_visual_work_package.py"
    module_dir = str(module_path.parent)
    if module_dir not in sys.path:
        sys.path.insert(0, module_dir)
    spec = importlib.util.spec_from_file_location("audit_visual_work_package", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载视觉工作包预审脚本: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def apply_pre_render_audit_state(
    workdir: pathlib.Path,
    receipt_path: pathlib.Path,
    receipt: dict[str, Any],
) -> None:
    status = str(receipt.get("status") or "rejected")
    blocked = status != "approved"
    issues = [str(item) for item in (receipt.get("issues") or [])]
    handoff_path = workdir / "codex-handoff.json"
    job_path = workdir / "codex-render-job.json"
    workflow_path = workdir / "codex-workflow.txt"
    thread_prompt_path = workdir / "codex-render-thread-prompt.md"

    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    handoff["pre_render_audit_required"] = True
    handoff["pre_render_audit_status"] = status
    handoff["pre_render_audit_receipt"] = str(receipt_path)
    handoff["render_blocked_until_preflight_approved"] = blocked
    handoff["pre_render_audit_issues"] = issues
    write_json(handoff_path, handoff)

    if job_path.exists():
        job = json.loads(job_path.read_text(encoding="utf-8"))
        job["pre_render_audit_required"] = True
        job["pre_render_audit_status"] = status
        job["pre_render_audit_receipt"] = str(receipt_path)
        job["render_blocked_until_preflight_approved"] = blocked
        job["render_ready"] = not blocked
        job["blocked_reason_before_render"] = issues[0] if issues else ""
        write_json(job_path, job)

    block = build_pre_render_audit_block(status, receipt_path, issues)
    if workflow_path.exists():
        workflow_text = workflow_path.read_text(encoding="utf-8")
        write_text(workflow_path, replace_pre_render_audit_block(workflow_text, block))
    if thread_prompt_path.exists():
        prompt_text = thread_prompt_path.read_text(encoding="utf-8")
        write_text(thread_prompt_path, replace_pre_render_audit_block(prompt_text, block))


def run_visual_preflight_audit(workdir: pathlib.Path) -> tuple[dict[str, Any], pathlib.Path]:
    module = load_visual_preflight_audit_module()
    receipt = module.audit(workdir)
    receipt_path = module.write_receipt(workdir, receipt)
    apply_pre_render_audit_state(workdir, receipt_path, receipt)
    return receipt, receipt_path


def prepare_review_evidence(workdir: pathlib.Path, review_dir: pathlib.Path) -> pathlib.Path:
    """Stage evidence beside composited review images, never in formal output.

    Pre-render approval only authorizes rendering. It must not create a
    partially populated formal gallery before 小审 has inspected the actual
    composed PNGs. The renderer writes final-review/page-*.png (and covers)
    here, creates the post-render receipt here, then copies the exact approved
    package to the formal gallery in one controlled publish action.
    """
    evidence_dir = ensure_dir(review_dir / "evidence")
    copied: list[dict[str, str]] = []
    # The output auditor binds its review to these two evidence copies, rather
    # than to mutable files in the work package.  Keep both source and copied
    # hashes so a stale or manually substituted review copy is detectable.
    contract_evidence: dict[str, dict[str, str]] = {}
    for filename in (
        "pages-spec.json",
        "codex-handoff.json",
        "codex-workflow.txt",
        "codex-render-job.json",
        ATTEMPT_LEDGER_FILENAME,
        "render-state.json",
        "visual-preflight-audit.json",
        "visual-semantic-review.json",
    ):
        source = workdir / filename
        if source.is_file():
            dest = evidence_dir / filename
            shutil.copy2(source, dest)
            source_sha256 = file_sha256(source)
            evidence_sha256 = file_sha256(dest)
            if source_sha256 != evidence_sha256:
                raise RuntimeError(f"终审运行证据复制哈希不一致: {filename}")
            copied.append({
                "file": filename,
                "source_sha256": source_sha256,
                "evidence_sha256": evidence_sha256,
            })
            if filename in {"pages-spec.json", "codex-handoff.json"}:
                contract_evidence[filename] = {
                    "work_package_sha256": source_sha256,
                    "evidence_sha256": evidence_sha256,
                }
    for dirname in ("prompts", "overlays"):
        source_dir = workdir / dirname
        if source_dir.is_dir():
            dest_dir = ensure_dir(evidence_dir / dirname)
            for source in source_dir.glob("*"):
                if source.is_file():
                    dest = dest_dir / source.name
                    shutil.copy2(source, dest)
                    copied.append({"file": f"{dirname}/{source.name}", "sha256": file_sha256(dest)})
    write_json(evidence_dir / "evidence-manifest.json", {
        "schema": "ip-visual-evidence-v1",
        "work_package": str(workdir),
        "files": copied,
        "output_audit_contract_evidence": contract_evidence,
    })
    return evidence_dir


def prepare_review_evidence_after_preflight(
    workdir: pathlib.Path,
    review_dir: pathlib.Path,
    receipt: dict[str, Any],
) -> pathlib.Path | None:
    """A passed preflight may prepare review evidence, never formal assets."""
    if str(receipt.get("status") or "") != "approved":
        return None
    return prepare_review_evidence(workdir, review_dir)


def archive_evidence(workdir: pathlib.Path, archive_dir: pathlib.Path) -> pathlib.Path:
    """Copy immutable work-package evidence without publishing images."""
    return prepare_review_evidence(workdir, archive_dir)


def archive_evidence_after_approved(
    workdir: pathlib.Path,
    archive_dir: pathlib.Path,
    receipt: dict[str, Any],
) -> pathlib.Path | None:
    """Never create a formal archive when the pre-render gate is rejected."""
    if str(receipt.get("status") or "") != "approved":
        return None
    return archive_evidence(workdir, archive_dir)


def build_archive_expected_outputs(
    selected_pages: list[int],
    archive_dir: pathlib.Path,
    include_covers: bool,
) -> list[str]:
    outputs = [str(archive_dir / f"page-{page_index:02d}.png") for page_index in selected_pages]
    if include_covers:
        outputs.extend([
            str(archive_dir / "cover-3x4.png"),
            str(archive_dir / "cover-4x3.png"),
        ])
    return outputs


def build_codex_render_prompt(
    *,
    deck_title: str,
    workdir: pathlib.Path,
    archive_dir: pathlib.Path,
    reference_image: pathlib.Path,
    handoff_path: pathlib.Path,
    specs_path: pathlib.Path,
    workflow_path: pathlib.Path,
    selected_pages: list[int],
    include_covers: bool,
) -> str:
    page_targets = ", ".join(f"page-{page_index:02d}.png" for page_index in selected_pages)
    cover_targets = "cover-3x4.png, cover-4x3.png" if include_covers else "无"
    expected_outputs = build_archive_expected_outputs(selected_pages, archive_dir, include_covers)
    expected_outputs_text = "\n".join(f"- {path}" for path in expected_outputs)
    quality_reference = QUALITY_REFERENCE_IMAGE.resolve()
    preflight_block = build_pre_render_audit_block("pending", None, ["工作包已生成，必须先通过小审预审后才能开始正式生图"])
    return (
        preflight_block
        + "\n"
        f"你正在当前这条正式出图对话里执行当前选题的出图任务。只执行现有 work package，不重写 skill 规则，不重新生成 handoff，不走任何降级路径。\n\n"
        f"选题：{deck_title}\n"
        f"工作包目录：{workdir}\n"
        f"正式成品目录：{archive_dir}\n"
        f"唯一主脸锚点参考图：{reference_image}\n"
        f"合格成图品质参考：{quality_reference}\n\n"
        f"必须严格执行以下硬约束：\n"
        f"1. 只读取并执行现有 work package：\n"
        f"- {handoff_path}\n"
        f"- {specs_path}\n"
        f"- {workflow_path}\n"
        f"2. 人物身份基准只允许：{reference_image.name}。左上正脸单图是唯一主脸锚点；允许配合固定人物特征文字做辅助稳定，并可按页面语义选择性带 1 张动作单图做辅助参考，但不得引入真人锚点图、姿态库身份图或第二身份源。\n"
        f"2.1 必须同时真实挂载 {quality_reference.name}。它只用于比照标题已填、图文一体、信息密度、手绘模块卡和对象关系；不得复制其中任何文字、坑洞、放大镜、天平、灯泡等语义内容。\n"
        f"3. 只允许 Codex 出图。不得使用任何外部 API、兼容模型、live 后端、CLI 替代渲染链路、本地其他渲染器。\n"
        f"4. 必须服从 handoff 中现有约束，尤其是：allowed_render_mode = codex、codex_only_rendering_required = true、external_api_rendering_forbidden = true。\n"
        f"5. 原生生图返回的就是图文一体最终 PNG，先写入 work package 的 final-review/。禁止无字底图与后续程序叠字；只有小审成品审核通过后，才受控复制到正式归档目录。\n\n"
        f"执行要求：\n"
        f"1. 本次开始生成前，必须确认当前对话真实看到主脸锚点和合格成图品质参考两张图；不是只读路径、不是只沿用记忆。缺少任一真实图片输入必须停止，不能降级为纯文字描述。\n"
        f"2. 先读取上面的预审门禁状态；只有 `预审状态：approved` 且 `未通过前禁止生图：False` 时，才允许开始任何页面生成。\n"
        f"3. 再校验 work package 是否存在且约束字段完整。\n"
        f"4. 按 page_index 顺序依次生成正文页：{page_targets}。\n"
        f"5. 每页执行固定闭环：读取本页 source_text_ledger 与关键词视觉映射 → 原生一次生成含全部文字和配图的最终 PNG → 对照主脸锚点与品质参考检查 → 运行机械与语义检查。不通过时只重画当前页，保留蓝图和原文台账；直到当前页通过才进入下一页。\n"
        f"6. 正文全部通过后，按同一闭环生成封面：{cover_targets}。\n"
        f"7. 每张 PNG 必须直接含精确标题、2–5 张主卡、每张 1–3 条证据短句及对应对象关系；任何空白标题栏、空白主卡/证据槽、伪文字、臆想中文、漏字或图文不匹配都必须退回当前页。\n"
        f"8. 禁止创建无文字候选、禁止任何后续叠字、禁止把对话里的未完成图展示成结果。输出只能写到 `{workdir}/final-review/`。\n"
        f"9. 全部最终 PNG 生成后，在 `{workdir}/final-review/` 建立并填写成图审核表；只有 `audit_visual_outputs.py` 对该暂存目录返回 approved，才把哈希一致的 PNG、evidence/ 和 approved 回执一次性写入正式目录。\n"
        f"10. 结束前逐项核对正式目录中的目标文件、evidence/ 和 approved 回执是否齐全，并把结果汇报清楚。\n\n"
        f"本次目标输出：\n"
        f"{expected_outputs_text}\n"
    )


def build_codex_thread_job_payload(
    *,
    deck_title: str,
    workdir: pathlib.Path,
    archive_dir: pathlib.Path,
    handoff_path: pathlib.Path,
    specs_path: pathlib.Path,
    workflow_path: pathlib.Path,
    reference_image: pathlib.Path,
    selected_pages: list[int],
    include_covers: bool,
) -> dict[str, Any]:
    expected_outputs = build_archive_expected_outputs(selected_pages, archive_dir, include_covers)
    return {
        "job_type": "codex-desktop-same-conversation-render",
        "deck_title": deck_title,
        "work_package_dir": str(workdir),
        "archive_dir": str(archive_dir),
        "handoff_file": str(handoff_path),
        "pages_spec_file": str(specs_path),
        "workflow_file": str(workflow_path),
        "formal_execution_mode": "same-conversation-single-reference-attachment",
        "reference_image": {
            "path": str(reference_image),
            "attachment_required": True,
            "must_be_real_image_input": True,
            "refresh_required_every_run": True,
            "identity_reference_mode": "face-anchor-plus-semantic-action-reference",
            "attach_once_per_new_topic_conversation": True,
        },
        "quality_reference_image": {
            "path": str(QUALITY_REFERENCE_IMAGE.resolve()),
            "sha256": file_sha256(QUALITY_REFERENCE_IMAGE),
            "attachment_required": True,
            "must_be_real_image_input": True,
            "purpose": "layout-density-and-integrated-text-only-not-semantic-source",
        },
        "action_reference_policy": {
            "action_reference_required": False,
            "action_reference_optional": True,
            "action_reference_count_max": 1,
            "identity_redefinition_forbidden": True,
        },
        "selected_pages": selected_pages,
        "include_covers": include_covers,
        "expected_outputs": expected_outputs,
        "pre_render_audit_required": True,
        "pre_render_audit_status": "pending",
        "pre_render_audit_receipt": "",
        "render_blocked_until_preflight_approved": True,
        "render_ready": False,
        "blocked_reason_before_render": "工作包已生成，必须先通过小审预审后才能开始正式生图。",
        "render_rules": {
            "allowed_render_mode": "codex",
            "codex_only_rendering_required": True,
            "external_api_rendering_forbidden": True,
            "direct_writeback_required": True,
            "reference_attachment_failure_route": "record-external:image-service-or-desktop-bridge; keep-reconnecting",
            "rerender_scope": "single-page-only",
            "automatic_serial_completion_required": True,
            "page_retry_policy": "retry-current-page-until-mechanical-and-visual-review-pass",
            "reference_image_must_be_shown_every_run": True,
            "quality_reference_must_be_shown_every_run": True,
            "model_integrated_chinese_required": True,
            "blank_text_region_forbidden": True,
            "program_text_overlay_forbidden": True,
            "identity_review_required_after_each_page": True,
        },
        "archive_delivery_mode": "direct-or-copy-then-clean",
        "intermediate_render_allowed": False,
        "intermediate_images_must_be_deleted_after_archive": True,
        "archive_completion_requires_formal_dir_only": True,
        "execution_entrypoint": "persistent-recovery-controller",
        "auto_attachment_capability_status": "awaiting-runtime-attachment-with-recovery",
        "current_conversation_rendering_required": True,
        "current_conversation_rendering_allowed_if_reference_visible": True,
        "recovery_reason_if_no_image_attachment": "当前执行环境暂不能真实挂载角色主脸锚点参考图；记录外部异常并在 reconnecting 状态等待桌面恢复，未进入正式出图链路。",
        "identity_baseline_image": reference_image.name,
        "fixed_identity_traits_required": True,
        "fixed_identity_traits_mode": "auxiliary-only",
        "secondary_identity_sources_forbidden": True,
        "identity_reference_mode": "face-anchor-plus-semantic-action-reference",
        "identity_face_anchor_variant": "top-left-frontal",
        "identity_face_anchor_required": True,
        "identity_face_anchor_image": reference_image.name,
        "action_reference_required": False,
        "action_reference_optional": True,
        "expression_exaggeration_limit": "reduced",
        "chibi_drift_forbidden": True,
        "identity_review_checklist": [
            "眼镜一致",
            "肤色一致",
            "发型一致",
            "脸型一致",
            "年龄感一致",
            "白西装黑内搭一致",
            "额头与发际线方向一致",
            "眼镜外轮廓一致",
            "脸宽脸长比一致",
            "五官间距一致",
            "成熟感一致",
        ],
    }


def write_codex_thread_job_files(
    *,
    deck_title: str,
    workdir: pathlib.Path,
    archive_dir: pathlib.Path,
    handoff_path: pathlib.Path,
    specs_path: pathlib.Path,
    workflow_path: pathlib.Path,
    reference_image: pathlib.Path,
    selected_pages: list[int],
    include_covers: bool,
) -> tuple[pathlib.Path, pathlib.Path]:
    prompt_path = workdir / "codex-render-thread-prompt.md"
    job_path = workdir / "codex-render-job.json"
    prompt_text = build_codex_render_prompt(
        deck_title=deck_title,
        workdir=workdir,
        archive_dir=archive_dir,
        reference_image=reference_image,
        handoff_path=handoff_path,
        specs_path=specs_path,
        workflow_path=workflow_path,
        selected_pages=selected_pages,
        include_covers=include_covers,
    )
    job_payload = build_codex_thread_job_payload(
        deck_title=deck_title,
        workdir=workdir,
        archive_dir=archive_dir,
        handoff_path=handoff_path,
        specs_path=specs_path,
        workflow_path=workflow_path,
        reference_image=reference_image,
        selected_pages=selected_pages,
        include_covers=include_covers,
    )
    write_text(prompt_path, prompt_text)
    write_json(job_path, job_payload)
    return prompt_path, job_path


def split_sentences(text: str) -> list[str]:
    normalized = clean_input_text(text)
    if not normalized:
        return []
    sentences: list[str] = []
    for raw_line in normalized.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = re.findall(r"[^。！？；!?;\n]+[。！？；!?;]?", line)
        for part in parts:
            sentence = part.strip()
            if sentence:
                sentences.append(sentence)
    return sentences


def extract_step_label(sentence: str) -> str | None:
    match = STEP_LABEL_RE.match(sentence)
    if not match:
        return None
    label = match.group("label").strip()
    return label.rstrip("，,：:。 ")


def strip_step_label(sentence: str) -> str:
    return STEP_LABEL_RE.sub("", sentence, count=1).lstrip("，,：:。 ")


def normalize_short_label(text: str) -> str:
    normalized = re.sub(r"[：:，,。！？；、“”\"'（）()《》【】\[\]]+", " ", text)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def clean_source_line(text: str) -> str:
    cleaned = strip_markdown_bold(text).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def trim_source_fragment(text: str) -> str:
    cleaned = clean_source_line(text)
    cleaned = cleaned.strip("，,。！？；;：:“”\"'（）()《》【】[] ")
    return cleaned.strip()


def normalize_source_lookup(text: str) -> str:
    normalized = trim_source_fragment(text)
    normalized = re.sub(r"\s+", "", normalized)
    return normalized


def split_direct_source_fragments(text: str, max_len: int = 16) -> list[str]:
    cleaned = trim_source_fragment(text)
    if not cleaned:
        return []
    candidates: list[str] = [cleaned]
    parts = re.split(r"[，,；;：:\|｜/]", cleaned)
    for part in parts:
        fragment = trim_source_fragment(part)
        if fragment:
            candidates.append(fragment)
    fragments: list[str] = []
    for candidate in candidates:
        if not candidate:
            continue
        if len(candidate) > max_len:
            candidate = candidate[:max_len].rstrip("，,；;：: ")
        if 2 <= len(candidate) <= max_len and candidate not in fragments:
            fragments.append(candidate)
    return fragments


def sentence_to_exact_fragment(sentence: str, limit: int = 14) -> tuple[str, str]:
    source_quote = trim_source_fragment(sentence)
    if not source_quote:
        return "", ""
    for fragment in split_direct_source_fragments(source_quote, max_len=limit):
        if 2 <= len(fragment) <= limit:
            return fragment, source_quote
    return source_quote[:limit].rstrip("，,；;：: "), source_quote


def extract_exact_display_fragments(sentences: list[str], limit_points: int = 4, limit: int = 14) -> tuple[list[str], dict[str, str]]:
    points: list[str] = []
    source_quotes: dict[str, str] = {}
    for sentence in sentences:
        fragment, source_quote = sentence_to_exact_fragment(sentence, limit=limit)
        if not fragment:
            continue
        if fragment not in points:
            points.append(fragment)
            source_quotes[fragment] = source_quote
        if len(points) >= limit_points:
            break
    return points[:limit_points], source_quotes


def is_formula_text(text: str) -> bool:
    cleaned = trim_source_fragment(text)
    return "=" in cleaned and bool(cleaned.split("=", 1)[0].strip()) and bool(cleaned.split("=", 1)[1].strip())


def extract_formula_fragment(text: str) -> str:
    cleaned = trim_source_fragment(text)
    if not is_formula_text(cleaned):
        return ""
    for separator in ("：", ":"):
        if separator in cleaned:
            suffix = cleaned.rsplit(separator, 1)[-1].strip()
            if is_formula_text(suffix):
                return suffix
    return cleaned


def is_semantically_complete_phrase(text: str) -> bool:
    cleaned = trim_source_fragment(text)
    if not cleaned or len(cleaned) < 2:
        return False
    if is_formula_text(cleaned):
        return True
    if WEAK_FRAGMENT_RE.search(cleaned):
        return False
    if cleaned in {"比如", "所以", "但是", "因为", "其实", "第一步", "为什么", "还记得最开始我说的"}:
        return False
    if cleaned.startswith("因为") and not re.search(r"(?:所以|因此|结果|导致|才)", cleaned):
        return False
    if re.match(r"^(?:我|你|他|她)想做拍", cleaned):
        return False
    if re.search(r"(?:为了|因为|所以|但是|而且|如果|只要|还是|应该|必须|才能|找到|实现|成为|发现)$", cleaned):
        return False
    return True


def split_complete_source_phrases(text: str) -> list[str]:
    source = trim_source_fragment(text)
    if not source:
        return []
    if is_formula_text(source):
        return [extract_formula_fragment(source)]
    if "连续追问" in source and "第一性原理" in source:
        return [source]
    # Visible copy must remain a complete spoken thought.  Commas and colons
    # frequently split a Chinese condition from its result (for example
    # "人只有安静下来，才有余地…") or an introducer from its actual content
    # ("真正的衡量标准是：…").  They are therefore not safe visual-text
    # boundaries.  Only terminal sentence boundaries may produce a label.
    raw_parts = re.split(r"[。！？!?；;]", source)
    phrases: list[str] = []
    for raw_part in raw_parts:
        part = trim_source_fragment(raw_part)
        if not part:
            continue
        stripped = TRANSITION_PREFIX_RE.sub("", part).strip()
        stripped = re.sub(r"^(?:所以你|这里面有|那我是应该先|还是应该先|还是去|应该先|去找|先把|再用)", "", stripped).strip()
        stripped = re.sub(r"^但是有?不能脱离你的", "", stripped).strip()
        stripped = re.sub(r"(?:呢|吗)$", "", stripped).strip()
        candidate = stripped if is_semantically_complete_phrase(stripped) else part
        if is_semantically_complete_phrase(candidate) and candidate not in phrases:
            phrases.append(candidate)
    for structural in re.findall(r"\d+个(?:点|步骤)|\d+步", source):
        if structural not in phrases:
            phrases.append(structural)
    if re.search(r"条件一变.*结论.*失效", source) and source not in phrases:
        phrases.insert(0, source)
    return phrases


def split_speech_clauses(text: str) -> list[str]:
    clauses: list[str] = []
    for raw_line in text.splitlines():
        line = clean_source_line(raw_line)
        if not line:
            continue
        # Keep the density metric aligned with the visible-label contract:
        # a comma/colon clause is not independently renderable unless it is a
        # complete thought.  Counting those fragments inflated the required
        # label density while the source-anchored selector correctly rejected
        # them, producing impossible work packages.
        for raw_part in re.split(r"[。！？!?；;]", line):
            part = trim_source_fragment(raw_part)
            if part and part not in clauses:
                clauses.append(part)
    return clauses


def is_valid_visible_clause(text: str, title: str) -> bool:
    cleaned = trim_source_fragment(text)
    if not cleaned or not is_semantically_complete_phrase(cleaned):
        return False
    information_type, _, _ = semantic_information_type(cleaned, title)
    return information_type != "transition"


def visible_text_density_target(valid_clause_count: int) -> int:
    if valid_clause_count <= 0:
        return 0
    return max(1, math.ceil(valid_clause_count / 2.5))


def merge_source_lines_for_semantics(body: str) -> list[str]:
    merged: list[str] = []
    pending = ""
    for raw_line in body.splitlines():
        line = clean_source_line(raw_line)
        if not line:
            continue
        if pending:
            line = f"{pending}{line}"
            pending = ""
        if line.endswith(("，", ",", "：", ":")):
            pending = line
            continue
        # Preserve complete sentence units as separate source quotes.  This
        # allows a long Markdown line with several full sentences to map to
        # several distinct visual modules, without falling back to comma-level
        # fragments or treating the whole paragraph as one dedupe bucket.
        merged.extend(
            trim_source_fragment(part)
            for part in re.findall(r"[^。！？!?；;]+[。！？!?；;]?", line)
            if trim_source_fragment(part)
        )
    if pending:
        merged.extend(
            trim_source_fragment(part)
            for part in re.findall(r"[^。！？!?；;]+[。！？!?；;]?", pending)
            if trim_source_fragment(part)
        )
    return merged


def semantic_information_type(text: str, page_title: str) -> tuple[str, int, str]:
    cleaned = trim_source_fragment(text)
    haystack = f"{page_title}\n{cleaned}"
    if is_formula_text(cleaned):
        return "formula", 100, "等式或公式必须完整显示"
    if cleaned.startswith(("今天来聊聊", "我就发现", "其实你只要懂", "刚刚我们讲了", "你会发现还是", "特别沉迷于找")) and not any(
        marker in cleaned for marker in ("唯一变量法", "只改变一个变量", "核心客户", "人群范围")
    ):
        return "transition", 10, "过渡、铺垫或不完整表达"
    if cleaned.startswith("光找到本质还不够") and "必须有明确的行动目标" not in cleaned:
        return "transition", 10, "承上启下，不作为独立可见重点"
    if "总结出过滤" in cleaned:
        return "context", 20, "原文表达不完整，只用于上下文"
    if re.search(r"\d+个(?:点|步骤)|\d+步", cleaned):
        return "action", 90, "步骤数量或结构入口"
    if "为什么" in cleaned and ("连续追问" in page_title or cleaned.startswith("为什么")):
        return "question-chain", 88, "连续追问节点"
    if cleaned.startswith("那为什么"):
        return "context", 35, "设问铺垫，只用于画面上下文"
    if cleaned.startswith("那如何") and "连续追问" not in page_title:
        return "context", 35, "设问铺垫，只用于画面上下文"
    if any(marker in cleaned for marker in ("写下来", "找反例", "只留下", "只改变", "连续追问", "清空", "找条件", "定方向", "只去")):
        return "action", 92, "可执行步骤动作"
    if any(marker in cleaned for marker in ("不是", "而是", "反例", "条件一变", "失效", "可以换", "不能动", "不管")):
        return "contrast", 86, "反例、对比或条件变化"
    if "每天工作2小时" in cleaned or "10小时的工作量" in cleaned:
        return "conclusion", 96, "效率对比结论必须作为可见锚点"
    if any(marker in cleaned for marker in ("必须", "不能", "只有", "肯定", "永远", "本质", "判断", "目标", "误区", "伪逻辑", "核心客户", "服从什么", "大家都是这么说的", "信任", "个人IP", "护城河", "容易被复制", "没办法复制", "任何产品", "28定位", "高效时间", "每天工作2小时", "10小时的工作量")):
        return "conclusion", 84, "核心判断、条件或结论"
    if any(marker in haystack for marker in ("写下来", "找反例", "只留下", "只改变一个变量", "连续追问", "清空", "找条件", "定方向", "只去")) and any(
        marker in cleaned for marker in ("写下来", "找反例", "只留下", "只改变", "连续追问", "清空", "找条件", "定方向", "只去")
    ):
        return "action", 92, "可执行步骤动作"
    if "为了" in cleaned:
        return "causal", 90, "目标或目的链"
    if "因为" in cleaned or "所以" in cleaned:
        return "causal", 78, "因果关系"
    if any(marker in cleaned for marker in ("选题", "文案", "画面", "人设", "爆款结构", "目标人群", "脚手架", "承重墙", "变量", "小群人", "一个问题", "超出预期", "客户", "经验和案例", "内容", "服务")):
        return "supporting-object", 68, "具体对象、变量或类比物"
    if TRANSITION_PREFIX_RE.match(cleaned) or not is_semantically_complete_phrase(cleaned):
        return "transition", 10, "过渡、铺垫或不完整表达"
    return "context", 35, "只用于理解画面上下文"


def visual_module_for_information_type(information_type: str) -> str:
    return {
        "formula": "formula-board",
        "contrast": "contrast-block",
        "causal": "causal-chain",
        "action": "action-node",
        "question-chain": "question-ladder",
        "supporting-object": "icon-tag-block",
        "conclusion": "conclusion-anchor",
    }.get(information_type, "planning-context")


def build_semantic_text_contract(
    title: str,
    body: str,
    page_type: str,
    cue_limit: int,
    support_limit: int,
) -> dict[str, Any]:
    del page_type
    speech_clauses = [
        {"text": clause, "valid_for_visible": is_valid_visible_clause(clause, title)}
        for clause in split_speech_clauses(body)
    ]
    valid_clause_count = sum(1 for clause in speech_clauses if clause["valid_for_visible"])
    density_target = visible_text_density_target(valid_clause_count)
    semantic_units: list[dict[str, Any]] = []
    must_show_quotes: list[str] = []
    supporting_quotes: list[str] = []
    context_quotes: list[str] = []
    discarded_quotes: list[str] = []
    formula_items: list[dict[str, str]] = []
    candidates: list[dict[str, Any]] = []

    for order, raw_line in enumerate(merge_source_lines_for_semantics(body)):
        source_quote = trim_source_fragment(raw_line)
        if not source_quote:
            continue
        information_type, priority, reason = semantic_information_type(source_quote, title)
        visibility = "context-only"
        if information_type in {"formula", "contrast", "conclusion", "action", "question-chain", "causal"}:
            visibility = "must-show"
            must_show_quotes.append(source_quote)
        elif information_type == "supporting-object":
            visibility = "supporting"
            supporting_quotes.append(source_quote)
        elif information_type == "transition":
            visibility = "discard-visible"
            discarded_quotes.append(source_quote)
        else:
            context_quotes.append(source_quote)
        phrases = split_complete_source_phrases(source_quote)
        entity_phrases = [] if information_type == "formula" else [
            entity for entity in ("唯一变量法", "爆款选题", "爆款结构", "视频画面", "人群范围", "核心客户")
            if entity in source_quote
        ]
        for entity in entity_phrases:
            if entity not in phrases:
                phrases.append(entity)
        if entity_phrases:
            phrases = [
                phrase for phrase in phrases
                if not any(entity in phrase and phrase != entity for entity in entity_phrases)
            ] + [entity for entity in entity_phrases if entity not in phrases]
        if information_type == "formula":
            formula_text = extract_formula_fragment(source_quote)
            left, right = formula_text.split("=", 1)
            formula_items.append({"text": formula_text, "left": left.strip(), "right": right.strip()})
        semantic_units.append({
            "order": order,
            "text": source_quote,
            "source_quote": source_quote,
            "information_type": information_type,
            "priority": priority,
            "visibility": visibility,
            "reason": reason,
            "complete_phrases": phrases,
        })
        contains_key_phrase = any(
            semantic_information_type(phrase, title)[0] not in {"transition", "context"}
            for phrase in phrases
        )
        if visibility in {"must-show", "supporting"} or entity_phrases or contains_key_phrase or is_valid_visible_clause(source_quote, title):
            for phrase in phrases:
                if visibility == "discard-visible" and phrase not in entity_phrases:
                    continue
                phrase_type, phrase_priority, phrase_reason = semantic_information_type(phrase, title)
                if phrase_type == "context" and is_valid_visible_clause(phrase, title):
                    phrase_type = "supporting-object"
                    phrase_priority = max(phrase_priority, 62)
                    phrase_reason = "有效口播小句，可作为模块标签辅助承接口播"
                if phrase_type in {"transition", "context"}:
                    continue
                phrase_priority += sum(2 for marker in KEY_INFORMATION_MARKERS if marker in phrase)
                if "误区" in phrase:
                    phrase_priority += 10
                if any(marker in phrase for marker in ("核心客户", "人群范围", "唯一变量法")):
                    phrase_priority += 12
                candidates.append({
                    "text": phrase,
                    "source_quote": source_quote,
                    "information_type": information_type if information_type == "formula" else phrase_type,
                    "priority": max(priority, phrase_priority) if information_type == "formula" else phrase_priority,
                    "reason": phrase_reason,
                    "order": order,
                })

    candidates.sort(key=lambda item: (-int(item["priority"]), int(item["order"])))
    cue_phrases: list[str] = []
    cue_quotes: dict[str, str] = {}
    support_labels: list[str] = []
    support_quotes: dict[str, str] = {}
    assignments: list[dict[str, str]] = []
    assigned_source_quote_keys: set[str] = set()

    formula_count = len(formula_items)
    # Long, complete source sentences are deliberately routed to cue slots.
    # Their capacity must be able to meet the page density contract; otherwise
    # only the first two long sentences survive and key causal/action units
    # are silently lost.
    effective_cue_limit = max(2, cue_limit, density_target, min(4, formula_count + 1))
    if "连续追问" in title:
        effective_cue_limit = max(effective_cue_limit, 4)
    effective_support_limit = max(support_limit, density_target)
    for item in candidates:
        text = str(item["text"])
        source_quote = str(item["source_quote"])
        information_type = str(item["information_type"])
        source_quote_key = normalize_source_lookup(source_quote)
        if text in cue_phrases or text in support_labels:
            continue
        # A source sentence can explain only one visible module. Otherwise the
        # renderer turns one spoken clause into several repeated label fragments.
        if source_quote_key and source_quote_key in assigned_source_quote_keys:
            continue
        if information_type == "formula" or len(text) > 14:
            if len(cue_phrases) >= effective_cue_limit:
                continue
            cue_phrases.append(text)
            cue_quotes[text] = source_quote
        else:
            if len(support_labels) >= effective_support_limit:
                continue
            support_labels.append(text)
            support_quotes[text] = source_quote
        if source_quote_key:
            assigned_source_quote_keys.add(source_quote_key)
        assignments.append({
            "visible_text": text,
            "source_quote": source_quote,
            "information_type": information_type,
            "visual_module": visual_module_for_information_type(information_type),
            "selection_reason": str(item["reason"]),
        })

    priority_order = [item["text"] for item in candidates if item["text"] in cue_phrases or item["text"] in support_labels]
    represented_quotes = {str(item["source_quote"]) for item in assignments}
    visible_density_actual = len(unique_preserve_order(cue_phrases + support_labels))
    eligible_visible_count = len(unique_preserve_order([str(item["text"]) for item in candidates]))
    density_gap_reason = ""
    if visible_density_actual < min(density_target, eligible_visible_count):
        density_gap_reason = "有效原文重点不足或被页内去重/完整性规则过滤"
    return {
        "speech_clauses": speech_clauses,
        "valid_clause_count": valid_clause_count,
        # Some pages have fewer independently source-traceable, non-duplicate
        # labels than the raw speech-clause heuristic.  A target above that
        # ceiling is impossible to satisfy without inventing or repeating text.
        "visible_text_density_target": min(density_target, eligible_visible_count),
        "visible_text_density_actual": visible_density_actual,
        "visible_text_density_required": True,
        "density_gap_reason": density_gap_reason,
        "parallel_items_must_show": [
            clause["text"] for clause in speech_clauses
            if clause["valid_for_visible"] and re.search(r"(?:什么内容|什么事|谁的问题|一个小群人|一个问题|结果|内容|服务|信任|护城河)", clause["text"])
        ],
        "formula_or_equation_must_show": bool(formula_items),
        "semantic_units": semantic_units,
        "must_show_source_quotes": unique_preserve_order([quote for quote in must_show_quotes if quote in represented_quotes]),
        "supporting_source_quotes": unique_preserve_order(supporting_quotes),
        "context_only_source_quotes": unique_preserve_order(context_quotes),
        "discarded_transition_quotes": unique_preserve_order(discarded_quotes),
        "key_information_types": unique_preserve_order([item["information_type"] for item in candidates]),
        "formula_items": formula_items,
        "semantic_priority_order": unique_preserve_order(priority_order),
        "visual_module_assignments": assignments,
        "cue_phrases": cue_phrases,
        "cue_phrase_source_quotes": cue_quotes,
        "support_labels": support_labels,
        "support_label_source_quotes": support_quotes,
    }


def infer_exact_source_quote(value: str, title: str, body: str) -> str:
    normalized_value = normalize_source_lookup(value)
    if not normalized_value:
        return ""
    sources = [title] + [line.strip() for line in body.splitlines() if line.strip()]
    for source in sources:
        cleaned_source = trim_source_fragment(source)
        if normalized_value and normalized_value in normalize_source_lookup(cleaned_source):
            return cleaned_source
    return ""


def extract_source_terms(text: str, limit: int = 4, max_len: int = 8) -> list[str]:
    terms: list[str] = []
    for token in re.findall(r"[\u4e00-\u9fffA-Za-z0-9]+", normalize_short_label(text)):
        if len(token) < 2 or len(token) > max_len:
            continue
        if token not in terms:
            terms.append(token)
        if len(terms) >= limit:
            break
    return terms[:limit]


def chunk_body_to_title_lines(chunk: str) -> tuple[str, str, bool]:
    lines = [line.strip() for line in chunk.splitlines() if line.strip()]
    if not lines:
        return "", "", False
    bold_title_index: int | None = None
    bold_title = ""
    for index, line in enumerate(lines):
        candidate = extract_bold_title(line)
        if candidate:
            bold_title_index = index
            bold_title = candidate
            break
    if bold_title_index is not None:
        title = bold_title
        body_lines = [strip_markdown_bold(line) for idx, line in enumerate(lines) if idx != bold_title_index]
        body = "\n".join(line for line in body_lines if line).strip()
        return title, body, True
    title = strip_markdown_bold(lines[0])
    body_lines = [strip_markdown_bold(line) for line in lines[1:]]
    body = "\n".join(line for line in body_lines if line).strip()
    return title, body, False


def build_cover_support_labels(specs: list[dict[str, Any]], cover_title: str) -> list[str]:
    labels: list[str] = []
    for spec in specs[:3]:
        labels.extend(spec.get("support_labels") or [])
        labels.extend(spec.get("flow_labels") or [])
    normalized: list[str] = []
    for label in labels:
        cleaned = normalize_short_label(str(label))
        if 1 <= len(cleaned) <= 10 and cleaned not in normalized:
            normalized.append(cleaned)
    title_tokens = set(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]+", cover_title))
    filtered = [label for label in normalized if label not in title_tokens]
    return filtered[:3]


def build_cover_cue_phrases(specs: list[dict[str, Any]], cover_title: str) -> list[str]:
    first_spec = specs[0] if specs else {}
    candidates = []
    for phrase in first_spec.get("cue_phrases") or []:
        cleaned = normalize_short_label(str(phrase))
        if not cleaned or cleaned == normalize_short_label(cover_title):
            continue
        if len(cleaned) > 16:
            continue
        candidates.append(cleaned)
    return unique_preserve_order(candidates)


def trim_cover_accent_blocks(
    cue_phrases: list[str],
    support_labels: list[str],
) -> tuple[list[str], list[str], int]:
    cue_candidates = unique_preserve_order(cue_phrases)
    support_candidates = [label for label in unique_preserve_order(support_labels) if label not in cue_candidates]
    selected_cue_phrases = cue_candidates[:1]
    remaining_slots = COVER_ACCENT_BLOCKS_MAX - len(selected_cue_phrases)
    selected_support_labels = support_candidates[:max(remaining_slots, 0)]
    total_blocks = len(selected_cue_phrases) + len(selected_support_labels)
    return selected_cue_phrases, selected_support_labels, total_blocks


def choose_cover_action_guidance(cover_title: str) -> str:
    if re.search(r"(赚不到|没钱|收入|变现|副业)", cover_title):
        return "角色要明确演出“白天很强、下班后变现受阻”的反差感，可以做出掏空口袋、推不开收入门、对着结果箭头发力的动作"
    if re.search(r"(误区|坑|陷阱)", cover_title):
        return "角色要像在识别和拆开误区，动作带有阻挡、拆解、指出问题的感觉"
    if re.search(r"(增长|突破|翻盘|逆袭)", cover_title):
        return "角色动作要更主动推进，带有冲刺、推开、跃迁、拉升的感觉"
    return "角色动作要服务标题核心矛盾，带有明显判断、推动、拆解或受阻后的反击感"


def choose_cover_expression_guidance(cover_title: str) -> str:
    if re.search(r"(赚不到|没钱|受困|卡住|误区)", cover_title):
        return "表情要有强烈反差，混合不甘、警醒、较真和一点点被现实卡住后的发狠感"
    if re.search(r"(机会|增长|翻盘|突破)", cover_title):
        return "表情要更兴奋、更笃定，带有抓住机会和主动突破的状态"
    return "表情要明显、夸张、可信，优先体现判断感、推进感和主题里的情绪张力"


def build_cover_outputs(
    specs: list[dict[str, Any]],
    deck_title: str | None,
    archive_dir: pathlib.Path,
    input_path: pathlib.Path,
    cover_text_mode: str = "source-labels",
) -> list[dict[str, Any]]:
    cover_title = resolve_cover_title(deck_title, specs, input_path)
    raw_support_labels = build_cover_support_labels(specs, cover_title)
    raw_cue_phrases = build_cover_cue_phrases(specs, cover_title)
    cue_phrases, support_labels, accent_blocks_total = trim_cover_accent_blocks(raw_cue_phrases, raw_support_labels)
    if cover_text_mode == "title-only":
        cue_phrases, support_labels, accent_blocks_total = [], [], 0
    first_spec = specs[0] if specs else {}
    role_expression_tags = unique_preserve_order(first_spec.get("role_expression_tags") or [])[:4]
    role_action_tags = unique_preserve_order(first_spec.get("role_action_tags") or [])[:4]
    items: list[dict[str, Any]] = []
    for cover in COVER_OUTPUT_SPECS:
        cover_ref_spec = {
            "page_title": cover_title,
            "title_text": cover_title,
            "display_title": cover_title,
            "page_type": "封面图",
            "section_kind": "cover",
            "role_action_tags": role_action_tags,
            "role_expression_tags": role_expression_tags,
            "cue_phrases": cue_phrases,
            "visual_action_cues": [cover_title],
            "visual_scene_cues": support_labels,
        }
        role_action_family, role_action_basis = infer_action_family(cover_ref_spec)
        role_expression_family, expression_basis = infer_expression_family(cover_ref_spec, role_action_family)
        allowed_role_framings = infer_allowed_role_framings("封面图", "large-focus", cover_title, 1, role_action_family)
        cover_prop_signature = infer_prop_signature(role_action_family)
        cover_pose_key = f"{cover['cover_type']}-{pose_digest(cover['cover_type'], cover_title, role_action_family, role_expression_family)}"
        cover_reference_filenames = build_reference_filename_preferences(role_action_family, cover_prop_signature)
        role_action_intent = choose_cover_action_guidance(cover_title)
        role_expression_intent = choose_cover_expression_guidance(cover_title)
        role_pose_brief = "封面动作由标题语义决定，优先用更强演法承载主题，但不复用正文第一页模板"
        role_prop_intent = choose_role_prop_intent(cover_title, "\n".join(cue_phrases), "封面图", role_action_family)
        hair_expression_mode = choose_hair_expression_mode(cover_title, "\n".join(cue_phrases), role_expression_family)
        if cover["cover_type"] == "cover-3x4":
            role_framing_intent = "full-body"
            role_position_intent = "inside-center"
            role_action_intent = f"{role_action_intent}，纵向封面更强调竖向张力和主体冲突"
        else:
            role_framing_intent = "three-quarter"
            role_position_intent = "inside-left"
            role_action_intent = f"{role_action_intent}，横向封面更强调横向推进和结构展开"
        render_signature = build_render_signature(
            role_action_intent,
            role_expression_intent,
            role_prop_intent,
            role_framing_intent,
            role_position_intent,
        )
        items.append({
            "cover_type": cover["cover_type"],
            "aspect_ratio": cover["aspect_ratio"],
            "title_text": cover_title,
            "display_title": cover_title,
            "source_title_full": cover_title,
            "page_body": "",
            "deck_title": cover_title,
            "deck_title_context_only": False,
            "deck_title_visible_forbidden": False,
            "background_color": COVER_BG,
            "skin_tone_base": SKIN_TONE_BASE,
            "line_color": ODD_LINE,
            "role_required": True,
            "style_mode": "hand-drawn-visual-note",
            "cover_text_mode": cover_text_mode,
            "support_labels_allowed": True,
            "support_labels": support_labels,
            "support_label_source_quotes": {label: label for label in support_labels},
            "support_labels_required": bool(support_labels),
            "source_rooted_labels_required": bool(support_labels),
            "visible_text_source_mode": "exact-source-only",
            "semantic_candidate_items": unique_preserve_order([cover_title] + cue_phrases + support_labels),
            "semantic_candidate_source_quotes": {item: item for item in unique_preserve_order([cover_title] + cue_phrases + support_labels)},
            "label_anchor_targets": ["primary-visual", "mini-visual", "node", "misconception-block", "flow-block"],
            "cue_phrases": cue_phrases,
            "cue_phrase_source_quotes": {phrase: phrase for phrase in cue_phrases},
            "flow_labels": [],
            "flow_label_source_quotes": {},
            "source_text_only_visual_mode": True,
            "inferred_visuals_forbidden": True,
            "role_count_min": 1,
            "role_count_max": 1,
            "role_count_decision_mode": "cover-single-role-only",
            "role_count_target": 1,
            "multi_role_required": False,
            "multi_role_trigger_type": "cover-single-role-only",
            "role_distribution_brief": "封面固定单人物，只允许一个当前角色承担封面主动作。",
            "role_slot_assignments": ["封面主角色"],
            "same_page_role_pose_distinct_required": False,
            "role_usage_mode": "supporting-only",
            "role_density_preference": "large-focus",
            "cover_accent_blocks_min": 0 if cover_text_mode == "title-only" else COVER_ACCENT_BLOCKS_MIN,
            "cover_accent_blocks_max": COVER_ACCENT_BLOCKS_MAX,
            "cover_accent_blocks_total": accent_blocks_total,
            "role_action_tags": role_action_tags,
            "role_expression_tags": role_expression_tags,
            "role_action_match_required": True,
            "role_action_match_basis": role_action_basis,
            "role_action_family": role_action_family,
            "role_expression_family": role_expression_family,
            "role_expression_match_basis": expression_basis,
            "role_action_intent": role_action_intent,
            "role_expression_intent": role_expression_intent,
            "role_pose_brief": role_pose_brief,
            "role_prop_intent": role_prop_intent,
            "role_framing_intent": role_framing_intent,
            "role_position_intent": role_position_intent,
            "hair_expression_mode": hair_expression_mode,
            "render_signature": render_signature,
            "identity_anchor_required": True,
            "face_anchor_attached_required": True,
            "identity_drift_forbidden": True,
            "hair_variant_forbidden": True,
            "role_pose_key": cover_pose_key,
            "role_pose_family": role_action_family,
            "role_pose_repeat_forbidden": True,
            "global_render_signature_unique_required": True,
            "mic_pose_limited_once": True,
            "prop_signature": cover_prop_signature,
            "role_reference_filenames": cover_reference_filenames,
            "single_role_required": True,
            "allowed_role_framings": allowed_role_framings,
            "action_reference_optional": True,
            "action_fallback_forbidden": False,
            "reserved_zone_enabled": False,
            "reserved_zone_scope": "none",
            "reserved_zone_size_cm": None,
            "reserved_zone_side_ratio_of_height": None,
            "reserved_zone": None,
            "reserved_zone_rules": [],
            "action_guidance": role_action_intent,
            "expression_guidance": role_expression_intent,
            "composition_guidance": cover["composition_guidance"],
            "title_zone": cover["title_zone"],
            "output_image": str(archive_dir / cover["filename"]),
        })
    return items


def build_cover_reference_chain(
    cover_ref_source: dict[str, Any],
    role: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str]:
    face_anchor = select_face_anchor_profile(role)
    action_ref, action_reason, action_family = select_action_reference_profile(cover_ref_source, role)
    return face_anchor, action_ref, action_reason


def attach_cover_role_chain(
    cover_outputs: list[dict[str, Any]],
    specs: list[dict[str, Any]],
    role: dict[str, Any],
) -> None:
    for cover_spec in cover_outputs:
        cover_ref_source = dict(specs[0]) if specs else {}
        cover_ref_source.update(cover_spec)
        face_anchor_ref, action_ref, action_reason = build_cover_reference_chain(cover_ref_source, role)
        cover_spec["role_face_anchor_image"] = str(face_anchor_ref["file_path"]) if face_anchor_ref else ""
        cover_spec["role_action_reference_image"] = str(action_ref["file_path"]) if action_ref else ""
        cover_spec["role_action_reference_reason"] = action_reason or (action_ref.get("name", "") if action_ref else "")
        cover_spec["quality_reference_image"] = str(QUALITY_REFERENCE_IMAGE.resolve())
        cover_spec["quality_reference_sha256"] = file_sha256(QUALITY_REFERENCE_IMAGE)


def attach_page_role_chain(specs: list[dict[str, Any]], role: dict[str, Any]) -> None:
    """Attach the same reference chain before prompt generation and handoff."""
    for spec in specs:
        face_anchor_ref, action_ref, action_reason = split_role_reference_chain(
            spec, role, preferred_variant="standard"
        )
        spec["role_face_anchor_image"] = str(face_anchor_ref["file_path"]) if face_anchor_ref else ""
        spec["role_action_reference_image"] = str(action_ref["file_path"]) if action_ref else ""
        spec["role_action_reference_reason"] = action_reason or (action_ref.get("name", "") if action_ref else "")
        spec["role_face_anchor_sha256"] = file_sha256(spec["role_face_anchor_image"])
        spec["role_action_reference_sha256"] = file_sha256(spec["role_action_reference_image"])
        spec["quality_reference_image"] = str(QUALITY_REFERENCE_IMAGE.resolve())
        spec["quality_reference_sha256"] = file_sha256(QUALITY_REFERENCE_IMAGE)


def build_reference_lock_metadata() -> dict[str, Any]:
    return {
        "reference_lock_required": True,
        "text_only_render_forbidden": True,
        "renderer_must_attach_reference_images": True,
        "reference_image_refresh_required_every_run": True,
        "reference_image_must_be_shown_to_model_every_run": True,
        "identity_reference_mode": "face-anchor-plus-semantic-action-reference",
        "identity_baseline_image": FACE_ANCHOR_FILENAME,
        "fixed_identity_traits_required": True,
        "fixed_identity_traits_mode": "auxiliary-only",
        "secondary_identity_sources_forbidden": True,
        "identity_face_anchor_variant": "top-left-frontal",
        "identity_face_anchor_required": True,
        "identity_face_anchor_image": FACE_ANCHOR_FILENAME,
        "identity_anchor_required": True,
        "face_anchor_attached_required": True,
        "identity_drift_forbidden": True,
        "hair_variant_forbidden": True,
        "action_reference_required": False,
        "action_reference_optional": True,
        "expression_exaggeration_limit": "reduced",
        "chibi_drift_forbidden": True,
        "required_reference_inputs": ["face-anchor", "approved-visual-note-quality-baseline", "action-reference?"],
        "quality_reference_required": True,
        "quality_reference_purpose": "layout-density-and-integrated-text-only-not-semantic-source",
        "optional_non_identity_references": ["approved-visual-note-quality-baseline"],
        "fail_if_reference_images_not_actually_attached": True,
        "role_action_match_required": True,
        "action_fallback_forbidden": False,
        "global_render_signature_unique_required": True,
        "mic_pose_limited_once": True,
        "single_role_covers_required": True,
        "single_role_page_01_required": True,
        "codex_only_rendering_required": True,
        "external_api_rendering_forbidden": True,
        "allowed_render_mode": "codex",
        "identity_review_required_after_each_page": True,
        "identity_review_reference_source": FACE_ANCHOR_FILENAME,
        "identity_review_checklist": [
            "黑框眼镜一致",
            "暖肤色一致",
            "背头侧分黑发一致",
            "白西装黑内搭一致",
            "年轻亚洲男性一致",
            "手绘线稿风一致",
            "发际线方向一致",
            "额头高度一致",
            "眼镜外轮廓一致",
            "脸宽脸长比一致",
            "鼻口间距一致",
            "年龄感一致",
        ],
        "archive_delivery_mode": "direct-or-copy-then-clean",
        "intermediate_render_allowed": True,
        "intermediate_images_must_be_deleted_after_archive": True,
        "archive_completion_requires_formal_dir_only": True,
        "source_text_only_visual_mode": True,
        "inferred_visuals_forbidden": True,
    }


def parse_explicit_pages(text: str) -> list[dict[str, Any]]:
    lines = text.splitlines()
    chunks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in lines:
        match = EXPLICIT_HEADING_RE.match(line)
        if match:
            if current is not None:
                chunks.append(current)
            heading_prefix = line.split(maxsplit=1)[0]
            current = {
                "title": strip_markdown_bold(match.group(1).strip()),
                "lines": [],
                "explicit_heading_level": max(1, min(3, heading_prefix.count("#"))),
            }
        elif current is not None:
            current["lines"].append(line)
    if current is not None:
        chunks.append(current)
    pages: list[dict[str, Any]] = []
    for idx, chunk in enumerate(chunks, start=1):
        body = "\n".join(chunk["lines"]).strip()
        pages.append({
            "index": idx,
            "title": chunk["title"],
            "body": body,
            "title_from_bold": False,
            "pagination_mode": "explicit",
            "explicit_heading_level": chunk.get("explicit_heading_level", 0),
            "section_kind": "manual",
            "step_label": "",
            "step_index": None,
            "step_page_index": 1,
            "step_page_total": 1,
            "is_continued": False,
        })
    if not pages:
        raise ValueError("没有解析到任何页面，请检查文案中是否包含 #、## 或 ### 标题分页")
    return pages


def group_sentences_by_structure(text: str) -> list[dict[str, Any]]:
    sentences = split_sentences(text)
    if not sentences:
        return []
    blocks: list[dict[str, Any]] = []
    current_intro: list[str] = []
    current_step: dict[str, Any] | None = None

    for sentence in sentences:
        label = extract_step_label(sentence)
        if label:
            if current_step:
                blocks.append(current_step)
            elif current_intro:
                blocks.append({"kind": "intro", "sentences": current_intro[:]})
                current_intro = []
            current_step = {
                "kind": "step",
                "step_label": label,
                "sentences": [sentence],
            }
            continue
        if current_step:
            current_step["sentences"].append(sentence)
        else:
            current_intro.append(sentence)

    if current_step:
        blocks.append(current_step)
    elif current_intro:
        blocks.append({"kind": "intro", "sentences": current_intro[:]})

    if blocks and blocks[-1]["kind"] == "step":
        trailing_outro = peel_outro_sentences(blocks[-1]["sentences"])
        if trailing_outro:
            blocks[-1]["sentences"] = blocks[-1]["sentences"][:-len(trailing_outro)]
            blocks.append({"kind": "outro", "sentences": trailing_outro})
    return [block for block in blocks if block.get("sentences")]


def peel_outro_sentences(sentences: list[str]) -> list[str]:
    if len(sentences) < 2:
        return []
    outro: list[str] = []
    for sentence in reversed(sentences):
        if SUMMARY_SENTENCE_RE.search(sentence):
            outro.insert(0, sentence)
        elif outro:
            break
        else:
            break
    if len(outro) == 1:
        return outro
    return outro


def count_chars(sentences: list[str]) -> int:
    return sum(len(sentence) for sentence in sentences)


def pick_split_index(sentences: list[str], min_left: int = 2, min_right: int = 2) -> int:
    if len(sentences) <= min_left + min_right:
        return max(min_left, len(sentences) - min_right)
    candidate_indices = []
    for idx in range(min_left, len(sentences) - min_right + 1):
        left = sentences[idx - 1]
        right = sentences[idx]
        if PAGE_BREAK_RE.search(right) or PAGE_BREAK_RE.search(left):
            candidate_indices.append(idx)
    if candidate_indices:
        midpoint = len(sentences) / 2.0
        return min(candidate_indices, key=lambda idx: abs(idx - midpoint))
    return max(min_left, len(sentences) // 2)


def summarize_page_title(step_label: str, sentences: list[str]) -> str:
    if not sentences:
        return ""
    text = strip_step_label(sentences[0])
    text = re.sub(r"^(那|所以|其实|就是|然后|你要知道|你现在最该做的，是|你现在最该做的|你该补的是|也就是说|正确顺序是|很多人|普通人最怕的不是|今天分享一个很扎心的真相，?)", "", text)
    text = re.sub(r"[，。！？；,;:：].*$", "", text).strip()
    text = text[:18].strip()
    if len(text) < 4:
        text = strip_step_label("".join(sentences))[:12].strip()
    if not text:
        return ""
    return text


def summarize_intro_title(sentences: list[str], page_index: int) -> str:
    if not sentences:
        return f"导语{page_index}"
    first = sentences[0]
    title = re.sub(r"[，。！？；,;:：].*$", "", first).strip()
    title = re.sub(r"^(今天分享一个|今天我就把|先说一个|先讲一个)", "", title).strip()
    if len(title) < 4:
        title = first[:12].strip()
    return title[:18] or f"导语{page_index}"


def summarize_hook(sentences: list[str], fallback: str = "") -> str:
    if not sentences:
        return fallback[:18]
    text = strip_step_label(sentences[0])
    text = re.sub(r"^(今天分享一个|今天我就把|所以|其实|也就是说|真正厉害的人，不是|真正厉害的人是)", "", text).strip()
    text = re.sub(r"[。！？；!?;].*$", "", text).strip()
    text = text[:22].strip()
    return text or fallback[:18]


def strip_leading_spoken_filler(text: str) -> str:
    return re.sub(
        r"^(对，你没听错。?|你没听错。?|好，?|那这时候你一定会问[:：]?|记住，?|所以，?|但是，?|因为，?|其实，?|也就是说，?)",
        "",
        text.strip(),
    ).strip()


def is_explicit_step_title(title: str) -> bool:
    return bool(EXPLICIT_STEP_TITLE_RE.search(title.strip()))


def normalize_step_title_entry(entry: str) -> str:
    cleaned = entry.strip().strip("。！？；; ")
    marker_match = EXPLICIT_STEP_TITLE_RE.search(cleaned)
    if not marker_match:
        return cleaned
    marker = marker_match.group(0).strip()
    rest = cleaned[marker_match.end():].lstrip("：:，,、 ")
    rest = re.sub(r"^(就是|是)\s*", "", rest).strip()
    if not rest:
        return marker
    return f"{marker}：{rest.strip().strip('。！？；; ')}"


def extract_step_title_layers(title: str, body: str) -> list[str]:
    layers: list[str] = []
    sources = [title] + [line.strip() for line in body.splitlines() if line.strip()]
    for idx, source in enumerate(sources):
        for match in STEP_TITLE_ENTRY_RE.finditer(source):
            entry = normalize_step_title_entry(match.group("entry"))
            if entry and "：" not in entry and idx + 1 < len(sources):
                next_line = strip_leading_spoken_filler(sources[idx + 1]).strip().strip("。！？；; ")
                if next_line and not is_explicit_step_title(next_line):
                    entry = f"{entry}：{next_line}"
            if entry and entry not in layers:
                layers.append(entry)
            if len(layers) >= 2:
                return layers[:2]
    return layers[:2]


def is_complete_sentence_title(text: str) -> bool:
    normalized = strip_leading_spoken_filler(strip_step_label(text)).strip()
    if len(normalized) < 8:
        return False
    if normalized.endswith(("，", ",", "：", ":", "；", ";", "、")):
        return False
    return any(mark in normalized for mark in ["，", "。", "：", "不是", "而是", "就是", "才是", "必须", "不要", "记住"])


def score_full_hook_title(text: str) -> int:
    normalized = strip_leading_spoken_filler(strip_step_label(text)).strip()
    score = 0
    if 10 <= len(normalized) <= 24:
        score += 2
    elif len(normalized) >= 8:
        score += 1
    for marker in ["不是", "而是", "就是", "才是", "记住", "真正", "最重要", "答案", "路线图", "闭环", "长出来"]:
        if marker in normalized:
            score += 2
    if normalized.startswith(("这时候", "然后", "那这时候", "好，这就", "对，你没听错")):
        score -= 2
    return score


def extract_full_hook_title(candidates: list[str], fallback: str = "") -> str:
    scored_complete_candidates: list[tuple[int, str]] = []
    for raw in candidates:
        cleaned = strip_leading_spoken_filler(strip_step_label(raw))
        cleaned = cleaned.replace("“", "").replace("”", "").strip()
        cleaned = re.sub(r"[。！？；!?;]+\s*$", "", cleaned).strip()
        if not cleaned:
            continue
        if len(cleaned) > 30:
            cleaned = cleaned[:30].rstrip("，,：:；; ")
        if is_complete_sentence_title(cleaned):
            scored_complete_candidates.append((score_full_hook_title(cleaned), cleaned))
    if scored_complete_candidates:
        scored_complete_candidates.sort(key=lambda item: item[0], reverse=True)
        return scored_complete_candidates[0][1]
    for raw in candidates:
        cleaned = strip_leading_spoken_filler(strip_step_label(raw))
        cleaned = re.sub(r"[。！？；!?;]+\s*$", "", cleaned).strip()
        if len(cleaned) >= 8:
            return cleaned[:30].rstrip("，,：:；; ")
    fallback_clean = strip_leading_spoken_filler(strip_step_label(fallback)).strip()
    return fallback_clean[:30].rstrip("，,：:；; ") or fallback[:30].rstrip("，,：:；; ")


def compress_sentence_to_phrase(sentence: str, limit: int = 14) -> str:
    fragment, _ = sentence_to_exact_fragment(sentence, limit=limit)
    return fragment


def extract_cue_phrases(sentences: list[str], limit_points: int = 4, limit: int = 14) -> tuple[list[str], dict[str, str]]:
    return extract_exact_display_fragments(sentences, limit_points=limit_points, limit=limit)


def extract_visual_keywords(title: str, body: str, icons: list[str], page_type: str) -> list[str]:
    del icons, page_type
    keywords: list[str] = []
    for source in [title] + [line.strip() for line in body.splitlines() if line.strip()][:3]:
        for term in extract_source_terms(source, limit=2, max_len=8):
            if term not in keywords:
                keywords.append(term)
            if len(keywords) >= 4:
                break
        if len(keywords) >= 4:
            break
    return keywords[:4]


def extract_visual_action_cues(title: str, body: str, page_type: str) -> list[str]:
    haystack = f"{title}\n{body}"
    cues: list[str] = []
    mapping = [
        (r"(打篮球|篮球)", "打篮球"),
        (r"(打游戏|游戏)", "打游戏"),
        (r"(写作|写东西|写内容)", "写作"),
        (r"(电脑|笔记本|办公)", "用电脑"),
        (r"(销售|成交|客户|沟通)", "谈销售"),
        (r"(对比|不是|而是|区别|反差)", "对比"),
        (r"(流程|步骤|推进|执行|行动)", "推进"),
        (r"(讲|解释|说明|拆解)", "讲解"),
        (r"(惊讶|扎心|戳中|反差)", "惊讶"),
        (r"(困惑|拖延|卡住|误区|没结果)", "困惑"),
        (r"(总结|收尾|结论|确认)", "确认"),
        (r"(目标|验证|深度工作)", "深度工作"),
    ]
    for pattern, cue in mapping:
        if re.search(pattern, haystack) and cue not in cues:
            cues.append(cue)
    fallback = {
        "对比页": ["对比", "讲解"],
        "流程页": ["推进", "讲解"],
        "观点页": ["讲解", "强调"],
        "总结页": ["确认", "讲解"],
        "步骤页": ["讲解"],
    }
    for cue in fallback.get(page_type, ["讲解"]):
        if cue not in cues:
            cues.append(cue)
    return cues[:4]


def extract_visual_scene_cues(title: str, body: str, page_type: str) -> list[str]:
    del page_type
    haystack = f"{title}\n{body}"
    cues: list[str] = []
    explicit_terms = [
        "步骤",
        "流程",
        "对比",
        "服务",
        "客户",
        "系统",
        "关系",
        "问题",
        "方法",
        "过程",
        "节点",
        "筛选",
        "展示",
    ]
    for term in explicit_terms:
        if term in haystack and term not in cues:
            cues.append(term)
    return cues[:4]


def extract_flow_labels(
    page: dict[str, Any],
    cue_phrases: list[str],
    text_density_mode: str,
    cue_phrase_source_quotes: dict[str, str] | None = None,
) -> tuple[list[str], dict[str, str]]:
    labels: list[str] = []
    source_quotes: dict[str, str] = {}
    if page.get("step_label"):
        step_label = str(page["step_label"]).strip()
        labels.append(step_label)
        source_quotes[step_label] = step_label
    if text_density_mode == "graph-first":
        return labels[:1], {label: source_quotes.get(label, label) for label in labels[:1]}
    limit = 1 if text_density_mode == "text-light" else 2
    for phrase in cue_phrases:
        if phrase not in labels:
            labels.append(phrase)
            if cue_phrase_source_quotes and phrase in cue_phrase_source_quotes:
                source_quotes[phrase] = cue_phrase_source_quotes[phrase]
        if len(labels) >= limit:
            break
    return labels[:limit], {label: source_quotes.get(label, label) for label in labels[:limit]}


def is_long_title(title: str) -> bool:
    plain = strip_step_label(title).replace("“", "").replace("”", "").strip()
    return len(plain) >= 24


def choose_display_title_mode(title: str, page_type: str) -> str:
    if is_long_title(title):
        return "compressed"
    if page_type in {"对比页", "流程页"} and len(strip_step_label(title)) >= 20:
        return "compressed"
    return "exact"


def choose_title_strategy(page: dict[str, Any], page_type: str, deck_title: str | None) -> str:
    del deck_title
    if str(page.get("pagination_mode") or "").strip() == "explicit" and str(page.get("title") or "").strip():
        if should_use_summary_title_exception(page, page_type):
            return "summary-body-source-title"
        return "explicit-heading-title"
    step_layers = extract_step_title_layers(str(page.get("title") or ""), str(page.get("body") or ""))
    if len(step_layers) >= 2:
        return "explicit-step-with-subtitle"
    if len(step_layers) == 1:
        return "explicit-step-title"
    return "extracted-full-hook"


def extract_guided_title_prefix(title: str) -> str:
    stripped = title.strip()
    match = GUIDE_TITLE_PREFIX_RE.match(stripped)
    if match:
        return match.group("prefix").strip()
    return extract_step_label(stripped) or ""


def strip_guided_title_prefix(title: str) -> str:
    stripped = title.strip()
    prefix = extract_guided_title_prefix(stripped)
    if not prefix:
        return stripped
    rest = stripped[len(prefix):].lstrip("，,：:。 、|｜-")
    return rest.strip()


def build_display_title(title: str, page_type: str, mode: str) -> str:
    if mode == "exact":
        return title
    prefix = extract_guided_title_prefix(title)
    base_title = strip_guided_title_prefix(title) if prefix else title
    limit = 16 if page_type in {"对比页", "总结页"} else 18
    if prefix:
        remainder_limit = max(6, limit - len(prefix) - 1)
        compressed = compress_sentence_to_phrase(base_title, limit=remainder_limit)
        if compressed:
            return f"{prefix}｜{compressed}"
        if base_title:
            return f"{prefix}｜{base_title[:remainder_limit]}"
        return prefix
    compressed = compress_sentence_to_phrase(base_title, limit=limit)
    return compressed or base_title[:limit]


def extract_subtitle_notes(title: str, mode: str, limit: int = 2) -> list[str]:
    if mode != "compressed":
        return []
    text = strip_guided_title_prefix(title).replace("“", "").replace("”", "").strip()
    chunks = re.split(r"[，。！？；!?;]", text)
    notes: list[str] = []
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        phrase = compress_sentence_to_phrase(chunk, limit=14)
        if phrase and phrase not in notes:
            notes.append(phrase)
        if len(notes) >= limit:
            break
    return notes[:limit]


def is_explicit_heading_page(page: dict[str, Any]) -> bool:
    return str(page.get("pagination_mode") or "").strip() == "explicit" and bool(str(page.get("title") or "").strip())


def should_use_summary_title_exception(page: dict[str, Any], page_type: str) -> bool:
    if not is_explicit_heading_page(page):
        return False
    if page_type != "总结页":
        return False
    if not bool(page.get("is_last_page", False)):
        return False
    title = normalize_source_lookup(str(page.get("title") or ""))
    return title in {normalize_source_lookup(item) for item in SUMMARY_EXCEPTION_TITLE_CANDIDATES}


def choose_summary_exception_title(page: dict[str, Any]) -> tuple[str, str]:
    source_title = str(page.get("title") or "").strip()
    sentences = [line.strip() for line in str(page.get("body") or "").splitlines() if line.strip()]
    for sentence in sentences:
        quote = infer_exact_source_quote(sentence, source_title, str(page.get("body") or ""))
        if sentence and quote:
            return sentence, quote
    return source_title, infer_exact_source_quote(source_title, source_title, str(page.get("body") or ""))


def choose_text_density_mode(index: int, page_type: str, title: str, scene_concept: str, section_kind: str) -> str:
    del title, scene_concept
    if index == 1 or section_kind == "intro":
        return "text-light"
    if page_type in {"总结页"} or section_kind == "outro":
        return "text-light"
    if page_type in {"步骤页", "观点页", "对比页", "流程页"} or section_kind == "step":
        return "graph-first"
    return "text-light"


def extract_support_labels(
    page_type: str,
    scene_concept: str,
    cue_phrases: list[str],
    flow_labels: list[str],
    visual_scene_cues: list[str],
    visual_keywords: list[str],
    title: str,
    body: str,
    text_density_mode: str,
) -> tuple[list[str], dict[str, str]]:
    del page_type, scene_concept, visual_keywords
    if text_density_mode == "minimal":
        return [], {}
    max_labels = 3 if text_density_mode == "text-light" else 5
    labels: list[str] = []
    source_quotes: dict[str, str] = {}
    title_candidates: list[str] = []
    title_terms = extract_source_terms(title, limit=6, max_len=6)
    cue_keys = {normalize_source_lookup(str(item)) for item in cue_phrases if str(item).strip()}
    for part in re.split(r"[：:，,；;｜|/]", trim_source_fragment(title)):
        fragment = trim_source_fragment(part)
        if 2 <= len(fragment) <= 8 and fragment not in title_candidates:
            title_candidates.append(fragment)
    prioritized_title_labels = [candidate for candidate in title_candidates if re.search(r"(第.+[步点条]|误区|结尾|内容|系统|服务|信任|经历|产品|答案|目标|本质|判断|选择)", candidate)]
    for term in title_terms:
        term_key = normalize_source_lookup(term)
        if any(term_key and (term_key in cue_key or cue_key in term_key) for cue_key in cue_keys):
            continue
        if term not in prioritized_title_labels:
            prioritized_title_labels.append(term)
    body_lines = [line.strip() for line in body.splitlines() if line.strip()]
    structural_candidates = [
        "本质",
        "做判断",
        "误区",
        "共同特点",
        "选择",
    ]
    phrase_sources = list(flow_labels)
    for source in phrase_sources:
        if len(labels) >= max_labels:
            break
        source_quote = trim_source_fragment(str(source))
        for term in split_direct_source_fragments(str(source), max_len=6):
            if term not in labels:
                labels.append(term)
                source_quotes[term] = source_quote or term
            if len(labels) >= max_labels:
                break
    for source in body_lines:
        if len(labels) >= max_labels:
            break
        source_quote = trim_source_fragment(source)
        for term in split_direct_source_fragments(source, max_len=6):
            term_key = normalize_source_lookup(term)
            if any(term_key and (term_key in cue_key or cue_key in term_key) for cue_key in cue_keys):
                continue
            if term not in labels:
                labels.append(term)
                source_quotes[term] = source_quote or term
            if len(labels) >= max_labels:
                break
    prioritized_body_terms: list[str] = []
    title_body_pool = "\n".join([title] + body_lines)
    for candidate in structural_candidates:
        candidate_key = normalize_source_lookup(candidate)
        if candidate in title_body_pool and not any(candidate_key and (candidate_key in cue_key or cue_key in candidate_key) for cue_key in cue_keys):
            prioritized_body_terms.append(candidate)
    for source in body_lines:
        for term in split_direct_source_fragments(source, max_len=6):
            if re.search(r"(本质|判断|误区|目标|方法|反例|答案|选择)", term) and term not in prioritized_body_terms:
                prioritized_body_terms.append(term)
    if prioritized_body_terms:
        prioritized_labels = [label for label in prioritized_body_terms if label in labels]
        tail_labels = [label for label in labels if label not in prioritized_labels]
        labels = prioritized_labels + tail_labels
    if not labels:
        for candidate in prioritized_title_labels:
            candidate_key = normalize_source_lookup(candidate)
            if any(candidate_key and (candidate_key in cue_key or cue_key in candidate_key) for cue_key in cue_keys):
                continue
            if candidate not in labels:
                labels.append(candidate)
                source_quotes[candidate] = trim_source_fragment(title) or candidate
            if len(labels) >= max_labels:
                break
    if not labels:
        fallback_phrase, fallback_quote = sentence_to_exact_fragment(str(title), limit=6)
        if fallback_phrase:
            labels.append(fallback_phrase)
            source_quotes[fallback_phrase] = fallback_quote or fallback_phrase
    return labels[:max_labels], {label: source_quotes.get(label, label) for label in labels[:max_labels]}


def dedupe_text_slots(
    display_title: str,
    subtitle_notes: list[str],
    cue_phrases: list[str],
    flow_labels: list[str],
    support_labels: list[str],
    semantic_candidate_source_quotes: dict[str, str],
) -> dict[str, Any]:
    used_keys: set[str] = set()
    used_entries: list[tuple[str, str]] = []
    slot_assignment: dict[str, list[str]] = {}
    repeated_sources: list[str] = []
    filtered_overlap_groups: list[list[str]] = []
    conflict_resolutions: list[str] = []

    def source_key(text: str) -> str:
        return normalize_source_lookup(text) or normalize_source_lookup(str(semantic_candidate_source_quotes.get(text) or ""))

    def source_overlaps(current_key: str, current_slot: str) -> bool:
        for used_slot, used_key in used_entries:
            if not current_key or not used_key:
                continue
            if used_slot == "display_title" and current_slot in {"support_labels", "flow_labels"}:
                if current_key == used_key:
                    return True
                continue
            if current_key == used_key or current_key in used_key or used_key in current_key:
                return True
        return False

    def assign(slot_name: str, items: list[str]) -> list[str]:
        selected: list[str] = []
        assigned_keys: list[str] = []
        for item in items:
            key = source_key(item)
            if not key:
                continue
            if key in used_keys or source_overlaps(key, slot_name):
                if item not in repeated_sources:
                    repeated_sources.append(item)
                filtered_overlap_groups.append([slot_name, item, key])
                conflict_resolutions.append(f"{slot_name}:{item}")
                continue
            used_keys.add(key)
            used_entries.append((slot_name, key))
            selected.append(item)
            assigned_keys.append(key)
        slot_assignment[slot_name] = assigned_keys
        return selected

    deduped_display_title = display_title if source_key(display_title) else display_title
    if source_key(display_title):
        used_keys.add(source_key(display_title))
        used_entries.append(("display_title", source_key(display_title)))
        slot_assignment["display_title"] = [source_key(display_title)]
    else:
        slot_assignment["display_title"] = []
    deduped_subtitle_notes = assign("subtitle_notes", subtitle_notes)
    deduped_cue_phrases = assign("cue_phrases", cue_phrases)
    deduped_flow_labels = assign("flow_labels", flow_labels)
    deduped_support_labels = assign("support_labels", support_labels)
    final_overlap_groups: list[list[str]] = []
    final_items = (
        [deduped_display_title]
        + deduped_subtitle_notes
        + deduped_cue_phrases
        + deduped_flow_labels
        + deduped_support_labels
    )
    final_keys: list[tuple[str, str, str]] = []
    final_slot_items = (
        [("display_title", deduped_display_title)]
        + [("subtitle_notes", item) for item in deduped_subtitle_notes]
        + [("cue_phrases", item) for item in deduped_cue_phrases]
        + [("flow_labels", item) for item in deduped_flow_labels]
        + [("support_labels", item) for item in deduped_support_labels]
    )
    for slot_name, item in final_slot_items:
        key = source_key(item)
        if key:
            final_keys.append((slot_name, item, key))
    for idx, (left_slot, left_item, left_key) in enumerate(final_keys):
        for right_slot, right_item, right_key in final_keys[idx + 1:]:
            if left_key == right_key:
                continue
            if {left_slot, right_slot} & {"support_labels", "flow_labels"} and {left_slot, right_slot} & {"display_title"}:
                continue
            if left_key in right_key or right_key in left_key:
                final_overlap_groups.append([left_item, right_item])
    return {
        "display_title": deduped_display_title,
        "subtitle_notes": deduped_subtitle_notes,
        "cue_phrases": deduped_cue_phrases,
        "flow_labels": deduped_flow_labels,
        "support_labels": deduped_support_labels,
        "text_slot_assignment": slot_assignment,
        "repeated_source_fragments_filtered": repeated_sources,
        "source_fragment_overlap_groups": final_overlap_groups,
        "text_slot_conflict_resolutions": [] if not final_overlap_groups else conflict_resolutions,
        "filtered_source_fragment_conflicts": filtered_overlap_groups,
    }


def infer_role_count_contract(index: int, page_type: str, scene_concept: str, title: str, body: str) -> dict[str, Any]:
    if index in SINGLE_ROLE_PAGE_INDEXES:
        return {
            "role_count_decision_mode": "hard-single",
            "role_count_target": 1,
            "multi_role_required": False,
            "multi_role_trigger_type": "page-01-single-role-only",
            "role_distribution_brief": "正文第1页固定单人物，只允许一个 IP 人物承担开场动作。",
            "role_slot_assignments": ["主结构单角色"],
            "same_page_role_pose_distinct_required": False,
        }
    haystack = "\n".join([title, body])
    sentences = [line.strip() for line in body.splitlines() if line.strip()]
    split_keywords = ("对比", "两侧", "左右", "一边", "另一边", "而是", "不是")
    flow_keywords = ("先", "再", "最后", "然后", "步骤", "流程", "节点", "一次咨询", "一次陪跑", "一份能交付的清单")
    if page_type == "对比页" or scene_concept == "contrast-split" or any(keyword in haystack for keyword in split_keywords):
        return {
            "role_count_decision_mode": "structure-triggered",
            "role_count_target": 2,
            "multi_role_required": True,
            "multi_role_trigger_type": "contrast-or-bridge",
            "role_distribution_brief": "至少两个人物分别进入左右或前后两个结构槽位，承担对照、桥接或转化关系。",
            "role_slot_assignments": ["左侧结构槽位", "右侧结构槽位"],
            "same_page_role_pose_distinct_required": True,
        }
    if page_type == "流程页" and (len(sentences) >= 6 or any(keyword in haystack for keyword in flow_keywords)):
        target = 3 if len(sentences) >= 8 else 2
        role_slots = ["节点1", "节点2", "节点3"][:target]
        return {
            "role_count_decision_mode": "structure-triggered",
            "role_count_target": target,
            "multi_role_required": True,
            "multi_role_trigger_type": "multi-node-flow",
            "role_distribution_brief": f"人物要分布到不同流程节点里做分工演示，本页固定 {target} 人物，不允许回落单人物。",
            "role_slot_assignments": role_slots,
            "same_page_role_pose_distinct_required": True,
        }
    return {
        "role_count_decision_mode": "structure-triggered",
        "role_count_target": 1,
        "multi_role_required": False,
        "multi_role_trigger_type": "single-conclusion-or-summary",
        "role_distribution_brief": "本页主结构是单锤点或单结论表达，单人物即可完成讲解，不强行扩成多人。",
        "role_slot_assignments": ["主结构单角色"],
        "same_page_role_pose_distinct_required": False,
    }


def derive_role_action_tags(page_type: str, visual_action_cues: list[str], role_action: str, role_pose_hint: str) -> list[str]:
    tags: list[str] = []
    for source in visual_action_cues + [role_action, role_pose_hint]:
        for label in ["讲解", "对比", "推进", "强调", "惊讶", "困惑", "确认", "打篮球", "打游戏", "写作", "用电脑", "谈销售", "深度工作"]:
            if label in source and label not in tags:
                tags.append(label)
    page_type_map = {
        "对比页": "对比",
        "流程页": "推进",
        "总结页": "确认",
        "观点页": "强调",
    }
    mapped = page_type_map.get(page_type)
    if mapped and mapped not in tags:
        tags.append(mapped)
    return tags[:5]


def derive_role_expression_tags(page_type: str, role_expression: str, title: str, body: str) -> list[str]:
    tags: list[str] = []
    haystack = "\n".join([page_type, title, body, role_expression])
    keyword_map = [
        ("惊讶", "惊讶"),
        ("质疑", "质疑"),
        ("困惑", "困惑"),
        ("思考", "思考"),
        ("顿悟", "顿悟"),
        ("判断", "判断"),
        ("解释", "解释"),
        ("推进", "推进"),
        ("执行", "执行"),
        ("确认", "确认"),
        ("号召", "号召"),
        ("笃定", "笃定"),
        ("警觉", "警觉"),
        ("专注", "专注"),
        ("鼓舞", "鼓舞"),
    ]
    for keyword, tag in keyword_map:
        if keyword in haystack and tag not in tags:
            tags.append(tag)
    fallback = {
        "对比页": ["判断", "解释"],
        "流程页": ["推进", "执行"],
        "总结页": ["确认", "号召"],
        "观点页": ["思考", "强调"],
    }
    for tag in fallback.get(page_type, ["说明"]):
        if tag not in tags:
            tags.append(tag)
    return tags[:4]


def build_role_variation_candidate(
    action_family: str,
    expression_family: str,
    action: str,
    expression: str,
    pose_hint: str,
    action_tags: list[str],
    expression_tags: list[str],
    preferred_framing: str | None = None,
    preferred_position: str | None = None,
    pose_key: str | None = None,
    pose_family: str | None = None,
    prop_signature: str | None = None,
    reference_filenames: list[str] | None = None,
) -> dict[str, Any]:
    pose_family_value = (pose_family or action_family).strip()
    # pose_hint 经常以“不要做普通主持姿态”描述禁忌；它不是道具需求。
    # 不得让这类否定提示触发“主持”关键词，把页面错误标记为麦克风姿态。
    prop_signature_value = (prop_signature or infer_prop_signature(action, expression, " ".join(action_tags), " ".join(expression_tags))).strip() or "none"
    pose_key_value = (pose_key or f"{pose_family_value}-{pose_digest(action_family, expression_family, action, expression, pose_hint, preferred_framing or '', preferred_position or '')}").strip()
    reference_preferences = reference_filenames or build_reference_filename_preferences(action_family, prop_signature_value)
    return {
        "action_family": action_family,
        "expression_family": expression_family,
        "role_action": action,
        "role_expression": expression,
        "role_pose_hint": pose_hint,
        "role_pose_key": pose_key_value,
        "role_pose_family": pose_family_value,
        "prop_signature": prop_signature_value,
        "reference_filenames": reference_preferences,
        "role_action_tags": unique_preserve_order([action_family] + action_tags),
        "role_expression_tags": unique_preserve_order([expression_family] + expression_tags),
        "preferred_framing": preferred_framing,
        "preferred_position": preferred_position,
    }


def extend_role_variation_candidates(candidates: list[dict[str, Any]], additions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    existing_keys = {
        (
            item["action_family"],
            item["expression_family"],
            item["role_action"],
            item["role_expression"],
            item["role_pose_key"],
        )
        for item in candidates
    }
    for item in additions:
        key = (
            item["action_family"],
            item["expression_family"],
            item["role_action"],
            item["role_expression"],
            item["role_pose_key"],
        )
        if key not in existing_keys:
            candidates.append(item)
            existing_keys.add(key)
    return candidates


def select_role_reference_profiles(spec: dict[str, Any], role: dict[str, Any], limit: int = 2) -> list[dict[str, Any]]:
    profiles = role.get("reference_profiles") or []
    if not profiles:
        return []
    desired = set((spec.get("role_action_tags") or []) + (spec.get("visual_action_cues") or []) + (spec.get("visual_scene_cues") or []))
    preferred_variant = "exaggerated"
    page_type = spec.get("page_type", "")
    if page_type in {"总结页"}:
        preferred_variant = "exaggerated"
    if spec.get("section_kind") in {"intro"} and spec.get("page_index") not in {1}:
        preferred_variant = "standard"
    if spec.get("role_scale") == "small-accent" and page_type not in {"对比页", "观点页"}:
        preferred_variant = "standard"
    scored: list[tuple[int, int, int, dict[str, Any]]] = []
    for item in profiles:
        tags = set(item.get("tags") or []) | set(item.get("use_cases") or [])
        score = len(desired & tags)
        variant_bonus = 1 if item.get("variant") == preferred_variant else 0
        intensity_bonus = 1 if item.get("expression_intensity") in {"high", "extreme-controlled"} else 0
        if score > 0 or item.get("is_base_pose"):
            scored.append((score, variant_bonus, intensity_bonus, item))
    if not scored:
        return profiles[:limit]
    scored.sort(key=lambda pair: (-pair[0], -pair[1], -pair[2], pair[3].get("name", "")))
    selected: list[dict[str, Any]] = []
    anchor_profile = next(
        (
            item
            for _, _, _, item in scored
            if "cartoon-style" in set(item.get("tags") or [])
            or "hair-anchor" in set(item.get("tags") or [])
            or "肤色锚定" in set(item.get("use_cases") or [])
        ),
        None,
    )
    if anchor_profile:
        selected.append(anchor_profile)
    for _, _, _, item in scored:
        if item in selected:
            continue
        selected.append(item)
        if len(selected) >= limit:
            break
    return selected[:limit]


def select_role_anchor_profile(role: dict[str, Any], preferred_variant: str = "standard") -> dict[str, Any] | None:
    profiles = role.get("reference_profiles") or []
    candidates = [
        item for item in profiles
        if "cartoon-style" in set(item.get("tags") or [])
        or "hair-anchor" in set(item.get("tags") or [])
        or "肤色锚定" in set(item.get("use_cases") or [])
    ]
    if not candidates:
        return None
    exact = next((item for item in candidates if item.get("variant") == preferred_variant), None)
    if exact:
        return exact
    return candidates[0]


def find_reference_profile_by_filename(role: dict[str, Any], filename: str) -> dict[str, Any] | None:
    profiles = role.get("reference_profiles") or []
    return next((item for item in profiles if pathlib.Path(item.get("path", "")).name == filename), None)


def select_face_anchor_profile(role: dict[str, Any]) -> dict[str, Any] | None:
    anchor = find_reference_profile_by_filename(role, FACE_ANCHOR_FILENAME)
    if anchor:
        return anchor
    return select_role_anchor_profile(role, preferred_variant="standard")


def build_action_contract_haystack(spec: dict[str, Any]) -> str:
    return " ".join(
        str(value)
        for value in [
            spec.get("page_type"),
            spec.get("scene_concept"),
            spec.get("page_title"),
            spec.get("title_text"),
            spec.get("display_title"),
            spec.get("section_kind"),
            " ".join(spec.get("role_action_tags") or []),
            " ".join(spec.get("role_expression_tags") or []),
            " ".join(spec.get("visual_action_cues") or []),
            " ".join(spec.get("visual_scene_cues") or []),
            " ".join(spec.get("cue_phrases") or []),
        ]
        if value
    )


def infer_action_family(spec: dict[str, Any]) -> tuple[str | None, str]:
    explicit = str(spec.get("role_action_family") or "").strip()
    if explicit:
        return explicit, f"explicit:{explicit}"
    haystack = build_action_contract_haystack(spec)
    for family, keywords in ACTION_FAMILY_RULES:
        matched = next((keyword for keyword in keywords if keyword in haystack), None)
        if matched:
            return family, matched
    return None, ""


def infer_expression_family(spec: dict[str, Any], action_family: str | None = None) -> tuple[str | None, str]:
    explicit = str(spec.get("role_expression_family") or "").strip()
    if explicit:
        return explicit, f"explicit:{explicit}"
    haystack = build_action_contract_haystack(spec)
    for family, keywords in EXPRESSION_FAMILY_RULES:
        matched = next((keyword for keyword in keywords if keyword in haystack), None)
        if matched:
            return family, matched
    if action_family:
        return action_family, f"fallback-action-family:{action_family}"
    return None, ""


def infer_allowed_role_framings(
    page_type: str,
    role_scale: str,
    title: str,
    index: int,
    action_family: str | None = None,
) -> list[str]:
    defaults = unique_preserve_order(
        build_role_framing_options(
            {
                "page_type": page_type,
                "role_scale": role_scale,
                "page_title": title,
                "role_framing": "",
                "role_action_family": action_family or "",
            }
        )
    )
    family_defaults = ACTION_FAMILY_ALLOWED_FRAMINGS.get(action_family or "", [])
    combined = unique_preserve_order(family_defaults + defaults)
    return combined or ["three-quarter", "half-body", "full-body"]


def select_action_reference_profile(spec: dict[str, Any], role: dict[str, Any]) -> tuple[dict[str, Any] | None, str, str]:
    action_family, basis = infer_action_family(spec)
    if not action_family:
        return None, "", ""
    preferred_filenames = unique_preserve_order(
        list(spec.get("role_reference_filenames") or [])
        + list(ACTION_FAMILY_REFERENCE_MAP.get(action_family, ()))
    )
    for filename in preferred_filenames:
        profile = find_reference_profile_by_filename(role, filename)
        if profile:
            return profile, basis, action_family
    haystack = " ".join(
        str(value)
        for value in [
            spec.get("page_type"),
            spec.get("scene_concept"),
            spec.get("page_title"),
            " ".join(spec.get("role_action_tags") or []),
            " ".join(spec.get("role_expression_tags") or []),
            " ".join(spec.get("visual_action_cues") or []),
            " ".join(spec.get("visual_scene_cues") or []),
        ]
        if value
    )
    for keywords, filenames in ACTION_REFERENCE_BY_INTENT:
        matched = next((keyword for keyword in keywords if keyword in haystack), None)
        if not matched:
            continue
        for filename in filenames:
            profile = find_reference_profile_by_filename(role, filename)
            if profile:
                return profile, matched, action_family
    return None, basis, action_family


def split_role_reference_chain(
    spec: dict[str, Any],
    role: dict[str, Any],
    preferred_variant: str = "standard",
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str]:
    face_anchor = select_face_anchor_profile(role)
    action_ref, action_reason, action_family = select_action_reference_profile(spec, role)
    return face_anchor, action_ref, action_reason


def choose_scene_concept(title: str, page_type: str, section_kind: str, index: int) -> str:
    if is_cover_like_page(index, title):
        return "cover-hero"
    if page_type == "流程页":
        return "path-flow"
    if page_type == "对比页":
        return "contrast-split"
    if page_type == "总结页":
        return "summary-stage"
    return "concept-note-scene"


def choose_scene_layout_type(scene_concept: str, role_scale: str, index: int) -> str:
    if scene_concept == "cover-hero":
        return "cover-hero"
    mapping = {
        "pit-map": "pit-map",
        "production-line": "production-line",
        "path-flow": "path-flow",
        "contrast-split": "contrast-split",
        "blocked-structure": "blocked-structure",
        "summary-stage": "summary-stage",
        "cover-hero": "cover-hero",
    }
    return mapping.get(scene_concept, "concept-board")


def choose_title_layout_mode(scene_concept: str, index: int, role_scale: str) -> str:
    if scene_concept == "cover-hero":
        return "center-hero"
    if index == 1:
        return "top-span" if role_scale != "large-focus" else "left-anchor"
    if scene_concept in {"pit-map", "path-flow"}:
        return "top-span"
    if scene_concept == "contrast-split":
        return "left-anchor" if role_scale != "large-focus" else "right-anchor"
    if scene_concept == "production-line":
        return "left-anchor"
    if scene_concept == "blocked-structure":
        return "right-anchor"
    if scene_concept == "summary-stage":
        return "center-hero"
    return "inline-scene"


def choose_title_alignment(title_layout_mode: str) -> str:
    mapping = {
        "center-hero": "center",
        "top-span": "center",
        "left-anchor": "left",
        "right-anchor": "right",
        "inline-scene": "left",
    }
    return mapping.get(title_layout_mode, "left")


def choose_title_anchor_zone(scene_concept: str, title_layout_mode: str) -> str:
    if title_layout_mode == "center-hero":
        return "center" if scene_concept == "cover-hero" else "top"
    if title_layout_mode == "top-span":
        return "top"
    mapping = {
        "top-span": "top",
        "left-anchor": "upper-left",
        "right-anchor": "upper-right",
        "inline-scene": "inline",
    }
    return mapping.get(title_layout_mode, "top")


def choose_title_flow_direction(scene_concept: str, title_layout_mode: str, title: str) -> str:
    if title_layout_mode == "top-span":
        return "horizontal"
    if title_layout_mode == "center-hero" and len(title) > 16:
        return "stacked"
    if scene_concept in {"path-flow", "blocked-structure"}:
        return "scene-following"
    return "horizontal"


def is_cover_like_page(index: int, title: str) -> bool:
    if index != 1:
        return False
    return bool(re.search(r"(封面|cover|目录|总览|导读|开场|首页)", title, re.I))


def choose_title_layout_guidance(
    scene_concept: str,
    title_layout_mode: str,
    title_alignment: str,
    title_anchor_zone: str,
    title_flow_direction: str,
) -> str:
    if title_layout_mode == "center-hero":
        return "标题作为中心锤点或上中锤点，与人物和主场景一起形成海报式主视觉"
    if title_layout_mode == "top-span":
        return "标题横跨顶部或偏上区域，下面完整展开结构和路径"
    if title_layout_mode == "left-anchor":
        return "标题偏左作为文字锚点，右侧或中部承接人物与主结构"
    if title_layout_mode == "right-anchor":
        return "标题偏右作为文字锚点，左侧或中部承接人物与主结构"
    return (
        f"标题融入场景内部，不像固定条幅；对齐方式 {title_alignment}，锚点区域 {title_anchor_zone}，"
        f"标题走向 {title_flow_direction}。人物不要默认站成画面中心，优先服从场景结构。"
    )


def choose_role_scene_relationship(scene_concept: str, role_scale: str, index: int) -> str:
    if index == 1:
        return "主题优先，第一张也必须先服从原文结构，角色只能作为辅助演示元素进入主结构"
    if role_scale == "small-accent":
        return "主题和主场景优先，角色缩小进入结构内部，作为辅助行动者参与表达"
    if role_scale == "large-focus":
        return "仅在封面或极少数强主视觉页允许更强存在感，但仍要服务原文"
    if scene_concept in {"pit-map", "production-line", "path-flow"}:
        return "主题和结构优先，角色必须走进结构、操作节点或被结构限制，不能站在结构外解说"
    return "主题优先，角色必须与主场景产生直接动作关系，主场景优先于角色单体"


def choose_role_in_scene_mode(title: str, page_type: str, scene_concept: str, index: int) -> str:
    haystack = f"{title}\n{scene_concept}"
    if index == 1:
        return "supporting-embedded"
    if page_type == "对比页":
        return "supporting-bridge"
    if page_type == "流程页" or scene_concept in {"production-line", "path-flow"}:
        return "supporting-operator"
    if re.search(r"(误区|踩坑|坑|卡住|地图|总览|路线图)", haystack):
        return "supporting-structure-interactor"
    if page_type == "总结页":
        return "supporting-summary-actor"
    return "supporting-structure-interactor"


def choose_role_in_scene_guidance(role_in_scene_mode: str, page_type: str, scene_concept: str) -> str:
    if role_in_scene_mode == "supporting-bridge":
        return "人物必须站进对比结构之间，同时连接左右两侧信息，像桥接、切换或权衡，但只能做辅助。"
    if role_in_scene_mode == "supporting-operator":
        return "人物必须进入流程、路径或操作结构内部，沿节点推进、推动、跨越或操作主机制，但不能取代主体内容。"
    if role_in_scene_mode == "supporting-summary-actor":
        return "人物必须在主场景内部承担动作或结论收束，不做画外主持人，不悬浮在空白边缘。"
    return "人物必须走进结构内部，触碰、踩入、跨过、被包围或被结构限制，不能独立站在主结构外。"


def choose_supporting_micro_visuals(icon_set: list[str], scene_concept: str) -> list[str]:
    items: list[str] = []
    for icon in icon_set[:3]:
        if icon not in items:
            items.append(icon)
    scene_defaults = {
        "pit-map": ["箭头", "标签框", "警示线"],
        "production-line": ["流程箭头", "节点框", "连接线"],
        "path-flow": ["箭头", "分叉点", "连接线"],
        "contrast-split": ["左右分栏", "对照线", "连接箭头"],
        "blocked-structure": ["阻断线", "门槛线", "框线"],
        "summary-stage": ["收束箭头", "重点框", "确认线"],
        "cover-hero": ["标题框", "强调线", "分栏提示"],
    }
    for extra in scene_defaults.get(scene_concept, []):
        if extra not in items:
            items.append(extra)
    return items[:6]


def get_density_profile(scene_concept: str, section_kind: str, is_continued: bool, index: int) -> dict[str, int]:
    if index == 1 or scene_concept == "cover-hero":
        return {"talking_points": 2, "micro_visuals": 4, "visual_keywords": 4, "icons": 2, "support_labels": 3, "primary_blocks": 2, "secondary_blocks": 0}
    if is_continued:
        return {"talking_points": 1, "micro_visuals": 4, "visual_keywords": 4, "icons": 2, "support_labels": 3, "primary_blocks": 2, "secondary_blocks": 0}
    if scene_concept in {"pit-map", "production-line", "path-flow", "blocked-structure"}:
        return {"talking_points": 1, "micro_visuals": 4, "visual_keywords": 4, "icons": 2, "support_labels": 5, "primary_blocks": 2, "secondary_blocks": 0}
    if scene_concept == "summary-stage":
        return {"talking_points": 2, "micro_visuals": 4, "visual_keywords": 4, "icons": 2, "support_labels": 4, "primary_blocks": 2, "secondary_blocks": 1}
    if section_kind == "step":
        return {"talking_points": 1, "micro_visuals": 4, "visual_keywords": 4, "icons": 2, "support_labels": 4, "primary_blocks": 2, "secondary_blocks": 0}
    return {"talking_points": 2, "micro_visuals": 4, "visual_keywords": 4, "icons": 2, "support_labels": 3, "primary_blocks": 2, "secondary_blocks": 0}


def extract_following_step_labels(pages: list[dict[str, str]], current_index: int, limit: int) -> list[str]:
    labels: list[str] = []
    for page in pages[current_index:]:
        title = str(page.get("title") or "").strip()
        if not title:
            continue
        label = strip_guided_title_prefix(title)
        label = compress_sentence_to_phrase(label or title, limit=6)
        if label and label not in labels:
            labels.append(label)
        if len(labels) >= limit:
            break
    return labels[:limit]


def build_page_dict(
    index: int,
    title: str,
    sentences: list[str],
    pagination_mode: str,
    section_kind: str,
    step_label: str = "",
    step_index: int | None = None,
    step_page_index: int = 1,
    step_page_total: int = 1,
) -> dict[str, Any]:
    return {
        "index": index,
        "title": title,
        "body": "\n".join(sentences).strip(),
        "pagination_mode": pagination_mode,
        "section_kind": section_kind,
        "step_label": step_label,
        "step_index": step_index,
        "step_page_index": step_page_index,
        "step_page_total": step_page_total,
        "is_continued": step_page_index > 1,
    }


def split_intro_block(sentences: list[str]) -> list[list[str]]:
    if len(sentences) <= 4 and count_chars(sentences) <= 140:
        return [sentences]
    if len(sentences) <= 2:
        return [sentences]
    split_idx = None
    for idx in range(1, len(sentences)):
        if INTRO_BREAK_RE.search(sentences[idx]):
            split_idx = idx
            break
    if split_idx is None:
        split_idx = pick_split_index(sentences, min_left=1, min_right=1)
    chunks = [sentences[:split_idx], sentences[split_idx:]]
    return [chunk for chunk in chunks if chunk]


def split_step_block(sentences: list[str]) -> list[list[str]]:
    if len(sentences) <= 5 and count_chars(sentences) <= 180:
        return [sentences]
    chunks: list[list[str]] = []
    remaining = sentences[:]
    while remaining:
        if len(remaining) <= 5 and count_chars(remaining) <= 180:
            chunks.append(remaining)
            break
        take = remaining[:6]
        split_idx = pick_split_index(take, min_left=2, min_right=2 if len(take) >= 4 else 1)
        chunk = remaining[:split_idx]
        chunks.append(chunk)
        remaining = remaining[split_idx:]
    return [chunk for chunk in chunks if chunk]


def parse_auto_pages(text: str) -> list[dict[str, Any]]:
    blocks = group_sentences_by_structure(text)
    if not blocks:
        raise ValueError("没有解析到任何页面，请检查文案中是否有内容")

    pages: list[dict[str, Any]] = []
    page_index = 1
    step_counter = 0
    for block in blocks:
        kind = block["kind"]
        sentences = block["sentences"]
        if kind == "intro":
            intro_chunks = split_intro_block(sentences)
            for idx, chunk in enumerate(intro_chunks, start=1):
                pages.append(build_page_dict(
                    index=page_index,
                    title=summarize_intro_title(chunk, idx),
                    sentences=chunk,
                    pagination_mode="auto",
                    section_kind="intro",
                ))
                page_index += 1
            continue
        if kind == "step":
            step_counter += 1
            step_chunks = split_step_block(sentences)
            step_label = block["step_label"]
            total = len(step_chunks)
            for idx, chunk in enumerate(step_chunks, start=1):
                title = step_label if idx == 1 else summarize_page_title(step_label, chunk)
                pages.append(build_page_dict(
                    index=page_index,
                    title=title,
                    sentences=chunk,
                    pagination_mode="auto",
                    section_kind="step",
                    step_label=step_label,
                    step_index=step_counter,
                    step_page_index=idx,
                    step_page_total=total,
                ))
                page_index += 1
            continue
        if kind == "outro":
            pages.append(build_page_dict(
                index=page_index,
                title="总结",
                sentences=sentences,
                pagination_mode="auto",
                section_kind="outro",
            ))
            page_index += 1
    return pages


def parse_pages(text: str) -> list[dict[str, Any]]:
    text = trim_non_visual_tail(text)
    if EXPLICIT_HEADING_RE.search(text):
        return parse_explicit_pages(text)
    return parse_auto_pages(text)


def parse_page_selection(selection: str | None, total_pages: int) -> list[int]:
    if not selection:
        return list(range(1, total_pages + 1))
    picked: set[int] = set()
    for chunk in selection.split(","):
        part = chunk.strip()
        if not part:
            continue
        match = PAGE_REF_RE.match(part)
        if not match:
            raise ValueError(f"无法解析页码范围: {part}")
        start = int(match.group(1))
        end = int(match.group(2) or start)
        if start > end:
            start, end = end, start
        if start < 1 or end > total_pages:
            raise ValueError(f"页码超出范围: {part}，当前总页数 {total_pages}")
        picked.update(range(start, end + 1))
    return sorted(picked)


def infer_page_type(title: str, body: str, index: int, total: int) -> str:
    haystack = f"{title}\n{body}"
    if index == total and re.search(r"(总结|结尾|最后|收尾|行动|号召)", haystack):
        return "总结页"
    if re.search(r"(对比|不是|而是|vs|区别|差异)", haystack, re.I):
        return "对比页"
    if re.search(r"(步骤|第一步|第二步|第三步|流程|路径|方法|先|再|然后)", haystack):
        return "流程页"
    if re.search(r"(认知|观点|本质|为什么|核心|真相|底层)", haystack):
        return "观点页"
    if index == total:
        return "总结页"
    return "步骤页"


def build_role_variation_candidates(spec: dict[str, Any]) -> list[dict[str, Any]]:
    page_type = spec["page_type"]
    title = spec["page_title"]
    body = spec.get("page_body", "")
    scene_concept = spec.get("scene_concept", "")
    haystack = f"{title}\n{body}"
    candidates: list[dict[str, Any]] = []

    if re.search(r"(误区|踩坑|坑)", haystack):
        extend_role_variation_candidates(candidates, [
            build_role_variation_candidate(
                "跨越",
                "警觉",
                "全身跨过坑位、障碍或错误节点，边躲边指认问题来源",
                "高夸张的警觉感和惊讶感，像刚发现关键风险",
                "让人物真正踩进或跨过误区结构，身体被坑位、箭头或警示标签包围",
                ["跨越", "误区", "推进"],
                ["警觉", "惊讶", "判断"],
                preferred_framing="full-body",
                preferred_position="inside-structure",
            ),
            build_role_variation_candidate(
                "阻挡",
                "质疑",
                "伸手挡住错误路径或标签，像在当场否决一个误区",
                "高夸张的质疑感和否定感，眉眼明显收紧",
                "用阻挡、拦截或推开的演法处理误区，不要只做普通解释",
                ["阻挡", "误区", "强调"],
                ["质疑", "判断", "警觉"],
                preferred_framing="three-quarter",
                preferred_position="mid-structure",
            ),
        ])
    if re.search(r"(路径|流程|步骤|顺序|验证)", haystack):
        extend_role_variation_candidates(candidates, [
            build_role_variation_candidate(
                "推进",
                "专注",
                "沿着流程节点推进、连接或逐步操作，把动作落在路径结构上",
                "高夸张的专注感和执行感，像在带着页面往前走",
                "动作必须贴着箭头、节点或流程线推进，不允许站在流程外讲解",
                ["推进", "流程", "操作"],
                ["专注", "执行", "推进"],
                preferred_framing="full-body",
                preferred_position="mid-path",
            ),
            build_role_variation_candidate(
                "连接",
                "带动",
                "跨步越过前后节点，伸手把两个阶段直接连起来",
                "高夸张的带动感和节奏感，像在把流程硬推起来",
                "用跨步、拉动、连接前后节点的方式表现顺序，不要只指着流程说",
                ["连接", "跨越", "流程"],
                ["带动", "推进", "执行"],
                preferred_framing="full-body",
                preferred_position="mid-path",
            ),
        ])
    if re.search(r"(赚钱|收入|变现|销售|成交|客户)", haystack):
        extend_role_variation_candidates(candidates, [
            build_role_variation_candidate(
                "对比",
                "判断",
                "一手对照投入，一手对照结果或收入符号，做强反差判断",
                "高夸张的判断感和解释感，像在拆开投入产出关系",
                "让人物同时连到投入和结果两边，形成明显的反差结构",
                ["对比", "收入", "谈销售"],
                ["判断", "解释", "质疑"],
                preferred_framing="three-quarter",
                preferred_position="center-bridge",
            ),
            build_role_variation_candidate(
                "确认",
                "困惑",
                "看向空空的钱包、订单或结果面板，做出落差确认",
                "高夸张的困惑感和落差感，像发现努力没有变成结果",
                "动作里要带结果落空的对象，不要只做口头说明姿势",
                ["确认", "收入", "结果"],
                ["困惑", "惊讶", "判断"],
                preferred_framing="three-quarter",
                preferred_position="inside-right",
            ),
        ])
    if re.search(r"(写作|内容|文案|输出)", haystack):
        extend_role_variation_candidates(candidates, [
            build_role_variation_candidate(
                "写作",
                "专注",
                "低头手写、标注或敲字，把内容动作直接放进页面结构里",
                "高夸张的专注感和思考感，像正在现场产出内容",
                "让人物直接操作纸张、键盘或文案节点，不要脱离内容结构",
                ["写作", "操作", "拆解"],
                ["专注", "思考", "执行"],
                preferred_framing="three-quarter",
                preferred_position="inside-left",
            ),
        ])
    if re.search(r"(电脑|系统|工具|模型)", haystack):
        extend_role_variation_candidates(candidates, [
            build_role_variation_candidate(
                "操作",
                "专注",
                "直接操作电脑、面板或系统节点，像在现场验证工具链路",
                "高夸张的专注感和判断感，眼神盯住屏幕或面板反馈",
                "让人物和工具结构发生操作关系，不要退回普通主持手势",
                ["操作", "用电脑", "推进"],
                ["专注", "判断", "执行"],
                preferred_framing="three-quarter",
                preferred_position="inside-right",
            ),
        ])

    page_type_defaults = {
        "对比页": [
            build_role_variation_candidate(
                "对比",
                "判断",
                "双手分别指向两侧内容，做取舍、对照和判断",
                "高夸张的判断感和解释感，眉眼和手势都更明显",
                "站进对比结构中间，让双手和视线同时连到两侧内容",
                ["对比", "判断", "讲解"],
                ["判断", "解释", "强调"],
                preferred_framing="three-quarter",
                preferred_position="center-bridge",
            ),
            build_role_variation_candidate(
                "桥接",
                "解释",
                "站在中间把两侧结构连接起来，像在搭桥解释差异",
                "高夸张的解释感和带动感，像把两组内容当场串起来",
                "身体要压在左右结构之间，做桥接动作，不要离场站桩",
                ["桥接", "对比", "连接"],
                ["解释", "带动", "判断"],
                preferred_framing="full-body",
                preferred_position="center-bridge",
            ),
            build_role_variation_candidate(
                "取舍",
                "质疑",
                "一手推开错误侧，一手拉近正确侧，明确做取舍",
                "高夸张的质疑感和判断感，像在当场否掉一个方向",
                "动作必须落在两侧结构上，形成明显推开和拉近的方向差",
                ["取舍", "对比", "强调"],
                ["质疑", "判断", "警觉"],
                preferred_framing="three-quarter",
                preferred_position="center-bridge",
            ),
        ],
        "流程页": [
            build_role_variation_candidate(
                "推进",
                "执行",
                "沿着流程节点逐步推进，手势落在关键连接点上",
                "高夸张的推进感和执行感，动作更有带动性",
                "不要站在流程旁边讲，必须沿着节点真正推进",
                ["推进", "流程", "执行"],
                ["执行", "推进", "专注"],
                preferred_framing="full-body",
                preferred_position="mid-path",
            ),
            build_role_variation_candidate(
                "操作",
                "专注",
                "蹲进或靠近某个关键节点，像在当场操作流程开关",
                "高夸张的专注感和判断感，注意力锁在结构细节上",
                "让人物缩进流程内部做操作，不要做飘在外面的讲解动作",
                ["操作", "流程", "拆解"],
                ["专注", "判断", "执行"],
                preferred_framing="three-quarter",
                preferred_position="mid-structure",
            ),
            build_role_variation_candidate(
                "连接",
                "带动",
                "伸手连接前后节点或把节点往前拖动，形成递进感",
                "高夸张的带动感和推进感，像在给流程加速度",
                "人物要和前后节点都发生连接，不要只指其中一个点",
                ["连接", "推进", "流程"],
                ["带动", "推进", "专注"],
                preferred_framing="full-body",
                preferred_position="mid-path",
            ),
        ],
        "总结页": [
            build_role_variation_candidate(
                "收束",
                "确认",
                "面向观众做收束确认，像在把重点压成一个结论",
                "高夸张的确认感和号召感，像在收束全场",
                "动作要稳住画面，把散开的信息收回到结论上",
                ["收束", "确认", "总结"],
                ["确认", "号召", "笃定"],
                preferred_framing="three-quarter",
                preferred_position="inside-center",
            ),
            build_role_variation_candidate(
                "展开",
                "鼓舞",
                "双手向外展开，把最终结论和行动口径一起打开",
                "高夸张的鼓舞感和笃定感，像在给最后一下推动",
                "总结页可以稳，但不要变成静止站姿，要有开场或号召手势",
                ["展开", "总结", "号召"],
                ["鼓舞", "笃定", "确认"],
                preferred_framing="half-body",
                preferred_position="inside-right",
            ),
            build_role_variation_candidate(
                "落点",
                "笃定",
                "伸手按住结论框、终点节点或总结标签，像在落锤",
                "高夸张的笃定感和确认感，像把结论直接钉住",
                "把动作压到最终落点上，不要只站着看总结框",
                ["落点", "确认", "总结"],
                ["笃定", "确认", "判断"],
                preferred_framing="three-quarter",
                preferred_position="inside-left",
            ),
        ],
        "观点页": [
            build_role_variation_candidate(
                "强调",
                "思考",
                "指向重点词，边强调边做思考或拆解动作",
                "高夸张的思考感和解释感，表情更戏剧化",
                "把手势和视线落在重点词或核心结构上，不要离题发挥",
                ["强调", "讲解", "拆解"],
                ["思考", "解释", "判断"],
                preferred_framing="three-quarter",
                preferred_position="inside-left",
            ),
            build_role_variation_candidate(
                "质疑",
                "质疑",
                "挑眉、半摊手，像在反问一个默认认知",
                "高夸张的质疑感和困惑感，形成明显的认知冲突",
                "人物要像在质问结构里的某个假设，不要变成普通说明员",
                ["质疑", "强调", "判断"],
                ["质疑", "困惑", "思考"],
                preferred_framing="half-body",
                preferred_position="inside-right",
            ),
            build_role_variation_candidate(
                "顿悟",
                "顿悟",
                "突然前探或握拳，像刚抓到一个关键认知",
                "高夸张的顿悟感和兴奋感，眼神更亮、动作更直接",
                "让人物像在主结构里突然点亮关键节点，而不是只讲观点",
                ["顿悟", "强调", "推进"],
                ["顿悟", "惊讶", "鼓舞"],
                preferred_framing="half-body",
                preferred_position="inside-center",
            ),
        ],
        "步骤页": [
            build_role_variation_candidate(
                "演示",
                "说明",
                "围绕页面核心概念做演示和拆解",
                "高夸张但稳定可辨认的说明型表情",
                "角色结合标题内容演示，不要站桩，不要只是普通主持姿态",
                ["演示", "讲解", "拆解"],
                ["说明", "解释", "思考"],
                preferred_framing="three-quarter",
                preferred_position="inside-right",
            ),
            build_role_variation_candidate(
                "拆解",
                "思考",
                "一边拆开结构，一边盯住某个关键点做解释",
                "高夸张的思考感和判断感，像在现场拆题",
                "动作要落在结构内部，不要只对着观众解释",
                ["拆解", "讲解", "判断"],
                ["思考", "判断", "解释"],
                preferred_framing="three-quarter",
                preferred_position="inside-left",
            ),
            build_role_variation_candidate(
                "强调",
                "确认",
                "抬手压住一个重点标签，像在把这一页的主张钉牢",
                "高夸张的确认感和强调感，像在对一个关键点定调",
                "重点是压住页面关键词，不要回到通用主持姿势",
                ["强调", "确认", "讲解"],
                ["确认", "判断", "解释"],
                preferred_framing="half-body",
                preferred_position="inside-center",
            ),
        ],
    }
    extend_role_variation_candidates(candidates, page_type_defaults.get(page_type, page_type_defaults["步骤页"]))
    if scene_concept in {"pit-map", "blocked-structure"}:
        extend_role_variation_candidates(candidates, [
            build_role_variation_candidate(
                "受限",
                "困惑",
                "让身体被结构卡住、挤压或围住，像被问题机制限制住",
                "高夸张的困惑感和警觉感，像刚意识到限制条件",
                "让人物真被结构限制住，而不是站在结构外讨论它",
                ["受限", "结构", "误区"],
                ["困惑", "警觉", "质疑"],
                preferred_framing="full-body",
                preferred_position="inside-structure",
            ),
        ])
    return candidates


def build_role_position_options(spec: dict[str, Any], preferred_position: str | None = None) -> list[str]:
    page_type = spec["page_type"]
    scene_concept = spec.get("scene_concept", "")
    role_scale = spec.get("role_scale", "medium-support")
    options = [preferred_position or "", spec.get("role_position", "")]
    if page_type == "对比页":
        options.extend(["center-bridge", "inside-left", "inside-right"])
    elif page_type == "流程页" or scene_concept in {"production-line", "path-flow"}:
        options.extend(["mid-path", "mid-structure", "inside-left", "inside-right"])
    elif scene_concept in {"pit-map", "blocked-structure"}:
        options.extend(["inside-structure", "mid-structure", "inside-left", "inside-right"])
    elif role_scale == "large-focus":
        options.extend(["inside-left", "inside-right", "inside-center"])
    else:
        options.extend(["inside-left", "inside-right", "inside-center", "mid-structure"])
    return unique_preserve_order(options)


def build_role_framing_options(spec: dict[str, Any], preferred_framing: str | None = None) -> list[str]:
    page_type = spec["page_type"]
    role_scale = spec.get("role_scale", "medium-support")
    title = spec.get("page_title", "")
    options = [preferred_framing or "", spec.get("role_framing", "")]
    options.extend(ACTION_FAMILY_ALLOWED_FRAMINGS.get(str(spec.get("role_action_family") or "").strip(), []))
    if re.search(r"(误区|踩坑|跨越|路径|流程|步骤|走路)", title):
        options.extend(["full-body", "three-quarter"])
    elif role_scale == "large-focus":
        options.extend(["three-quarter", "half-body", "full-body"])
    elif page_type == "总结页":
        options.extend(["three-quarter", "half-body", "full-body"])
    elif role_scale == "small-accent":
        options.extend(["full-body", "three-quarter"])
    else:
        options.extend(["three-quarter", "half-body", "full-body"])
    return unique_preserve_order(options)


def choose_role_variation_staging(
    spec: dict[str, Any],
    candidate: dict[str, Any],
    recent_specs: list[dict[str, Any]],
) -> tuple[str, str, str]:
    if not recent_specs:
        return spec.get("role_position", ""), spec.get("role_framing", ""), "keep-default-staging"
    position_options = build_role_position_options(spec, candidate.get("preferred_position"))
    framing_options = build_role_framing_options(spec, candidate.get("preferred_framing"))
    previous = recent_specs[-1] if recent_specs else {}
    previous_combo = (
        previous.get("role_position"),
        previous.get("role_framing"),
        previous.get("role_composition_mode"),
    )
    best_combo = (
        spec.get("role_position", ""),
        spec.get("role_framing", ""),
        spec.get("role_composition_mode", ""),
    )
    best_score: int | None = None
    for framing in framing_options:
        for position in position_options:
            combo = (position, framing, spec.get("role_composition_mode", ""))
            score = 0
            if combo == previous_combo:
                score += 20
            if previous and position == previous.get("role_position"):
                score += 4
            if previous and framing == previous.get("role_framing"):
                score += 4
            if position == spec.get("role_position"):
                score += 1
            if framing == spec.get("role_framing"):
                score += 1
            if best_score is None or score < best_score:
                best_score = score
                best_combo = combo
    position, framing, _ = best_combo
    guard = "keep-default-staging"
    if position != spec.get("role_position") or framing != spec.get("role_framing"):
        guard = "adjust-staging-to-break-repeat"
    return position, framing, guard


def apply_role_variation_across_specs(specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not specs:
        return specs
    action_counts: Counter[str] = Counter()
    expression_counts: Counter[str] = Counter()
    pose_family_counts: Counter[str] = Counter()
    prop_signature_counts: Counter[str] = Counter()
    signature_counts: Counter[str] = Counter()
    used_render_signatures: set[str] = set()
    varied_specs: list[dict[str, Any]] = []
    for spec in specs:
        candidates = build_role_variation_candidates(spec)
        previous = varied_specs[-1] if varied_specs else {}
        previous2 = varied_specs[-2] if len(varied_specs) > 1 else {}
        best_candidate = candidates[0]
        best_score: int | None = None
        for idx, candidate in enumerate(candidates):
            action_family = candidate["action_family"]
            expression_family = candidate["expression_family"]
            pose_family = str(candidate.get("role_pose_family") or action_family or "generic")
            prop_signature = infer_prop_signature(candidate.get("prop_signature"))
            role_position, role_framing, staging_guard = choose_role_variation_staging(spec, candidate, varied_specs)
            action_intent = candidate.get("role_action") or spec.get("role_action_intent") or spec.get("role_action")
            expression_intent = candidate.get("role_expression") or spec.get("role_expression_intent") or spec.get("role_expression")
            prop_intent = candidate.get("prop_signature") or spec.get("role_prop_intent") or "none"
            hair_expression_mode = spec.get("hair_expression_mode") or "slicked-back-side-part"
            render_signature = build_render_signature(
                str(action_intent),
                str(expression_intent),
                str(prop_intent),
                str(role_framing),
                str(role_position),
            )
            signature = f"{action_family}|{expression_family}"
            score = idx * 4
            score += action_counts[action_family] * 5
            score += expression_counts[expression_family] * 4
            score += pose_family_counts[pose_family] * 9
            score += signature_counts[signature] * 12
            score += prop_signature_counts[prop_signature] * 7
            if prop_signature in MIC_PROP_SIGNATURES:
                score += 25
                if prop_signature_counts[prop_signature] >= MAX_MIC_POSE_PER_DECK:
                    score += 200
            if render_signature in used_render_signatures:
                score += 500
            if previous:
                if action_family in (previous.get("role_action_tags") or [])[:1]:
                    score += 18
                if expression_family in (previous.get("role_expression_tags") or [])[:1]:
                    score += 18
                if pose_family == previous.get("role_pose_family"):
                    score += 24
                if role_position == previous.get("role_position"):
                    score += 2
                if role_framing == previous.get("role_framing"):
                    score += 6
                if render_signature == previous.get("render_signature"):
                    score += 500
            if previous2:
                if action_family in (previous2.get("role_action_tags") or [])[:1]:
                    score += 6
                if expression_family in (previous2.get("role_expression_tags") or [])[:1]:
                    score += 6
                if pose_family == previous2.get("role_pose_family"):
                    score += 10
                if render_signature == previous2.get("render_signature"):
                    score += 220
            if best_score is None or score < best_score:
                best_score = score
                best_candidate = candidate

        role_position, role_framing, staging_guard = choose_role_variation_staging(spec, best_candidate, varied_specs)
        role_action_intent = best_candidate.get("role_action") or spec.get("role_action_intent") or spec.get("role_action")
        role_expression_intent = best_candidate.get("role_expression") or spec.get("role_expression_intent") or spec.get("role_expression")
        role_prop_intent = best_candidate.get("prop_signature") or spec.get("role_prop_intent") or "none"
        hair_expression_mode = spec.get("hair_expression_mode") or "slicked-back-side-part"
        render_signature = build_render_signature(
            str(role_action_intent),
            str(role_expression_intent),
            str(role_prop_intent),
            str(role_framing),
            str(role_position),
        )
        if render_signature in used_render_signatures:
            page_label = spec.get("page_title") or spec.get("display_title") or f"page-{spec.get('page_index', '?')}"
            raise ValueError(f"语义动作去重失败：{page_label} 在多轮语义改写后仍与前页或全篇演法重复")
        role_position, role_framing, staging_guard = choose_role_variation_staging(spec, best_candidate, varied_specs)
        updated = dict(spec)
        updated["role_action"] = best_candidate["role_action"]
        updated["role_expression"] = best_candidate["role_expression"]
        updated["role_action_tags"] = best_candidate["role_action_tags"]
        updated["role_expression_tags"] = best_candidate["role_expression_tags"]
        updated["role_variation_action_family"] = best_candidate["action_family"]
        updated["role_variation_expression_family"] = best_candidate["expression_family"]
        updated["role_action_intent"] = role_action_intent
        updated["role_expression_intent"] = role_expression_intent
        updated["role_prop_intent"] = role_prop_intent
        updated["role_framing_intent"] = role_framing
        updated["role_position_intent"] = role_position
        updated["render_signature"] = render_signature
        updated["role_pose_key"] = best_candidate["role_pose_key"]
        updated["role_pose_family"] = best_candidate["role_pose_family"]
        updated["role_pose_repeat_forbidden"] = True
        updated["global_render_signature_unique_required"] = True
        updated["mic_pose_limited_once"] = True
        updated["prop_signature"] = infer_prop_signature(best_candidate.get("prop_signature"))
        updated["role_reference_filenames"] = best_candidate.get("reference_filenames") or build_reference_filename_preferences(
            best_candidate["action_family"],
            best_candidate.get("prop_signature", ""),
        )
        updated["role_pose_hint"] = (
            f"{best_candidate['role_pose_hint']}；动作必须由本页语义决定；"
            "若成图与已生成页演法相似，必须改动作、表情、道具、景别或站位后重做"
        )
        updated["role_position"] = role_position
        updated["role_framing"] = role_framing
        updated["allowed_role_framings"] = infer_allowed_role_framings(
            updated["page_type"],
            updated.get("role_scale", "medium-support"),
            updated.get("page_title", ""),
            updated.get("page_index", 1),
            best_candidate["action_family"],
        )
        guard_parts = []
        reason_parts = []
        if best_candidate is not candidates[0]:
            guard_parts.append("switch-action-expression-family")
            reason_parts.append(
                f"为避开同题重复，本页改用“{best_candidate['action_family']} + {best_candidate['expression_family']}”组合"
            )
        guard_parts.append("semantic-render-signature-unique")
        reason_parts.append(f"本页最终演法签名为 {render_signature}，需与全篇其他页面保持不同")
        if infer_prop_signature(best_candidate.get("prop_signature")) in MIC_PROP_SIGNATURES:
            guard_parts.append("mic-pose-limited-once")
            reason_parts.append("拿麦讲话属于高频风险姿态，本篇仅允许本页使用一次")
        if staging_guard != "keep-default-staging":
            guard_parts.append(staging_guard)
            reason_parts.append("同时调整人物景别或站位，避免连续页出现近似构图")
        if not guard_parts:
            guard_parts.append("semantic-match-primary")
            reason_parts.append("当前页首选动作已经与近邻页拉开差异，保持该页语义优先")
        updated["role_variation_guard"] = " + ".join(guard_parts)
        updated["role_variation_reason"] = "；".join(reason_parts)
        varied_specs.append(updated)
        action_counts[best_candidate["action_family"]] += 1
        expression_counts[best_candidate["expression_family"]] += 1
        pose_family_counts[best_candidate["role_pose_family"]] += 1
        used_render_signatures.add(render_signature)
        prop_signature_counts[infer_prop_signature(best_candidate.get("prop_signature"))] += 1
        signature_counts[f"{best_candidate['action_family']}|{best_candidate['expression_family']}"] += 1
    return varied_specs


def choose_role_action(page_type: str, title: str, body: str) -> str:
    if page_type == "对比页":
        return "用双手分别指向两侧内容，做对比和取舍"
    if page_type == "流程页":
        return "沿着流程节点推进、连接或跨越"
    if page_type == "总结页":
        return "面向观众做收束确认，像在总结重点"
    if page_type == "观点页":
        return "指向重点词、做思考或顿悟动作"
    return "围绕页面核心概念做演示和拆解"


def choose_role_expression(page_type: str, title: str, body: str) -> str:
    if page_type == "对比页":
        return "高夸张的判断感和解释感，眉眼和手势都更明显"
    if page_type == "流程页":
        return "高夸张的推进感和执行感，动作更有带动性"
    if page_type == "总结页":
        return "高夸张的确认感和号召感，像在收束全场"
    if page_type == "观点页":
        return "高夸张的思考、质疑或顿悟感，表情更戏剧化"
    return "高夸张但稳定可辨认的说明型表情"


def choose_role_prop_intent(title: str, body: str, page_type: str, action_family: str | None = None) -> str:
    haystack = f"{title}\n{body}"
    if re.search(r"(话筒|麦克风|直播|主持|播客|演讲)", haystack):
        return "mic"
    if re.search(r"(电脑|系统|写作|文档|屏幕|键盘)", haystack):
        return "computer"
    if re.search(r"(笔记|拆解|结构|标注|白板|流程图)", haystack):
        return "pen-board"
    if re.search(r"(对比|选择|判断|路线|方向)", haystack):
        return "pointer"
    if action_family == "explaining":
        return "pointer"
    return "none"


def choose_hair_expression_mode(title: str, body: str, expression_family: str | None = None) -> str:
    del title, body, expression_family
    return "slicked-back-side-part"


def build_render_signature(
    action_intent: str,
    expression_intent: str,
    prop_intent: str,
    framing_intent: str,
    position_intent: str,
) -> str:
    return "|".join(
        [
            action_intent.strip(),
            expression_intent.strip(),
            prop_intent.strip(),
            framing_intent.strip(),
            position_intent.strip(),
        ]
    )


def choose_icon_set(title: str, body: str, page_type: str) -> list[str]:
    haystack = f"{title}\n{body}"
    icons: list[str] = []
    keyword_map = [
        ("系统", "齿轮"),
        ("步骤", "箭头"),
        ("流程", "流程箭头"),
        ("执行", "勾选框"),
        ("认知", "灯泡"),
        ("对比", "天平"),
        ("时间", "时钟"),
        ("增长", "上升曲线"),
        ("用户", "人物群像"),
    ]
    for keyword, icon in keyword_map:
        if keyword in haystack and icon not in icons:
            icons.append(icon)
    if not icons:
        fallback = extract_source_terms(haystack, limit=2, max_len=4)
        icons.extend(fallback or ["箭头"])
    return icons[:4]


def choose_role_scale(page_type: str, section_kind: str, title: str, visual_keywords: list[str], index: int) -> str:
    if is_cover_like_page(index, title):
        return "large-focus"
    del visual_keywords
    if index == 1:
        return "medium-support"
    if page_type == "总结页":
        return "medium-support"
    if page_type in {"流程页", "对比页"}:
        return "small-accent"
    if section_kind in {"intro", "manual"}:
        return "small-accent"
    return "small-accent"


def choose_role_position(index: int, role_scale: str, section_kind: str, page_type: str, scene_concept: str) -> str:
    if page_type == "对比页":
        return "center-bridge"
    if page_type == "流程页" or scene_concept in {"production-line", "path-flow"}:
        return "mid-path"
    if page_type == "总结页":
        return "inside-center"
    if section_kind == "outro":
        return ["inside-right", "inside-left", "inside-center"][(index - 2) % 3]
    return ["inside-left", "inside-right", "inside-center", "mid-structure"][(index - 2) % 4]


def choose_role_framing(role_scale: str, page_type: str, title: str, index: int, action_family: str | None = None) -> str:
    haystack = title
    if action_family == "blocking":
        return "full-body"
    if action_family in {"shocked", "confused"} and role_scale == "small-accent":
        return "full-body"
    if action_family in {"thinking", "questioning"} and role_scale == "large-focus":
        return "three-quarter"
    if is_cover_like_page(index, title) and role_scale == "large-focus":
        return "three-quarter"
    if role_scale == "small-accent":
        return "full-body"
    if page_type in {"总结页", "对比页", "流程页"}:
        return "three-quarter"
    return "three-quarter"


def choose_role_composition_mode(
    title: str,
    page_type: str,
    role_scale: str,
    role_position: str,
    role_framing: str,
    index: int,
) -> str:
    haystack = title
    if is_cover_like_page(index, title):
        return "cover-centered-focus"
    if index == 1:
        return "supporting-opening-scene"
    if re.search(r"(误区|踩坑|坑)", haystack):
        return "structure-first-supporting-role"
    if re.search(r"(路径|流程|步骤|验证|顺序)", haystack):
        return "supporting-operator-inside-flow"
    if page_type == "对比页":
        return "supporting-contrast-bridge"
    if role_scale == "small-accent":
        return "structure-first-small-support"
    if role_scale == "large-focus" and role_position == "center" and role_framing == "half-body":
        return "cover-centered-focus"
    return "supporting-role-in-scene"


def choose_camera_energy(page_type: str, title: str, role_scale: str) -> str:
    haystack = title
    if role_scale == "large-focus" or re.search(r"(扎心|真相|赚不到|误区|踩坑|拖延)", haystack):
        return "high"
    return "medium"


def choose_role_pose_hint(title: str, page_type: str, role_scale: str) -> str:
    haystack = title
    if is_cover_like_page(1, title):
        return "封面可以更强，但正文页先搭原文结构，再把一到三个角色嵌进去；人物只是辅助演示元素"
    if re.search(r"(7个误区|误区|踩坑|坑)", haystack):
        return "角色要走进结构里，但只能辅助指向、对照或操作，不允许用一排人物替代内容"
    if re.search(r"(赚不到|收入|变现)", haystack):
        return "做出明显反差，但不要画收入、金币、火箭等原文没说的结果物"
    if re.search(r"(路径|流程|步骤|顺序|验证)", haystack):
        return "沿着箭头、节点或路径真正推进、跨越或操作结构，动作要和路径发生直接接触"
    if page_type == "对比页":
        return "身体和手势同时连到左右两侧结构，站在中间做桥接和判断，不允许独立站在空白侧边"
    if page_type == "总结页":
        return "站稳画面，手势展开，像在做最后确认和收束"
    if role_scale == "large-focus":
        return "人物作为主视觉主体，只用于封面或极少数特殊页，正文页默认不用大主角"
    return "角色结合标题内容演示，不要站桩，不要只是普通主持姿态"


def role_scale_ratio(role_scale: str) -> str:
    return {
        "small-accent": "roughly 10% to 18% of the canvas",
        "medium-support": "roughly 20% to 35% of the canvas",
        "large-focus": "roughly 38% to 55% of the canvas",
    }.get(role_scale, "roughly 20% to 35% of the canvas")


def build_page_spec(page: dict[str, str], total: int, pages: list[dict[str, str]] | None = None) -> dict[str, Any]:
    index = int(page["index"])
    page_type = infer_page_type(page["title"], page["body"], index, total)
    odd = index % 2 == 1
    sentences = [line.strip() for line in page["body"].splitlines() if line.strip()]
    full_icon_set = choose_icon_set(page["title"], page["body"], page_type)
    page_hook = page.get("page_hook") or summarize_hook(sentences, fallback=page["title"])
    speaker_guides = sentences[: min(2, len(sentences))]
    raw_visual_keywords = page.get("visual_keywords") or extract_visual_keywords(page["title"], page["body"], full_icon_set, page_type)
    role_scale = choose_role_scale(page_type, page.get("section_kind", "manual"), page["title"], raw_visual_keywords, index)
    scene_concept = choose_scene_concept(page["title"], page_type, page.get("section_kind", "manual"), index)
    density = get_density_profile(scene_concept, page.get("section_kind", "manual"), bool(page.get("is_continued", False)), index)
    text_density_mode = page.get("text_density_mode") or choose_text_density_mode(
        index,
        page_type,
        page["title"],
        scene_concept,
        page.get("section_kind", "manual"),
    )
    icon_set = full_icon_set[: density["icons"]]
    page_title = str(page.get("title") or "").strip()
    deck_title_text = str(page.get("deck_title") or "").strip()
    explicit_heading_title_required = is_explicit_heading_page(page)
    explicit_heading_source_level = int(page.get("explicit_heading_level") or 0)
    summary_title_exception_allowed = should_use_summary_title_exception(page, page_type)
    force_exact_page_title = explicit_heading_title_required and not summary_title_exception_allowed and bool(page_title)
    title_strategy = page.get("title_strategy") or choose_title_strategy(page, page_type, page.get("deck_title"))
    step_title_layers = extract_step_title_layers(page["title"], page["body"])
    title_candidates = [page["title"]] + sentences
    effective_title = page["title"]
    display_title_mode = page.get("display_title_mode") or choose_display_title_mode(page["title"], page_type)
    explicit_subtitle_notes: list[str] = []
    summary_title_exception_source_quote = ""
    if force_exact_page_title:
        effective_title = page_title
        display_title_mode = "exact"
    elif title_strategy == "explicit-heading-title":
        effective_title = page_title or page["title"]
        display_title_mode = "exact"
    elif title_strategy == "summary-body-source-title":
        effective_title, summary_title_exception_source_quote = choose_summary_exception_title(page)
        display_title_mode = "exact"
    elif title_strategy == "explicit-step-with-subtitle":
        effective_title = step_title_layers[0] if step_title_layers else page["title"]
        explicit_subtitle_notes = step_title_layers[1:2]
        display_title_mode = "exact"
    elif title_strategy == "explicit-step-title":
        effective_title = step_title_layers[0] if step_title_layers else page["title"]
        display_title_mode = "exact"
    else:
        extracted_title_candidates = (
            [page["title"]] if is_complete_sentence_title(page["title"]) else []
        ) + sentences + [page["title"]]
        effective_title = extract_full_hook_title(extracted_title_candidates, fallback=page["title"])
        display_title_mode = "exact"
    if explicit_heading_title_required and not summary_title_exception_allowed:
        display_title = page_title or page["title"]
    elif title_strategy == "summary-body-source-title":
        display_title = effective_title
    else:
        display_title = page.get("display_title") or (effective_title if display_title_mode == "exact" else build_display_title(effective_title, page_type, display_title_mode))
    subtitle_notes = page.get("subtitle_notes") or explicit_subtitle_notes or extract_subtitle_notes(effective_title, display_title_mode)
    semantic_text_contract = build_semantic_text_contract(
        page["title"],
        page["body"],
        page_type,
        cue_limit=int(density.get("talking_points", 2)),
        support_limit=(5 if "唯一变量" in page["title"] else 4),
    )
    # Commercial/time umbrellas can be genuinely source-supported, so they
    # remain a fallback.  Specific actions, judgments, causes, mistakes and
    # steps are selected first on every page.
    deprioritized_concepts = {"赚钱", "收入", "收益", "收益刻度", "省时"}
    if page.get("keyword_visual_mappings"):
        keyword_visual_mappings = validate_keyword_visual_mappings(
            page.get("keyword_visual_mappings"),
            page["title"],
            page["body"],
            context=f"page-spec/page-{index:02d}",
        )
    else:
        keyword_visual_mappings = build_keyword_visual_mappings(
            page["title"],
            page["body"],
            semantic_text_contract,
            deprioritized_concepts,
        )
    cue_phrase_source_quotes = page.get("cue_phrase_source_quotes") or semantic_text_contract["cue_phrase_source_quotes"]
    if page.get("cue_phrases") or page.get("talking_points"):
        cue_phrases = page.get("cue_phrases") or page.get("talking_points") or []
        cue_phrase_source_quotes = cue_phrase_source_quotes or {
            phrase: infer_exact_source_quote(str(phrase), page["title"], page["body"])
            for phrase in cue_phrases
        }
    else:
        cue_phrases = semantic_text_contract["cue_phrases"]
    visual_keywords = (page.get("visual_keywords") or raw_visual_keywords)[: density["visual_keywords"]]
    visual_action_cues = page.get("visual_action_cues") or extract_visual_action_cues(page["title"], page["body"], page_type)
    visual_scene_cues = page.get("visual_scene_cues") or extract_visual_scene_cues(page["title"], page["body"], page_type)
    scene_layout_type = choose_scene_layout_type(scene_concept, role_scale, index)
    title_layout_mode = choose_title_layout_mode(scene_concept, index, role_scale)
    title_alignment = choose_title_alignment(title_layout_mode)
    title_anchor_zone = choose_title_anchor_zone(scene_concept, title_layout_mode)
    title_flow_direction = choose_title_flow_direction(scene_concept, title_layout_mode, page["title"])
    role_action = choose_role_action(page_type, page["title"], page["body"])
    role_expression = choose_role_expression(page_type, page["title"], page["body"])
    role_action_tags = page.get("role_action_tags") or derive_role_action_tags(page_type, visual_action_cues, role_action, "")
    role_expression_tags = page.get("role_expression_tags") or derive_role_expression_tags(page_type, role_expression, page["title"], page["body"])
    action_contract_seed = {
        "page_index": index,
        "page_type": page_type,
        "page_title": page["title"],
        "title_text": display_title,
        "display_title": display_title,
        "section_kind": page.get("section_kind", "manual"),
        "scene_concept": scene_concept,
        "role_action_tags": role_action_tags,
        "role_expression_tags": role_expression_tags,
        "visual_action_cues": visual_action_cues,
        "visual_scene_cues": visual_scene_cues,
        "cue_phrases": cue_phrases,
    }
    role_action_family, role_action_match_basis = infer_action_family(action_contract_seed)
    role_expression_family, role_expression_match_basis = infer_expression_family(action_contract_seed, role_action_family)
    prop_signature = infer_prop_signature(role_action_family)
    role_pose_key = f"page-{index:02d}-{pose_digest(page['title'], role_action_family, role_expression_family, role_action)}"
    role_reference_filenames = build_reference_filename_preferences(role_action_family, prop_signature)
    role_action_intent = role_action
    role_expression_intent = role_expression
    role_prop_intent = choose_role_prop_intent(page["title"], page["body"], page_type, role_action_family)
    hair_expression_mode = choose_hair_expression_mode(page["title"], page["body"], role_expression_family)
    role_position = choose_role_position(index, role_scale, page.get("section_kind", "manual"), page_type, scene_concept)
    role_framing = choose_role_framing(role_scale, page_type, page["title"], index, role_action_family)
    role_framing_intent = role_framing
    role_position_intent = role_position
    role_composition_mode = choose_role_composition_mode(page["title"], page_type, role_scale, role_position, role_framing, index)
    role_in_scene_mode = choose_role_in_scene_mode(page["title"], page_type, scene_concept, index)
    camera_energy = choose_camera_energy(page_type, page["title"], role_scale)
    role_pose_hint = choose_role_pose_hint(page["title"], page_type, role_scale)
    render_signature = build_render_signature(
        role_action_intent,
        role_expression_intent,
        role_prop_intent,
        role_framing_intent,
        role_position_intent,
    )
    role_action_tags = page.get("role_action_tags") or derive_role_action_tags(page_type, visual_action_cues, role_action, role_pose_hint)
    role_expression_tags = page.get("role_expression_tags") or derive_role_expression_tags(page_type, role_expression, page["title"], page["body"])
    allowed_role_framings = infer_allowed_role_framings(page_type, role_scale, page["title"], index, role_action_family)
    flow_label_source_quotes = page.get("flow_label_source_quotes") or {}
    if page.get("flow_labels"):
        flow_labels = page.get("flow_labels") or []
        flow_label_source_quotes = flow_label_source_quotes or {
            label: infer_exact_source_quote(str(label), page["title"], page["body"])
            for label in flow_labels
        }
    else:
        flow_labels, flow_label_source_quotes = extract_flow_labels(page, cue_phrases, text_density_mode, cue_phrase_source_quotes)
    support_label_source_quotes = page.get("support_label_source_quotes") or semantic_text_contract["support_label_source_quotes"]
    if page.get("support_labels"):
        support_labels = page.get("support_labels") or []
        support_label_source_quotes = support_label_source_quotes or {
            label: infer_exact_source_quote(str(label), page["title"], page["body"])
            for label in support_labels
        }
    else:
        support_labels = semantic_text_contract["support_labels"]
    cue_phrase_source_quotes = {label: cue_phrase_source_quotes.get(label, infer_exact_source_quote(label, page["title"], page["body"])) for label in cue_phrases}
    flow_label_source_quotes = {label: flow_label_source_quotes.get(label, infer_exact_source_quote(label, page["title"], page["body"])) for label in flow_labels}
    support_label_source_quotes = {label: support_label_source_quotes.get(label, infer_exact_source_quote(label, page["title"], page["body"])) for label in support_labels}
    semantic_candidate_source_quotes = {
        display_title: summary_title_exception_source_quote or infer_exact_source_quote(display_title, page["title"], page["body"]),
    }
    for note in subtitle_notes:
        semantic_candidate_source_quotes[note] = infer_exact_source_quote(note, page["title"], page["body"])
    semantic_candidate_source_quotes.update(cue_phrase_source_quotes)
    semantic_candidate_source_quotes.update(flow_label_source_quotes)
    semantic_candidate_source_quotes.update(support_label_source_quotes)
    slot_contract = dedupe_text_slots(
        display_title,
        subtitle_notes,
        cue_phrases,
        flow_labels,
        support_labels,
        semantic_candidate_source_quotes,
    )
    subtitle_notes = slot_contract["subtitle_notes"]
    cue_phrases = slot_contract["cue_phrases"]
    flow_labels = slot_contract["flow_labels"]
    support_labels = slot_contract["support_labels"]
    cue_phrase_source_quotes = {label: semantic_candidate_source_quotes.get(label, cue_phrase_source_quotes.get(label, label)) for label in cue_phrases}
    flow_label_source_quotes = {label: semantic_candidate_source_quotes.get(label, flow_label_source_quotes.get(label, label)) for label in flow_labels}
    support_label_source_quotes = {label: semantic_candidate_source_quotes.get(label, support_label_source_quotes.get(label, label)) for label in support_labels}
    primary_seed = [display_title] + subtitle_notes[:1] + cue_phrases[:1]
    primary_info_blocks = unique_preserve_order(primary_seed)[: density.get("primary_blocks", 2)]
    secondary_info_blocks: list[str] = []
    if density.get("secondary_blocks", 0) > 0 and text_density_mode != "graph-first":
        secondary_info_blocks = unique_preserve_order(
            [label for label in support_labels + flow_labels if label not in primary_info_blocks]
        )[: density.get("secondary_blocks", 1)]
    supporting_micro_visuals = choose_supporting_micro_visuals(icon_set, scene_concept)[: density["micro_visuals"]]
    single_role_required = index in SINGLE_ROLE_PAGE_INDEXES
    role_count_contract = infer_role_count_contract(index, page_type, scene_concept, page["title"], page["body"])
    role_count_target = int(role_count_contract["role_count_target"])
    semantic_candidate_items = unique_preserve_order([display_title] + subtitle_notes + cue_phrases + flow_labels + support_labels)
    semantic_candidate_source_quotes = {
        item: semantic_candidate_source_quotes.get(item, infer_exact_source_quote(item, page["title"], page["body"]))
        for item in semantic_candidate_items
    }
    visible_semantic_texts = set(cue_phrases + flow_labels + support_labels)
    visual_module_assignments = [
        item for item in semantic_text_contract["visual_module_assignments"]
        if item.get("visible_text") in visible_semantic_texts
    ]
    label_module_targets = ["mini-visual", "node", "misconception-block", "flow-block", "icon-tag-block"]
    label_module_required = bool(visual_module_assignments)
    # The final visual-note gate counts frozen main cards, not only legacy
    # support-label assignments.  A page with two source-rooted causal cards
    # therefore needs two hand-drawn module blocks even when text-slot
    # de-duplication leaves just one support label.
    module_block_count_target = min(
        KEYWORD_VISUAL_MAPPING_MAX,
        max(KEYWORD_VISUAL_MAPPING_MIN, len(visual_module_assignments), len(keyword_visual_mappings)),
    )
    return {
        "page_index": index,
        "page_title": page["title"],
        "step_title_layers": step_title_layers,
        "title_text": effective_title,
        "title_strategy": title_strategy,
        "title_extraction_required": title_strategy == "extracted-full-hook",
        "forbid_fragment_title": title_strategy == "extracted-full-hook",
        "display_title_mode": display_title_mode,
        "display_title": display_title,
        "explicit_heading_title_required": explicit_heading_title_required,
        "explicit_heading_source_level": explicit_heading_source_level,
        "summary_title_exception_allowed": summary_title_exception_allowed,
        "summary_title_exception_source_quote": summary_title_exception_source_quote,
        "source_title_full": page["title"],
        "subtitle_notes": subtitle_notes,
        "page_body": page["body"],
        "deck_title": page.get("deck_title"),
        "deck_title_context_only": True,
        "deck_title_visible_forbidden": True,
        "page_hook": page_hook,
        "cue_phrases": cue_phrases,
        "cue_phrase_source_quotes": cue_phrase_source_quotes,
        "talking_points": cue_phrases,
        "flow_labels": flow_labels,
        "flow_label_source_quotes": flow_label_source_quotes,
        "support_labels": support_labels,
        "support_label_source_quotes": support_label_source_quotes,
        "support_labels_required": bool(support_labels),
        "source_rooted_labels_required": bool(support_labels),
        "visible_text_source_mode": "exact-source-only",
        "visible_text_repeat_forbidden": True,
        "visible_text_slot_dedup_required": True,
        "repeated_source_fragment_forbidden": True,
        "visible_text_overlap_forbidden": True,
        "text_slot_assignment": slot_contract["text_slot_assignment"],
        "repeated_source_fragments_filtered": slot_contract["repeated_source_fragments_filtered"],
        "source_fragment_overlap_groups": slot_contract["source_fragment_overlap_groups"],
        "text_slot_conflict_resolutions": slot_contract["text_slot_conflict_resolutions"],
        "semantic_candidate_items": semantic_candidate_items,
        "semantic_candidate_source_quotes": semantic_candidate_source_quotes,
        # Final rendered Chinese comes only from source_text_ledger, which is
        # built after keyword-to-visual mappings are frozen.
        "speech_clauses": semantic_text_contract["speech_clauses"],
        "valid_clause_count": semantic_text_contract["valid_clause_count"],
        "visible_text_density_target": semantic_text_contract["visible_text_density_target"],
        "visible_text_density_actual": semantic_text_contract["visible_text_density_actual"],
        "visible_text_density_required": semantic_text_contract["visible_text_density_required"],
        "density_gap_reason": semantic_text_contract["density_gap_reason"],
        "parallel_items_must_show": semantic_text_contract["parallel_items_must_show"],
        "formula_or_equation_must_show": semantic_text_contract["formula_or_equation_must_show"],
        "semantic_units": semantic_text_contract["semantic_units"],
        "must_show_source_quotes": semantic_text_contract["must_show_source_quotes"],
        "supporting_source_quotes": semantic_text_contract["supporting_source_quotes"],
        "context_only_source_quotes": semantic_text_contract["context_only_source_quotes"],
        "discarded_transition_quotes": semantic_text_contract["discarded_transition_quotes"],
        "key_information_types": semantic_text_contract["key_information_types"],
        "formula_items": semantic_text_contract["formula_items"],
        "semantic_priority_order": [
            item for item in semantic_text_contract["semantic_priority_order"] if item in visible_semantic_texts
        ],
        "visual_module_assignments": visual_module_assignments,
        "core_visual_keywords": [item["keyword"] for item in keyword_visual_mappings],
        "keyword_visual_mappings": keyword_visual_mappings,
        "evidence_nodes": [
            node for mapping in keyword_visual_mappings for node in (mapping.get("evidence_nodes") or [])
        ],
        "main_card_count": len(keyword_visual_mappings),
        "parallel_branch_groups": _numbered_branch_blocks(page["body"]),
        "keyword_visual_mappings_required": True,
        "keyword_visual_mappings_min": KEYWORD_VISUAL_MAPPING_MIN,
        "keyword_visual_mappings_max": KEYWORD_VISUAL_MAPPING_MAX,
        "visual_composition_mode": "visual-note",
        "poster_like_forbidden": True,
        "generic_action_as_only_mapping_forbidden": True,
        "text_semantic_completeness_required": True,
        "transition_text_visible_forbidden": True,
        "formula_preservation_required": bool(semantic_text_contract["formula_items"]),
        "label_anchor_targets": ["primary-visual", "mini-visual", "node", "misconception-block", "flow-block"],
        "label_module_required": label_module_required,
        "label_module_targets": label_module_targets,
        "label_visual_pairing_required": True,
        "micro_visual_anchor_required": True,
        "module_block_count_target": module_block_count_target,
        "micro_visual_style": MICRO_VISUAL_STYLE,
        "micro_visual_style_label": MICRO_VISUAL_STYLE_LABEL,
        "micro_visual_style_required": True,
        "micro_visual_container_required": True,
        "bare_line_icon_forbidden": True,
        "ui_flat_icon_forbidden": True,
        "sticker_style_forbidden": True,
        "realistic_micro_illustration_forbidden": True,
        "three_d_icon_forbidden": True,
        "micro_visual_style_consistency_required": True,
        "micro_visual_style_components": MICRO_VISUAL_STYLE_COMPONENTS,
        "primary_info_blocks": primary_info_blocks,
        "secondary_info_blocks": secondary_info_blocks,
        "primary_info_block_visual_required": True,
        "secondary_info_block_visual_optional": True,
        "visual_keywords": visual_keywords,
        "visual_action_cues": visual_action_cues,
        "visual_scene_cues": visual_scene_cues,
        "role_action_tags": role_action_tags,
        "role_expression_tags": role_expression_tags,
        "speaker_guides": speaker_guides,
        "density_profile": density,
        "text_density_mode": text_density_mode,
        "graph_first_mode": text_density_mode == "graph-first",
        "text_light_mode": text_density_mode == "text-light",
        "page_type": page_type,
        "page_background_mode": "odd" if odd else "even",
        "background_color": ODD_BG if odd else EVEN_BG,
        "skin_tone_base": SKIN_TONE_BASE,
        "line_color": ODD_LINE if odd else EVEN_LINE,
        "red_accent_required": True,
        "red_accent_count_min": 1,
        "red_accent_count_max": 3,
        "red_accent_allowed_targets": ["keyword", "arrow", "tag", "result", "warning"],
        "red_accent_semantic_only": True,
        "uniform_label_container_forbidden": True,
        "scene_priority": "scene-first",
        "scene_concept": scene_concept,
        "scene_layout_type": scene_layout_type,
        "title_layout_mode": title_layout_mode,
        "title_alignment": title_alignment,
        "title_anchor_zone": title_anchor_zone,
        "title_flow_direction": title_flow_direction,
        "title_layout_guidance": choose_title_layout_guidance(
            scene_concept,
            title_layout_mode,
            title_alignment,
            title_anchor_zone,
            title_flow_direction,
        ),
        "supporting_micro_visuals": supporting_micro_visuals,
        "source_text_only_visual_mode": True,
        "inferred_visuals_forbidden": True,
        "role_required": True,
        "role_count_min": role_count_target,
        "role_count_max": role_count_target,
        "role_count_decision_mode": role_count_contract["role_count_decision_mode"],
        "role_count_target": role_count_target,
        "multi_role_required": role_count_contract["multi_role_required"],
        "multi_role_trigger_type": role_count_contract["multi_role_trigger_type"],
        "role_distribution_brief": role_count_contract["role_distribution_brief"],
        "role_slot_assignments": role_count_contract["role_slot_assignments"],
        "same_page_role_pose_distinct_required": role_count_contract["same_page_role_pose_distinct_required"],
        "role_usage_mode": "supporting-only",
        "role_density_preference": role_scale,
        "single_role_required": single_role_required,
        "role_action_match_required": True,
        "role_action_match_basis": role_action_match_basis,
        "role_action_family": role_action_family,
        "role_expression_family": role_expression_family,
        "role_expression_match_basis": role_expression_match_basis,
        "role_action_intent": role_action_intent,
        "role_expression_intent": role_expression_intent,
        "role_pose_brief": role_pose_hint,
        "role_prop_intent": role_prop_intent,
        "role_framing_intent": role_framing_intent,
        "role_position_intent": role_position_intent,
        "hair_expression_mode": hair_expression_mode,
        "render_signature": render_signature,
        "identity_anchor_required": True,
        "face_anchor_attached_required": True,
        "identity_drift_forbidden": True,
        "hair_variant_forbidden": True,
        "role_pose_key": role_pose_key,
        "role_pose_family": role_action_family,
        "role_pose_repeat_forbidden": True,
        "global_render_signature_unique_required": True,
        "mic_pose_limited_once": True,
        "prop_signature": prop_signature,
        "role_reference_filenames": role_reference_filenames,
        "allowed_role_framings": allowed_role_framings,
        "action_reference_optional": True,
        "action_fallback_forbidden": False,
        "reserved_zone_enabled": True,
        "reserved_zone_scope": "body-page-only",
        "reserved_zone_size_cm": RESERVED_ZONE_SIZE_CM,
        "reserved_zone_side_ratio_of_height": RESERVED_ZONE_SIDE_RATIO_OF_HEIGHT,
        "role_scene_relationship": choose_role_scene_relationship(scene_concept, role_scale, index),
        "role_in_scene_mode": role_in_scene_mode,
        "role_in_scene_guidance": choose_role_in_scene_guidance(role_in_scene_mode, page_type, scene_concept),
        "reserved_zone": RESERVED_ZONE,
        "reserved_zone_rules": RESERVED_ZONE_RULES,
        "pagination_mode": page.get("pagination_mode", "explicit"),
        "section_kind": page.get("section_kind", "manual"),
        "step_label": page.get("step_label", ""),
        "step_index": page.get("step_index"),
        "step_page_index": page.get("step_page_index", 1),
        "step_page_total": page.get("step_page_total", 1),
        "is_continued": page.get("is_continued", False),
        "forbid_visible_page_number": True,
        "role_action": role_action,
        "role_expression": role_expression,
        "role_identity_lock": "strict",
        "role_scale": role_scale,
        "role_position": role_position,
        "role_framing": role_framing,
        "role_composition_mode": role_composition_mode,
        "camera_energy": camera_energy,
        "role_pose_hint": role_pose_hint,
        "role_variation_guard": page.get("role_variation_guard", "semantic-match-primary"),
        "role_variation_reason": page.get("role_variation_reason", "基础语义分配，后续允许按整套选题做去重调整"),
        "icon_set": icon_set,
        "layout_constraints": DEFAULT_LAYOUT_CONSTRAINTS,
    }


def attach_cross_page_motif_guards(specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Expose only real cross-page overlaps to the rendering instruction.

    A repeated source concept is not itself an error: a later paragraph may
    genuinely discuss income, time or choice again.  The generator gets a
    compact, page-specific guard only when it would otherwise repeat the same
    source concept, the same drawn-object combination and the same relation.
    """
    previous: list[dict[str, Any]] = []
    guarded_specs: list[dict[str, Any]] = []
    for spec in specs:
        current = [dict(item) for item in (spec.get("keyword_visual_mappings") or [])]
        repeated: list[dict[str, Any]] = []
        for mapping in current:
            mapping_core = _concept_core(str(mapping.get("concept") or mapping.get("keyword") or ""))
            mapping_objects = tuple(normalize_source_lookup(value) for value in (mapping.get("visual_objects") or []))
            for prior in previous:
                prior_core = _concept_core(str(prior.get("concept") or prior.get("keyword") or ""))
                prior_objects = tuple(normalize_source_lookup(value) for value in (prior.get("visual_objects") or []))
                same_relation = normalize_source_lookup(str(mapping.get("action_or_relation") or "")) == normalize_source_lookup(str(prior.get("action_or_relation") or ""))
                if mapping_core and mapping_core == prior_core and mapping_objects == prior_objects and same_relation:
                    repeated.append({
                        "source_label": str(mapping.get("source_label") or mapping.get("keyword") or ""),
                        "prior_page_index": int(prior.get("page_index") or 0),
                        "prior_objects": list(prior.get("visual_objects") or []),
                    })
                    break
        if repeated:
            details = "; ".join(
                f"page-{int(item['prior_page_index']):02d} 与 page-{int(spec['page_index']):02d}: {item['source_label']}"
                for item in repeated
            )
            raise ValueError(f"跨页重复主视觉组合：{details}；同一文字+物件+关系不得原样复用")
        updated = dict(spec)
        updated["cross_page_motif_reuse_policy"] = "source-supported-only-and-not-identical-combination"
        updated["prior_page_matching_motifs"] = repeated
        guarded_specs.append(updated)
        previous.extend([{**mapping, "page_index": updated["page_index"]} for mapping in current])
    return guarded_specs


def build_prompt(spec: dict[str, Any], role: dict[str, Any]) -> str:
    """Six-part v4.1 prompt: main cards carry source-backed evidence."""
    plan = spec.get("render_plan") or build_render_plan(spec)
    canvas, scene, role_plan = plan["canvas"], plan["scene"], plan["role"]
    blueprint = plan["visual_blueprint"]
    keyword_maps = blueprint["keyword_visual_mappings"]
    if not keyword_maps:
        raise ValueError(f"page-{int(spec.get('page_index') or 0):02d} 缺少 keyword_visual_mappings，不能生成提示词")
    visual_map = "\n".join(f"- {item['prompt_fragment']}" for item in keyword_maps)
    title_text = str(blueprint["text_slots"][0].get("source_text") or "")
    label_texts = " | ".join(
        f"“{slot.get('source_text') or ''}”"
        for slot in blueprint["text_slots"][1:] if slot.get("kind") == "source-label-card"
    )
    evidence_plan = "\n".join(
        f"- Main card “{mapping['source_label']}”: inside the SAME card render "
        + "; ".join(
            f"“{node['text']}” + {node['action_or_relation']} + objects {'/'.join(node['visual_objects'])}"
            for node in (mapping.get("evidence_nodes") or [])
        )
        for mapping in keyword_maps
    )
    evidence_texts = " | ".join(
        f"“{slot.get('source_text') or ''}”"
        for slot in blueprint["text_slots"][1:] if slot.get("kind") == "evidence-node"
    )
    slot_map = f"Title: “{title_text}”\nMain card labels: {label_texts}\nEvidence lines inside their parent cards: {evidence_texts}"
    matching_motifs = spec.get("prior_page_matching_motifs") or []
    if matching_motifs:
        reuse_guard = "; ".join(
            f"page-{int(item['prior_page_index']):02d} already used “{item['source_label']}” with {'/'.join(item['prior_objects'])}"
            for item in matching_motifs
        )
        reuse_guard = (
            f"REUSE GUARD: {reuse_guard}; keep the current source label but change the object/relationship/layout "
            "so it is not the same visual motif."
        )
    else:
        reuse_guard = "REUSE GUARD: every motif must directly visualize a listed source label; do not copy a prior page's label + objects + relationship."
    face_anchor = str(spec.get("role_face_anchor_image") or "")
    action_anchor = str(spec.get("role_action_reference_image") or "")
    quality_reference = str(spec.get("quality_reference_image") or QUALITY_REFERENCE_IMAGE.resolve())
    role_name = str(role.get("meta", {}).get("display_name") or role.get("slug") or "IP角色")
    role_action_contract = build_native_role_action_contract(spec, role_plan)
    prompt = f"""---
render_plan: {RENDER_PLAN_VERSION}
asset: page-{int(spec['page_index']):02d}
aspect_ratio: {canvas['aspect_ratio']}
render_profile: creative
text_layer: model-integrated-chinese
---
1. CANVAS AND STYLE
16:9 hand-drawn visual note. Flat solid exact background {canvas['background_color']}; no gradient or texture. {canvas['line_color']} lines; red only on semantic nodes. Layout {blueprint['layout_skeleton']}; variant {blueprint['creative_variant']}.
2. REFERENCES
{role_name}; {role_plan['count']} locked role(s); {role_plan['action_family']} ({role_plan['action']}), {role_plan['framing']} at {role_plan['position']}, inside the structure. Face {face_anchor} sha256={file_sha256(face_anchor)}. Action {action_anchor} sha256={file_sha256(action_anchor)}. Keep black glasses, side-part hair, white blazer and black shirt.
Approved quality baseline {pathlib.Path(quality_reference).name} sha256={file_sha256(quality_reference)}: match its information density and integrated title/cards/mini-scenes; copy none of its words or objects.
3. VISUAL KEYWORD MAP
Every line is mandatory and distinct. Use its module and relation; no generic pose or decorative icon.
{visual_map}
4. CONTENT DENSITY PLAN
Every main card must visibly contain every listed evidence short sentence below. Pair each evidence sentence with its named object, process, condition, result or comparison inside that same card; do not turn evidence into a separate card, detached tag, or decorative icon.
{evidence_plan}
5. SOURCE TEXT LEDGER AND HAND-DRAWN MODULE CARDS
The native output is the final image. render each listed phrase exactly once in clear Chinese, already filled inside its hand-drawn title/card surface:
{slot_map}
Put each main label, its 1-3 evidence lines, and their mapped mini-scene/relationship in one module. A main title plus decorative icon alone fails. Show title, all cards, visuals and role together.
6. FORBIDDEN
No blank title/card/evidence slot, placeholder, pseudo text, missing phrase, extra Chinese, later overlay, glossy/UI/3D/sticker style, detached presenter, identity drift or invented claim. Every motif must directly visualize a listed source label. Bottom-left 3cm x 3cm is pure {canvas['background_color']}.
{role_action_contract}
{reuse_guard}

FINAL DELIVERY RULE: this bitmap is the complete final visual note; rerender if any title/card is blank, missing, duplicated, invented or visually mismatched.
"""
    if len(prompt) > BODY_PROMPT_MAX_CHARS:
        raise ValueError(f"page-{int(spec['page_index']):02d} v4.1 prompt 超过 {BODY_PROMPT_MAX_CHARS} 字符")
    return prompt


def build_native_role_action_contract(spec: dict[str, Any], role_plan: dict[str, Any]) -> str:
    """Turn frozen role geometry into an unambiguous native-image requirement.

    The output audit must be able to reject a plausible but wrong presenter
    pose (for example, a chin-resting host beside a comparison).  These are
    prompt constraints only: they neither change the page blueprint nor add
    visible source text.
    """
    display_title = str(spec.get("display_title") or spec.get("title_text") or spec.get("page_title") or "")
    action = " ".join([
        str(spec.get("role_action_intent") or ""),
        str(spec.get("role_action") or ""),
        str(role_plan.get("action") or ""),
        str(role_plan.get("brief") or ""),
    ])
    requirements: list[str] = []
    if display_title == "没流量是你对干货的定义错了":
        requirements.append("TITLE CONTRACT: top title must render exactly “没流量是你对干货的定义错了”, character-for-character; do not shorten, paraphrase or replace it.")
    if "双手分别指向" in action:
        requirements.append("ROLE ACTION CONTRACT: the locked role uses both hands, each pointing to a different left/right content branch inside the comparison; no chin-resting, folded-arm or detached presenter pose.")
    if any(token in action for token in ("沿着流程节点", "跨步越过", "推进", "连接前后节点", "跨越")):
        requirements.append("ROLE ACTION CONTRACT: the locked role must visibly advance along, cross over, or operate the drawn arrow/node structure; do not merely stand beside it and explain.")
    if any(token in action for token in ("空空的钱包", "订单", "结果面板", "落差确认")):
        requirements.append("ROLE ACTION CONTRACT: the locked role must look toward a visibly drawn empty wallet, order, or result panel and make the outcome-gap confirmation; the referenced object must be visible, not implied off-canvas.")
    return "\n".join(requirements) if requirements else "ROLE ACTION CONTRACT: keep the locked role embedded in its frozen structure and perform the declared action."


def build_ppt_from_pages(page_paths: list[pathlib.Path], out_path: pathlib.Path) -> None:
    prs = Presentation()
    prs.slide_width = 16256000
    prs.slide_height = 9144000
    blank = prs.slide_layouts[6]
    for page_path in page_paths:
        slide = prs.slides.add_slide(blank)
        slide.shapes.add_picture(str(page_path), 0, 0, width=prs.slide_width, height=prs.slide_height)
    ensure_dir(out_path.parent)
    prs.save(str(out_path))


def load_specs_from_workdir(workdir: pathlib.Path) -> list[dict[str, Any]]:
    specs_path = workdir / "pages-spec.json"
    if not specs_path.exists():
        raise FileNotFoundError(f"找不到 pages-spec.json: {specs_path}")
    payload = json.loads(specs_path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and payload.get("contract_version") == CONTRACT_VERSION and isinstance(payload.get("pages"), list):
        return payload["pages"]
    raise ValueError(f"pages-spec.json 不是当前 v{CONTRACT_VERSION} 工作包: {specs_path}")


def build_cover_prompt(cover_spec: dict[str, Any], role: dict[str, Any]) -> str:
    """Five-part v4.1 cover prompt; the model renders final source labels itself."""
    plan = cover_spec.get("render_plan") or build_render_plan(cover_spec, is_cover=True)
    canvas, scene, role_plan = plan["canvas"], plan["scene"], plan["role"]
    blueprint = plan["visual_blueprint"]
    face_anchor = str(cover_spec.get("role_face_anchor_image") or "")
    action_anchor = str(cover_spec.get("role_action_reference_image") or "")
    quality_reference = str(cover_spec.get("quality_reference_image") or QUALITY_REFERENCE_IMAGE.resolve())
    role_name = str(role.get("meta", {}).get("display_name") or role.get("slug") or "IP角色")
    text_mode = str(cover_spec.get("cover_text_mode") or "source-labels")
    active_slots = list(blueprint["text_slots"])
    if text_mode == "title-only":
        active_slots = active_slots[:1]
    ledger_lines = " | ".join(f"“{slot.get('source_text') or ''}”" for slot in active_slots)
    prompt = f"""---
render_plan: {RENDER_PLAN_VERSION}
asset: {cover_spec['cover_type']}
aspect_ratio: {canvas['aspect_ratio']}
render_profile: creative
cover_text_mode: {text_mode}
text_layer: model-integrated-chinese
---
1. CANVAS AND STYLE
Native {canvas['aspect_ratio']} hand-drawn IP cover, not a crop. Flat solid exact background {canvas['background_color']}; no gradient or texture. Black linework, restrained red accents; {blueprint['creative_variant']}.
2. ROLE AND APPROVED QUALITY REFERENCES
{role_name}; one identity-locked role, {role_plan['action_family']} at {role_plan['position']}. Face anchor {face_anchor} sha256={file_sha256(face_anchor)}. Preserve glasses, side-part hair, white blazer, black inner shirt and warm skin.
Approved quality baseline {quality_reference} sha256={file_sha256(quality_reference)}. Use only its integrated visual-note finish; never copy its text or semantic objects.
3. VISUAL FOCUS
One source-rooted hand-drawn conflict scene; no invented result, industry scene or label wall.
4. SOURCE TEXT LEDGER AND HAND-DRAWN CARDS
The native output is final. render each listed phrase exactly once in clear Chinese inside completed hand-drawn title/source cards: {ledger_lines}
5. FORBIDDEN
No blank title/card, placeholder, pseudo text, extra Chinese, later text overlay, poster gloss, 3D, sticker style, duplicate avatars, face/hair/outfit drift or body-page reserved-zone rule.

FINAL DELIVERY RULE: the generated bitmap itself must contain the exact source-ledger text and complete visual scene before audit or delivery.
"""
    if len(prompt) > COVER_PROMPT_MAX_CHARS:
        raise ValueError(f"{cover_spec['cover_type']} v4.1 prompt 超过 {COVER_PROMPT_MAX_CHARS} 字符")
    return prompt


def ensure_page_images_exist(page_paths: list[pathlib.Path]) -> None:
    missing = [str(path) for path in page_paths if not path.exists()]
    if missing:
        raise FileNotFoundError("以下目标归档图片未写回，任务未完成，暂时不能装配 PPT:\n" + "\n".join(missing))


def ensure_archive_writeback_complete(page_paths: list[pathlib.Path], archive_dir: pathlib.Path) -> None:
    missing = [str(path) for path in page_paths if not path.exists()]
    outside_archive = [str(path) for path in page_paths if archive_dir not in path.parents]
    if missing:
        raise FileNotFoundError("以下目标归档图片未写回，任务未完成:\n" + "\n".join(missing))
    if outside_archive:
        raise FileNotFoundError("以下图片路径不在指定归档目录内，不能视为正式交付结果:\n" + "\n".join(outside_archive))


def build_codex_handoff(
    specs: list[dict[str, Any]],
    cover_outputs: list[dict[str, Any]],
    selected_pages: list[int],
    workdir: pathlib.Path,
    prompt_paths: list[pathlib.Path],
    page_paths: list[pathlib.Path],
    cover_prompt_paths: dict[str, pathlib.Path],
    role: dict[str, Any],
) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path, pathlib.Path]:
    prompts_by_page = {spec["page_index"]: prompt_path for spec, prompt_path in zip(specs, prompt_paths)}
    pages_by_page = {spec["page_index"]: page_path for spec, page_path in zip(specs, page_paths)}
    selected_specs = [spec for spec in specs if spec["page_index"] in selected_pages]
    items = []
    for spec in selected_specs:
        face_anchor_ref, action_ref, action_reason = split_role_reference_chain(spec, role, preferred_variant="standard")
        item = {
            "page_index": spec["page_index"],
            "page_title": spec["page_title"],
            "title_text": spec.get("title_text"),
            "title_strategy": spec.get("title_strategy"),
            "display_title_mode": spec.get("display_title_mode"),
            "display_title": spec.get("display_title"),
            "explicit_heading_title_required": spec.get("explicit_heading_title_required"),
            "explicit_heading_source_level": spec.get("explicit_heading_source_level"),
            "summary_title_exception_allowed": spec.get("summary_title_exception_allowed"),
            "summary_title_exception_source_quote": spec.get("summary_title_exception_source_quote"),
            "source_title_full": spec.get("source_title_full"),
            "page_body": spec.get("page_body"),
            "deck_title": spec.get("deck_title"),
            "deck_title_context_only": spec.get("deck_title_context_only"),
            "deck_title_visible_forbidden": spec.get("deck_title_visible_forbidden"),
            "page_hook": spec.get("page_hook"),
            "cue_phrases": spec.get("cue_phrases"),
            "cue_phrase_source_quotes": spec.get("cue_phrase_source_quotes"),
            "flow_labels": spec.get("flow_labels"),
            "flow_label_source_quotes": spec.get("flow_label_source_quotes"),
            "support_labels": spec.get("support_labels"),
            "support_label_source_quotes": spec.get("support_label_source_quotes"),
            "support_labels_required": spec.get("support_labels_required"),
            "source_rooted_labels_required": spec.get("source_rooted_labels_required"),
            "visible_text_source_mode": spec.get("visible_text_source_mode"),
            "visible_text_repeat_forbidden": spec.get("visible_text_repeat_forbidden"),
            "visible_text_slot_dedup_required": spec.get("visible_text_slot_dedup_required"),
            "repeated_source_fragment_forbidden": spec.get("repeated_source_fragment_forbidden"),
            "visible_text_overlap_forbidden": spec.get("visible_text_overlap_forbidden"),
            "text_slot_assignment": spec.get("text_slot_assignment"),
            "source_fragment_overlap_groups": spec.get("source_fragment_overlap_groups"),
            "text_slot_conflict_resolutions": spec.get("text_slot_conflict_resolutions"),
            "source_text_ledger": (spec.get("render_plan") or {}).get("source_text_ledger") or spec.get("source_text_ledger"),
            "speech_clauses": spec.get("speech_clauses"),
            "valid_clause_count": spec.get("valid_clause_count"),
            "visible_text_density_target": spec.get("visible_text_density_target"),
            "visible_text_density_actual": spec.get("visible_text_density_actual"),
            "visible_text_density_required": spec.get("visible_text_density_required"),
            "density_gap_reason": spec.get("density_gap_reason"),
            "parallel_items_must_show": spec.get("parallel_items_must_show"),
            "formula_or_equation_must_show": spec.get("formula_or_equation_must_show"),
            "semantic_units": spec.get("semantic_units"),
            "must_show_source_quotes": spec.get("must_show_source_quotes"),
            "supporting_source_quotes": spec.get("supporting_source_quotes"),
            "context_only_source_quotes": spec.get("context_only_source_quotes"),
            "discarded_transition_quotes": spec.get("discarded_transition_quotes"),
            "key_information_types": spec.get("key_information_types"),
            "formula_items": spec.get("formula_items"),
            "semantic_priority_order": spec.get("semantic_priority_order"),
            "visual_module_assignments": spec.get("visual_module_assignments"),
            "core_visual_keywords": spec.get("core_visual_keywords"),
            "keyword_visual_mappings": spec.get("keyword_visual_mappings"),
            "evidence_nodes": spec.get("evidence_nodes"),
            "main_card_count": spec.get("main_card_count"),
            "parallel_branch_groups": spec.get("parallel_branch_groups"),
            "keyword_visual_mappings_required": spec.get("keyword_visual_mappings_required"),
            "keyword_visual_mappings_min": spec.get("keyword_visual_mappings_min"),
            "keyword_visual_mappings_max": spec.get("keyword_visual_mappings_max"),
            "visual_composition_mode": spec.get("visual_composition_mode"),
            "poster_like_forbidden": spec.get("poster_like_forbidden"),
            "text_semantic_completeness_required": spec.get("text_semantic_completeness_required"),
            "transition_text_visible_forbidden": spec.get("transition_text_visible_forbidden"),
            "formula_preservation_required": spec.get("formula_preservation_required"),
            "label_anchor_targets": spec.get("label_anchor_targets"),
            "label_module_required": spec.get("label_module_required"),
            "label_module_targets": spec.get("label_module_targets"),
            "label_visual_pairing_required": spec.get("label_visual_pairing_required"),
            "micro_visual_anchor_required": spec.get("micro_visual_anchor_required"),
            "module_block_count_target": spec.get("module_block_count_target"),
            "micro_visual_style": spec.get("micro_visual_style"),
            "micro_visual_style_label": spec.get("micro_visual_style_label"),
            "micro_visual_style_required": spec.get("micro_visual_style_required"),
            "micro_visual_container_required": spec.get("micro_visual_container_required"),
            "bare_line_icon_forbidden": spec.get("bare_line_icon_forbidden"),
            "ui_flat_icon_forbidden": spec.get("ui_flat_icon_forbidden"),
            "sticker_style_forbidden": spec.get("sticker_style_forbidden"),
            "realistic_micro_illustration_forbidden": spec.get("realistic_micro_illustration_forbidden"),
            "three_d_icon_forbidden": spec.get("three_d_icon_forbidden"),
            "micro_visual_style_consistency_required": spec.get("micro_visual_style_consistency_required"),
            "micro_visual_style_components": spec.get("micro_visual_style_components"),
            "red_accent_semantic_only": spec.get("red_accent_semantic_only"),
            "uniform_label_container_forbidden": spec.get("uniform_label_container_forbidden"),
            "subtitle_notes": spec.get("subtitle_notes"),
            "talking_points": spec.get("talking_points"),
            "text_density_mode": spec.get("text_density_mode"),
            "visual_keywords": spec.get("visual_keywords"),
            "visual_action_cues": spec.get("visual_action_cues"),
            "visual_scene_cues": spec.get("visual_scene_cues"),
            "role_action_tags": spec.get("role_action_tags"),
            "role_expression_tags": spec.get("role_expression_tags"),
            "role_scale": spec.get("role_scale"),
            "role_position": spec.get("role_position"),
            "role_framing": spec.get("role_framing"),
            "role_composition_mode": spec.get("role_composition_mode"),
            "role_in_scene_mode": spec.get("role_in_scene_mode"),
            "role_in_scene_guidance": spec.get("role_in_scene_guidance"),
            "camera_energy": spec.get("camera_energy"),
            "role_pose_hint": spec.get("role_pose_hint"),
            "role_identity_lock": spec.get("role_identity_lock"),
            "role_variation_guard": spec.get("role_variation_guard"),
            "role_variation_reason": spec.get("role_variation_reason"),
            "section_kind": spec.get("section_kind"),
            "step_label": spec.get("step_label"),
            "step_page_index": spec.get("step_page_index"),
            "step_page_total": spec.get("step_page_total"),
            "forbid_visible_page_number": spec.get("forbid_visible_page_number"),
            "background_color": spec["background_color"],
            "line_color": spec["line_color"],
            "scene_priority": spec.get("scene_priority"),
            "scene_concept": spec.get("scene_concept"),
            "scene_layout_type": spec.get("scene_layout_type"),
            "title_layout_mode": spec.get("title_layout_mode"),
            "title_alignment": spec.get("title_alignment"),
            "title_anchor_zone": spec.get("title_anchor_zone"),
            "title_flow_direction": spec.get("title_flow_direction"),
            "supporting_micro_visuals": spec.get("supporting_micro_visuals"),
            "role_scene_relationship": spec.get("role_scene_relationship"),
            "role_required": spec.get("role_required"),
            "source_text_only_visual_mode": spec.get("source_text_only_visual_mode"),
            "inferred_visuals_forbidden": spec.get("inferred_visuals_forbidden"),
            "role_count_min": spec.get("role_count_min"),
            "role_count_max": spec.get("role_count_max"),
            "role_count_decision_mode": spec.get("role_count_decision_mode"),
            "role_count_target": spec.get("role_count_target"),
            "multi_role_required": spec.get("multi_role_required"),
            "multi_role_trigger_type": spec.get("multi_role_trigger_type"),
            "role_distribution_brief": spec.get("role_distribution_brief"),
            "role_slot_assignments": spec.get("role_slot_assignments"),
            "same_page_role_pose_distinct_required": spec.get("same_page_role_pose_distinct_required"),
            "role_usage_mode": spec.get("role_usage_mode"),
            "role_density_preference": spec.get("role_density_preference"),
            "single_role_required": spec.get("single_role_required"),
            "role_action_match_required": spec.get("role_action_match_required"),
            "role_action_match_basis": spec.get("role_action_match_basis"),
            "role_action_family": spec.get("role_action_family"),
            "role_expression_family": spec.get("role_expression_family"),
            "role_action_intent": spec.get("role_action_intent"),
            "role_expression_intent": spec.get("role_expression_intent"),
            "role_pose_brief": spec.get("role_pose_brief"),
            "role_prop_intent": spec.get("role_prop_intent"),
            "role_framing_intent": spec.get("role_framing_intent"),
            "role_position_intent": spec.get("role_position_intent"),
            "hair_expression_mode": spec.get("hair_expression_mode"),
            "render_signature": spec.get("render_signature"),
            "role_pose_key": spec.get("role_pose_key"),
            "role_pose_family": spec.get("role_pose_family"),
            "role_pose_repeat_forbidden": spec.get("role_pose_repeat_forbidden"),
            "global_render_signature_unique_required": spec.get("global_render_signature_unique_required"),
            "mic_pose_limited_once": spec.get("mic_pose_limited_once"),
            "prop_signature": spec.get("prop_signature"),
            "allowed_role_framings": spec.get("allowed_role_framings"),
            "action_fallback_forbidden": spec.get("action_fallback_forbidden"),
            "action_reference_optional": spec.get("action_reference_optional"),
            "reserved_zone_enabled": spec.get("reserved_zone_enabled"),
            "reserved_zone_scope": spec.get("reserved_zone_scope"),
            "reserved_zone_size_cm": spec.get("reserved_zone_size_cm"),
            "reserved_zone_side_ratio_of_height": spec.get("reserved_zone_side_ratio_of_height"),
            "reserved_zone": spec.get("reserved_zone"),
            "reserved_zone_rules": spec.get("reserved_zone_rules"),
            "role_face_anchor_image": spec.get("role_face_anchor_image") or (str(face_anchor_ref["file_path"]) if face_anchor_ref else ""),
            "role_action_reference_image": spec.get("role_action_reference_image") or (str(action_ref["file_path"]) if action_ref else ""),
            "role_action_reference_reason": spec.get("role_action_reference_reason") or action_reason or (action_ref.get("name", "") if action_ref else ""),
            "quality_reference_image": spec.get("quality_reference_image") or str(QUALITY_REFERENCE_IMAGE.resolve()),
            "quality_reference_sha256": spec.get("quality_reference_sha256") or file_sha256(QUALITY_REFERENCE_IMAGE),
            "role_reference_strategy": "anchor-plus-semantic-action",
            "prompt_file": str(prompts_by_page[spec["page_index"]]),
            "output_image": str(pages_by_page[spec["page_index"]]),
            "output_image_required": True,
            "archive_writeback_required": True,
            "delivery_mode": "direct-or-copy-then-clean",
        }
        item.update(build_reference_lock_metadata())
        item["render_plan"] = spec.get("render_plan") or build_render_plan(spec)
        item["visual_blueprint"] = item["render_plan"]["visual_blueprint"]
        item["visual_blueprint_hash"] = item["visual_blueprint"]["content_hash"]
        item["text_overlay_plan"] = spec.get("text_overlay_plan") or build_text_overlay_plan(spec)
        item["text_overlay_plan_file"] = spec.get("text_overlay_plan_file") or ""
        item["role_face_anchor_sha256"] = file_sha256(item.get("role_face_anchor_image"))
        item["role_action_reference_sha256"] = file_sha256(item.get("role_action_reference_image"))
        items.append(item)
    is_full_run = len(selected_pages) == len(specs)
    cover_items = []
    if is_full_run:
        for cover_spec in cover_outputs:
            cover_ref_source = dict(selected_specs[0]) if selected_specs else (dict(specs[0]) if specs else {})
            cover_ref_source.update(cover_spec)
            face_anchor_ref, action_ref, action_reason = build_cover_reference_chain(cover_ref_source, role)
            cover_item = {
                "cover_type": cover_spec["cover_type"],
                "aspect_ratio": cover_spec["aspect_ratio"],
                "deck_title": cover_spec.get("deck_title"),
                "source_title_full": cover_spec.get("source_title_full"),
                "page_body": cover_spec.get("page_body"),
                "title_text": cover_spec["title_text"],
                "display_title": cover_spec["display_title"],
                "background_color": cover_spec["background_color"],
                "line_color": cover_spec["line_color"],
                "style_mode": cover_spec["style_mode"],
                "role_required": cover_spec["role_required"],
                "support_labels_allowed": cover_spec["support_labels_allowed"],
                "cue_phrases": cover_spec.get("cue_phrases"),
                "cue_phrase_source_quotes": cover_spec.get("cue_phrase_source_quotes"),
                "flow_labels": cover_spec.get("flow_labels"),
                "flow_label_source_quotes": cover_spec.get("flow_label_source_quotes"),
                "support_labels": cover_spec.get("support_labels"),
                "support_label_source_quotes": cover_spec.get("support_label_source_quotes"),
                "support_labels_required": cover_spec.get("support_labels_required"),
                "source_rooted_labels_required": cover_spec.get("source_rooted_labels_required"),
                "label_anchor_targets": cover_spec.get("label_anchor_targets"),
                "deck_title_context_only": cover_spec.get("deck_title_context_only"),
                "deck_title_visible_forbidden": cover_spec.get("deck_title_visible_forbidden"),
                "visible_text_source_mode": cover_spec.get("visible_text_source_mode"),
                "visible_text_repeat_forbidden": False,
                "visible_text_slot_dedup_required": False,
                "repeated_source_fragment_forbidden": False,
                "visible_text_overlap_forbidden": False,
                "text_slot_assignment": {},
                "source_fragment_overlap_groups": [],
                "text_slot_conflict_resolutions": [],
                "source_text_ledger": (cover_spec.get("render_plan") or {}).get("source_text_ledger") or cover_spec.get("source_text_ledger"),
                "speech_clauses": [],
                "valid_clause_count": 0,
                "visible_text_density_target": 0,
                "visible_text_density_actual": 0,
                "visible_text_density_required": False,
                "density_gap_reason": "",
                "parallel_items_must_show": [],
                "formula_or_equation_must_show": False,
                "label_module_required": False,
                "label_module_targets": cover_spec.get("label_anchor_targets") or [],
                "label_visual_pairing_required": False,
                "micro_visual_anchor_required": False,
                "module_block_count_target": 0,
                "cover_accent_blocks_min": cover_spec.get("cover_accent_blocks_min"),
                "cover_accent_blocks_max": cover_spec.get("cover_accent_blocks_max"),
                "cover_accent_blocks_total": cover_spec.get("cover_accent_blocks_total"),
                "role_action_tags": cover_spec.get("role_action_tags"),
                "role_expression_tags": cover_spec.get("role_expression_tags"),
                "expression_guidance": cover_spec.get("expression_guidance"),
                "action_guidance": cover_spec.get("action_guidance"),
                "composition_guidance": cover_spec.get("composition_guidance"),
                "title_zone": cover_spec.get("title_zone"),
                "source_text_only_visual_mode": cover_spec.get("source_text_only_visual_mode"),
                "inferred_visuals_forbidden": cover_spec.get("inferred_visuals_forbidden"),
                "role_count_min": cover_spec.get("role_count_min"),
                "role_count_max": cover_spec.get("role_count_max"),
                "role_usage_mode": cover_spec.get("role_usage_mode"),
                "role_density_preference": cover_spec.get("role_density_preference"),
                "role_count_decision_mode": cover_spec.get("role_count_decision_mode"),
                "role_count_target": cover_spec.get("role_count_target"),
                "multi_role_required": cover_spec.get("multi_role_required"),
                "multi_role_trigger_type": cover_spec.get("multi_role_trigger_type"),
                "role_distribution_brief": cover_spec.get("role_distribution_brief"),
                "role_slot_assignments": cover_spec.get("role_slot_assignments"),
                "same_page_role_pose_distinct_required": cover_spec.get("same_page_role_pose_distinct_required"),
                "single_role_required": cover_spec.get("single_role_required"),
                "role_action_match_required": cover_spec.get("role_action_match_required"),
                "role_action_match_basis": cover_spec.get("role_action_match_basis"),
                "role_action_family": cover_spec.get("role_action_family"),
                "role_expression_family": cover_spec.get("role_expression_family"),
                "role_action_intent": cover_spec.get("role_action_intent"),
                "role_expression_intent": cover_spec.get("role_expression_intent"),
                "role_pose_brief": cover_spec.get("role_pose_brief"),
                "role_prop_intent": cover_spec.get("role_prop_intent"),
                "role_framing_intent": cover_spec.get("role_framing_intent"),
                "role_position_intent": cover_spec.get("role_position_intent"),
                "hair_expression_mode": cover_spec.get("hair_expression_mode"),
                "render_signature": cover_spec.get("render_signature"),
                "role_pose_key": cover_spec.get("role_pose_key"),
                "role_pose_family": cover_spec.get("role_pose_family"),
                "role_pose_repeat_forbidden": cover_spec.get("role_pose_repeat_forbidden"),
                "global_render_signature_unique_required": cover_spec.get("global_render_signature_unique_required"),
                "mic_pose_limited_once": cover_spec.get("mic_pose_limited_once"),
                "prop_signature": cover_spec.get("prop_signature"),
                "allowed_role_framings": cover_spec.get("allowed_role_framings"),
                "action_fallback_forbidden": cover_spec.get("action_fallback_forbidden"),
                "action_reference_optional": cover_spec.get("action_reference_optional"),
                "reserved_zone_enabled": cover_spec.get("reserved_zone_enabled"),
                "reserved_zone_scope": cover_spec.get("reserved_zone_scope"),
                "reserved_zone_size_cm": cover_spec.get("reserved_zone_size_cm"),
                "reserved_zone_side_ratio_of_height": cover_spec.get("reserved_zone_side_ratio_of_height"),
                "reserved_zone": cover_spec.get("reserved_zone"),
                "reserved_zone_rules": cover_spec.get("reserved_zone_rules"),
                "role_face_anchor_image": cover_spec.get("role_face_anchor_image") or (str(face_anchor_ref["file_path"]) if face_anchor_ref else ""),
                "role_action_reference_image": cover_spec.get("role_action_reference_image") or (str(action_ref["file_path"]) if action_ref else ""),
                "role_action_reference_reason": cover_spec.get("role_action_reference_reason") or action_reason or (action_ref.get("name", "") if action_ref else ""),
                "quality_reference_image": cover_spec.get("quality_reference_image") or str(QUALITY_REFERENCE_IMAGE.resolve()),
                "quality_reference_sha256": cover_spec.get("quality_reference_sha256") or file_sha256(QUALITY_REFERENCE_IMAGE),
                "role_reference_strategy": "anchor-plus-semantic-action",
                "prompt_file": str(cover_prompt_paths[cover_spec["cover_type"]]),
                "output_image": cover_spec["output_image"],
                "output_image_required": True,
                "archive_writeback_required": True,
                "delivery_mode": "direct-or-copy-then-clean",
            }
            cover_item.update(build_reference_lock_metadata())
            cover_item["cover_text_mode"] = cover_spec.get("cover_text_mode", "source-labels")
            cover_item["render_plan"] = cover_spec.get("render_plan") or build_render_plan(cover_spec, is_cover=True)
            cover_item["visual_blueprint"] = cover_item["render_plan"]["visual_blueprint"]
            cover_item["visual_blueprint_hash"] = cover_item["visual_blueprint"]["content_hash"]
            cover_item["text_overlay_plan"] = cover_spec.get("text_overlay_plan") or build_text_overlay_plan(cover_spec, is_cover=True)
            cover_item["text_overlay_plan_file"] = cover_spec.get("text_overlay_plan_file") or ""
            cover_item["role_face_anchor_sha256"] = file_sha256(cover_item.get("role_face_anchor_image"))
            cover_item["role_action_reference_sha256"] = file_sha256(cover_item.get("role_action_reference_image"))
            cover_items.append(cover_item)
    handoff = {
        "mode": "codex",
        "contract_version": CONTRACT_VERSION,
        "reserved_zone_contract": {
            "body_pages": {
                "reserved_zone_enabled": True,
                "reserved_zone_scope": "body-page-only",
                "reserved_zone_size_cm": RESERVED_ZONE_SIZE_CM,
                "reserved_zone_side_ratio_of_height": RESERVED_ZONE_SIDE_RATIO_OF_HEIGHT,
                "pixel_formula": "side_px = round(image_height * 3 / 19.05)",
                "pixel_zone_formula": "zone = [0, image_height - side_px, side_px, image_height]",
            },
            "covers": {
                "reserved_zone_enabled": False,
                "reserved_zone_scope": "none",
                "reserved_zone": None,
            },
        },
        "reserved_zone_export_normalization": {
            "enabled": True,
            "stage": "before-output-audit",
            "scope": "body-pages-bottom-left-declared-no-draw-zone-only",
            "operation": "overwrite only declared no-draw pixels with the page background_color exact RGB",
            "text_overlay_forbidden": True,
            "semantic_or_drawing_edit_forbidden": True,
            "outside_zone_pixels_must_remain_unchanged": True,
            "renderer_input_and_final_png_hashes_required": True,
            "script": "scripts/normalize_reserved_zone.py",
        },
        "workdir": str(workdir),
        "work_package_dir": str(workdir),
        "archive_dir": str(page_paths[0].parent if page_paths else ""),
        "final_archive_dir": str(page_paths[0].parent if page_paths else ""),
        "output_image_required": True,
        "archive_writeback_required": True,
        "delivery_mode": "direct-or-copy-then-clean",
        "pre_render_audit_required": True,
        "pre_render_audit_status": "pending",
        "pre_render_audit_receipt": "",
        "render_blocked_until_preflight_approved": True,
        "selected_pages": selected_pages,
        "full_run": is_full_run,
        "render_plan_version": RENDER_PLAN_VERSION,
        "render_profile": "creative",
        "text_overlay_version": TEXT_OVERLAY_VERSION,
        "attempt_ledger_file": str(workdir / ATTEMPT_LEDGER_FILENAME),
        "render_state_file": str(workdir / "render-state.json"),
        "render_recovery_controller": "scripts/render_recovery_loop.py",
        "auto_recovery_required": True,
        "unlimited_single_asset_retry_required": True,
        "archive_evidence_dir": str((page_paths[0].parent / "evidence") if page_paths else ""),
        "pages": items,
        "covers": cover_items,
    }
    handoff.update(build_reference_lock_metadata())
    handoff_path = workdir / "codex-handoff.json"
    workflow_path = workdir / "codex-workflow.txt"
    write_json(handoff_path, handoff)
    workflow = (
        build_pre_render_audit_block("pending", None, ["工作包已生成，必须先通过小审预审后才能开始正式生图"])
        + "\n"
        "Codex 出图工作流\n"
        "阶段 0：工作包预审门禁\n"
        "0. 先运行视觉工作包预审；只有拿到 approved 预审回执后，才允许进入后续正式生图。\n"
        "0.1. 预审未通过时，禁止生成任何 page-*.png 或 cover-*.png；必须先修工作包，再重新预审。\n"
        "阶段 1：参考图接入校验\n"
        "1. 正式出图前先确认 config/skill-config.json 里的 archive_root 已显式配置；默认工作包固定写入 `outputs/<选题名>-work`，正式成品固定写入 `archive_root/<选题名>/`，若 archive_root 为空且会触发 skill 相邻目录回退，必须先停止并修正配置，再继续正式出图。\n"
        "2. 出图前先核对 codex-handoff.json 顶层的 reference_lock_required、renderer_must_attach_reference_images、identity_reference_mode、identity_baseline_image、quality_reference_required、fixed_identity_traits_required、secondary_identity_sources_forbidden、required_reference_inputs、fail_if_reference_images_not_actually_attached、codex_only_rendering_required、external_api_rendering_forbidden、allowed_render_mode。\n"
        "2. 每次新文案正式出图前，都必须重新让模型真实看到 role_face_anchor_image 这张主脸锚点图；不能只复用上一次会话记忆。\n"
        f"2.1 每次还必须真实查看并挂载合格成图品质参考 {QUALITY_REFERENCE_IMAGE.resolve()}；它只约束标题已填、图文一体、信息密度和手绘模块结构，严禁复制案例文字或语义对象。\n"
        "3. 固定人物特征文字只作为辅助稳定器，帮助锁定黑框眼镜、暖肤色、背头侧分黑发、偏长椭圆脸、白西装黑内搭、全身时蓝色牛仔裤和白鞋、手绘卡通线稿风；这些文字不能替代主脸锚点图，也不能变成第二身份源。\n"
        "4. 左上正脸主脸模板负责锁定额头高度、发际线方向、五官比例、眼镜大小、脸宽脸长比和年龄感；动作参考单图只允许提供角度和动作变化边界，不得重新定义主脸。\n"
        "5. 本流程禁止真人锚点照、姿态库身份图、第二角色参考图进入正式身份链路；人物身份只审核 role_face_anchor_image 这张主脸锚点图。\n"
        "6. 只看到参考图路径、只把参考要求写进文字 prompt、只抽取人物特征文字，或无法确认主脸锚点图是否真的被模型使用，全部视为未通过校验。\n"
        "7. 若当前工具只支持文字 prompt、不支持真实参考图输入，必须立即停止并汇报：当前执行环境无法真实挂载角色主脸锚点参考图，本次停止生成，未进入正式出图链路。\n"
        "8. 不允许先出图再人工挑一张像的，也不允许改用泛化人物继续生成。\n"
        "9. 同一页若出现多个同角色小人、不同景别或不同动作，也必须继续使用同一张主脸锚点图锁定；若当前执行端做不到稳定锁定，必须先降为单主角色或单次校准，不允许硬出整页。\n"
        "阶段 2：逐页最终图生成与审核\n"
        "10. 只有通过阶段 1 校验后，才按 codex-handoff.json 中的 page_index 顺序逐页生成图文一体最终 PNG；先写入工作包 final-review/，不得创建无文字候选分支。\n"
        "11. 每生成一页，必须先回头对照主脸锚点图确认是不是同一个人；先做左上正脸主模板一致性判定，再核对眼镜、肤色、发型、脸型、年龄感和白西装黑内搭。不一致就只重做该页。\n"
        "12. 每张原生 PNG 必须一次包含标题、2–5 张主卡、每张 1–3 条证据短句、source_text_ledger 全部原文标签、已填文字的手绘模块卡、每条标签对应的小场景/对象关系和嵌入人物。禁止后续叠字、空白标题栏、空白主卡/证据槽、伪文字和臆想中文。\n"
        "12.1 所有可见中文必须等于本页 source_text_ledger；图标、坑位、箭头、图表和路牌不得自造中文。纯人物插画、无文字图、图文错配或重复画面必须退回当前页重画。\n"
        "12.2 正文页原生 PNG 写入 final-review/ 后、建立任何成图审核表前，必须运行 python scripts/normalize_reserved_zone.py --workdir <workdir>。该受控导出归一化只能把已声明左下 3cm 无绘制区写为 background_color 精确 RGB；禁止叠字、绘制、语义改图或改动禁绘区外像素，并在 evidence/reserved-zone-normalization.json 同时记录原生输入与最终 PNG 哈希。\n"
        "12.3 再运行 audit_visual_outputs.py <workdir>/final-review --create-review-template，交由小审逐主卡、逐证据填写实际可见中文及对象关系；再运行同脚本生成审核回执。缺少 evidence/visual-output-semantic-review.json、禁绘区归一化证据、未逐主卡和逐证据复核、或回执非 approved，均不得交付。\n"
        "13. 受控发布只接收 final-review/ 中通过成图审核且哈希绑定回执的原生最终 PNG。\n"
        "13.1 默认按单文件粒度清理缓存：只删除本轮刚刚归档成功的那一张缓存图，不清空整包缓存目录，也不删除其他历史缓存文件。\n"
        "14. 若当前平台既不能直接写正式目录，也不能先得到可复制的中间 PNG，才视为真正阻塞并立即停止。\n"
        "15. 仅存在于临时生成目录、缓存目录、对话附件或 C 盘缓存中的图片都不算完成；工作包目录和中间图片目录都不是最终交付目录。\n"
        "16. 如果这次是整套完整出图，在正文页全部归档到正式目录后，还要继续生成 cover-3x4.png 和 cover-4x3.png。\n"
        "17. 禁止脱离 handoff 另起一套临时手写 prompt 直接出图。\n"
        "18. 先做 1-2 页校准风格，再继续后续页面；试投页必须先通过左上正脸主模板一致性，再看构图。\n"
        "19. 页面实际可见中文只认 handoff 里的 source_text_ledger；其他语义分析字段只用于追溯和构图，不得自行渲染。正文页里的 deck_title 只做上下文，不得渲染成可见文字。\n"
        "19.1. 所有 cue_phrases、flow_labels、support_labels 都必须能直接回指到当前页 title + body 的原文片段；不允许同义改写、概括命名、结果延伸或补充解释。\n"
        "20. 正文页左下角 3cm × 3cm 只能保留自然连续的纯背景，不画框、不画格、不画占位提示；按 16:9 标准页高 19.05cm 换算，检测公式为 side_px = round(image_height * 3 / 19.05)。\n"
        "20.1. cover-3x4.png 与 cover-4x3.png 不设置左下角禁绘区，不得继承正文页 3cm 留白合同；封面只按完整画布构图。\n"
        "21. 页面允许同时使用非人物插画、结构示意图、流程图、箭头和关系图，但这些元素必须直接回指到原文，不得额外补出金币、火箭、收入回报、办公室工作等原文未说的东西。\n"
        "22. 人物必须先嵌入主结构再谈造型，不能作为画外独立主持人站在空白侧边；单页人物数量必须服从 handoff 里的 role_count_target 和 multi_role_required，不能擅自回落成单人物，也不能擅自加人。\n"
        "22.1. 若 multi_role_required = true，必须按 role_slot_assignments 把同一角色的多个实例分配到不同结构槽位，不能做同姿态复制摆人。\n"
        "22.2. 正文小模块必须统一使用 handdrawn-card-icon-module（手绘卡片式图标模块）：卡片/节点容器 + 手绘小图标/小场景 + 原文短标签 + 少量扁平色块；不得出现裸线条图标散落、UI 扁平图标、写实小插画、贴纸风或 3D 图标，若整套模块风格漂移必须重做。\n"
        "23. 同一选题内，全文具体可见姿态不得重复；不仅近邻页不能重复，整篇所有正文页和封面都不能复用同一个托下巴、拿麦讲话、单手指向、双手阻挡之类的具体演法。\n"
        "23.1. 拿麦讲话属于高频风险姿态，整篇最多允许 1 次；如果当前页或封面再次回落到拿麦姿态，必须重做该张图，不能继续带入下一张。\n"
        "23.2. 若 handoff 的 render_signature 与其他页或封面重复，或生成结果回看时与已用演法明显重复，必须立即重做当前页；动作参考库只做辅助，不再作为库存门禁。\n"
        "23.3. 正文页默认压低 large-focus，优先 small-accent 或 medium-support，继续参考 handoff 里的 role_variation_guard 和 role_variation_reason。\n"
        f"24. 最终交付图只认当前配置归档根目录下的选题目录：{handoff['archive_dir']}，不认任何临时目录或缓存图。\n"
        "25. 即使只是单独重做某页、单独重做某张封面，或单独生成某一张图片，也必须最终归档到该选题目录里的正式文件名；若先产生中间图，复制并校验正式文件存在后必须删除这张对应缓存图。\n"
        "26. 如需只重做某页，重新运行 build_ip_ppt.py 并传 --pages。\n"
        "27. 只有当本次目标页和本次目标封面都已出现在正式归档目录，且中间图片已清理，这一套图才算生成完成。\n"
        "28. 只有在用户明确要求 PPT 时，才在全部目标页都已写回 output_image 后，再传 --assemble-only 和 --out 重新装配。\n"
    )
    write_text(workflow_path, workflow)
    face_anchor_image = pathlib.Path(
        next(
            (
                item.get("role_face_anchor_image")
                for item in items
                if item.get("role_face_anchor_image")
            ),
            "",
        )
    )
    prompt_path, job_path = write_codex_thread_job_files(
        deck_title=str(next((spec.get("deck_title") for spec in specs if spec.get("deck_title")), "") or specs[0].get("page_title") or "").strip(),
        workdir=workdir,
        archive_dir=page_paths[0].parent if page_paths else workdir,
        handoff_path=handoff_path,
        specs_path=workdir / "pages-spec.json",
        workflow_path=workflow_path,
        reference_image=face_anchor_image,
        selected_pages=selected_pages,
        include_covers=is_full_run,
    )
    handoff["codex_render_thread_prompt_file"] = str(prompt_path)
    handoff["codex_render_job_file"] = str(job_path)
    handoff["codex_render_thread_required"] = True
    handoff["codex_render_current_thread_allowed"] = True
    write_json(handoff_path, handoff)
    return handoff_path, workflow_path, prompt_path, job_path


def initialize_attempt_ledger(workdir: pathlib.Path, handoff_path: pathlib.Path) -> pathlib.Path:
    """Record per-asset retries without allowing a retry to mutate its blueprint."""
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    assets = []
    for item in list(handoff.get("pages") or []) + list(handoff.get("covers") or []):
        asset_id = f"page-{int(item['page_index']):02d}" if item.get("page_index") else str(item.get("cover_type") or "")
        prompt_path = pathlib.Path(str(item.get("prompt_file") or ""))
        assets.append({
            "asset_id": asset_id,
            "visual_blueprint_hash": str(item.get("visual_blueprint_hash") or ""),
            "prompt_sha256": file_sha256(prompt_path),
            "status": "pending",
            "attempts": [],
        })
    ledger_path = workdir / ATTEMPT_LEDGER_FILENAME
    write_json(ledger_path, {
        "schema": "ip-visual-attempt-ledger-v4.1",
        "contract_version": CONTRACT_VERSION,
        "retry_policy": "single-asset-unlimited-until-approved",
        "assets": assets,
    })
    # The ledger remains the sole mutable truth.  render-state.json is only a
    # projection for the workbench/Desktop bridge and is regenerated whenever
    # the controller changes the ledger.
    from render_recovery_loop import initialize as initialize_recovery_controller
    initialize_recovery_controller(workdir)
    return ledger_path


def record_retry_attempt(
    ledger_path: pathlib.Path,
    asset_id: str,
    *,
    audit_status: str,
    reason: str,
    correction_instruction: str,
) -> None:
    """Route an audited retry through the durable controller, never a raw edit."""
    from render_recovery_loop import record_asset
    record_asset(
        ledger_path.parent,
        asset_id,
        "approved" if audit_status == "approved" else "rejected",
        reason=reason.strip(),
        correction=correction_instruction.strip(),
        input_hash="",
        receipt="",
    )


def apply_deck_title(pages: list[dict[str, Any]], deck_title: str | None) -> list[dict[str, Any]]:
    if not pages:
        return pages
    if not deck_title:
        return pages
    first = pages[0]
    if first.get("title_from_bold"):
        first["deck_title"] = deck_title
        for idx in range(1, len(pages)):
            pages[idx]["deck_title"] = deck_title
        return pages
    original_title = first["title"]
    hook = original_title if original_title != deck_title else ""
    updated = dict(first)
    updated["deck_title"] = deck_title
    updated["title"] = deck_title
    if hook:
        updated["page_hook"] = hook
    pages[0] = updated
    for idx in range(1, len(pages)):
        pages[idx]["deck_title"] = deck_title
    return pages


def normalize_page_images(page_paths: list[pathlib.Path], width: int, height: int) -> None:
    for page_path in page_paths:
        with Image.open(page_path) as img:
            if img.size == (width, height):
                continue
            rgb = img.convert("RGB")
            resized = rgb.resize((width, height))
            resized.save(page_path)


def main() -> None:
    ap = argparse.ArgumentParser(description="把中文文案生成成带固定角色的整页图片；优先支持 #/##/### 标题手动分页，无显式标题时自动分页")
    ap.add_argument("--input", required=True, help="已定稿中文文案路径；v4.1 不复绑历史工作包")
    ap.add_argument("--out", default=None, help="可选 PPTX 路径；默认不输出 PPT，只有在 --assemble-only 时才需要")
    ap.add_argument("--character", default=None, help="显式指定角色 slug")
    ap.add_argument("--render-mode", choices=["codex"], default="codex", help="只允许 codex：生成给 Codex 使用的出图工作清单")
    ap.add_argument("--workdir", default=None, help="可选工作包目录；默认固定为 SKILL_ROOT/outputs/<选题名>-work")
    ap.add_argument("--pages", default=None, help="可选页码范围，例如 1-2,4,6-7；用于只重做部分页面")
    ap.add_argument("--cover-text-mode", choices=["source-labels", "title-only"], default="source-labels", help="封面配字：默认主标题加最多两条原文短标签；title-only 仅显示标题")
    ap.add_argument("--assemble-only", action="store_true", help="只根据现有 pages/*.png 装配 PPT，不重新生成规格与 prompt")
    args = ap.parse_args()

    out_path = pathlib.Path(args.out).expanduser().resolve() if args.out else None
    cfg = load_config()
    character_slug = resolve_default_character(args.character)
    role = load_character(character_slug)
    if not QUALITY_REFERENCE_IMAGE.is_file():
        raise FileNotFoundError(f"缺少合格成图品质参考，禁止生成工作包: {QUALITY_REFERENCE_IMAGE}")
    archive_root = resolve_archive_root(cfg)
    input_path = pathlib.Path(args.input).expanduser().resolve()
    if not input_path.is_file():
        raise FileNotFoundError(f"输入文案不存在: {input_path}")
    raw_text = input_path.read_text(encoding="utf-8")
    deck_title, content_text = extract_deck_title(raw_text)

    archive_dir = resolve_archive_dir(deck_title, input_path, archive_root)
    outputs_root = SKILL_ROOT / "outputs"

    if args.workdir:
        workdir = pathlib.Path(args.workdir).expanduser().resolve()
    else:
        title_folder = resolve_title_folder_name(deck_title, input_path)
        workdir = (outputs_root / f"{title_folder}-work").resolve()
    prompts_dir = ensure_dir(workdir / "prompts")
    pages_dir = archive_dir
    specs_path = workdir / "pages-spec.json"

    if args.assemble_only:
        if out_path is None:
            raise ValueError("--assemble-only 时必须传 --out；默认最终交付只输出页面图，不自动输出 PPT")
        specs = load_specs_from_workdir(workdir)
        page_paths = [pages_dir / f"page-{int(spec['page_index']):02d}.png" for spec in specs]
        ensure_archive_writeback_complete(page_paths, pages_dir)
        normalize_page_images(
            page_paths,
            int(cfg.get("default_slide_width_px", 1600)),
            int(cfg.get("default_slide_height_px", 900)),
        )
        build_ppt_from_pages(page_paths, out_path)
        print(f"已根据现有页面图片装配 PPT: {out_path}")
        print(json.dumps({
            "default_character": character_slug,
            "pages": len(specs),
            "workdir": str(workdir),
            "pages_spec": str(specs_path),
            "archive_root": str(archive_root),
            "archive_dir": str(archive_dir),
            "mode": "assemble-only",
        }, ensure_ascii=False, indent=2))
        return

    pages = parse_pages(content_text)
    pages = apply_deck_title(pages, deck_title)
    total_pages = len(pages)
    for idx, page in enumerate(pages, start=1):
        page["is_last_page"] = idx == total_pages
    specs = [build_page_spec(page, len(pages), pages) for page in pages]
    specs = attach_cross_page_motif_guards(specs)
    specs = apply_role_variation_across_specs(specs)
    attach_page_role_chain(specs, role)
    for spec in specs:
        spec["render_plan"] = build_render_plan(spec)
        spec["visual_blueprint"] = spec["render_plan"]["visual_blueprint"]
        spec["source_text_ledger"] = spec["render_plan"]["source_text_ledger"]
        spec["text_overlay_plan"] = build_text_overlay_plan(spec)
    cover_outputs = build_cover_outputs(specs, deck_title, archive_dir, input_path, args.cover_text_mode)
    attach_cover_role_chain(cover_outputs, specs, role)
    for cover_spec in cover_outputs:
        cover_spec["role_face_anchor_sha256"] = file_sha256(cover_spec.get("role_face_anchor_image"))
        cover_spec["role_action_reference_sha256"] = file_sha256(cover_spec.get("role_action_reference_image"))
        cover_spec["render_plan"] = build_render_plan(cover_spec, is_cover=True)
        cover_spec["visual_blueprint"] = cover_spec["render_plan"]["visual_blueprint"]
        cover_spec["source_text_ledger"] = cover_spec["render_plan"]["source_text_ledger"]
        cover_spec["text_overlay_plan"] = build_text_overlay_plan(cover_spec, is_cover=True)
    overlays_dir = ensure_dir(workdir / "overlays")
    for spec in specs:
        overlay_path = overlays_dir / f"page-{int(spec['page_index']):02d}.json"
        write_json(overlay_path, spec["text_overlay_plan"])
        spec["text_overlay_plan_file"] = str(overlay_path)
    for cover_spec in cover_outputs:
        overlay_path = overlays_dir / f"{cover_spec['cover_type']}.json"
        write_json(overlay_path, cover_spec["text_overlay_plan"])
        cover_spec["text_overlay_plan_file"] = str(overlay_path)
    write_json(specs_path, {
        "contract_version": CONTRACT_VERSION,
        "reserved_zone_contract": {
            "body_pages": {
                "reserved_zone_enabled": True,
                "reserved_zone_scope": "body-page-only",
                "reserved_zone_size_cm": RESERVED_ZONE_SIZE_CM,
                "reserved_zone_side_ratio_of_height": RESERVED_ZONE_SIDE_RATIO_OF_HEIGHT,
                "pixel_formula": "side_px = round(image_height * 3 / 19.05)",
                "pixel_zone_formula": "zone = [0, image_height - side_px, side_px, image_height]",
            },
            "covers": {
                "reserved_zone_enabled": False,
                "reserved_zone_scope": "none",
                "reserved_zone": None,
            },
        },
        "reserved_zone_export_normalization": {
            "enabled": True,
            "stage": "before-output-audit",
            "scope": "body-pages-bottom-left-declared-no-draw-zone-only",
            "operation": "overwrite only declared no-draw pixels with the page background_color exact RGB",
            "text_overlay_forbidden": True,
            "semantic_or_drawing_edit_forbidden": True,
            "outside_zone_pixels_must_remain_unchanged": True,
            "renderer_input_and_final_png_hashes_required": True,
            "script": "scripts/normalize_reserved_zone.py",
        },
        "pages": specs,
        "cover_outputs": cover_outputs,
    })
    ensure_visual_semantic_review_scaffold(workdir, specs_path, specs)
    selected_pages = parse_page_selection(args.pages, len(specs))
    is_full_run = len(selected_pages) == len(specs)

    prompt_paths: list[pathlib.Path] = []
    page_paths: list[pathlib.Path] = []
    for spec in specs:
        idx = int(spec["page_index"])
        prompt_path = prompts_dir / f"page-{idx:02d}.md"
        page_path = pages_dir / f"page-{idx:02d}.png"
        if idx in selected_pages:
            write_text(prompt_path, build_prompt(spec, role))
        prompt_paths.append(prompt_path)
        page_paths.append(page_path)
    cover_prompt_paths: dict[str, pathlib.Path] = {}
    if is_full_run:
        for cover_spec in cover_outputs:
            cover_prompt_path = prompts_dir / f"{cover_spec['cover_type']}.md"
            write_text(
                cover_prompt_path,
                build_cover_prompt(
                    cover_spec,
                    role,
                ),
            )
            cover_prompt_paths[cover_spec["cover_type"]] = cover_prompt_path

    handoff_path, workflow_path, thread_prompt_path, thread_job_path = build_codex_handoff(
        specs=specs,
        cover_outputs=cover_outputs,
        selected_pages=selected_pages,
        workdir=workdir,
        prompt_paths=prompt_paths,
        page_paths=page_paths,
        cover_prompt_paths=cover_prompt_paths,
        role=role,
    )
    initialize_attempt_ledger(workdir, handoff_path)
    recovery_metadata = {
        "enabled": True,
        "attempt_ledger": str(workdir / ATTEMPT_LEDGER_FILENAME),
        "render_state": str(workdir / "render-state.json"),
        "controller": str(SKILL_ROOT / "scripts" / "render_recovery_loop.py"),
        "policy": "audit-rejected-and-external-errors-must-continue",
    }
    handoff_payload = json.loads(handoff_path.read_text(encoding="utf-8"))
    handoff_payload["render_recovery"] = recovery_metadata
    write_json(handoff_path, handoff_payload)
    job_payload = json.loads(thread_job_path.read_text(encoding="utf-8"))
    job_payload["render_recovery"] = recovery_metadata
    job_payload["execution_entrypoint"] = "persistent-recovery-controller"
    job_payload["resume_instruction"] = "Read render-state.json, run render_recovery_loop.py --workdir <workdir> next, and execute only its next_action. Never write blocked for audit rejection or external recovery."
    write_json(thread_job_path, job_payload)
    refresh_visual_semantic_review_scaffold(
        workdir,
        specs_path,
        handoff_path,
        specs,
        prompt_paths,
    )
    print(f"已生成 Codex 出图工作清单: {handoff_path}")
    print(f"已生成 Codex 操作说明: {workflow_path}")
    preflight_receipt, preflight_receipt_path = run_visual_preflight_audit(workdir)
    from render_recovery_loop import record_preflight
    recovery_state = record_preflight(workdir, preflight_receipt_path)
    review_dir = workdir / "final-review"
    evidence_dir = prepare_review_evidence_after_preflight(workdir, review_dir, preflight_receipt)
    preflight_approved = preflight_receipt.get("status") == "approved"

    print(json.dumps({
        "default_character": character_slug,
        "pages": len(specs),
        "selected_pages": selected_pages,
        "covers": [cover["cover_type"] for cover in cover_outputs] if is_full_run else [],
        "workdir": str(workdir),
        "work_package_dir": str(workdir),
        "pages_spec": str(specs_path),
        "codex_render_thread_prompt": str(thread_prompt_path),
        "codex_render_job": str(thread_job_path),
        "archive_root": str(archive_root),
        "archive_dir": "",
        "final_archive_dir": "",
        "archive_target_pending_preflight": str(archive_dir),
        "review_dir": str(review_dir) if preflight_approved else "",
        "pre_render_audit_status": preflight_receipt.get("status"),
        "pre_render_audit_receipt": str(preflight_receipt_path),
        "render_recovery_state": str(workdir / "render-state.json"),
        "render_recovery_next_action": recovery_state.get("state"),
        "archive_evidence_dir": str(evidence_dir) if evidence_dir else "",
        "mode": args.render_mode,
        "output": "images-only",
    }, ensure_ascii=False, indent=2))
    if preflight_receipt.get("status") != "approved":
        # A rejected preflight is a controller input, not a process-level
        # terminal failure. The next Desktop recovery turn rebuilds or repairs
        # from the durable state without relaxing the audit gate.
        print("视觉预审未通过；已写入不断线恢复控制器，等待下一步修复。")


if __name__ == "__main__":
    main()
