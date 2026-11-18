"""SC-016 判定与 run 对比（T076）。

`tu eval compare --sc016 <base_run> <trained_run>`：输入未经微调的基座 run 与同一
基座的自训模型 run（同一评测集），按 spec SC-016 的三项条件判定"模型是否从训练
中学到了知识"：

1. 条级命中（宽松解析《文件名》第N条）显著多于基座（Fisher 双侧 p < 0.05）；
2. 款/项级精确命中（严格口径 `scores.cited_clause_ids`）比例 >= 10%；
3. 在"基座从未正确识别过 gold 文件"的用例子集上，文件级命中显著多于基座
   （Fisher 双侧 p < 0.05）；子集为空时无法判定。

已知输入冲突（不同基座、adapter 充当基座、诊断集、残缺结果）抛 `CompareError`，
由 CLI 以"输入错误"返回 2；字段缺失导致无法确认可比性时返回"无法判定"（非零）。

口径与 scripts/experiments/e002/review_stats.py（宽松解析、Fisher）及
scripts/experiments/e003/sc016.py（判定与文件子集定义）一致。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from math import comb
from pathlib import Path

from ..kb.numbers import chinese_to_int
from ..kb.store import open_kb
from ..manifest import read_manifest

_NUM = r"[0-9零〇一二三四五六七八九十百千]+"
RE_LOOSE = re.compile(rf"《([^》]+)》(?:（[^）]*）)?(?:第({_NUM})条)?")

FISHER_ALPHA = 0.05
PARA_RATIO_THRESHOLD = 0.10
ADAPTER_MODEL = "default_model"
DIAGNOSTIC_SOURCES = {"train_probe"}


class CompareError(ValueError):
    """输入的 run 不存在、已知冲突（不同基座/诊断集/残缺）或数据不完整。"""


@dataclass
class EvalRunResults:
    run_id: str
    dir: Path
    manifest: dict
    rows: dict[str, dict]  # case_id -> results.jsonl 行


def load_run(artifacts_dir: str | Path, run_id: str) -> EvalRunResults:
    """从 artifacts/eval/<run_id>/ 读取 manifest 与 results.jsonl。"""
    d = Path(artifacts_dir) / "eval" / run_id
    if not d.is_dir():
        raise CompareError(f"找不到评测产物目录：{d}")
    manifest_path = d / "manifest.json"
    try:
        manifest = read_manifest(d)
    except FileNotFoundError as e:
        raise CompareError(f"缺少 manifest.json：{manifest_path}") from e
    except json.JSONDecodeError as e:
        raise CompareError(f"manifest.json 不是合法 JSON：{manifest_path}（{e}）") from e
    if not isinstance(manifest, dict):
        raise CompareError(f"manifest.json 不是 JSON 对象：{manifest_path}")
    res_file = d / "results.jsonl"
    if not res_file.is_file():
        raise CompareError(f"缺少 results.jsonl：{res_file}")
    rows: dict[str, dict] = {}
    dupes = set()
    total = 0
    for lineno, line in enumerate(res_file.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as e:
            raise CompareError(f"results.jsonl 第 {lineno} 行不是合法 JSON：{res_file}") from e
        if not isinstance(row, dict):
            raise CompareError(f"{run_id} 的 results.jsonl 第 {lineno} 行不是 JSON 对象")
        total += 1
        cid = row.get("case_id")
        if cid is None:
            raise CompareError(f"{run_id} 的 results.jsonl 第 {lineno} 行无 case_id")
        if cid in rows:
            dupes.add(cid)
        rows[cid] = row
    if dupes:
        raise CompareError(f"{run_id} 存在重复 case_id：{sorted(dupes)}")
    declared = manifest.get("case_count")
    if declared is not None and declared != total:
        raise CompareError(f"{run_id} manifest 声明 case_count={declared}，实际 {total} 行")
    return EvalRunResults(run_id=run_id, dir=d, manifest=manifest, rows=rows)


@dataclass
class CasesCheck:
    """评测集文件核对结果：issue 非空 = 无法核对来源；case_ids = 实际加载的用例 ID。"""

    issue: str | None
    case_ids: set[str] | None


def cases_source_check(cases: str | None) -> CasesCheck:
    """核对评测集来源并加载用例 ID（与 eval.cases.load_cases 的加载方式对齐）。

    发现诊断集（路径特征或用例 source=train_probe）抛 CompareError。
    无法核对（路径不存在、无 .jsonl、没有任何用例）返回带原因的 CasesCheck，
    由调用方按"无法判定"处理。
    """
    if not cases:
        return CasesCheck(issue=None, case_ids=None)  # 缺失在可比性检查里单独报
    p = Path(str(cases))
    if "diagnostics" in p.parts or "probe" in p.name:
        raise CompareError(f"评测集是诊断集（{cases}），不得用于 SC 判定")
    files = sorted(p.glob("*.jsonl")) if p.is_dir() else ([p] if p.is_file() else [])
    if not files:
        return CasesCheck(
            issue=f"无法核对评测集来源：{cases} 不存在或不含 .jsonl 文件",
            case_ids=None,
        )
    ids: set[str] = set()
    for f in files:
        if "diagnostics" in f.parts or "probe" in f.name:
            raise CompareError(f"评测集文件是诊断集（{f}），不得用于 SC 判定")
        for lineno, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError as e:
                raise CompareError(f"评测集文件第 {lineno} 行不是合法 JSON：{f}") from e
            if not isinstance(d, dict):
                raise CompareError(f"评测集文件第 {lineno} 行不是 JSON 对象：{f}")
            if d.get("source") in DIAGNOSTIC_SOURCES:
                raise CompareError(
                    f"评测集 {f} 含诊断来源用例（source={d.get('source')}），不得用于 SC 判定"
                )
            cid = d.get("case_id")
            if isinstance(cid, str):
                ids.add(cid)
    if not ids:
        return CasesCheck(
            issue=f"无法核对评测集来源：{cases} 未包含任何用例",
            case_ids=None,
        )
    return CasesCheck(issue=None, case_ids=ids)


def comparability_issues(base: EvalRunResults, trained: EvalRunResults) -> list[str]:
    """核对两个 run 的可比性。已知冲突抛 CompareError；返回"无法确认"的原因列表。

    返回非空列表时，调用方应输出"无法判定"并以非零退出（字段缺失，无法确认
    同基座/同设置），而不是当作通过。JSON null 与缺失同等对待。
    最后核对各 run 的结果 case_id 与其 manifest 所指评测集的实际用例一致——
    同一文件被清空（无法核对）或替换（ID 冲突）都不能放行。
    """
    bi = base.manifest.get("inputs") or {}
    ti = trained.manifest.get("inputs") or {}
    reasons: list[str] = []
    checks: list[tuple[EvalRunResults, CasesCheck]] = []
    for run, mi in ((base, bi), (trained, ti)):
        chk = cases_source_check(mi.get("cases"))
        if chk.issue:
            reasons.append(f"{run.run_id}：{chk.issue}")
        checks.append((run, chk))
    for key, label in (("kb", "知识库"), ("cases", "评测集")):
        bv, tv = bi.get(key), ti.get(key)
        if bv and tv:
            if Path(str(bv)).name != Path(str(tv)).name:
                raise CompareError(f"{label}不一致：{bv} vs {tv}")
        else:
            reasons.append(f"manifest 缺少 inputs.{key}，无法确认两边{label}一致")
    bc = base.manifest.get("config") or {}
    tc = trained.manifest.get("config") or {}
    for key in ("temperature", "use_system_prompt"):
        bv, tv = bc.get(key), tc.get(key)
        if bv is not None and tv is not None and bv != tv:
            raise CompareError(f"评测设置 {key} 不一致：{bv!r} vs {tv!r}")
        if bv is None or tv is None:
            reasons.append(f"manifest 缺少 config.{key}，无法确认评测设置一致")
    for run, chk in checks:
        if chk.case_ids is not None and chk.case_ids != set(run.rows):
            only_eval = sorted(chk.case_ids - set(run.rows))[:5]
            only_res = sorted(set(run.rows) - chk.case_ids)[:5]
            raise CompareError(
                f"{run.run_id} 的结果与评测集用例不一致："
                f"仅在评测集 {only_eval}，仅在结果 {only_res}"
            )
    return reasons


def role_issues(base: EvalRunResults, trained: EvalRunResults) -> list[str]:
    """核对两个 run 的模型角色。已知冲突抛 CompareError；无法确认返回原因列表。

    E002 的路由证据：config.model 是实际请求的模型名；只有 default_model 会挂
    adapter；自训 run 的 adapter 与实际基座记录在 config.exp 和 config.base_model。
    inputs.exp_id 只记录提交给服务端的实验标识，裸基座 run 也可能带，不作证据。
    """
    bc = base.manifest.get("config") or {}
    tc = trained.manifest.get("config") or {}
    bm, tm = bc.get("model"), tc.get("model")
    if bm is None or tm is None:
        return ["manifest 缺少 config.model，无法确认两个 run 的模型角色"]
    if bm == ADAPTER_MODEL:
        raise CompareError(
            f"基座 run 的 config.model={ADAPTER_MODEL}（exp={bc.get('exp')}），"
            "它挂的是 adapter，不是未训练基座"
        )
    if tm != ADAPTER_MODEL:
        raise CompareError(
            f"自训 run 的 config.model={tm}，不是 {ADAPTER_MODEL}，"
            "它评测的是未挂 adapter 的模型，不能放在自训位置"
        )
    reasons: list[str] = []
    if not tc.get("exp"):
        reasons.append("自训 run 缺少 config.exp，无法确认 adapter 身份")
    tb = tc.get("base_model")
    if not tb:
        reasons.append("自训 run 缺少 config.base_model，无法确认它与基座 run 是同一底座")
    elif tb != bm:
        raise CompareError(
            f"基座不一致：基座 run 实际请求 {bm}，自训 run 记录的底座是 {tb}"
        )
    return reasons


def _is_str_list(v: object) -> bool:
    return isinstance(v, list) and all(isinstance(x, str) for x in v)


def _users(row: dict) -> list:
    return [t.get("user") for t in row.get("turns") or []]


def align_cases(base: EvalRunResults, trained: EvalRunResults) -> list[tuple[str, dict, dict]]:
    """按 case_id 对齐两侧结果，返回 (case_id, base_row, trained_row) 的 clause_id 用例。

    同时校验计分所需字段：final_raw 必须存在（空串是合法的无引用回答），
    scores.cited_clause_ids 键必须存在（显式空列表是合法未命中）。
    """
    b_ids, t_ids = set(base.rows), set(trained.rows)
    if b_ids != t_ids:
        raise CompareError(
            "两侧用例集合不同："
            f"仅在基座 {sorted(b_ids - t_ids)[:5]}，仅在自训 {sorted(t_ids - b_ids)[:5]}"
        )
    mismatch = []
    for cid in sorted(b_ids):
        br, tr = base.rows[cid], trained.rows[cid]
        if br.get("category") != tr.get("category"):
            mismatch.append(f"{cid}: category 不一致")
        if _users(br) != _users(tr):
            mismatch.append(f"{cid}: 用户提问不一致")
        if br.get("gold") != tr.get("gold"):
            mismatch.append(f"{cid}: gold 不一致")
    if mismatch:
        raise CompareError("同 ID 用例内容不一致：" + "；".join(mismatch[:10]))
    kept, invalid, missing = [], [], []
    for cid in sorted(b_ids):
        br, tr = base.rows[cid], trained.rows[cid]
        if br.get("category") != "clause_id":
            continue
        clauses = (br.get("gold") or {}).get("clauses") or []
        if len(clauses) != 1:
            invalid.append(f"{cid}（gold 条款数 {len(clauses)}）")
            continue
        for label, row in ((base.run_id, br), (trained.run_id, tr)):
            if "final_raw" not in row:
                missing.append(f"{label} 用例 {cid} 缺失 final_raw")
            elif not isinstance(row["final_raw"], str):
                missing.append(f"{label} 用例 {cid} final_raw 应为字符串")
            scores = row.get("scores")
            if not isinstance(scores, dict) or "cited_clause_ids" not in scores:
                missing.append(f"{label} 用例 {cid} 缺失 scores.cited_clause_ids")
            elif not _is_str_list(scores["cited_clause_ids"]):
                missing.append(f"{label} 用例 {cid} scores.cited_clause_ids 应为字符串列表")
        kept.append((cid, br, tr))
    if invalid:
        raise CompareError("clause_id 用例要求恰好一个 gold 条款：" + "、".join(invalid))
    if missing:
        raise CompareError("计分字段缺失：" + "；".join(missing[:10]))
    if not kept:
        raise CompareError("没有 category=clause_id 的用例")
    return kept


def load_doc_index(kb_path: str | Path) -> list[tuple[str, str]]:
    """读取历史知识库的文件名映射：[(doc_id, title)]。"""
    conn = open_kb(kb_path)
    try:
        return conn.execute("select doc_id, title from legal_documents").fetchall()
    finally:
        conn.close()


def resolve_kb_path(manifest: dict, artifacts_dir: str | Path) -> Path:
    """manifest inputs.kb 是相对仓库的路径；跨工作区时退回 artifacts_dir/kb/ 同名文件。"""
    stored = (manifest.get("inputs") or {}).get("kb")
    if not stored:
        raise CompareError("manifest 缺少 inputs.kb，无法定位知识库")
    p = Path(stored)
    if p.is_file():
        return p
    alt = Path(artifacts_dir) / "kb" / p.name
    if alt.is_file():
        return alt
    raise CompareError(f"知识库文件不存在：{p}（备选 {alt} 也不存在）")


def _norm(title: str) -> str:
    return title.replace("中华人民共和国", "")


def loose(raw: str, docs: list[tuple[str, str]]) -> tuple[set[str], set[str]]:
    """宽松解析输出里的 `《文件名》第N条` 引用。

    返回 (article_ids, doc_ids)：article 为 "doc_id:aN"；单独的《文件名》计文件命中。
    """
    articles, doc_hits = set(), set()
    for m in RE_LOOSE.finditer(raw):
        t = _norm(m.group(1))
        cand = [d for d, tt in docs if _norm(tt) == t] or [
            d for d, tt in docs if t in _norm(tt) or _norm(tt) in t
        ]
        if not cand:
            continue
        doc_hits.add(cand[0])
        if m.group(2):
            n = chinese_to_int(m.group(2))
            if n is not None:
                articles.add(f"{cand[0]}:a{n}")
    return articles, doc_hits


def fisher_exact_two_sided(a: int, b: int, c: int, d: int) -> float:
    """2x2 列联表 [[a,b],[c,d]] 的 Fisher 双侧 p 值。"""
    n, r1, c1 = a + b + c + d, a + b, a + c

    def p(x: int) -> float:
        return comb(r1, x) * comb(n - r1, c1 - x) / comb(n, c1)

    p0 = p(a)
    lo, hi = max(0, c1 - (n - r1)), min(r1, c1)
    return sum(p(x) for x in range(lo, hi + 1) if p(x) <= p0 + 1e-12)


@dataclass
class CaseHits:
    doc: bool  # 找对文件（宽松）
    article: bool  # 找对条（宽松：文件 ID + 条号，带款/项也算）
    paragraph: bool  # 条、款、项都精确（严格口径，校验层解析/纠正后）


def score_case(row: dict, docs: list[tuple[str, str]]) -> CaseHits:
    gold = row["gold"]["clauses"][0]
    articles, doc_hits = loose(row.get("final_raw") or "", docs)
    return CaseHits(
        doc=gold.split(":")[0] in doc_hits,
        article=":".join(gold.split(":")[:2]) in articles,
        paragraph=gold in set(row.get("scores", {}).get("cited_clause_ids") or []),
    )


@dataclass
class Sc016Result:
    n: int
    cond1_base: int
    cond1_trained: int
    cond1_p: float
    cond2_trained: int
    cond2_ratio: float
    subset_n: int
    cond3_base: int
    cond3_trained: int
    cond3_p: float | None
    cond1_ok: bool
    cond2_ok: bool
    cond3_ok: bool | None  # None = 子集为空，无法判定

    @property
    def passed(self) -> bool:
        return self.cond1_ok and self.cond2_ok and self.cond3_ok is True


def sc016(aligned: list[tuple[str, dict, dict]], docs: list[tuple[str, str]]) -> Sc016Result:
    """对已对齐的 clause_id 用例执行 SC-016 三项判定。"""
    n = len(aligned)
    scored = [(cid, row, score_case(row, docs)) for cid, _, row in aligned]
    base_hits = {cid: score_case(br, docs) for cid, br, _ in aligned}

    cond1_base = sum(base_hits[cid].article for cid, _, _ in aligned)
    cond1_trained = sum(h.article for _, _, h in scored)
    cond1_p = fisher_exact_two_sided(cond1_base, n - cond1_base, cond1_trained, n - cond1_trained)
    cond1_ok = cond1_trained > cond1_base and cond1_p < FISHER_ALPHA

    cond2_trained = sum(h.paragraph for _, _, h in scored)
    cond2_ratio = cond2_trained / n
    cond2_ok = cond2_ratio >= PARA_RATIO_THRESHOLD

    # 条件③子集：gold 文件从未被基座正确识别的用例
    known_docs = set()
    for cid, br, _ in aligned:
        if base_hits[cid].doc:
            known_docs.add(br["gold"]["clauses"][0].split(":")[0])
    subset = [
        (cid, row, hits)
        for cid, row, hits in scored
        if row["gold"]["clauses"][0].split(":")[0] not in known_docs
    ]
    subset_n = len(subset)
    if subset_n:
        cond3_base = sum(base_hits[cid].doc for cid, _, _ in subset)
        cond3_trained = sum(h.doc for _, _, h in subset)
        cond3_p = fisher_exact_two_sided(
            cond3_base, subset_n - cond3_base, cond3_trained, subset_n - cond3_trained
        )
        cond3_ok: bool | None = cond3_trained > cond3_base and cond3_p < FISHER_ALPHA
    else:
        cond3_base = cond3_trained = 0
        cond3_p = None
        cond3_ok = None

    return Sc016Result(
        n=n,
        cond1_base=cond1_base,
        cond1_trained=cond1_trained,
        cond1_p=cond1_p,
        cond2_trained=cond2_trained,
        cond2_ratio=cond2_ratio,
        subset_n=subset_n,
        cond3_base=cond3_base,
        cond3_trained=cond3_trained,
        cond3_p=cond3_p,
        cond1_ok=cond1_ok,
        cond2_ok=cond2_ok,
        cond3_ok=cond3_ok,
    )
