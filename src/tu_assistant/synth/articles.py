"""T052/T053：按已确认的条款关系合成普法文章初稿及多轮修改样本。"""

from __future__ import annotations

import copy
import hashlib
import json
import random
import re
import sqlite3
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

from ..chat.orchestrator import DISCLAIMER, _related_clause_block
from ..chat.prompts import build_system_prompt
from ..citation.parse import RE_BARE_ARTICLE, parse_citations
from ..citation.verify import verify_output
from ..config import load_yaml
from ..eval.cases import eval_questions, load_cases
from ..eval.metrics import extract_articles
from ..kb.numbers import chinese_to_int
from ..kb.store import all_clauses, confirmed_relations_from
from ..train.dataset import dedup_against_eval
from .check import CheckStats, citation_issue
from .knowledge import _canonical_text, _marker, doc_titles
from .llm import CompletionTruncatedError, ExternalLLM

TRAIN_CONFIG = Path("configs/train/demo-7b-resume.yaml")
ARTICLE_PROMPT_VERSION = "t057-v4.0"
REVISION_PROMPT_VERSION = "t053-v1.1"
COUNT_MODES = (None, 1, 2, 3, 4)
ALL_REQUEST_MODES = (None, "vague", 1, 2, 3, 4)
ARTICLE_USER_PROMPTS: dict[str, tuple[str, ...]] = {
    "n1": (
        "请围绕“{topic}”写1篇普法文章。",
        "帮我写一篇关于“{topic}”的以案说法文章。",
        "围绕“{topic}”出一篇给工友看的普法宣传稿。",
    ),
    "n2": (
        "请围绕“{topic}”写2篇普法文章。",
        "围绕“{topic}”写两篇以案说法的普法文章，场景要有区分。",
    ),
    "n3": (
        "请围绕“{topic}”写3篇普法文章。",
        "帮我写三篇讲“{topic}”的普法宣传文章。",
    ),
    "n3_default": (
        "请围绕“{topic}”写普法文章。",
        "帮我写一下关于“{topic}”的以案说法普法宣传文章。",
    ),
    "n3_vague": (
        "帮我写几篇关于“{topic}”的普法宣传文章。",
        "围绕“{topic}”写几篇以案说法文章，发给职工看。",
    ),
    "n4": (
        "给我写4篇讲“{topic}”的以案说法文章，场景要有区分度。",
        "请围绕“{topic}”写四篇普法宣传文章。",
    ),
}
CASE_USER_PROMPTS: tuple[str, ...] = (
    "写一篇普法文章：{case_brief}",
    "帮我把这个事写成1篇以案说法：{case_brief}",
    "请根据下面这个情况写一篇给职工看的普法文章：{case_brief}",
)
REVISION_TYPES = ("plainer", "swap_subject")
MAX_DRAFT_TOKENS = 1050
REVISION_USER_PROMPTS: dict[str, tuple[str, ...]] = {
    "plainer": (
        "语言再通俗一些，少用书面语。",
        "写得更口语化点，方便发在工友群里看。",
        "能不能把分析和提示改得更接地气些，案情和法条不用动？",
        "这版有点太正式了，帮我改成大白话发宣传栏。",
        "麻烦把措辞改得更浅显易懂一点，其他内容保持不变。",
        "语气再亲切直白些，别像公文一样。",
    ),
    "swap_subject": (
        "换一个违法主体重写一版，条款不变。",
        "把涉事单位换成其他行业重新写一下。",
        "这个案例背景太常见了，换个不同类型的主体和情节再出一版。",
        "麻烦把里面的违法主体和工作场景都换掉，法条依据保持一样。",
        "再帮我改一版，换个不同的单位和行业背景来讲这些规定。",
        "违法主体换一家别的类型企业，具体情节也跟着调整一下。",
    ),
}
SCENARIOS = (
    "一次事件当场被当事人发现。写清实施手段、当事人身份和直接影响。",
    "换一个工作场所和实施手段，通过事后发现的书面或电子记录还原事实。",
    "行为被提醒后以新的方式持续，影响扩大。交代纠正经过与责任成立的条件。",
    "发生在中小型服务或物流企业，当事人向工会或主管部门反映后核查清楚。",
    "发生在制造或加工车间，由班组长/部门负责人奉单位决定执行，交代决策与受益归属。",
    "发生在民办机构或连锁门店，通过考勤表、工资条、聊天记录等电子凭证还原经过。",
    "单位以内部规定或换个名义掩盖违法做法，经整改通知后仍未纠正。",
    "涉及多名一线职工的共同遭遇，交代集体反映经过、书面留证与法定处理途径。",
)
NUM = r"[0-9零〇一二三四五六七八九十百千]+"
PARAGRAPH_REF = re.compile(rf"第({NUM})条第({NUM})款")
COUNT_IN_TOPIC = re.compile(rf"(?:{NUM}|两)\s*篇")
SECTIONS = re.compile(r"^## (.+?)\s*$", re.M)
ACT = re.compile(r"^### [^\n：:]+[：:][^\n]+$", re.M)
LABEL = re.compile(r"^\*\*(法律依据|法律责任)\*\*[ \t]*$", re.M)

