#!/usr/bin/env python3
"""Create a V14 corrective candidate whose structure-three evidence is processing-library-only."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
LIB="02_资产中心/02_处理库"
VIEW=f"{LIB}/01_观点_内容模块/01_推荐好书/01_个人IP金句模块.md"
PAIN=f"{LIB}/02_痛点_内容模块（会员专享）/内容与流量/选题_内容_文案/PAIN-A02-NO-CONTEXT-AUDIENCE-MARK_短视频随机闯入用户生活，开头却没有人群印记.md"
MIS=f"{LIB}/03_误区_内容模块/01_推荐好书/《疯传》_07_错误观点：传播效果差还只会继续堆干货.md"
SOL=f"{LIB}/04_解决方案_内容模块/01_推荐好书/《金字塔原理大全集》_01_表达前怎么先把核心结论最前面.md"
raise SystemExit("旧思考卡修复脚本已退役；结构三只能从 V12 案例卡索引重新选择正式 CASE 资产。")

def source(path:str,kind:str,section:str)->dict:
    absolute=ROOT/path
    return {"path":path,"sha256":hashlib.sha256(absolute.read_bytes()).hexdigest(),"framework_type":kind,"section":section}
def row(ident:str,kind:str,claim:str,lines:list[str],path:str,section:str)->dict:
    return {"core_framework_id":ident,"framework_label":kind,"core_claim":claim,"evidence_chain":[{"text":line} for line in lines],"processing_sources":[source(path,kind.rstrip("一二三四五六七八九十"),section)]}
def main()->int:
    parser=argparse.ArgumentParser();parser.add_argument("--input",type=Path,required=True);parser.add_argument("--output",type=Path,required=True);parser.add_argument("--preset",choices=("GHX-001","HKX-001"),required=True);args=parser.parse_args()
    data=json.loads(args.input.read_text(encoding="utf-8")); plan=data["structures"]["structure_three"]
    if args.preset=="GHX-001":
        rows=[
          row("CF-F01","观点","对陌生观众而言，内容要先给出可判断的价值，才有被继续理解的机会。",["信息能否被接住，取决于它是否先提供一个让人愿意继续交流的抓手。","先交付一个清楚判断，再解释理由，能把等待变成有回报的阅读。"],VIEW,"《弱传播：舆论世界的哲学》"),
          row("CF-F02","痛点","短视频随机闯入用户生活，开头没有明确的人群和收益印记时，相关观众也很难停下来。",["短视频缺少前后语境，开端需要让目标用户立即识别“这条和我有关”。","没有人群印记的开场，无法在浏览池筛出真正需要这条内容的人。"],PAIN,"角度 1"),
          row("CF-F03","误区一","第一个误区，是以为把更多知识堆在前面，就自然能换来传播和停留。",["实用价值不是信息越多越好，而是要让人看得见、说得出。","密集罗列而没有可复述抓手，只会加大阅读负担。"],MIS,"误区1"),
          row("CF-F04","误区二","第二个误区，是只把价值写成抽象大词，却不给观众一眼可见的具体抓手。",["有用的信息需要被做成可见、可指、可复述的形式。","没有把价值包装成抓手，用户难以带走或转述。"],MIS,"误区2"),
          row("CF-F05","解决方案","把价值前置写成“先给结论，再给理由”：开头先交付观众要记住的那一句，再展开解释。",["先写出只能留一句时要让观众记住的结论。","第一句直接给结论，理由随后展开，让观众先拿到答案再决定是否继续。"],SOL,"步骤1-3"),]
    else:
        rows=[
          row("CF-F01","痛点","短视频没有前后语境；干货开头若没有指出谁能拿走什么，用户难以判断是否与自己有关。",["随机触达的短视频需要开端携带人群印记。","没有相关性标记，真正需要内容的人也难以在浏览中停下。"],PAIN,"角度 1"),
          row("CF-F03","误区一","第一个误区，是把“多堆干货”当成内容有用、就会被传播的充分条件。",["实用价值需要可谈论的包装，不是信息量越大越有效。","只增加密度而不提供可复述抓手，会增加读者负担。"],MIS,"误区1"),
          row("CF-F04","解决方案","干货先交付一句可独立成立的结论，再用理由和动作展开，观众先拿到答案。",["先写下最想让观众记住的一句结论。","把结论放在第一句，理由跟在后面，让听众先收到答案。"],SOL,"步骤1-3"),
          row("CF-F05","案例","内容生产可先按框架列问题和观点，再配方案，最后补故事与现象，避免从任意模块盲拼。",["复盘中发现任意组合四类模块会造成变量爆炸。","采用先观点、再方案、最后故事的顺序后，单条内容的决策点减少。"],CASE,"正文故事核"),
          row("CF-F06","误区二","第二个误区，是把系列或长内容理解为把同一类干货反复堆叠。",["信息若没有可见抓手和推进载体，重复增加只会提高阅读负担。","有用的内容需要被组织成可带走、可转述的单元。"],MIS,"误区1-3"),
          row("CF-F07","观点","短视频干货是否有用，不取决于讲得多，而取决于用户能否立刻看见、带走并复述一个具体价值。",["内容的价值必须能被接住和带出去，才不会停留在创作者的文档里。","可见、可指的实用信息比密集知识更容易被用户使用和传播。"],VIEW,"《弱传播：舆论世界的哲学》")]
    plan["core_frameworks"]=rows
    plan["asset_gap_note"]="**处理库检索缺口**：本轮所有非空结构三节点均已绑定处理库同类型模块；未使用选题表、对标拆解或策划说明作为出处。"
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return 0
if __name__=="__main__":raise SystemExit(main())
