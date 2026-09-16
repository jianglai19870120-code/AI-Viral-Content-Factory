"""V14 structure handoff: the benchmark contributes only ordered big frameworks."""
from __future__ import annotations
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from workflow.benchmark_cases import approved_case
from workflow.benchmark_structure_v3 import digest,parse_markdown

FORMAL={"观点","痛点","误区","解决方案","案例","推荐理由"}
# These labels are always support-only even though some include a formal type
# word (for example, “观点回扣”).  Resolve them before substring matching.
SUPPORT_ONLY={"开场","转场","观点回扣","行动引导"}
FRAMEWORK_FUNCTIONS={
    "开场":"用主题、对象或场景建立进入理由，并提出本文要解决的问题。",
    "观点":"提出全文需要证明的核心判断，并为后文建立理解坐标。",
    "痛点":"还原读者正在经历的场景、障碍或代价，说明问题为何值得解决。",
    "误区":"点破一个具体错误认知，解释它为何看似合理、为何不成立以及继续相信的代价。",
    "解决方案":"把前文判断落为最少充分、可执行且可验证的动作。",
    "案例":"用具体场景、行为和结果证明前文判断或方案。",
    "推荐理由":"说明目标读者当前成本，以及该选择能缩短的路径或获得的结果。",
    "转场":"承接前一框架的结论，明确指出接下来必须回答或推进的问题。",
    "观点回扣":"回扣前文核心判断，说明它如何被后续论证证实。",
    "行动引导":"基于全文判断给出可立即开始的收束动作，不引入新的核心结论。",
}
def formal_type(label:str)->str|None:
    normalized=label.strip()
    for name in SUPPORT_ONLY:
        if name in normalized:
            return None
    # 对标三列表可在内容类型前保留序号或说明，例如“第二点：误区”。
    # 只要名称包含一个正式内容家族词，即按该词映射；展示名称与 FNN 顺序不改。
    matches=[name for name in FORMAL if name in normalized]
    if len(matches)==1:
        return matches[0]
    return None
def framework_function(label:str,kind:str|None)->str:
    normalized=label.strip()
    for name,definition in FRAMEWORK_FUNCTIONS.items():
        suffix=normalized.removeprefix(name)
        if normalized==name or (suffix and all(x in '一二三四五六七八九十0123456789' for x in suffix)):
            return definition
    if kind:
        return FRAMEWORK_FUNCTIONS[kind]
    return f"完成“{normalized}”在全文中的承接、推进或收束功能，并与相邻 FNN 框架连贯衔接。"
def framework_rows(path:Path)->list[dict]:
    rows=[]; seen=set()
    for row in parse_markdown(path):
        if row['编号'] in seen:
            continue
        seen.add(row['编号'])
        name=row['大框架'];kind=formal_type(name)
        rows.append({'core_framework_id':f"CF-{row['编号']}",'framework_block_id':row['编号'],'framework_label':name,'framework_function':framework_function(name,kind),'formal_framework_type':kind,'asset_framework_type':kind})
    return rows
def build_handoff_v14(*,topic:str,benchmark_id:str,topic_table_binding:dict|None=None)->dict:
    case=approved_case(benchmark_id);benchmark=Path(case['breakdownPath']);frameworks=framework_rows(benchmark)
    # 只有正式处理库内容家族才是结构阶段可编辑的核心框架。开场、转场、
    # 行动引导等支撑段保留在交接元数据中，专供正文阶段生成，绝不进入结构一至四。
    cores=[row for row in frameworks if row['formal_framework_type'] in FORMAL]
    final_only=[dict(row)|{'generation_owner':'final-copy','generation_instruction':f"按“{row['framework_function']}”补足该非核心 FNN 框架；只使用相邻框架推进关系与已冻结核心内容，不得检索或复述对标原文、处理库或输入库。"} for row in frameworks if row['formal_framework_type'] is None]
    if not cores:raise ValueError('对标案例没有可映射到处理库的正式核心大框架')
    return {'schema':'copy-structure-handoff-v14','topic':topic,'benchmark_case_id':benchmark_id,'benchmark_path':str(benchmark.resolve()),'benchmark_sha256':digest(benchmark),'benchmark_audit_receipt':str(case['auditPath'].resolve()),'big_frameworks':frameworks,'core_frameworks':cores,'final_copy_only_frameworks':final_only,'topic_table_binding':topic_table_binding}
def build_candidate_v14(handoff_path:Path,authoring_path:Path,output:Path)->None:
    h=json.loads(handoff_path.read_text(encoding='utf-8'))
    if h.get('schema')!='copy-structure-handoff-v14':raise ValueError('仅接受 copy-structure-handoff-v14')
    authored=json.loads(authoring_path.read_text(encoding='utf-8'));plans=authored.get('structures') if isinstance(authored.get('structures'),dict) else authored
    expected=[str(x['core_framework_id']) for x in h['core_frameworks']];result={}
    for name in ('structure_one','structure_two','structure_three'):
        plan=plans.get(name) if isinstance(plans,dict) else None;rows=plan.get('core_frameworks') if isinstance(plan,dict) else None
        if not isinstance(rows,list) or [str(x.get('core_framework_id')) for x in rows]!=expected:raise ValueError(f'{name} 必须逐个覆盖已锁定的正式大框架')
        if name=='structure_three':
            for row in rows:
                if not isinstance(row,dict): continue
                has_content=bool(str(row.get('core_claim') or '').strip()); sources=row.get('processing_sources')
                if 'source_note' in row: raise ValueError('structure_three 禁止 source_note；出处只能来自处理库模块')
                if has_content and not isinstance(sources,list): raise ValueError('structure_three 的非空内容必须提供 processing_sources')
                if not has_content and sources: raise ValueError('structure_three 未命中时内容与出处必须同时留空')
        result[name]=plan
    result['structure_four']={'core_frameworks':[dict(row)|{'core_claim':'','evidence_chain':[],'solution_steps':[]} for row in h['core_frameworks']]}
    keys=('topic','benchmark_case_id','benchmark_path','benchmark_audit_receipt','benchmark_sha256','big_frameworks','final_copy_only_frameworks','topic_table_binding')
    payload={key:h.get(key) for key in keys}|{'schema':'copy-structure-v14','producer':{'agent_id':'xiaochai'},'structure_four_status':'user-pending','structures':result}
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