INSTRUCTIONS = """编写给职工阅读的虚构普法文章初稿。只用提供的条款及对应关系。
首行严格写“主题：<职工听得懂的具体话题>”。主题用日常用语，不带篇数、法规名或条号。
从第二行起给文章原稿。每篇以 # 标题 开头，篇间用单独一行 ---。
按顺序写 ## 案例、## 以案说法、## 普法提示。人物、单位一律虚构。
案例不超过150字。每项小标题冒号左边填实际责任主体，右边填行为，例如“### 某厂：拒绝改正”。
小标题下一行单独写一段不超过80字的分析，把本案事实与条款适用条件对应起来。
案例先写清是谁作出决定、由谁执行、为谁办事，再按条款确定谁承担责任。
若条款限定特定主体（如董事、监事、高级管理人员，或大众传播媒介、住宿经营者），须写明符合法定身份的主体。
有返还争议时写清财物归属、谁控制或受益、向谁索还及对方的明确回应；
只在案情和条款都支持时认定该责任。分析引用的事实都要在案例中交代。
给职工的行动建议要区分“工作人员可以做什么”和“条款要求哪个主体履行义务”。
再依次写 **法律依据** 和 **法律责任**（各自单独一行），紧接原样复制对应的标记行和 > 原文行。
提示不超过80字。正文提及同一条款时仍需完整标记。勿引入其他条款或原文未规定的处罚。
遵循篇计划及行为顺序，各篇的主体身份、手段或情节要有实质差异，同篇各行为须能共同发生；
各写明主体、条件、事实与责任。无法从素材设计相符情境时只返回“素材不适用”。
每篇请逐行填下面的骨架。保留三个 ## 标题。在 ## 以案说法 下按行为依次重复整个 ### 小节。

# <文章标题>
## 案例
<虚构经过，交代责任主体及责任条款要求的事实>
## 以案说法
### <案中的实际主体>：<具体行为>
<把关键事实与构成要件对照，直接点明已满足或尚欠的条件，不在分析里复述条号>
**法律依据**
<素材中的依据标记行>
> <依据原文>
**法律责任**
<素材中的责任标记行>
> <责任原文>
## 普法提示
<工友能采取的措施。责任另有前提时明确区分，不把可能处罚写成已处罚>

仅输出主题行及 Markdown 成稿，无代码围栏和附言。"""


@dataclass(frozen=True)
class Relation:
    doc_id: str
    basis: str
    liability: str
    basis_block: str
    liability_block: str


@dataclass
class ArticleStats(CheckStats):
    materials: Counter = field(default_factory=Counter)
    drops: list[dict] = field(default_factory=list)


class Rejected(ValueError):
    def __init__(self, reason: str, article: int | None = None):
        super().__init__(reason)
        self.reason = reason
        self.article = article


def _materials(conn, stats):
    clauses = all_clauses(conn)
    by_id = {c.clause_id: c for c in clauses}
    titles = doc_titles(conn)
    current = {r[0] for r in conn.execute("SELECT doc_id FROM legal_documents WHERE status='current'")}

    def block(c):
        return f"{_marker(*titles[c.doc_id], c)}\n> {_canonical_text(c, clauses)}"

    pairs = []
    for aid, bid in conn.execute(
        "SELECT from_clause_id, to_clause_id FROM clause_relations "
        "WHERE confirmed=1 AND relation_type='liability_for' ORDER BY from_clause_id, to_clause_id"
    ):
        a, b = by_id.get(aid), by_id.get(bid)
        if not a or not b or a.doc_id not in current or b.doc_id not in current:
            stats.materials["material_unresolved"] += 1
            continue
        # 已确认关系可能只匹配到条号、默认定位到第一款，责任原文却指向另一款。
        paragraphs = {
            chinese_to_int(p) for n, p in PARAGRAPH_REF.findall(b.text) if chinese_to_int(n) == a.article_no
        }
        if a.doc_id == b.doc_id and paragraphs and a.paragraph_no not in paragraphs:
            stats.materials["paragraph_mismatch"] += 1
            continue
        pairs.append(Relation(a.doc_id, aid, bid, block(a), block(b)))
    stats.materials["eligible"] = len(pairs)
    return pairs


def _prompt(plan, focuses):
    instructions = []
    layout = ""
    for i, (acts, focus) in enumerate(zip(plan, focuses, strict=True), 1):
        materials = [{"依据": r.basis_block, "责任": r.liability_block} for r in acts]
        instructions.append({"篇": i, "场景要求": focus, "行为素材": materials})
        if len(acts) > 1:
            outline = "\n".join(
                f"### <主体>：<行为{j}>\n<本项事实分析>\n**法律依据**\n{r.basis_block}"
                f"\n**法律责任**\n{r.liability_block}"
                for j, r in enumerate(acts, 1)
            )
            layout += (
                f"\n第{i}篇只写一个事件、一段案例，两项行为要由同一纠纷串起。"
                "逐项判断，两项可以由同一家单位承担责任。若本项由单位决定、员工奉命办理，"
                "财物由单位控制且利益也归单位，本项标题左边填该单位，人员的动作放在案例里。"
                "若依据条款涉及劳动者身份或收入来源，在案例中明确交代。"
                "两项素材如无法成立同一场景，直接返回“素材不适用”。在同一个 ## 以案说法 下严格填以下"
                f"{len(acts)}节。每对素材只分析一次。\n{outline}\n## 普法提示\n<汇总建议>\n"
            )
    separator = "单篇从标题写到提示结尾，全文不要分隔线。" if len(plan) == 1 else "只在两篇之间使用 ---。"
    return f"{INSTRUCTIONS}{layout}\n本次交付 {len(plan)} 篇，{separator}\n篇计划\n" + json.dumps(
        instructions, ensure_ascii=False
    )


