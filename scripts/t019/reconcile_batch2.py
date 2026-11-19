"""T019 第 3 步：第二批导入后对账与全链路核验。

产物写入 artifacts/logs/t019/batch2_reconcile.md，绝不触碰 inputs/ 或历史基线文件。
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from tu_assistant.kb.store import open_kb
from tu_assistant.synth.articles import ArticleStats, _materials
from tu_assistant.synth.check import CheckStats, check_sample
from tu_assistant.synth.knowledge import doc_titles, relation_samples

OLD_KB_VER = "kb-20261113-093057"
NEW_KB_VER = "kb-20261119-045641"
ARTIFACTS = Path("artifacts")
OUT_PATH = Path("artifacts/logs/t019/batch2_reconcile.md")
REVIEW_REPO = Path("data/relation-reviews/kb-20261119-045641-batch2-references_review.jsonl")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    # 1. 核验历史 18 个文件 0 改动
    base_hashes = json.loads(
        Path("artifacts/logs/t077/baseline_hashes.json").read_text(encoding="utf-8")
    )
    bad = [p for p, exp in base_hashes.items() if sha256_file(Path(p)) != exp]
    assert not bad, f"历史产物被修改：{bad}"

    # 2. 核验入库审阅文件 SHA-256 与 manifest 一致
    mf = json.loads(
        (ARTIFACTS / "kb" / NEW_KB_VER / "manifest.json").read_text(encoding="utf-8")
    )
    last_imp = mf["relation_imports"][-1]
    assert last_imp["batch"] == "batch2-references"
    repo_sha = sha256_file(REVIEW_REPO)
    assert repo_sha == last_imp["file_sha256"], f"{repo_sha} != {last_imp['file_sha256']}"

    # 3. 查库核对关系总数、类型分布、relation_samples 质检与文章素材池
    old_conn = open_kb(ARTIFACTS / "kb" / f"{OLD_KB_VER}.sqlite")
    new_conn = open_kb(ARTIFACTS / "kb" / f"{NEW_KB_VER}.sqlite")
    try:
        old_rels = {
            (r[0], r[1], r[2])
            for r in old_conn.execute(
                "SELECT from_clause_id, to_clause_id, relation_type "
                "FROM clause_relations WHERE confirmed=1"
            )
        }
        new_rels = {
            (r[0], r[1], r[2])
            for r in new_conn.execute(
                "SELECT from_clause_id, to_clause_id, relation_type "
                "FROM clause_relations WHERE confirmed=1"
            )
        }
        by_type = Counter(k[2] for k in new_rels)
        assert by_type["liability_for"] == 26
        assert by_type["references"] == 41
        assert len(new_rels) == 67

        # 核对 4 条旧 references 错边均已撤销
        revoked_check = [
            ("be21194cc551533d:a44:p1", "be21194cc551533d:a46:p1:i5", "references"),
            ("be21194cc551533d:a44:p1", "be21194cc551533d:a46:p1:i6", "references"),
            ("f603773a50aeb8a5:a116:p1", "f603773a50aeb8a5:a146:p1", "references"),
            ("f603773a50aeb8a5:a214:p1", "f603773a50aeb8a5:a225:p1", "references"),
        ]
        for k in revoked_check:
            assert k not in new_rels, f"旧错边未撤销：{k}"

        # 核对 67 条 relation_samples 100% 通过 check_sample
        samples = relation_samples(new_conn, doc_titles(new_conn))
        chk = CheckStats()
        for s in samples:
            ok = check_sample(
                s["messages"][1]["content"],
                new_conn,
                chk,
                require_citation=True,
                expected_clause_ids=set(s["meta"]["clause_ids"]),
            )
            assert ok, f"关系样本未通过检查：{s['meta']}"
        assert chk.kept == 67 and chk.dropped == 0

        # 核对文章素材池不受影响
        art_stats = ArticleStats()
        pairs = _materials(new_conn, art_stats)
        assert len(pairs) == 26 and art_stats.materials["paragraph_mismatch"] == 0
    finally:
        old_conn.close()
        new_conn.close()

    kb_sha16 = mf["sqlite_sha256"][:16]
    pm = art_stats.materials["paragraph_mismatch"]
    md = [
        f"# T019 第二批（`references`）导入后对账报告（`{NEW_KB_VER}`）",
        "",
        "## 1. 版本与校验值",
        "",
        f"- 目标新 KB：`artifacts/kb/{NEW_KB_VER}.sqlite`（最终 `sqlite_sha256`：`{kb_sha16}`）",
        f"- 入库审阅文件：`{REVIEW_REPO}`（SHA-256：`{repo_sha[:16]}`，与 `manifest.json` 逐字一致）",
        f"- 历史产物校验：18 个基线文件（含 `{OLD_KB_VER}.sqlite`）全部 **0 改动**",
        "",
        "## 2. 关系表与下游核验结果",
        "",
        "| 核验项 | 旧 KB `kb-20261113-093057` | 导入第一批后 | 导入第二批后（最终） |",
        "|---|---:|---:|---:|",
        "| `liability_for` | 12 | 26 | **26**（零改动） |",
        "| `references` | 23 | 23 | **41**（撤销 4，新增 22） |",
        f"| 已确认关系合计 | {len(old_rels)} | 49 | **{len(new_rels)}** |",
        f"| `knowledge.relation_samples` + `check_sample` | 35/35 | 49/49 "
        f"| **{chk.kept}/{chk.total}**（丢弃 {chk.dropped}） |",
        f"| `synth/articles._materials` 可用对数 (`paragraph_mismatch`) | 6 (6) | 26 (0) "
        f"| **{len(pairs)} ({pm})** |",
        "",
        "## 3. 第二批导入明细",
        "",
        f"- 批次标识：`{last_imp['batch']}`（导入时间 `{last_imp['imported_at']}`）",
        f"- 决策汇总：`confirm` **{last_imp['confirmed']}** / `revoke` **{last_imp['revoked']}**"
        f"（实际删除 **{last_imp['revoked_deleted']}**）/ `reject` **{last_imp['rejected']}** / "
        f"`pending` **{last_imp['pending']}**",
        "- 4 条旧 `references` 错边（`a44:p1→a46:p1:i5/i6`、`a116:p1→a146:p1`、"
        "`a214:p1→a225:p1`）均已核实从库中清除。",
        "- 落在《上海市工伤保险实施办法》的行 18–25（共 8 行）已全部 `reject`，"
        "条旨误切问题登记为 T078 另行处理。",
    ]
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    print(
        f"Reconcile PASS: total={len(new_rels)} (liability_for=26, references=41), "
        f"samples={chk.kept}/{chk.total}, articles={len(pairs)}, "
        f"kb_sha256={mf['sqlite_sha256'][:16]}, review_sha256={repo_sha[:16]}"
    )


if __name__ == "__main__":
    main()
