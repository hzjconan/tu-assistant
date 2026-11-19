"""T019 第 1 步（本地准备）：生成第二批 references 审阅清单、对照表与测试库试导入验证。

不修改正式新 KB（kb-20261119-045641.sqlite）与旧 KB（kb-20261113-093057.sqlite），
绝不读取 inputs/。
"""

from __future__ import annotations

import json
import shutil
import tempfile
from collections import Counter
from pathlib import Path

from tu_assistant.kb.relations import (
    RelationImportError,
    apply_relations_diff,
    article_paragraph_count,
    canonical_clause_text,
)
from tu_assistant.kb.store import get_clause_by_id, get_document, open_kb

NEW_KB_VER = "kb-20261119-045641"
ARTIFACTS = Path("artifacts")
OUT_DIR = Path("artifacts/logs/t019")

MANUAL_BATCH2_CANDIDATES = [
    {
        "from_clause_id": "f603773a50aeb8a5:a154:p2",
        "to_clause_id": "f603773a50aeb8a5:a100:p1",
        "relation_type": "references",
        "origin": "manual",
        "decision": "pending",
        "confirmed": False,
        "evidence": "本法第一百五十四条第二款、第三款所列",
        "scope": "explicit_paragraph",
        "suggested_decision": "confirm",
        "note": "第一批因非法律责任拒收，按语义属一般引用（认股书载明事项）",
    },
    {
        "from_clause_id": "f603773a50aeb8a5:a154:p3",
        "to_clause_id": "f603773a50aeb8a5:a100:p1",
        "relation_type": "references",
        "origin": "manual",
        "decision": "pending",
        "confirmed": False,
        "evidence": "本法第一百五十四条第二款、第三款所列",
        "scope": "explicit_paragraph",
        "suggested_decision": "confirm",
        "note": "第一批因非法律责任拒收，按语义属一般引用（认股书载明事项）",
    },
]