def _check_structure(article, acts, index, resolved):
    # 训练稿的三段必须齐全且有内容，评测侧拆篇本身允许不完整的交付。
    sections = SECTIONS.split(article)
    if (
        not re.fullmatch(r"# [^\n]+", sections[0].strip())
        or sections[1::2] != ["案例", "以案说法", "普法提示"]
        or not all(part.strip() for part in sections[2::2])
    ):
        raise Rejected("article_section_missing", index)
    if LABEL.search(sections[6]):
        raise Rejected("citation_in_tip", index)
    items = ACT.split(sections[4])
    if len(items) != len(acts) + 1:
        raise Rejected("violation_count_mismatch", index)
    for heading in ACT.findall(sections[4]):
        if re.split("[：:]", heading[4:], maxsplit=1)[0].strip() in {"违法主体", "<违法主体>"}:
            raise Rejected("actor_missing", index)
    for item, relation in zip(items[1:], acts, strict=True):
        parts = LABEL.split(item)
        if parts[1::2] != ["法律依据", "法律责任"]:
            raise Rejected("liability_missing", index)
        if not parts[0].strip():
            raise Rejected("analysis_missing", index)
        for part, expected, opposite in (
            (parts[2], relation.basis, relation.liability),
            (parts[4], relation.liability, relation.basis),
        ):
            citations = parse_citations(part)
            if not citations:
                raise Rejected("citation_missing", index)
            for n, citation in enumerate(citations):
                clause_id = resolved.get((citation.raw, citation.quoted_text))
                if n == 0 and not citation.quoted_text:
                    raise Rejected("quote_missing", index)
                if clause_id == opposite:
                    raise Rejected("liability_basis_swapped", index)
                if clause_id != expected:
                    raise Rejected("citation_mismatch", index)
    return sections[2].strip()


def _validate(text, plan, conn):
    chunks = re.split(r"(?m)^---[ \t]*$", text)
    if len(chunks) != len(plan) or len(re.findall(r"(?m)^# [^\n]+", text)) != len(plan):
        raise Rejected("article_count_mismatch")
    cited = set()
    seen_cases = set()
    for i, (chunk, acts) in enumerate(zip(chunks, plan, strict=True), 1):
        planned = {cid for act in acts for cid in (act.basis, act.liability)}
        result = verify_output(chunk, conn)
        resolved = {(c.raw, c.quoted_text): c.resolved_clause_id for c in result.citations}
        # 先报能直接定位的引用错误，缺段/错项则留给逐行为检查。
        issue = citation_issue(result, require_citation=False, expected_clause_ids=None)
        if issue:
            raise Rejected(issue, i)
        case = _check_structure(chunk, acts, i, resolved)
        if case in seen_cases:
            raise Rejected("duplicate_case", i)
        seen_cases.add(case)
        actual = set(resolved.values())
        if actual != planned or any(c.verdict != "ok" for c in result.citations):
            raise Rejected("citation_mismatch", i)
        seen = set()
        for c in result.citations:
            if not c.quoted_text and c.resolved_clause_id not in seen:
                raise Rejected("quote_missing", i)
            seen.add(c.resolved_clause_id)
        cited.update(actual)
    if len(extract_articles(text)) != len(plan):
        raise Rejected("article_count_mismatch")
    return sorted(cited)


def training_token_counter(model: str):
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model, local_files_only=True)

    def count(messages):
        return len(tokenizer.apply_chat_template(messages, tokenize=True, return_dict=False))

    return count


