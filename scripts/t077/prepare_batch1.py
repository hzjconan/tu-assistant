"""T077 第 4 步：生成候选增删改对照表、第一批审阅清单与测试库试导入验证。

不修改正式新 KB（kb-20261119-045641.sqlite）与旧 KB（kb-20261113-093057.sqlite），
仅在临时目录复制测试库验证事务化导入。
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

OLD_KB_VER = "kb-20261113-093057"
NEW_KB_VER = "kb-20261119-045641"
ARTIFACTS = Path("artifacts")
OUT_DIR = Path("artifacts/logs/t077")


def clip(text: str, limit: int = 15) -> str:
    s = " ".join(text.split())
    return s if len(s) <= limit else s[:limit] + "…"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    old_conn = open_kb(ARTIFACTS / "kb" / f"{OLD_KB_VER}.sqlite")
    new_conn = open_kb(ARTIFACTS / "kb" / f"{NEW_KB_VER}.sqlite")
    pending_path = ARTIFACTS / "kb" / f"{NEW_KB_VER}-relations_pending.jsonl"

    try:
        old_confirmed = {
            (r[0], r[1], r[2]): r[3]
            for r in old_conn.execute(
                "SELECT from_clause_id, to_clause_id, relation_type, origin "
                "FROM clause_relations WHERE confirmed=1"
            ).fetchall()
        }
        extracted = [
            json.loads(line)
            for line in pending_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        extracted_map = {
            (r["from_clause_id"], r["to_clause_id"], r["relation_type"]): r for r in extracted
        }

        ext_by_type = Counter(r["relation_type"] for r in extracted)
        old_by_type = Counter(k[2] for k in old_confirmed)

        # 第一批聚焦：全部 liability_for（新抽取候选 + 旧库已确认中已被新规则不再命中的错边）
        old_liab_keys = {k for k in old_confirmed if k[2] == "liability_for"}
        new_liab_keys = {k for k in extracted_map if k[2] == "liability_for"}

        # 旧库已确认但新规则不再命中的 liability_for → 正是 6 对错款旧边，需列明撤销
        to_revoke = sorted(old_liab_keys - new_liab_keys)
        kept_liab = sorted(old_liab_keys & new_liab_keys)
        added_liab = sorted(new_liab_keys - old_liab_keys)

        def fmt_clause(cid: str) -> tuple[str, str, int, str]:
            c = get_clause_by_id(new_conn, cid)
            doc = get_document(new_conn, c.doc_id) if c else None
            if not c or not doc:
                return cid, "", 0, ""
            n_p = article_paragraph_count(new_conn, c)
            full_t = canonical_clause_text(new_conn, c)
            return f"《{doc.title}》{c.number_text}", c.number_text, n_p, clip(full_t, 15)

        # 组装第一批审阅 JSONL：全部待处理项（6 条待撤销旧错边 + 全部新增 liability_for 候选）
        # 初始 decision 均为 pending，suggested_decision 供人工审阅参考，正式确认前不入库。
        batch1_rows: list[dict] = []
        for fid, tid, rtype in to_revoke:
            # 找同一 to_clause 的新候选以便标注替代建议
            repl = [
                r["from_clause_id"]
                for r in extracted
                if r["to_clause_id"] == tid and r["relation_type"] == rtype
            ]
            ev = next(
                (
                    r["evidence"]
                    for r in extracted
                    if r["to_clause_id"] == tid and r["relation_type"] == rtype
                ),
                "",
            )
            batch1_rows.append(
                {
                    "from_clause_id": fid,
                    "to_clause_id": tid,
                    "relation_type": rtype,
                    "origin": old_confirmed[(fid, tid, rtype)],
                    "decision": "pending",
                    "confirmed": False,
                    "evidence": ev,
                    "scope": "legacy_wrong_paragraph",
                    "suggested_decision": "revoke",
                    "note": f"旧库错款边，建议撤销（新规则指向 {', '.join(repl)}）",
                }
            )

        for fid, tid, rtype in added_liab:
            r = extracted_map[(fid, tid, rtype)]
            # 所列事项非法律责任（如“载明…所列”）提示人工重点甄别
            is_suolie = "所列" in r.get("evidence", "") and "违反" not in r.get("evidence", "")
            sug = "reject" if is_suolie else "confirm"
            note = (
                "非违反触发（“所列”条款），请核对是否属于法律责任"
                if is_suolie
                else (
                    "整条引用按款展开，请逐款核对是否受该责任条款约束"
                    if r.get("scope") == "whole_article_expanded"
                    else "规则新增候选，请核对款号与责任对应关系"
                )
            )
            batch1_rows.append(
                {
                    "from_clause_id": fid,
                    "to_clause_id": tid,
                    "relation_type": rtype,
                    "origin": r["origin"],
                    "decision": "pending",
                    "confirmed": False,
                    "evidence": r.get("evidence", ""),
                    "scope": r.get("scope", ""),
                    "suggested_decision": sug,
                    "note": note,
                }
            )

        batch1_path = ARTIFACTS / "kb" / f"{NEW_KB_VER}-batch1-liability_review.jsonl"
        batch1_path.write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in batch1_rows),
            encoding="utf-8",
        )

        # 第二批参考汇总（references / exception_of 增删变化）
        old_other = {k for k in old_confirmed if k[2] != "liability_for"}
        new_other = {k for k in extracted_map if k[2] != "liability_for"}
        other_revoke = sorted(old_other - new_other)
        other_kept = sorted(old_other & new_other)
        other_added = sorted(new_other - old_other)

        # 生成 candidates_diff.md
        md: list[str] = [
            f"# T077 候选关系增删改对照表（旧 `{OLD_KB_VER}` vs 新 `{NEW_KB_VER}`）",
            "",
            f"- 旧库已确认：**{len(old_confirmed)}** 条（{dict(old_by_type)}）",
            f"- 新规则全量抽取：**{len(extracted)}** 条（{dict(ext_by_type)}）",
            f"- 第一批审阅文件：`{batch1_path}`（共 **{len(batch1_rows)}** 条："
            f"待撤销旧错边 {len(to_revoke)} 条 + 新增 `liability_for` 候选 {len(added_liab)} 条；"
            f"另有 {len(kept_liab)} 条旧 `liability_for` 仍被新规则命中且已存在于新库）",
            "",
            "## 1. 第一批（`liability_for`）：待撤销旧错边（6 条）",
            "",
            "| 行号 | 旧 `from_clause_id` | `to_clause_id` | 旧 from（总款数） | 触发片段 | 建议动作 |",
            "|---:|---|---|---|---|---|",
        ]
        for idx, row in enumerate(batch1_rows[: len(to_revoke)], 1):
            label, _, n_p, snip = fmt_clause(row["from_clause_id"])
            md.append(
                f"| {idx} | `{row['from_clause_id']}` | `{row['to_clause_id']}` "
                f"| {label}（共{n_p}款，{snip}） | {row['evidence']} "
                f"| `{row['suggested_decision']}`（{row['note']}） |"
            )

        md.extend(
            [
                "",
                f"## 2. 第一批（`liability_for`）：新增候选（{len(added_liab)} 条）",
                "",
                "| 行号 | 新 `from_clause_id` | `to_clause_id` "
                "| from（总款数 / 摘要≤15字） | scope | 触发片段 | 建议与提示 |",
                "|---:|---|---|---|---|---|---|",
            ]
        )
        for idx, row in enumerate(batch1_rows[len(to_revoke) :], len(to_revoke) + 1):
            label, _, n_p, snip = fmt_clause(row["from_clause_id"])
            md.append(
                f"| {idx} | `{row['from_clause_id']}` | `{row['to_clause_id']}` "
                f"| {label}（共{n_p}款，{snip}） | `{row['scope']}` | {row['evidence']} "
                f"| `{row['suggested_decision']}`：{row['note']} |"
            )

        md.extend(
            [
                "",
                f"## 3. 旧库中已确认且新规则仍命中的 `liability_for`（{len(kept_liab)} 条，保留不动）",
                "",
                "| `from_clause_id` | `to_clause_id` | from（总款数 / 摘要≤15字） | scope | 触发片段 |",
                "|---|---|---|---|---|",
            ]
        )
        for fid, tid, rtype in kept_liab:
            r = extracted_map[(fid, tid, rtype)]
            label, _, n_p, snip = fmt_clause(fid)
            md.append(
                f"| `{fid}` | `{tid}` | {label}（共{n_p}款，{snip}） | `{r['scope']}` | {r['evidence']} |"
            )

        md.extend(
            [
                "",
                "## 4. 第二批（`references` / `exception_of`）变化概览（待第二批审阅）",
                "",
                f"- 旧已确认仍命中：{len(other_kept)} 条",
                f"- 旧已确认但新规则指向更精确款/项（第二批待撤销旧边）：{len(other_revoke)} 条",
                f"- 新规则新增候选：{len(other_added)} 条",
                "",
                "第二批已知偏差旧边清单（供第二批审阅追踪）：",
                "",
                "| 旧 `from_clause_id` | `to_clause_id` | 类型 | 原文触发片段（新规则） |",
                "|---|---|---|---|",
            ]
        )
        for fid, tid, rtype in other_revoke:
            evs = sorted(
                {
                    r["evidence"]
                    for r in extracted
                    if r["to_clause_id"] == tid and r["relation_type"] == rtype
                }
            )
            md.append(f"| `{fid}` | `{tid}` | `{rtype}` | {'；'.join(evs)} |")

        diff_md_path = OUT_DIR / "candidates_diff.md"
        diff_md_path.write_text("\n".join(md) + "\n", encoding="utf-8")

        # 测试库试导入验证（在临时目录复制新 KB，不碰正式新 KB）
        with tempfile.TemporaryDirectory() as tmp:
            tmp_art = Path(tmp) / "artifacts"
            (tmp_art / "kb" / NEW_KB_VER).mkdir(parents=True)
            shutil.copy2(ARTIFACTS / "kb" / f"{NEW_KB_VER}.sqlite", tmp_art / "kb" / f"{NEW_KB_VER}.sqlite")
            shutil.copy2(
                ARTIFACTS / "kb" / NEW_KB_VER / "manifest.json",
                tmp_art / "kb" / NEW_KB_VER / "manifest.json",
            )
            sim_rows = []
            for r in batch1_rows:
                rr = dict(r)
                rr["decision"] = r["suggested_decision"]
                rr["confirmed"] = rr["decision"] == "confirm"
                sim_rows.append(rr)
            sim_file = Path(tmp) / "sim_batch1.jsonl"
            sim_file.write_text(
                "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in sim_rows),
                encoding="utf-8",
            )
            r1 = apply_relations_diff(sim_file, NEW_KB_VER, tmp_art, batch="dryrun-b1")
            r2 = apply_relations_diff(sim_file, NEW_KB_VER, tmp_art, batch="dryrun-b1")
            assert r1["revoked_deleted"] == len(to_revoke)
            assert r2["revoked_deleted"] == 0
            assert r1["total_confirmed_after"] == r2["total_confirmed_after"]

            # 再测坏行回滚
            bad_file = Path(tmp) / "bad.jsonl"
            bad_file.write_text(
                json.dumps(
                    {
                        "from_clause_id": "nonexistent:a1:p1",
                        "to_clause_id": "nonexistent:a2:p1",
                        "relation_type": "liability_for",
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
                f"Dry-run on temp copy OK: revoke_del={r1['revoked_deleted']}, "
                f"confirm={r1['confirmed']}, reject={r1['rejected']}, "
                f"total_after={r1['total_confirmed_after']} (idempotent={r2['total_confirmed_after']})"
            )

        print(f"Wrote {diff_md_path}")
        print(f"Wrote {batch1_path} ({len(batch1_rows)} rows)")
    finally:
        old_conn.close()
        new_conn.close()


if __name__ == "__main__":
    main()