def clip(text: str, limit: int = 15) -> str:
    s = " ".join(text.split())
    return s if len(s) <= limit else s[:limit] + "…"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    kb_path = ARTIFACTS / "kb" / f"{NEW_KB_VER}.sqlite"
    pending_path = ARTIFACTS / "kb" / f"{NEW_KB_VER}-relations_pending.jsonl"

    conn = open_kb(kb_path)
    try:
        cur_other = {
            (r[0], r[1], r[2]): r[3]
            for r in conn.execute(
                "SELECT from_clause_id, to_clause_id, relation_type, origin "
                "FROM clause_relations WHERE confirmed=1 AND relation_type != 'liability_for'"
            ).fetchall()
        }
        extracted = [
            json.loads(line)
            for line in pending_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        new_other = {
            (r["from_clause_id"], r["to_clause_id"], r["relation_type"]): r
            for r in extracted
            if r["relation_type"] != "liability_for"
        }

        to_revoke = sorted(set(cur_other) - set(new_other))
        kept = sorted(set(cur_other) & set(new_other))
        added = sorted(set(new_other) - set(cur_other))

        def fmt_clause(cid: str) -> tuple[str, int, str]:
            c = get_clause_by_id(conn, cid)
            doc = get_document(conn, c.doc_id) if c else None
            if not c or not doc:
                return cid, 0, ""
            n_p = article_paragraph_count(conn, c)
            full_t = canonical_clause_text(conn, c)
            return f"《{doc.title}》{c.number_text}", n_p, clip(full_t, 15)

        batch2_rows: list[dict] = []
        for fid, tid, rtype in to_revoke:
            repl = [
                r["from_clause_id"]
                for r in new_other.values()
                if r["to_clause_id"] == tid and r["relation_type"] == rtype
            ]
            ev = next(
                (
                    r["evidence"]
                    for r in new_other.values()
                    if r["to_clause_id"] == tid and r["relation_type"] == rtype
                ),
                "",
            )
            batch2_rows.append(
                {
                    "from_clause_id": fid,
                    "to_clause_id": tid,
                    "relation_type": rtype,
                    "origin": cur_other[(fid, tid, rtype)],
                    "decision": "pending",
                    "confirmed": False,
                    "evidence": ev,
                    "scope": "legacy_wrong_granularity",
                    "suggested_decision": "revoke",
                    "note": f"旧库错款/漏项边，建议撤销（新规则指向 {', '.join(repl)}）",
                }
            )

        for fid, tid, rtype in added:
            r = new_other[(fid, tid, rtype)]
            scope = r.get("scope", "")
            note = (
                "整条引用按款展开，请结合语义核对该款是否属于实质引用对象"
                if scope == "whole_article_expanded"
                else "规则新增精确候选，请核对款/项对齐"
            )
            batch2_rows.append(
                {
                    "from_clause_id": fid,
                    "to_clause_id": tid,
                    "relation_type": rtype,
                    "origin": r["origin"],
                    "decision": "pending",
                    "confirmed": False,
                    "evidence": r.get("evidence", ""),
                    "scope": scope,
                    "suggested_decision": "confirm",
                    "note": note,
                }
            )

        batch2_rows.extend(MANUAL_BATCH2_CANDIDATES)

        batch2_path = ARTIFACTS / "kb" / f"{NEW_KB_VER}-batch2-references_review.jsonl"
        batch2_path.write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in batch2_rows),
            encoding="utf-8",
        )

        scope_counts = Counter(r["scope"] for r in batch2_rows)
        md: list[str] = [
            f"# T019 第二批（`references`）候选增删改对照表（`{NEW_KB_VER}`）",
            "",
            f"- 当前库内已有 `references`：**{len(cur_other)}** 条（其中 {len(kept)} 条新规则仍命中，"
            f"{len(to_revoke)} 条为旧错款/漏项待撤销）",
            f"- 第二批审阅文件：`{batch2_path}`（共 **{len(batch2_rows)}** 行："
            f"待撤销 {len(to_revoke)} + 规则新增 {len(added)} + "
            f"手动补充 {len(MANUAL_BATCH2_CANDIDATES)}；按 scope 分布 `{dict(scope_counts)}`）",
            "",
            f"## 1. 待撤销旧错边（行 1–{len(to_revoke)}）",
            "",
            "| 行号 | 旧 `from_clause_id` | `to_clause_id` "
            "| from（总款数 / 摘要≤15字） | 触发片段 | 建议与提示 |",
            "|---:|---|---|---|---|---|",
        ]
        for idx, row in enumerate(batch2_rows[: len(to_revoke)], 1):
            label, n_p, snip = fmt_clause(row["from_clause_id"])
            md.append(
                f"| {idx} | `{row['from_clause_id']}` | `{row['to_clause_id']}` "
                f"| {label}（共{n_p}款，{snip}） | {row['evidence']} "
                f"| `{row['suggested_decision']}`：{row['note']} |"
            )

        md.extend(
            [
                "",
                f"## 2. 新增 `references` 候选（行 {len(to_revoke) + 1}–{len(batch2_rows)}）",
                "",
                "| 行号 | 新 `from_clause_id` | `to_clause_id` "
                "| from（总款数 / 摘要≤15字） | scope | 触发片段 |",
                "|---:|---|---|---|---|---|",
            ]
        )
        for idx, row in enumerate(batch2_rows[len(to_revoke) :], len(to_revoke) + 1):
            label, n_p, snip = fmt_clause(row["from_clause_id"])
            md.append(
                f"| {idx} | `{row['from_clause_id']}` | `{row['to_clause_id']}` "
                f"| {label}（共{n_p}款，{snip}） | `{row['scope']}` | {row['evidence']} |"
            )

        md.extend(
            [
                "",
                f"## 3. 库内沿用的旧 `references`（{len(kept)} 条，将一并送 DeepSeek 复核）",
                "",
                "| `from_clause_id` | `to_clause_id` | from（总款数 / 摘要≤15字） | scope | 触发片段 |",
                "|---|---|---|---|---|",
            ]
        )
        for fid, tid, rtype in kept:
            r = new_other[(fid, tid, rtype)]
            label, n_p, snip = fmt_clause(fid)
            md.append(
                f"| `{fid}` | `{tid}` | {label}（共{n_p}款，{snip}） "
                f"| `{r['scope']}` | {r['evidence']} |"
            )

        diff_path = OUT_DIR / "batch2_candidates_diff.md"
        diff_path.write_text("\n".join(md) + "\n", encoding="utf-8")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_art = Path(tmp) / "artifacts"
            (tmp_art / "kb" / NEW_KB_VER).mkdir(parents=True)
            shutil.copy2(kb_path, tmp_art / "kb" / f"{NEW_KB_VER}.sqlite")
            shutil.copy2(
                ARTIFACTS / "kb" / NEW_KB_VER / "manifest.json",
                tmp_art / "kb" / NEW_KB_VER / "manifest.json",
            )
            sim_rows = []
            for r in batch2_rows:
                rr = dict(r)
                rr["decision"] = r["suggested_decision"]
                rr["confirmed"] = rr["decision"] == "confirm"
                sim_rows.append(rr)
            sim_file = Path(tmp) / "sim_batch2.jsonl"
            sim_file.write_text(
                "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in sim_rows),
                encoding="utf-8",
            )
            r1 = apply_relations_diff(sim_file, NEW_KB_VER, tmp_art, batch="dryrun-b2")
            r2 = apply_relations_diff(sim_file, NEW_KB_VER, tmp_art, batch="dryrun-b2")
            assert r1["revoked_deleted"] == len(to_revoke)
            assert r2["revoked_deleted"] == 0
            assert r1["total_confirmed_after"] == r2["total_confirmed_after"]

            bad_file = Path(tmp) / "bad.jsonl"
            bad_file.write_text(
                json.dumps(
                    {
                        "from_clause_id": "bad:a1:p1",
                        "to_clause_id": "bad:a2:p1",
                        "relation_type": "references",
                        "decision": "confirm",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            try:
                apply_relations_diff(bad_file, NEW_KB_VER, tmp_art)
                raise AssertionError("预期抛出 RelationImportError")
            except RelationImportError:
                pass

            print(
                f"Dry-run OK: revoke_del={r1['revoked_deleted']}, confirm={r1['confirmed']}, "
                f"total_after={r1['total_confirmed_after']} (idempotent={r2['total_confirmed_after']})"
            )

        print(f"Wrote {batch2_path} ({len(batch2_rows)} rows)")
        print(f"Wrote {diff_path}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