def generate(
    kb_conn: sqlite3.Connection,
    llm: ExternalLLM,
    cfg: dict,
    *,
    n_requests: int = 12,
    request_modes: tuple[int | str | None, ...] = (None, 1, 2, 3),
    stats: ArticleStats | None = None,
    count_tokens: Callable[[list[dict]], int] | None = None,
    train_config: Path = TRAIN_CONFIG,
    eval_cases: Path = Path("eval/cases/v1"),
    doc_ids: set[str] | None = None,
    multi_whitelist: set[tuple[tuple[str, str], tuple[str, str]]] | None = None,
) -> list[dict]:
    """生成初稿。传入 stats 可取得材料与逐请求丢弃记录，测试可注入计数器。"""
    if n_requests < 0:
        raise ValueError("n_requests 必须非负")
    if not request_modes or any(mode not in ALL_REQUEST_MODES for mode in request_modes):
        raise ValueError("训练篇数可选默认、vague、1、2、3、4")
    stats = stats if stats is not None else ArticleStats()
    train = load_yaml(train_config)
    max_length = train["max_seq_length"]
    questions = eval_questions(load_cases(eval_cases))
    rng = random.Random(cfg.get("seed", 42))
    pool = _materials(kb_conn, stats)
    if doc_ids is not None:
        pool = [r for r in pool if r.doc_id in doc_ids]
    rng.shuffle(pool)
    if not pool or not n_requests:
        return []
    titles = [title for title, _ in doc_titles(kb_conn).values() if title]
    count_tokens = count_tokens or training_token_counter(train["base_model"])
    # 每四个请求中给单篇请求安排一个多行为场景，给其他请求留足训练窗口。
    combos = [
        (first, second)
        for j, first in enumerate(pool)
        for second in pool[j + 1 :]
        if first.doc_id == second.doc_id
        and first.basis != second.basis
        and first.liability != second.liability
        and (
            multi_whitelist is None
            or ((first.basis, first.liability), (second.basis, second.liability)) in multi_whitelist
            or ((second.basis, second.liability), (first.basis, first.liability)) in multi_whitelist
        )
    ]
    samples = []
    multi_index = 0
    for idx in range(n_requests):
        mode = request_modes[idx % len(request_modes)]
        if mode is None:
            n, kind = 3, "n3_default"
        elif mode == "vague":
            n, kind = 3, "n3_vague"
        else:
            n, kind = int(mode), f"n{mode}"
        first = pool[idx % len(pool)]
        plan = [[first] for _ in range(n)]
        if mode == 1:
            if combos:
                plan[0] = list(combos[multi_index % len(combos)])
                multi_index += 1
            else:
                stats.materials["no_multi_pair"] += 1
        focuses = rng.sample(SCENARIOS, n)
        q = rng.randint(2, 6)
        stats.total += 1
        try:
            out = llm.chat(
                [{"role": "user", "content": _prompt(plan, focuses)}],
                input_source="kb_clause",
                max_tokens=4096,
                reject_truncated=True,
            )
            if out.strip() == "素材不适用":
                raise Rejected("scenario_unsuitable")
            lead, _, text = out.strip().partition("\n")
            topic = lead.removeprefix("主题：").strip()
            if (
                not lead.startswith("主题：")
                or not topic
                or "《" in topic
                or RE_BARE_ARTICLE.search(topic)
                or COUNT_IN_TOPIC.search(topic)
                or any(title in topic for title in titles)
            ):
                raise Rejected("invalid_topic")
            text = text.strip()
            ids = _validate(text, plan, kb_conn)
            user_prompt = rng.choice(ARTICLE_USER_PROMPTS[kind]).format(topic=topic)
            messages = [
                {"role": "system", "content": build_system_prompt(max_questions=q)},
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": text},
            ]
            length = count_tokens(messages)
            if length > max_length:
                raise Rejected("too_long")
            meta_plan = [
                {"focus": focus, "acts": [[r.basis, r.liability] for r in acts]}
                for acts, focus in zip(plan, focuses, strict=True)
            ]
            sample = {
                "messages": messages,
                "meta": {
                    "type": "article",
                    "kind": kind,
                    "doc_id": plan[0][0].doc_id,
                    "clause_ids": ids,
                    "plan": meta_plan,
                    "n_requested": n,
                    "max_questions": q,
                    "tokens": length,
                    "request": idx + 1,
                },
            }
            if _eval_overlap_any_turn(sample, questions):
                raise Rejected("eval_overlap")
        except (Rejected, CompletionTruncatedError) as exc:
            reason = exc.reason if isinstance(exc, Rejected) else "llm_truncated"
            stats.record_drop(reason)
            stats.drops.append(
                {
                    "request": idx + 1,
                    "reason": reason,
                    "article": getattr(exc, "article", None),
                }
            )
            continue
        stats.kept += 1
        samples.append(sample)
    return samples


REVISION_INSTRUCTIONS = """根据用户的修改要求重写下面的普法文章初稿。只用提供的条款及对应关系。
输出完整修改稿（不写“主题：”首行，无代码围栏、无附言、无免责声明）。
保留与初稿相同的篇数和 Markdown 骨架：每篇以 # 标题 开头，篇间仅用单独一行 ---（单篇全文不要分隔线）。
每篇按顺序写 ## 案例、## 以案说法、## 普法提示。人物、单位一律虚构。
篇幅控制在初稿相近水平，不得大幅扩写：案例不超过150字，每项 ### 小节下的分析不超过80字，普法提示不超过80字。
每项小标题保持“### <案中的实际主体>：<具体行为>”格式，下方依次写分析、
**法律依据**和**法律责任**（各自单独一行），紧接原样复制下方素材中的标记行和 > 原文行。
正文若再提条款须带完整标记，勿引入其他条款或原文未规定的处罚。"""

REVISION_TYPE_RULES: dict[str, str] = {
    "plainer": (
        "修改要求（更通俗）：把叙述、分析和普法提示改得更口语化、接地气、便于普通职工看懂。"
        "必须保持每篇的案情核心事实、时间/结果等关键要件、每个 ### 冒号左侧的实际责任主体、"
        "责任归属结论以及法律依据/法律责任引用完全不变，只调整表达风格；每篇文本不能与初稿逐字照搬。"
    ),
    "swap_subject": (
        "修改要求（换违法主体）：在条款允许的主体范围内，为每篇更换新的虚构违法主体"
        "（不同行业、单位类型或身份）以及相配套的人物与具体情节，使每篇每个 ### 冒号左侧的责任主体"
        "都与初稿不同；若条款义务固定落在特定主体（如住宿经营者、用人单位、人力资源服务机构），"
        "则更换具体虚构机构、行业场景或实施手段，且不得脱离原条款规定的法定主体范围。"
        "更换后的案情须完整交代责任主体及构成要件所需事实，保持法律依据与法律责任条款不变；"
        "普法提示仍面向普通职工/工作人员，不要改成对经营者或单位喊话。"
        "若无法合理更换，只返回“素材不适用”。"
    ),
}


