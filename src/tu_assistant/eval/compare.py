"""评测 run 对比、SC-015 重复评测稳定性与 SC-016 POC 验收判定（T076 / T062）。

三种模式：
1. 通用多 run 对比（FR-035）：`tu eval compare <run_1> <run_2> [<run_3> ...]`
   复用 `eval/report.py` 的 `summarize_run` / `extract_failures` / `load_reviews`，
   在同一评测集与同一口径下输出 `compare.md`（总体指标、差值/最大波动、按类别失败数、
   逐题状态变化）。
2. SC-015 重复评测稳定性校验：`tu eval compare --sc015 <run_1> <run_2> ...`
   在通用对比基础上叠加“同一系统版本核对”与“全部有效百分比指标最大波动 ≤ 2.0 pp”
   门禁（单侧无分母判 FAIL，0 项可评判无法判定）。
3. SC-016 判定（T076）：`tu eval compare --sc016 <base_run> <trained_run>`
   输入未经微调的基座 run 与同一基座的自训模型 run（同一评测集），按 spec SC-016
   的三项条件判定"模型是否从训练中学到了知识"：
   - 条级命中（宽松解析《文件名》第N条）显著多于基座（Fisher 双侧 p < 0.05）；
   - 款/项级精确命中（严格口径 `scores.cited_clause_ids`）比例 >= 10%；
   - 在"基座从未正确识别过 gold 文件"的用例子集上，文件级命中显著多于基座
     （Fisher 双侧 p < 0.05）；子集为空时无法判定。

已知输入冲突（不同基座、adapter 充当基座、诊断集、残缺结果）抛 `CompareError`，
由 CLI 以"输入错误"返回 2；字段缺失导致无法确认可比性时返回"无法判定"（非零）。

SC-016 口径与 scripts/experiments/e002/review_stats.py（宽松解析、Fisher）及
scripts/experiments/e003/sc016.py（判定与文件子集定义）一致。
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from math import comb
from pathlib import Path
from typing import Any

from ..kb.numbers import chinese_to_int
from ..kb.store import open_kb
from ..manifest import read_manifest, write_manifest
from .report import (
    POC_TARGETS,
    ReportError,
    extract_failures,
    load_reviews,
    summarize_run,
)

_NUM = r"[0-9零〇一二三四五六七八九十百千]+"
RE_LOOSE = re.compile(rf"《([^》]+)》(?:（[^）]*）)?(?:第({_NUM})条)?")

FISHER_ALPHA = 0.05
PARA_RATIO_THRESHOLD = 0.10
SC015_MAX_SPREAD = 0.02
SC015_EPS = 1e-9
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


def _validate_run_id(run_id: str) -> None:
    if (
        not run_id
        or run_id != run_id.strip()
        or run_id in {".", ".."}
        or "/" in run_id
        or "\\" in run_id
        or ".." in run_id
        or Path(run_id).name != run_id
    ):
        raise CompareError(f"非法的 run_id：{run_id!r}")


def load_run(artifacts_dir: str | Path, run_id: str) -> EvalRunResults:
    """从 artifacts/eval/<run_id>/ 读取 manifest 与 results.jsonl。"""
    _validate_run_id(run_id)
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
    conn = open_kb(kb_path, read_only=True)
    try:
        return conn.execute("select doc_id, title from legal_documents").fetchall()
    finally:
        conn.close()


def _kb_path_from_manifest(manifest: dict, artifacts_dir: str | Path) -> Path:
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


# ---------- 通用多 run 对比与 SC-015 稳定性校验（T062） ----------


def _setting_equal(a: object, b: object) -> bool:
    if isinstance(a, bool) != isinstance(b, bool):
        return False
    return bool(a == b)


def check_general_comparable(
    runs: list[EvalRunResults],
) -> tuple[list[str], list[str]]:
    """核对多个 run 的通用可比性。

    已知冲突（run 不足、重复 run_id、诊断集、KB/评测集/设置不一致、结果含磁盘不存在题号）
    抛 `CompareError`（退出 2）；字段缺失或磁盘路径缺失/为空归入 `issues`（退出 1）。
    磁盘目录扩题（`run.rows` 为磁盘 `cases` 真子集）放行并在 `notes` 中提示。
    """
    if len(runs) < 2:
        raise CompareError("至少需要 2 个 run 进行对比")
    seen_ids: set[str] = set()
    dup_ids: set[str] = set()
    for r in runs:
        if r.run_id in seen_ids:
            dup_ids.add(r.run_id)
        seen_ids.add(r.run_id)
    if dup_ids:
        raise CompareError(f"存在重复的 run_id：{sorted(dup_ids)}")

    issues: list[str] = []
    notes: list[str] = []
    checks: list[tuple[EvalRunResults, CasesCheck]] = []
    for run in runs:
        mi = run.manifest.get("inputs") or {}
        chk = cases_source_check(mi.get("cases"))
        if chk.issue:
            issues.append(f"{run.run_id}：{chk.issue}")
        checks.append((run, chk))

    for key, label in (("kb", "知识库"), ("cases", "评测集")):
        vals = [(r.run_id, (r.manifest.get("inputs") or {}).get(key)) for r in runs]
        present = [(rid, str(v)) for rid, v in vals if v]
        missing = [rid for rid, v in vals if not v]
        if present:
            ref_name = Path(present[0][1]).name
            for _rid, v in present[1:]:
                if Path(v).name != ref_name:
                    desc = " vs ".join(f"{r}={val}" for r, val in present)
                    raise CompareError(f"{label}不一致：{desc}")
        if missing:
            issues.append(
                f"manifest 缺少 inputs.{key}（{', '.join(missing)}），无法确认{label}一致"
            )

    for key in ("temperature", "use_system_prompt"):
        vals = [(r.run_id, (r.manifest.get("config") or {}).get(key)) for r in runs]
        present = [(rid, v) for rid, v in vals if v is not None]
        missing = [rid for rid, v in vals if v is None]
        if present:
            ref_val = present[0][1]
            for _rid, v in present[1:]:
                if not _setting_equal(v, ref_val):
                    desc = " vs ".join(f"{r}={val!r}" for r, val in present)
                    raise CompareError(f"评测设置 {key} 不一致：{desc}")
        if missing:
            issues.append(
                f"manifest 缺少 config.{key}（{', '.join(missing)}），无法确认评测设置一致"
            )

    subset_notes_seen: set[tuple[str, int, int]] = set()
    for run, chk in checks:
        if chk.case_ids is None:
            continue
        run_case_ids = set(run.rows)
        only_res = sorted(run_case_ids - chk.case_ids)
        if only_res:
            raise CompareError(
                f"{run.run_id} 的结果包含评测集中不存在的用例：{only_res[:5]}"
            )
        if len(run_case_ids) < len(chk.case_ids):
            cases_raw = str((run.manifest.get("inputs") or {}).get("cases") or "")
            sig = (cases_raw, len(chk.case_ids), len(run_case_ids))
            if sig not in subset_notes_seen:
                subset_notes_seen.add(sig)
                notes.append(
                    f"评测集 `{cases_raw}` 后续扩题（当前磁盘共 {len(chk.case_ids)} 题），"
                    f"本次仅按历史共有 {len(run_case_ids)} 题对比"
                )
    return issues, notes


def align_general_cases(runs: list[EvalRunResults]) -> list[str]:
    """核对多个 run 的全类别用例 ID、类别、提问与 gold 一致性，返回升序 case_id 列表。"""
    if len(runs) < 2:
        raise CompareError("至少需要 2 个 run 进行对比")
    ref = runs[0]
    ref_ids = set(ref.rows)
    if not ref_ids:
        raise CompareError(f"{ref.run_id} 的评测结果为空，至少需要 1 条用例")
    for other in runs[1:]:
        o_ids = set(other.rows)
        if o_ids != ref_ids:
            raise CompareError(
                f"{ref.run_id} 与 {other.run_id} 用例集合不同："
                f"仅在 {ref.run_id} {sorted(ref_ids - o_ids)[:5]}，"
                f"仅在 {other.run_id} {sorted(o_ids - ref_ids)[:5]}"
            )

    case_ids = sorted(ref_ids)
    mismatch: list[str] = []
    for cid in case_ids:
        rr = ref.rows[cid]
        for other in runs[1:]:
            orow = other.rows[cid]
            if rr.get("category") != orow.get("category"):
                mismatch.append(f"{cid}（{other.run_id}）: category 不一致")
            if _users(rr) != _users(orow):
                mismatch.append(f"{cid}（{other.run_id}）: 用户提问不一致")
            if rr.get("gold") != orow.get("gold"):
                mismatch.append(f"{cid}（{other.run_id}）: gold 不一致")
    if mismatch:
        raise CompareError("同 ID 用例内容不一致：" + "；".join(mismatch[:10]))
    return case_ids


def same_system_issues(runs: list[EvalRunResults]) -> list[str]:
    """核对多个 run 是否为同一系统版本（供 SC-015 使用）。

    已知冲突（model / exp / base_model 不一致）抛 `CompareError`（退出 2）；
    字段缺失归入返回列表（无法判定，退出 1）。
    """
    issues: list[str] = []
    models = [(r.run_id, (r.manifest.get("config") or {}).get("model")) for r in runs]
    present_models = [(rid, m) for rid, m in models if isinstance(m, str) and m.strip()]
    missing_models = [rid for rid, m in models if not (isinstance(m, str) and m.strip())]
    if present_models:
        ref_m = present_models[0][1]
        for _rid, m in present_models[1:]:
            if m != ref_m:
                desc = " vs ".join(f"{r}={val!r}" for r, val in present_models)
                raise CompareError(f"SC-015 要求同一系统版本，但 config.model 不一致：{desc}")
    if missing_models:
        issues.append(
            f"manifest 缺少 config.model（{', '.join(missing_models)}），"
            "无法确认属于同一系统版本"
        )

    adapter_runs = [
        r for r in runs if (r.manifest.get("config") or {}).get("model") == ADAPTER_MODEL
    ]
    if adapter_runs:
        adapter_fields = (
            ("exp", "实验/adapter（config.exp）"),
            ("base_model", "基座（config.base_model）"),
        )
        for key, label in adapter_fields:
            vals = [(r.run_id, (r.manifest.get("config") or {}).get(key)) for r in adapter_runs]
            present = [(rid, v) for rid, v in vals if isinstance(v, str) and v.strip()]
            missing = [rid for rid, v in vals if not (isinstance(v, str) and v.strip())]
            if present:
                ref_v = present[0][1]
                for _rid, v in present[1:]:
                    if v != ref_v:
                        desc = " vs ".join(f"{r}={val!r}" for r, val in present)
                        raise CompareError(f"SC-015 要求同一系统版本，但 {label} 不一致：{desc}")
            if missing:
                issues.append(
                    f"default_model run 缺少 {label}（{', '.join(missing)}），"
                    "无法确认属于同一系统版本"
                )
    return issues


@dataclass(frozen=True)
class MetricRow:
    code: str
    name: str
    values: tuple[float | None, ...]
    cells: tuple[str, ...]
    delta: float | None
    spread: float | None
    partial_none: bool
    poc_target: str


@dataclass(frozen=True)
class AuxiliaryRow:
    code: str
    name: str
    cells: tuple[str, ...]
    note: str = ""


@dataclass(frozen=True)
class CaseTransition:
    case_id: str
    category: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ComparisonResult:
    runs: tuple[EvalRunResults, ...]
    case_ids: tuple[str, ...]
    summaries: tuple[dict[str, Any], ...]
    failures_by_run: tuple[dict[str, list[str]], ...]
    metrics: tuple[MetricRow, ...]
    auxiliary: tuple[AuxiliaryRow, ...]
    categories: tuple[str, ...]
    newly_passed: tuple[CaseTransition, ...]
    regressed: tuple[CaseTransition, ...]
    always_passed: int
    always_failed: int
    reason_changed_count: int
    flip_matrix: tuple[tuple[str, str, tuple[bool, ...]], ...]  # (case_id, cat, per_run_passed)
    notes: tuple[str, ...] = ()
    reviews_path: str | None = None

    @property
    def case_count(self) -> int:
        return len(self.case_ids)


@dataclass(frozen=True)
class Sc015MetricCheck:
    code: str
    name: str
    values: tuple[float | None, ...]
    spread: float | None
    status: str  # "pass" | "fail" | "skipped"
    reason: str


@dataclass(frozen=True)
class Sc015Result:
    threshold: float
    checks: tuple[Sc015MetricCheck, ...]
    evaluated_count: int
    failed_count: int
    passed: bool | None  # True=PASS, False=FAIL, None=无法判定（0 项有效指标）


def _fmt_ratio_cell(val: float | None, num: int, den: int) -> str:
    if val is None or den == 0:
        return f"-（{num}/{den}）"
    return f"{val:.3f}（{num}/{den}）"


def _fmt_mean_cell(val: float | None, n: int) -> str:
    if val is None or n == 0:
        return f"-（n={n}）"
    return f"{val:.3f}（n={n}）"


def _fmt_manual_cell(agg: dict[str, Any], *, is_sc010: bool = False) -> str:
    val = agg.get("value")
    total = int(agg.get("total", 0))
    eligible = int(agg.get("eligible_cases", 0))
    if val is None or total == 0:
        if eligible == 0:
            return "-（无适用题）"
        return f"-（待评审，{eligible} 题）"
    counts = agg.get("counts") or {}
    num = int(counts.get("fail", 0)) if is_sc010 else int(counts.get("pass", 0))
    return f"{val:.3f}（{num}/{total}）"


_MetricExtractor = tuple[
    str,
    str,
    Callable[[dict[str, Any]], float | None],
    Callable[[dict[str, Any]], str],
    str,
]

_COMPARED_METRICS: tuple[_MetricExtractor, ...] = (
    (
        "SC-001",
        "意图确认率（≤3 轮）",
        lambda s: s["sc001"]["value"],
        lambda s: _fmt_ratio_cell(s["sc001"]["value"], s["sc001"]["hits"], s["sc001"]["total"]),
        POC_TARGETS["SC-001"],
    ),
    (
        "SC-002",
        "条款识别召回率",
        lambda s: s["sc002"]["value"],
        lambda s: _fmt_mean_cell(s["sc002"]["value"], s["sc002"]["n"]),
        POC_TARGETS["SC-002"],
    ),
    (
        "SC-003",
        "条款识别精确率",
        lambda s: s["sc003"]["value"],
        lambda s: _fmt_mean_cell(s["sc003"]["value"], s["sc003"]["n"]),
        POC_TARGETS["SC-003"],
    ),
    (
        "SC-004",
        "多违法行为识别率",
        lambda s: s["sc004"]["value"],
        lambda s: _fmt_mean_cell(s["sc004"]["value"], s["sc004"]["n"]),
        POC_TARGETS["SC-004"],
    ),
    (
        "SC-005",
        "关联条款完整率",
        lambda s: s["sc005"]["value"],
        lambda s: _fmt_mean_cell(s["sc005"]["value"], s["sc005"]["n"]),
        POC_TARGETS["SC-005"],
    ),
    (
        "SC-006",
        "出处标注完整率",
        lambda s: s["sc006"]["value"],
        lambda s: _fmt_ratio_cell(
            s["sc006"]["value"], s["sc006"]["complete"], s["sc006"]["total"]
        ),
        POC_TARGETS["SC-006"],
    ),
    (
        "SC-007（校验前）",
        "条款引用准确率（校验前·全分母）",
        lambda s: s["sc007"]["pre"],
        lambda s: _fmt_ratio_cell(
            s["sc007"]["pre"], s["sc007"]["counts"]["ok"], s["sc007"]["total"]
        ),
        POC_TARGETS["SC-007"],
    ),
    (
        "SC-007（校验后）",
        "条款引用准确率（校验后·全分母）",
        lambda s: s["sc007"]["post"],
        lambda s: _fmt_ratio_cell(
            s["sc007"]["post"],
            s["sc007"]["counts"]["ok"] + s["sc007"]["counts"]["corrected"],
            s["sc007"]["total"],
        ),
        POC_TARGETS["SC-007"],
    ),
    (
        "SC-008（范围外）",
        "范围外正确拒答率",
        lambda s: s["sc008"]["outside_rate"],
        lambda s: _fmt_ratio_cell(
            s["sc008"]["outside_rate"],
            s["sc008"]["outside_hits"],
            s["sc008"]["outside_total"],
        ),
        "≥95%",
    ),
    (
        "SC-008（误拒）",
        "范围内误拒率",
        lambda s: s["sc008"]["false_refusal_rate"],
        lambda s: _fmt_ratio_cell(
            s["sc008"]["false_refusal_rate"],
            s["sc008"]["false_refusal_hits"],
            s["sc008"]["false_refusal_total"],
        ),
        "≤5%",
    ),
    (
        "SC-009",
        "普法文章正确性",
        lambda s: s["sc009"]["value"],
        lambda s: _fmt_manual_cell(s["sc009"], is_sc010=False),
        POC_TARGETS["SC-009"],
    ),
    (
        "SC-010",
        "普法文章实质重复率",
        lambda s: s["sc010"]["value"],
        lambda s: _fmt_manual_cell(s["sc010"], is_sc010=True),
        POC_TARGETS["SC-010"],
    ),
    (
        "SC-011",
        "普法文章身份无泄露率",
        lambda s: s["sc011"]["ratio"],
        lambda s: _fmt_ratio_cell(
            s["sc011"]["ratio"], s["sc011"]["passed"], s["sc011"]["total"]
        ),
        POC_TARGETS["SC-011"],
    ),
)


def compare_runs(
    runs: list[EvalRunResults],
    *,
    reviews_path: str | Path | None = None,
    notes: list[str] | None = None,
) -> ComparisonResult:
    """对已通过可比性核对的多个 run 聚合对比指标与逐题变化。"""
    case_ids = align_general_cases(runs)
    summaries: list[dict[str, Any]] = []
    failures_by_run: list[dict[str, list[str]]] = []

    for run in runs:
        results_list = [run.rows[cid] for cid in case_ids]
        if reviews_path is not None:
            try:
                reviews = load_reviews(reviews_path, run_id=run.run_id, results=results_list)
            except ReportError as exc:
                raise CompareError(str(exc)) from exc
        else:
            reviews = None
        failures = extract_failures(results_list, reviews=reviews)
        summary = summarize_run(
            results_list,
            reviews=reviews,
            run_id=run.run_id,
            _failures=failures,
        )
        summaries.append(summary)
        failures_by_run.append({f["case_id"]: list(f["reasons"]) for f in failures})

    metric_rows: list[MetricRow] = []
    for code, name, get_val, fmt_cell, target in _COMPARED_METRICS:
        vals = tuple(get_val(s) for s in summaries)
        cells = tuple(fmt_cell(s) for s in summaries)
        non_null = [v for v in vals if v is not None]
        if not non_null:
            delta: float | None = None
            spread: float | None = None
            partial_none = False
        elif len(non_null) < len(vals):
            delta = None
            spread = None
            partial_none = True
        else:
            raw_delta = vals[-1] - vals[0]  # type: ignore[operator]
            delta = 0.0 if abs(raw_delta) < 1e-12 else raw_delta
            raw_spread = max(non_null) - min(non_null)
            spread = 0.0 if abs(raw_spread) < 1e-12 else raw_spread
            partial_none = False
        metric_rows.append(
            MetricRow(
                code=code,
                name=name,
                values=vals,
                cells=cells,
                delta=delta,
                spread=spread,
                partial_none=partial_none,
                poc_target=target,
            )
        )

    aux_rows: list[AuxiliaryRow] = [
        AuxiliaryRow(
            code="对照",
            name="SC-007（已定位·校验前）",
            cells=tuple(
                _fmt_ratio_cell(
                    s["sc007"]["resolved_pre"],
                    s["sc007"]["counts"]["ok"],
                    s["sc007"]["resolved_total"],
                )
                for s in summaries
            ),
            note="排除 incomplete",
        ),
        AuxiliaryRow(
            code="对照",
            name="SC-007（已定位·校验后）",
            cells=tuple(
                _fmt_ratio_cell(
                    s["sc007"]["resolved_post"],
                    s["sc007"]["counts"]["ok"] + s["sc007"]["counts"]["corrected"],
                    s["sc007"]["resolved_total"],
                )
                for s in summaries
            ),
            note="排除 incomplete",
        ),
        AuxiliaryRow(
            code="分布",
            name="引用判定分布（ok/corr/nf/inc）",
            cells=tuple(
                f"{s['sc007']['counts']['ok']}/{s['sc007']['counts']['corrected']}/"
                f"{s['sc007']['counts']['not_found']}/{s['sc007']['counts']['incomplete']}"
                for s in summaries
            ),
            note="非门禁",
        ),
        AuxiliaryRow(
            code="辅助",
            name="引用冲突暂缓交稿（T054）",
            cells=tuple(f"{len(s['auxiliary']['blocked_turns'])} 轮" for s in summaries),
            note="非门禁",
        ),
        AuxiliaryRow(
            code="辅助",
            name="文章篇数符合（FR-028）",
            cells=tuple(
                f"{s['auxiliary']['article_count_ok']}/{s['auxiliary']['article_count_total']}"
                if s["auxiliary"]["article_count_total"] > 0
                else "-"
                for s in summaries
            ),
            note="非门禁",
        ),
    ]

    all_cats = sorted({cat for s in summaries for cat in s["by_category"]})

    base_fail = failures_by_run[0]
    last_fail = failures_by_run[-1]
    newly_passed: list[CaseTransition] = []
    regressed: list[CaseTransition] = []
    always_passed = 0
    always_failed = 0
    reason_changed_count = 0
    flip_matrix: list[tuple[str, str, tuple[bool, ...]]] = []

    for cid in case_ids:
        cat = str(runs[0].rows[cid].get("category", ""))
        b_failed = cid in base_fail
        l_failed = cid in last_fail
        if b_failed and not l_failed:
            newly_passed.append(
                CaseTransition(case_id=cid, category=cat, reasons=tuple(base_fail[cid]))
            )
        elif not b_failed and l_failed:
            regressed.append(
                CaseTransition(case_id=cid, category=cat, reasons=tuple(last_fail[cid]))
            )
        elif not b_failed and not l_failed:
            always_passed += 1
        else:
            always_failed += 1
            if base_fail[cid] != last_fail[cid]:
                reason_changed_count += 1

        per_run_passed = tuple(cid not in fdict for fdict in failures_by_run)
        if len(set(per_run_passed)) > 1:
            flip_matrix.append((cid, cat, per_run_passed))

    return ComparisonResult(
        runs=tuple(runs),
        case_ids=tuple(case_ids),
        summaries=tuple(summaries),
        failures_by_run=tuple(failures_by_run),
        metrics=tuple(metric_rows),
        auxiliary=tuple(aux_rows),
        categories=tuple(all_cats),
        newly_passed=tuple(newly_passed),
        regressed=tuple(regressed),
        always_passed=always_passed,
        always_failed=always_failed,
        reason_changed_count=reason_changed_count,
        flip_matrix=tuple(flip_matrix),
        notes=tuple(notes or []),
        reviews_path=str(reviews_path) if reviews_path is not None else None,
    )


def _fmt_sc015_pp(spread: float, threshold: float) -> str:
    """格式化 SC-015 波动百分点；超限但 .1f 舍入后与阈值相等时自动提高精度避免歧义。"""
    base = f"{spread * 100:.1f}"
    thr = f"{threshold * 100:.1f}"
    if spread > threshold + SC015_EPS and base == thr:
        for digits in (2, 3, 4):
            cand = f"{spread * 100:.{digits}f}"
            if float(cand) > float(thr):
                return f"{cand} pp"
        return f"{spread * 100:.6g} pp"
    return f"{base} pp"


def evaluate_sc015(
    comparison: ComparisonResult,
    *,
    threshold: float = SC015_MAX_SPREAD,
) -> Sc015Result:
    """按 SC-015 判定同模型重复评测波动是否 ≤ 2.0 个百分点。"""
    checks: list[Sc015MetricCheck] = []
    evaluated = 0
    failed = 0
    for m in comparison.metrics:
        if all(v is None for v in m.values):
            checks.append(
                Sc015MetricCheck(
                    code=m.code,
                    name=m.name,
                    values=m.values,
                    spread=None,
                    status="skipped",
                    reason="无样本/待评审",
                )
            )
            continue
        evaluated += 1
        if m.partial_none or m.spread is None:
            failed += 1
            checks.append(
                Sc015MetricCheck(
                    code=m.code,
                    name=m.name,
                    values=m.values,
                    spread=None,
                    status="fail",
                    reason="部分 run 无有效分母",
                )
            )
            continue
        if m.spread <= threshold + SC015_EPS:
            checks.append(
                Sc015MetricCheck(
                    code=m.code,
                    name=m.name,
                    values=m.values,
                    spread=m.spread,
                    status="pass",
                    reason=f"{m.spread * 100:.1f} pp ≤ {threshold * 100:.1f} pp",
                )
            )
        else:
            failed += 1
            sp_text = _fmt_sc015_pp(m.spread, threshold)
            checks.append(
                Sc015MetricCheck(
                    code=m.code,
                    name=m.name,
                    values=m.values,
                    spread=m.spread,
                    status="fail",
                    reason=f"波动 {sp_text} > {threshold * 100:.1f} pp",
                )
            )

    if evaluated == 0:
        passed: bool | None = None
    else:
        passed = failed == 0

    return Sc015Result(
        threshold=threshold,
        checks=tuple(checks),
        evaluated_count=evaluated,
        failed_count=failed,
        passed=passed,
    )


def _esc_cell(text: str) -> str:
    return (
        text.replace("|", "\\|")
        .replace("\r\n", " ")
        .replace("\r", " ")
        .replace("\n", " ")
    )


def _fmt_delta(m: MetricRow) -> str:
    if m.partial_none:
        return "无法比较（部分无样本）"
    if m.delta is None:
        return "-"
    return f"{m.delta:+.3f}（{m.delta * 100:+.1f} pp）"


def _fmt_spread(m: MetricRow) -> str:
    if m.partial_none:
        return "无法比较（部分无样本）"
    if m.spread is None:
        return "-"
    return f"{m.spread * 100:.1f} pp"


def _run_model_desc(run: EvalRunResults) -> str:
    cfg = run.manifest.get("config") or {}
    model = cfg.get("model")
    base = cfg.get("base_model")
    if model == ADAPTER_MODEL and base:
        return f"{base}（adapter）"
    if model:
        return str(model)
    return "-"


def _run_exp_desc(run: EvalRunResults) -> str:
    cfg = run.manifest.get("config") or {}
    inp = run.manifest.get("inputs") or {}
    exp = cfg.get("exp") or inp.get("exp_id")
    return str(exp) if exp else "-"


def render_compare_markdown(
    comparison: ComparisonResult,
    *,
    sc015_result: Sc015Result | None = None,
) -> str:
    """渲染多 run 对比报告 compare.md。"""
    runs = comparison.runs
    ref_manifest = runs[0].manifest
    ref_inputs = ref_manifest.get("inputs") or {}
    ref_config = ref_manifest.get("config") or {}

    kb_val = ref_inputs.get("kb")
    kb_label = Path(str(kb_val)).stem if kb_val else "-"
    cases_label = str(ref_inputs.get("cases") or "-")
    temp_val = ref_config.get("temperature")
    sys_val = ref_config.get("use_system_prompt")

    run_list_str = " → ".join(
        f"`{r.run_id}`（基准）" if idx == 0 else f"`{r.run_id}`"
        for idx, r in enumerate(runs)
    )
    lines: list[str] = [
        "# 评测对比报告",
        "",
        f"- 对比 run：{run_list_str}",
        f"- 共同知识库：`{kb_label}`",
        f"- 共同评测集：`{cases_label}`（共 {comparison.case_count} 题）",
        f"- 评测设置：`temperature={temp_val}`，`use_system_prompt={sys_val}`",
    ]
    if comparison.reviews_path:
        lines.append(f"- 人工评审表：`{comparison.reviews_path}`")
    for note in comparison.notes:
        lines.append(f"- 兼容提示：{note}")

    recomp_parts = [
        f"{r.run_id}（{s['sc008']['recomputed_count']} 题）"
        for r, s in zip(runs, comparison.summaries, strict=True)
        if s["sc008"]["recomputed_count"] > 0
    ]
    if recomp_parts:
        lines.append(
            f"- SC-008 历史兼容复算：{'、'.join(recomp_parts)}"
            "（缺少 `refusal_evidence`，已按当前规则只读复算）"
        )

    lines += [
        "",
        "### 参与对比的 Run 概览",
        "",
        "| 序号 | run_id | 实验（exp） | 基座 / 请求模型 | 用例数 | 失败用例数 |",
        "|---|---|---|---|---|---|",
    ]
    for idx, (r, fdict) in enumerate(zip(runs, comparison.failures_by_run, strict=True), 1):
        role_tag = "（基准）" if idx == 1 else ""
        lines.append(
            f"| {idx} | {_esc_cell(r.run_id)}{role_tag} | "
            f"{_esc_cell(_run_exp_desc(r))} | {_esc_cell(_run_model_desc(r))} | "
            f"{comparison.case_count} | {len(fdict)} |"
        )

    lines += [
        "",
        "> **口径说明**：POC 阶段目标值仅作差距观察参考，不作为验收条件；"
        "单位 `1 pp = 0.01`（1 个百分点），差值为末轮相对基准（第 1 列）的变化。",
    ]

    if sc015_result is not None:
        ref_model = ref_config.get("model")
        if ref_model == ADAPTER_MODEL:
            sys_desc = f"`{_run_model_desc(runs[0])}`，exp=`{ref_config.get('exp')}`"
        else:
            sys_desc = f"`{_run_model_desc(runs[0])}`（未挂 adapter）"
        lines += [
            "",
            "## SC-015 重复评测稳定性判定",
            "",
            f"- 系统版本核对：一致（{sys_desc}）",
            f"- 稳定性阈值：全部有效百分比指标最大波动 ≤ {sc015_result.threshold * 100:.1f} pp（容差 1e-9）",
            f"- 有效参与判定指标：{sc015_result.evaluated_count} 项，"
            f"超限/异常：{sc015_result.failed_count} 项",
            "",
            "| 编号 | 指标 | 最大波动 | 判定 | 说明 |",
            "|---|---|---|---|---|",
        ]
        status_map = {"pass": "PASS", "fail": "FAIL", "skipped": "跳过"}
        for chk in sc015_result.checks:
            sp_str = (
                _fmt_sc015_pp(chk.spread, sc015_result.threshold)
                if chk.spread is not None
                else "-"
            )
            lines.append(
                f"| {_esc_cell(chk.code)} | {_esc_cell(chk.name)} | {sp_str} | "
                f"{status_map[chk.status]} | {_esc_cell(chk.reason)} |"
            )
        verdict = (
            "PASS"
            if sc015_result.passed is True
            else ("无法判定（无有效指标）" if sc015_result.passed is None else "FAIL")
        )
        lines += ["", f"**总判定：{verdict}**"]

    delta_header = "差值（相对基准）" if len(runs) == 2 else "末轮相对基准"
    run_headers = [
        f"{_esc_cell(r.run_id)}（基准）" if idx == 0 else _esc_cell(r.run_id)
        for idx, r in enumerate(runs)
    ]
    header_cols = ["编号", "指标", *run_headers, delta_header, "最大波动", "POC 目标值"]
    lines += [
        "",
        "## 总体指标对比（SC-001 ~ SC-011）",
        "",
        "| " + " | ".join(header_cols) + " |",
        "|" + "|".join("---" for _ in header_cols) + "|",
    ]
    for m in comparison.metrics:
        row_cols = [
            _esc_cell(m.code),
            _esc_cell(m.name),
            *(_esc_cell(c) for c in m.cells),
            _esc_cell(_fmt_delta(m)),
            _esc_cell(_fmt_spread(m)),
            _esc_cell(m.poc_target),
        ]
        lines.append("| " + " | ".join(row_cols) + " |")
    for aux in comparison.auxiliary:
        row_cols = [
            _esc_cell(aux.code),
            _esc_cell(aux.name),
            *(_esc_cell(c) for c in aux.cells),
            "-",
            "-",
            _esc_cell(aux.note or "-"),
        ]
        lines.append("| " + " | ".join(row_cols) + " |")

    cat_headers = [
        "类别",
        "用例数",
        *(f"{_esc_cell(r.run_id)} 失败数" for r in runs),
        delta_header,
    ]
    lines += [
        "",
        "## 按类别失败数对比",
        "",
        "| " + " | ".join(cat_headers) + " |",
        "|" + "|".join("---" for _ in cat_headers) + "|",
    ]
    for cat in comparison.categories:
        total = comparison.summaries[0]["by_category"].get(cat, {}).get("total", 0)
        fail_counts = [
            s["by_category"].get(cat, {}).get("failed", 0) for s in comparison.summaries
        ]
        diff = fail_counts[-1] - fail_counts[0]
        diff_str = f"{diff:+d}" if diff != 0 else "0"
        lines.append(
            "| "
            + " | ".join(
                [
                    _esc_cell(cat),
                    str(total),
                    *(str(c) for c in fail_counts),
                    diff_str,
                ]
            )
            + " |"
        )

    lines += [
        "",
        f"## 逐题状态变化（相对基准 `{runs[0].run_id}`）",
        "",
    ]
    if not comparison.flip_matrix:
        lines.append("各 run 逐题通过/失败状态无变化。")
        if comparison.reason_changed_count > 0:
            lines.append(
                f"（基准与末轮始终失败的 {comparison.always_failed} 题中，"
                f"有 {comparison.reason_changed_count} 题失败原因发生变化。）"
            )
    else:
        lines.append(
            f"- 基准（`{runs[0].run_id}`）→ 末轮（`{runs[-1].run_id}`）汇总："
            f"新通过（fail→pass）**{len(comparison.newly_passed)}** 题，"
            f"退步（pass→fail）**{len(comparison.regressed)}** 题，"
            f"始终通过 **{comparison.always_passed}** 题，"
            f"始终失败 **{comparison.always_failed}** 题"
            f"（其中失败原因变化 {comparison.reason_changed_count} 题）。"
        )
        if comparison.newly_passed:
            lines += [
                "",
                "### 新通过用例（fail → pass）",
                "",
                "| case_id | 类别 | 原失败原因 |",
                "|---|---|---|",
            ]
            for item in comparison.newly_passed:
                lines.append(
                    f"| {_esc_cell(item.case_id)} | {_esc_cell(item.category)} | "
                    f"{_esc_cell('；'.join(item.reasons))} |"
                )
        if comparison.regressed:
            lines += [
                "",
                "### 退步用例（pass → fail）",
                "",
                "| case_id | 类别 | 新失败原因 |",
                "|---|---|---|",
            ]
            for item in comparison.regressed:
                lines.append(
                    f"| {_esc_cell(item.case_id)} | {_esc_cell(item.category)} | "
                    f"{_esc_cell('；'.join(item.reasons))} |"
                )
        if len(runs) >= 3:
            mat_headers = ["case_id", "类别", *(_esc_cell(r.run_id) for r in runs)]
            lines += [
                "",
                "### 多轮状态切换矩阵",
                "",
                "| " + " | ".join(mat_headers) + " |",
                "|" + "|".join("---" for _ in mat_headers) + "|",
            ]
            for cid, cat, states in comparison.flip_matrix:
                st_cells = ["PASS" if ok else "FAIL" for ok in states]
                lines.append(
                    "| " + " | ".join([_esc_cell(cid), _esc_cell(cat), *st_cells]) + " |"
                )

    lines.append("")
    return "\n".join(lines)


def save_compare_artifact(
    artifacts_dir: str | Path,
    comparison: ComparisonResult,
    markdown: str,
    *,
    sc015_result: Sc015Result | None = None,
    timestamp: str | None = None,
) -> Path:
    """将对比报告安全落盘到 artifacts/eval/compare-<ts>/（含 compare.md 与 manifest.json）。"""
    eval_dir = Path(artifacts_dir) / "eval"
    eval_dir.mkdir(parents=True, exist_ok=True)
    ts = timestamp or datetime.now().strftime("%Y%m%d-%H%M%S")
    base_name = f"compare-{ts}"
    suffix = 1
    while True:
        compare_id = base_name if suffix == 1 else f"{base_name}-{suffix}"
        out_dir = eval_dir / compare_id
        try:
            out_dir.mkdir(parents=False, exist_ok=False)
            break
        except FileExistsError:
            suffix += 1

    (out_dir / "compare.md").write_text(markdown, encoding="utf-8")
    ref_inputs = comparison.runs[0].manifest.get("inputs") or {}
    config: dict[str, Any] = {
        "mode": "sc015" if sc015_result is not None else "general",
        "threshold_pp": round(sc015_result.threshold * 100, 3)
        if sc015_result is not None
        else None,
    }
    write_manifest(
        out_dir,
        artifact_id=compare_id,
        artifact_type="eval_compare",
        inputs={
            "runs": [r.run_id for r in comparison.runs],
            "kb": ref_inputs.get("kb"),
            "cases": ref_inputs.get("cases"),
            "reviews": comparison.reviews_path,
        },
        config=config,
        extra={
            "case_count": comparison.case_count,
            "sc015_passed": sc015_result.passed if sc015_result is not None else None,
        },
    )
    return out_dir
