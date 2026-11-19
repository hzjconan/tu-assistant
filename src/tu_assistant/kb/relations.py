"""条款关联的规则抽取、审阅辅助与事务化差异确认（T017 / T018 / T077）。

从条款原文里识别明文引用，生成候选 ClauseRelation（confirmed=false），
经人工确认后才用于训练数据、关联补全兜底与 SC-005。

方向约定：``from`` = 被引用的条款（如被违反的义务条款），
``to`` = 含有该引用的条款（如法律责任条款）。

只处理同一份文件内的引用（"本法第X条..."）；跨文件引用留到正式阶段。
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from .models import Clause, ClauseRelation
from .numbers import chinese_to_int
from .store import delete_relation, insert_relation, open_kb

VALID_RELATION_TYPES = frozenset({"liability_for", "references", "exception_of"})
VALID_DECISIONS = frozenset({"confirm", "revoke", "reject", "pending"})

_NUM = r"[0-9零〇一二三四五六七八九十百千]+"
_REF_ATOM = rf"第{_NUM}条(?:第{_NUM}款)?(?:第{_NUM}项)?"
_REF_TAIL = rf"(?:第{_NUM}条(?:第{_NUM}款)?(?:第{_NUM}项)?|第{_NUM}款(?:第{_NUM}项)?|第{_NUM}项)"
_REF_LIST = rf"{_REF_ATOM}(?:(?:、|和|或者|及|至){_REF_TAIL})*"

_RE_TOKEN_SPLIT = re.compile(r"(、|和|或者|及|至)")
_RE_SPEC = re.compile(
    rf"^(?:第(?P<art>{_NUM})条)?(?:第(?P<para>{_NUM})款)?(?:第(?P<item>{_NUM})项)?$"
)

# (正则, 关系类型)
# 注意：所有模式都要求触发词，避免把普通提及全抽进来
_PATTERNS: list[tuple[re.Pattern, str]] = [
    # "违反本法第X条（第Y款）..." → 本条款是对应条款的法律责任
    (re.compile(rf"违反本?[法条例规定办法章]*?({_REF_LIST})"), "liability_for"),
    # "（本法）第X条（第Y款）所列" → 候选（需人工甄别是否实质法律责任）
    (re.compile(rf"(?:本[法条例规定办法章]*)?({_REF_LIST})(?:规定)?所列"), "liability_for"),
    # "（本法）第X条（规定）的除外" → 本条款是对应条款的例外
    (re.compile(rf"(?:本[法条例规定办法章]*)?({_REF_LIST})(?:规定)?(?:的)?除外"), "exception_of"),
    # "依照|按照|依据|比照 本法第X条..." → 一般引用
    (re.compile(rf"(?:依照|按照|依据|比照)本?[法条例规定办法]*?({_REF_LIST})"), "references"),
]

_MAX_RANGE_SPAN = 50


class RelationImportError(ValueError):
    """关系审阅文件格式错误、端点缺失或目标 KB 不可写。"""


def _parse_ref_list(ref_list: str) -> list[tuple[int, int | None, int | None]]:
    """把连续的中文条款引用串拆解为 ``(article_no, paragraph_no, item_no)`` 列表。

    支持显式款/项、并列（`、` / `和` / `或者` / `及`）及区间（`至`）。
    """
    parts = _RE_TOKEN_SPLIT.split(ref_list)
    specs: list[tuple[int, int | None, int | None]] = []
    cur_art: int | None = None
    cur_para: int | None = None
    prev_sep: str | None = None
    prev_spec: tuple[int, int | None, int | None] | None = None

    for part in parts:
        if not part:
            continue
        if part in {"、", "和", "或者", "及", "至"}:
            prev_sep = part
            continue
        m = _RE_SPEC.match(part)
        if not m:
            prev_sep = None
            continue
        art_s, para_s, item_s = m.group("art"), m.group("para"), m.group("item")
        art = chinese_to_int(art_s) if art_s else None
        para = chinese_to_int(para_s) if para_s else None
        item = chinese_to_int(item_s) if item_s else None

        if art is not None:
            if art <= 0:
                prev_sep = None
                continue
            cur_art = art
            cur_para = para
        elif para is not None:
            if cur_art is None or para <= 0:
                prev_sep = None
                continue
            art = cur_art
            cur_para = para
        elif item is not None:
            if cur_art is None or item <= 0:
                prev_sep = None
                continue
            art = cur_art
            para = cur_para
        else:
            prev_sep = None
            continue

        if (para is not None and para <= 0) or (item is not None and item <= 0):
            prev_sep = None
            continue

        cur_spec = (art, para, item)
        if prev_sep == "至" and prev_spec is not None:
            pa, pp, pi = prev_spec
            if pp is None and pi is None and para is None and item is None and pa < art:
                if art - pa <= _MAX_RANGE_SPAN:
                    for a_no in range(pa + 1, art + 1):
                        specs.append((a_no, None, None))
            elif (
                pa == art
                and pp is not None
                and para is not None
                and pi is None
                and item is None
                and pp < para
            ):
                if para - pp <= _MAX_RANGE_SPAN:
                    for p_no in range(pp + 1, para + 1):
                        specs.append((art, p_no, None))
            elif (
                pa == art
                and pp == para
                and pi is not None
                and item is not None
                and pi < item
            ):
                if item - pi <= _MAX_RANGE_SPAN:
                    for i_no in range(pi + 1, item + 1):
                        specs.append((art, para, i_no))
            else:
                specs.append(cur_spec)
        else:
            specs.append(cur_spec)

        prev_spec = cur_spec
        prev_sep = None

    return specs


def _resolve_target_clauses(
    by_article: dict[int, list[Clause]],
    article_no: int,
    paragraph_no: int | None,
    item_no: int | None,
) -> list[tuple[Clause, str]]:
    """把目标 ``(article_no, paragraph_no, item_no)`` 解析为 ``[(Clause, scope)]``。"""
    rows = by_article.get(article_no, [])
    if not rows:
        return []

    if item_no is not None:
        if paragraph_no is not None:
            hit = next(
                (r for r in rows if r.paragraph_no == paragraph_no and r.item_no == item_no),
                None,
            )
            return [(hit, "explicit_item")] if hit else []
        item_rows = [r for r in rows if r.item_no == item_no]
        if len(item_rows) == 1:
            return [(item_rows[0], "explicit_item")]
        return []

    if paragraph_no is not None:
        hit = next(
            (r for r in rows if r.paragraph_no == paragraph_no and r.item_no is None),
            None,
        )
        return [(hit, "explicit_paragraph")] if hit else []

    # 整条引用：单款条文取主行；多款条文按款展开为多条候选（交人工逐款取舍）
    paras = sorted({r.paragraph_no for r in rows if r.paragraph_no is not None})
    if not paras:
        return [(rows[0], "single_paragraph_article")]
    scope = "whole_article_expanded" if len(paras) >= 2 else "single_paragraph_article"
    resolved: list[tuple[Clause, str]] = []
    for p_no in paras:
        main = next((r for r in rows if r.paragraph_no == p_no and r.item_no is None), None)
        if main is None:
            main = next((r for r in rows if r.paragraph_no == p_no), None)
        if main is not None:
            resolved.append((main, scope))
    return resolved


def extract_relations(clauses: list[Clause]) -> list[ClauseRelation]:
    """对同一份文件的条款列表抽取候选关联（支持款/项、并列、区间与整条按款展开）。"""
    if not clauses:
        return []
    doc_ids = {c.doc_id for c in clauses}
    if len(doc_ids) != 1:
        raise ValueError("extract_relations 只接受同一份文件的条款")

    by_article: dict[int, list[Clause]] = {}
    for c in clauses:
        by_article.setdefault(c.article_no, []).append(c)

    relations: dict[tuple[str, str, str], ClauseRelation] = {}
    for c in clauses:
        for pattern, rel_type in _PATTERNS:
            for m in pattern.finditer(c.text):
                # 排除跨法引用（紧跟书名号结尾如"《治安管理处罚法》第X条"）
                if m.start() > 0 and c.text[m.start() - 1] == "》":
                    continue
                evidence = m.group(0)
                ref_list = m.group(1)
                for art_no, para_no, item_no in _parse_ref_list(ref_list):
                    # 整条引用本条视为自引用，跳过
                    if art_no == c.article_no and para_no is None and item_no is None:
                        continue
                    for target, scope in _resolve_target_clauses(
                        by_article, art_no, para_no, item_no
                    ):
                        if target.clause_id == c.clause_id:
                            continue
                        key = (target.clause_id, c.clause_id, rel_type)
                        relations.setdefault(
                            key,
                            ClauseRelation(
                                from_clause_id=target.clause_id,
                                to_clause_id=c.clause_id,
                                relation_type=rel_type,
                                origin="rule",
                                confirmed=False,
                                evidence=evidence,
                                scope=scope,
                            ),
                        )
    return list(relations.values())


def canonical_clause_text(conn: sqlite3.Connection, clause: Clause) -> str:
    """与校验层一致的完整条款原文：款主行自动拼接所属各项。"""
    if clause.item_no is not None:
        return clause.text
    rows = conn.execute(
        """SELECT text FROM clauses
           WHERE doc_id=? AND article_no=? AND paragraph_no=? AND item_no IS NOT NULL
           ORDER BY item_no""",
        (clause.doc_id, clause.article_no, clause.paragraph_no),
    ).fetchall()
    return clause.text + "".join(r[0] for r in rows) if rows else clause.text


def article_paragraph_count(conn: sqlite3.Connection, clause: Clause) -> int:
    """返回该条款所属"条"共有多少款。"""
    row = conn.execute(
        "SELECT COUNT(DISTINCT paragraph_no) FROM clauses WHERE doc_id=? AND article_no=?",
        (clause.doc_id, clause.article_no),
    ).fetchone()
    return int(row[0]) if row and row[0] else 0


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _find_kb_references(kb_version: str, artifacts_dir: Path) -> list[str]:
    """检查是否有数据集或评测 manifest 引用了指定 KB 版本。"""
    refs: list[str] = []
    for sub in ("datasets", "eval"):
        root = artifacts_dir / sub
        if not root.is_dir():
            continue
        for mf in sorted(root.glob("*/manifest.json")):
            try:
                data = json.loads(mf.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            inputs = data.get("inputs") or {}
            kb_ref = inputs.get("kb_version")
            kb_file = inputs.get("kb")
            if kb_ref == kb_version or (kb_file and Path(str(kb_file)).stem == kb_version):
                refs.append(str(mf))
    return refs


def check_kb_writable(kb_version: str, artifacts_dir: str | Path = "artifacts") -> Path:
    """确认目标 KB 存在且允许写入关系变更；历史/只读版本一律拒绝。"""
    root = Path(artifacts_dir)
    kb_path = root / "kb" / f"{kb_version}.sqlite"
    if not kb_path.is_file():
        raise RelationImportError(f"找不到知识库文件：{kb_path}")

    manifest_path = root / "kb" / kb_version / "manifest.json"
    if not manifest_path.is_file():
        raise RelationImportError(
            f"知识库 {kb_version} 缺少 manifest.json（{manifest_path}），拒绝原地写入"
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise RelationImportError(f"知识库 manifest 不是合法 JSON：{manifest_path}") from e

    if manifest.get("historical") is True or manifest.get("writable") is False:
        raise RelationImportError(
            f"知识库 {kb_version} 在 manifest 中标记为历史/只读版本，拒绝写入"
        )
    if manifest.get("writable") is not True:
        raise RelationImportError(
            f"知识库 {kb_version} 未标记为可写新版本（历史基线库），拒绝原地写入；请先派生新版本"
        )

    refs = _find_kb_references(kb_version, root)
    if refs:
        raise RelationImportError(
            f"知识库 {kb_version} 已被产物引用（如 {refs[0]}），拒绝原地写入；请先派生新版本"
        )
    return kb_path


def parse_review_decision(row: dict, lineno: int) -> str:
    """解析审阅行决策，支持四态 ``decision`` 并向后兼容旧版布尔 ``confirmed``。"""
    if "decision" in row and row["decision"] is not None:
        dec = row["decision"]
        if not isinstance(dec, str) or dec not in VALID_DECISIONS:
            raise RelationImportError(
                f"第 {lineno} 行 decision 非法：{dec!r}（允许 {sorted(VALID_DECISIONS)}）"
            )
        if "confirmed" in row and row["confirmed"] is not None:
            if not isinstance(row["confirmed"], bool):
                raise RelationImportError(f"第 {lineno} 行 confirmed 必须为布尔值")
            if dec == "confirm" and row["confirmed"] is False:
                raise RelationImportError(f"第 {lineno} 行 decision=confirm 与 confirmed=false 冲突")
            if dec != "confirm" and row["confirmed"] is True:
                raise RelationImportError(f"第 {lineno} 行 decision={dec} 与 confirmed=true 冲突")
        return dec

    if "confirmed" not in row or not isinstance(row["confirmed"], bool):
        raise RelationImportError(f"第 {lineno} 行缺少合法的 decision 或布尔 confirmed 字段")
    return "confirm" if row["confirmed"] else "reject"


def apply_relations_diff(
    review_file: str | Path,
    kb_version: str,
    artifacts_dir: str | Path = "artifacts",
    *,
    batch: str | None = None,
) -> dict:
    """事务化差异导入审阅结果到指定新 KB 版本。

    语义：
    - ``confirm``：插入/保留已确认边（confirmed=1）；
    - ``revoke``：删除对应旧边；
    - ``reject`` / ``pending``：不生效，也不影响文件中未列出的已有已确认边；
    - 任一行格式错误、端点不存在或批内冲突，整批回滚，数据库与 manifest 均不变。
    """
    kb_path = check_kb_writable(kb_version, artifacts_dir)
    path = Path(review_file)
    if not path.is_file():
        raise RelationImportError(f"审阅文件不存在：{path}")

    parsed_rows: list[dict] = []
    seen_decisions: dict[tuple[str, str, str], str] = {}
    for lineno, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as e:
            raise RelationImportError(f"{path} 第 {lineno} 行不是合法 JSON：{e}") from e
        if not isinstance(row, dict):
            raise RelationImportError(f"{path} 第 {lineno} 行不是 JSON 对象")

        fid = row.get("from_clause_id")
        tid = row.get("to_clause_id")
        rtype = row.get("relation_type")
        if not isinstance(fid, str) or not fid.strip():
            raise RelationImportError(f"{path} 第 {lineno} 行缺少合法的 from_clause_id")
        if not isinstance(tid, str) or not tid.strip():
            raise RelationImportError(f"{path} 第 {lineno} 行缺少合法的 to_clause_id")
        if not isinstance(rtype, str) or rtype not in VALID_RELATION_TYPES:
            raise RelationImportError(
                f"{path} 第 {lineno} 行 relation_type 非法：{rtype!r}"
            )
        origin = row.get("origin", "manual")
        if not isinstance(origin, str) or not origin.strip():
            raise RelationImportError(f"{path} 第 {lineno} 行 origin 非法：{origin!r}")

        decision = parse_review_decision(row, lineno)
        key = (fid, tid, rtype)
        if key in seen_decisions and seen_decisions[key] != decision:
            raise RelationImportError(
                f"{path} 第 {lineno} 行同边 {key} 存在冲突决策："
                f"{seen_decisions[key]} vs {decision}"
            )
        seen_decisions[key] = decision
        parsed_rows.append(
            {
                "lineno": lineno,
                "from_clause_id": fid,
                "to_clause_id": tid,
                "relation_type": rtype,
                "origin": origin,
                "decision": decision,
            }
        )

    conn = open_kb(kb_path)
    conn.isolation_level = None  # 显式控制事务边界，保证整批原子性
    counts = {"confirmed": 0, "revoked": 0, "revoked_deleted": 0, "rejected": 0, "pending": 0}
    try:
        # 1. 先检查所有端点都存在于目标 KB，任一缺失直接失败不改库
        missing_endpoints: list[str] = []
        existing_ids = {
            r[0] for r in conn.execute("SELECT clause_id FROM clauses").fetchall()
        }
        for item in parsed_rows:
            for field in ("from_clause_id", "to_clause_id"):
                cid = item[field]
                if cid not in existing_ids:
                    missing_endpoints.append(f"第 {item['lineno']} 行 {field}={cid}")
        if missing_endpoints:
            raise RelationImportError(
                f"目标知识库 {kb_version} 中存在未找到的端点：" + "；".join(missing_endpoints[:10])
            )

        # 2. 单事务执行撤销与新增
        conn.execute("BEGIN")
        for item in parsed_rows:
            dec = item["decision"]
            if dec == "revoke":
                deleted = delete_relation(
                    conn,
                    item["from_clause_id"],
                    item["to_clause_id"],
                    item["relation_type"],
                )
                counts["revoked"] += 1
                counts["revoked_deleted"] += deleted
            elif dec == "confirm":
                insert_relation(
                    conn,
                    ClauseRelation(
                        from_clause_id=item["from_clause_id"],
                        to_clause_id=item["to_clause_id"],
                        relation_type=item["relation_type"],
                        origin=item["origin"],
                        confirmed=True,
                    ),
                )
                counts["confirmed"] += 1
            elif dec == "reject":
                counts["rejected"] += 1
            else:
                counts["pending"] += 1
        conn.execute("COMMIT")
        total_confirmed_after = conn.execute(
            "SELECT COUNT(*) FROM clause_relations WHERE confirmed=1"
        ).fetchone()[0]
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()

    # 3. 记录导入元数据到目标 KB 的 manifest.json
    manifest_path = Path(artifacts_dir) / "kb" / kb_version / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    imports = manifest.setdefault("relation_imports", [])
    record = {
        "imported_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "batch": batch,
        "file": str(path),
        "file_sha256": _sha256_file(path),
        **counts,
        "total_confirmed_after": total_confirmed_after,
    }
    imports.append(record)
    manifest["confirmed_relations_count"] = total_confirmed_after
    manifest["sqlite_sha256"] = _sha256_file(kb_path)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    return {
        "kb_version": kb_version,
        "manifest": str(manifest_path),
        **counts,
        "total_confirmed_after": total_confirmed_after,
    }