def draft_id(draft: dict) -> str:
    """为初稿生成稳定标识，供 T053 meta.parent 与 T057 同侧划分追溯。"""
    meta = draft.get("meta") or {}
    for key in ("sample_id", "id"):
        if meta.get(key):
            return str(meta[key])
    if meta.get("source_batch") and meta.get("request") is not None:
        return f"{meta['source_batch']}:req{meta['request']}"
    raw = json.dumps(draft.get("messages", []), ensure_ascii=False, sort_keys=True)
    return "draft-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def normalize_draft_markers(draft: dict, kb_conn: sqlite3.Connection) -> dict:
    """把初稿中的引用标记规范为当前 KB 的标准写法（如补齐多款条文的“第1款”）。

    按 citation.span 从右往左切片替换，不改动正文叙述与引文内容，返回拷贝后的样本。
    """
    out = copy.deepcopy(draft)
    messages = out.get("messages") or []
    if not messages or messages[-1].get("role") != "assistant":
        return out
    text = messages[-1]["content"]
    verified = verify_output(text, kb_conn)
    by_id = {c.clause_id: c for c in all_clauses(kb_conn)}
    titles = doc_titles(kb_conn)
    edits: list[tuple[int, int, str]] = []
    for cit in verified.citations:
        if not cit.resolved_clause_id or cit.resolved_clause_id not in by_id:
            continue
        clause = by_id[cit.resolved_clause_id]
        canonical = _marker(*titles[clause.doc_id], clause)
        start, end = cit.span
        if cit.raw != canonical and text[start:end] == cit.raw:
            edits.append((start, end, canonical))
    for start, end, repl in sorted(edits, key=lambda e: e[0], reverse=True):
        text = text[:start] + repl + text[end:]
    messages[-1]["content"] = text
    return out


def _history_assistant_text(draft_text: str, kb_conn: sqlite3.Connection) -> str:
    """按运行时 process_turn 交付格式生成历史轮初稿文本（含关联补全与免责声明）。"""
    verified = verify_output(draft_text, kb_conn)
    text = verified.text
    resolved = {c.resolved_clause_id for c in verified.citations if c.resolved_clause_id}
    related = confirmed_relations_from(kb_conn, list(resolved))
    extra = list(
        dict.fromkeys(rel.to_clause_id for rel in related if rel.to_clause_id not in resolved)
    )
    if extra:
        blocks = [b for cid in extra if (b := _related_clause_block(cid, kb_conn))]
        if blocks:
            text += "\n\n**相关条款（系统补充）**\n\n" + "\n\n".join(blocks)
    if verified.citations:
        text += DISCLAIMER
    return text


def _extract_article_actors(text: str) -> list[list[str]]:
    chunks = re.split(r"(?m)^---[ \t]*$", text)
    actors: list[list[str]] = []
    for chunk in chunks:
        actors.append(
            [re.split("[：:]", h[4:], maxsplit=1)[0].strip() for h in ACT.findall(chunk)]
        )
    return actors


def _eval_overlap_any_turn(sample: dict, questions: list[str]) -> bool:
    if not questions:
        return False
    _, duplicates = dedup_against_eval([sample], questions)
    if duplicates:
        return True
    for msg in sample.get("messages", []):
        if msg.get("role") == "user":
            _, turn_dups = dedup_against_eval([{"messages": [msg]}], questions)
            if turn_dups:
                return True
    return False


def _revision_prompt(
    draft_text: str,
    plan: list[list[Relation]],
    revision_type: str,
    user_request: str,
) -> str:
    materials = [
        {
            "篇": i,
            "行为素材": [{"依据": r.basis_block, "责任": r.liability_block} for r in acts],
        }
        for i, acts in enumerate(plan, 1)
    ]
    separator = "单篇从标题写到提示结尾，全文不要分隔线。" if len(plan) == 1 else "只在两篇之间使用 ---。"
    return (
        f"{REVISION_INSTRUCTIONS}\n"
        f"{REVISION_TYPE_RULES[revision_type]}\n"
        f"本次交付 {len(plan)} 篇，{separator}\n"
        f"用户修改要求：{user_request}\n"
        f"逐篇素材\n{json.dumps(materials, ensure_ascii=False)}\n"
        f"原初稿\n{draft_text}"
    )


