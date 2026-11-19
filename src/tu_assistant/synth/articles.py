"""T052：按已确认的条款关系合成一至三篇普法文章初稿。"""

from __future__ import annotations

import json
import random
import re
import sqlite3
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ..chat.prompts import build_system_prompt
from ..citation.parse import RE_BARE_ARTICLE, parse_citations
from ..citation.verify import verify_output
from ..config import load_yaml
from ..eval.cases import eval_questions, load_cases
from ..eval.metrics import extract_articles
from ..kb.numbers import chinese_to_int
from ..kb.store import all_clauses
from ..train.dataset import dedup_against_eval
from .check import CheckStats, citation_issue
from .knowledge import _canonical_text, _marker, doc_titles
from .llm import CompletionTruncatedError, ExternalLLM

TRAIN_CONFIG = Path("configs/train/demo-7b-resume.yaml")
ARTICLE_PROMPT_VERSION = "t052-v3.3"
COUNT_MODES = (None, 1, 2, 3)
SCENARIOS = (
    "一次事件当场被当事人发现。写清实施手段、当事人身份和直接影响。",
    "换一个工作场所和实施手段，通过事后发现的书面或电子记录还原事实。",
    "行为被提醒后以新的方式持续，影响扩大。交代纠正经过与责任成立的条件。",
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
    request_modes: tuple[int | None, ...] = COUNT_MODES,
    stats: ArticleStats | None = None,
    count_tokens: Callable[[list[dict]], int] | None = None,
    train_config: Path = TRAIN_CONFIG,
    eval_cases: Path = Path("eval/cases/v1"),
) -> list[dict]:
    """生成初稿。传入 stats 可取得材料与逐请求丢弃记录，测试可注入计数器。"""
    if n_requests < 0:
        raise ValueError("n_requests 必须非负")
    if not request_modes or any(mode not in COUNT_MODES for mode in request_modes):
        raise ValueError("训练篇数可选默认、1、2、3")
    stats = stats if stats is not None else ArticleStats()
    train = load_yaml(train_config)
    max_length = train["max_seq_length"]
    questions = eval_questions(load_cases(eval_cases))
    rng = random.Random(cfg.get("seed", 42))
    pool = _materials(kb_conn, stats)
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
    ]
    samples = []
    multi_index = 0
    for idx in range(n_requests):
        mode = request_modes[idx % len(request_modes)]
        n = mode or 3
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
            count_hint = f"{mode}篇" if mode else ""
            messages = [
                {"role": "system", "content": build_system_prompt(max_questions=q)},
                {"role": "user", "content": f"请围绕“{topic}”写{count_hint}普法文章。"},
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
                    "kind": f"n{n}" if mode else "n3_default",
                    "doc_id": plan[0][0].doc_id,
                    "clause_ids": ids,
                    "plan": meta_plan,
                    "n_requested": n,
                    "max_questions": q,
                    "tokens": length,
                    "request": idx + 1,
                },
            }
            _, duplicates = dedup_against_eval([sample], questions)
            if duplicates:
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