def _validate_revision(
    revised_text: str,
    draft_text: str,
    plan: list[list[Relation]],
    revision_type: str,
    kb_conn: sqlite3.Connection,
) -> list[str]:
    ids = _validate(revised_text, plan, kb_conn)
    if revised_text.strip() == draft_text.strip():
        raise Rejected("revision_unchanged")
    rev_chunks = re.split(r"(?m)^---[ \t]*$", revised_text)
    draft_chunks = re.split(r"(?m)^---[ \t]*$", draft_text)
    for i, (rev_chunk, draft_chunk) in enumerate(zip(rev_chunks, draft_chunks, strict=True), 1):
        if rev_chunk.strip() == draft_chunk.strip():
            raise Rejected("revision_unchanged", i)
    draft_actors = _extract_article_actors(draft_text)
    rev_actors = _extract_article_actors(revised_text)
    for i, (rev_chunk, d_acts, r_acts) in enumerate(
        zip(rev_chunks, draft_actors, rev_actors, strict=True), 1
    ):
        if revision_type == "plainer" and r_acts != d_acts:
            raise Rejected("actor_changed", i)
        if revision_type == "swap_subject":
            if any(r == d for d, r in zip(d_acts, r_acts, strict=True)):
                raise Rejected("actor_unchanged", i)
            if any((len(d) >= 3 or d.endswith("某")) and d in rev_chunk for d in d_acts):
                raise Rejected("actor_residual", i)
    return ids


def generate_revisions(
    kb_conn: sqlite3.Connection,
    llm: ExternalLLM,
    cfg: dict,
    drafts: list[dict],
    *,
    revision_types: tuple[str, ...] = REVISION_TYPES,
    n_requests: int | None = None,
    stats: ArticleStats | None = None,
    count_tokens: Callable[[list[dict]], int] | None = None,
    train_config: Path = TRAIN_CONFIG,
    eval_cases: Path = Path("eval/cases/v1"),
    max_draft_tokens: int = MAX_DRAFT_TOKENS,
    normalize_markers: bool = True,
) -> list[dict]:
    """T053：基于已通过人工复审的 1–2 篇初稿，合成多轮修改样本（plainer / swap_subject）。"""
    if not revision_types or any(rt not in REVISION_TYPES for rt in revision_types):
        raise ValueError(f"修改类型仅支持 {REVISION_TYPES}")
    if n_requests is not None and n_requests < 0:
        raise ValueError("n_requests 必须非负")
    stats = stats if stats is not None else ArticleStats()
    pool = _materials(kb_conn, stats)
    rel_by_pair = {(r.basis, r.liability): r for r in pool}
    total_requests = len(drafts) * len(revision_types) if n_requests is None else n_requests
    if not drafts or not total_requests:
        return []
    train = load_yaml(train_config)
    max_length = train["max_seq_length"]
    questions = eval_questions(load_cases(eval_cases))
    rng = random.Random(cfg.get("seed", 42))
    count_tokens = count_tokens or training_token_counter(train["base_model"])

    samples: list[dict] = []
    for idx in range(total_requests):
        raw_draft = drafts[(idx // len(revision_types)) % len(drafts)]
        rtype = revision_types[idx % len(revision_types)]
        stats.total += 1
        try:
            draft = normalize_draft_markers(raw_draft, kb_conn) if normalize_markers else raw_draft
            d_msgs = draft.get("messages") or []
            d_meta = draft.get("meta") or {}
            if len(d_msgs) != 3 or [m.get("role") for m in d_msgs] != ["system", "user", "assistant"]:
                raise Rejected("invalid_draft")
            meta_plan = d_meta.get("plan") or []
            if len(meta_plan) not in (1, 2):
                raise Rejected("unsupported_article_count")
            plan: list[list[Relation]] = []
            for entry in meta_plan:
                acts_rel = []
                for pair in entry.get("acts") or []:
                    rel = rel_by_pair.get((pair[0], pair[1]))
                    if rel is None:
                        raise Rejected("material_unresolved")
                    acts_rel.append(rel)
                if not acts_rel:
                    raise Rejected("material_unresolved")
                plan.append(acts_rel)

            draft_text = d_msgs[2]["content"].strip()
            draft_chunks = re.split(r"(?m)^---[ \t]*$", draft_text)
            draft_actors = _extract_article_actors(draft_text)
            if len(draft_chunks) != len(plan) or any(
                len(a) != len(acts) for a, acts in zip(draft_actors, plan, strict=True)
            ):
                raise Rejected("invalid_draft")
            history_assistant = _history_assistant_text(draft_text, kb_conn)
            draft_turn_messages = [
                d_msgs[0],
                d_msgs[1],
                {"role": "assistant", "content": history_assistant},
            ]
            if count_tokens(draft_turn_messages) > max_draft_tokens:
                raise Rejected("draft_too_long")

            user_rev = rng.choice(REVISION_USER_PROMPTS[rtype])
            out = llm.chat(
                [{"role": "user", "content": _revision_prompt(draft_text, plan, rtype, user_rev)}],
                input_source="kb_clause",
                max_tokens=4096,
                reject_truncated=True,
            )
            if out.strip() == "素材不适用":
                raise Rejected("scenario_unsuitable")
            revised_text = out.strip()
            ids = _validate_revision(revised_text, draft_text, plan, rtype, kb_conn)

            messages = [
                *draft_turn_messages,
                {"role": "user", "content": user_rev},
                {"role": "assistant", "content": revised_text},
            ]
            length = count_tokens(messages)
            if length > max_length:
                raise Rejected("too_long")

            sample = {
                "messages": messages,
                "meta": {
                    "type": "article",
                    "kind": f"revise_{rtype}",
                    "revision_type": rtype,
                    "parent": draft_id(raw_draft),
                    "doc_id": d_meta.get("doc_id") or plan[0][0].doc_id,
                    "clause_ids": ids,
                    "plan": meta_plan,
                    "n_requested": len(plan),
                    "max_questions": d_meta.get("max_questions"),
                    "tokens": length,
                    "request": idx + 1,
                },
            }
            if _eval_overlap_any_turn(sample, questions):
                raise Rejected("eval_overlap")
        except (Rejected, CompletionTruncatedError) as exc:
            reason = exc.reason if isinstance(exc, Rejected) else "llm_truncated"
            stats.record_drop(reason)
            stats.drops.append(
                {
                    "request": idx + 1,
                    "reason": reason,
                    "article": getattr(exc, "article", None),
                }
            )
            continue
        stats.kept += 1
        samples.append(sample)
    return samples


CASE_INSTRUCTIONS = """根据提供的依据与责任条款，构造“用户自带虚构案情、请求写成1篇普法文章”的样本。
首行严格写“用户案情：<1至2句日常口语虚构纠纷，人物和单位一律虚构，不带法规名、书名号或条号>”。
从第二行起给出对应的 1 篇完整普法文章（全文不要分隔线 ---），文章中的 ## 案例 须与首行案情事实一致，
并在案例中补全条款适用所需的细节。按顺序写 # 标题、## 案例、## 以案说法、## 普法提示。
案例不超过150字，每项 ### 小节分析不超过80字，普法提示不超过80字且面向普通职工。
每项小标题用“### <实际责任主体>：<具体行为>”，下方依次写分析、**法律依据**和**法律责任**（各自单独一行），
紧接原样复制下方素材中的标记行和 > 原文行。勿引入其他条款或原文未规定的处罚。
仅输出首行用户案情及 Markdown 成稿，无代码围栏和附言。"""


def generate_from_case(
    kb_conn: sqlite3.Connection,
    llm: ExternalLLM,
    cfg: dict,
    *,
    n_requests: int = 4,
    stats: ArticleStats | None = None,
    count_tokens: Callable[[list[dict]], int] | None = None,
    train_config: Path = TRAIN_CONFIG,
    eval_cases: Path = Path("eval/cases/v1"),
    doc_ids: set[str] | None = None,
    multi_whitelist: set[tuple[tuple[str, str], tuple[str, str]]] | None = None,
) -> list[dict]:
    """T057：生成“用户自带虚构案情 → 1篇普法文章”样本（meta.kind='n1_case'）。"""
    if n_requests < 0:
        raise ValueError("n_requests 必须非负")
    stats = stats if stats is not None else ArticleStats()
    train = load_yaml(train_config)
    max_length = train["max_seq_length"]
    questions = eval_questions(load_cases(eval_cases))
    rng = random.Random(cfg.get("seed", 42) + 101)
    pool = _materials(kb_conn, stats)
    if doc_ids is not None:
        pool = [r for r in pool if r.doc_id in doc_ids]
    rng.shuffle(pool)
    if not pool or not n_requests:
        return []
    titles = [title for title, _ in doc_titles(kb_conn).values() if title]
    count_tokens = count_tokens or training_token_counter(train["base_model"])
    combos = [
        (first, second)
        for j, first in enumerate(pool)
        for second in pool[j + 1 :]
        if first.doc_id == second.doc_id
        and first.basis != second.basis
        and first.liability != second.liability
        and (
            multi_whitelist is None
            or ((first.basis, first.liability), (second.basis, second.liability)) in multi_whitelist
            or ((second.basis, second.liability), (first.basis, first.liability)) in multi_whitelist
        )
    ]

    samples: list[dict] = []
    for idx in range(n_requests):
        # 奇数请求优先使用白名单双行为组合（对应 article-005/006），其余用单行为
        acts = (
            list(combos[(idx // 2) % len(combos)])
            if combos and idx % 2 == 0
            else [pool[idx % len(pool)]]
        )
        plan = [acts]
        focus = rng.choice(SCENARIOS)
        q = rng.randint(2, 6)
        materials = [{"依据": r.basis_block, "责任": r.liability_block} for r in acts]
        prompt = (
            f"{CASE_INSTRUCTIONS}\n场景要求：{focus}\n行为素材\n"
            + json.dumps(materials, ensure_ascii=False)
        )
        stats.total += 1
        try:
            out = llm.chat(
                [{"role": "user", "content": prompt}],
                input_source="kb_clause",
                max_tokens=4096,
                reject_truncated=True,
            )
            if out.strip() == "素材不适用":
                raise Rejected("scenario_unsuitable")
            lead, _, text = out.strip().partition("\n")
            case_brief = lead.removeprefix("用户案情：").strip()
            if (
                not lead.startswith("用户案情：")
                or not case_brief
                or "《" in case_brief
                or RE_BARE_ARTICLE.search(case_brief)
                or any(title in case_brief for title in titles)
            ):
                raise Rejected("invalid_case_brief")
            text = text.strip()
            ids = _validate(text, plan, kb_conn)
            user_prompt = rng.choice(CASE_USER_PROMPTS).format(case_brief=case_brief)
            messages = [
                {"role": "system", "content": build_system_prompt(max_questions=q)},
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": text},
            ]
            length = count_tokens(messages)
            if length > max_length:
                raise Rejected("too_long")
            meta_plan = [{"focus": focus, "acts": [[r.basis, r.liability] for r in acts]}]
            sample = {
                "messages": messages,
                "meta": {
                    "type": "article",
                    "kind": "n1_case",
                    "doc_id": acts[0].doc_id,
                    "clause_ids": ids,
                    "plan": meta_plan,
                    "n_requested": 1,
                    "max_questions": q,
                    "tokens": length,
                    "request": idx + 1,
                },
            }
            if _eval_overlap_any_turn(sample, questions):
                raise Rejected("eval_overlap")
        except (Rejected, CompletionTruncatedError) as exc:
            reason = exc.reason if isinstance(exc, Rejected) else "llm_truncated"
            stats.record_drop(reason)
            stats.drops.append(
                {
                    "request": idx + 1,
                    "reason": reason,
                    "article": getattr(exc, "article", None),
                }
            )
            continue
        stats.kept += 1
        samples.append(sample)
    return samples


_RE_PERSON = re.compile(r"[\u4e00-\u9fff]某")
_RE_ORG = re.compile(
    r"某[\u4e00-\u9fff]{1,6}"
    r"(?:酒店|旅馆|宾馆|民宿|公司|工厂|厂|医院|学校|机构|中心|集团|养老院|幼儿园|商行|餐厅|餐馆)"
)
_RE_PUNCT_SPACE = re.compile(r"[\s，。、；：！？“”‘’（）()《》【】—\-·,.!?;:\"'`]+")


def _normalize_case_text(case_text: str) -> str:
    s = _RE_ORG.sub("<单位>", case_text)
    s = _RE_PERSON.sub("<人>", s)
    return _RE_PUNCT_SPACE.sub("", s)


def _extract_title_and_cases(text: str) -> list[tuple[str, str]]:
    chunks = re.split(r"(?m)^---[ \t]*$", text.strip())
    out: list[tuple[str, str]] = []
    for chunk in chunks:
        sections = SECTIONS.split(chunk)
        title = sections[0].strip().lstrip("#").strip() if sections else ""
        case_text = ""
        for name, body in zip(sections[1::2], sections[2::2], strict=False):
            if name == "案例":
                case_text = body.strip()
                break
        if title or case_text:
            out.append((title, case_text))
    return out


def _char_bigrams(s: str) -> set[str]:
    if len(s) < 2:
        return {s} if s else set()
    return {s[i : i + 2] for i in range(len(s) - 1)}


def find_case_near_duplicates(
    samples: list[dict],
    *,
    jaccard_threshold: float = 0.15,
    seq_threshold: float = 0.35,
) -> list[dict]:
    """跨请求案例近重复检测：仅比对脱敏后的 ## 案例 段与标题，自动跳过 plainer 与其 parent。"""
    entries: list[tuple[str, dict, list[tuple[str, str, set[str]]]]] = []
    for s in samples:
        msgs = s.get("messages") or []
        ans = msgs[-1]["content"] if msgs and msgs[-1].get("role") == "assistant" else ""
        meta = s.get("meta") or {}
        if not meta.get("parent"):
            sid = draft_id(s)
        elif meta.get("request") is not None:
            sid = f"{meta.get('source_batch', 'rev')}:req{meta['request']}"
        else:
            sid = draft_id(s)
        arts = []
        for title, case_text in _extract_title_and_cases(ans):
            norm = _normalize_case_text(case_text)
            arts.append((title, norm, _char_bigrams(norm)))
        entries.append((sid, s, arts))

    matches: list[dict] = []
    for i in range(len(entries)):
        sid_a, sa, arts_a = entries[i]
        ma = sa.get("meta") or {}
        id_a = draft_id(sa)
        for j in range(i + 1, len(entries)):
            sid_b, sb, arts_b = entries[j]
            mb = sb.get("meta") or {}
            id_b = draft_id(sb)
            # 跳过 plainer 修改稿与其 parent 初稿的天然案情一致
            if (ma.get("kind") == "revise_plainer" and ma.get("parent") == id_b) or (
                mb.get("kind") == "revise_plainer" and mb.get("parent") == id_a
            ):
                continue
            for ai, (ta, na, ga) in enumerate(arts_a, 1):
                for bi, (tb, nb, gb) in enumerate(arts_b, 1):
                    union = ga | gb
                    jacc = (len(ga & gb) / len(union)) if union else 0.0
                    seq = SequenceMatcher(None, na, nb).ratio() if (na and nb) else 0.0
                    same_title = bool(ta and ta == tb)
                    if jacc >= jaccard_threshold or seq >= seq_threshold or same_title:
                        matches.append(
                            {
                                "left_id": sid_a,
                                "right_id": sid_b,
                                "left_article": ai,
                                "right_article": bi,
                                "left_title": ta,
                                "right_title": tb,
                                "jaccard": round(jacc, 4),
                                "seq_ratio": round(seq, 4),
                                "same_title": same_title,
                            }
                        )
    return matches
