"""T019 诊断脚本：委托 DeepSeek 核查 KB 中是否存在“条旨（括号小标题）被切为第1款”的解析问题。

- 只读取本地 SQLite KB（不触碰 inputs/），不在终端输出完整条文；
- 按文档汇总 p1 形如“（……）”或“【……】”的条文数量；
- 将抽样条款（含《上海市工伤保险实施办法》第27条、第43条等）发给 DeepSeek
  （input_source="kb_clause"），由 DeepSeek 给出结构诊断与影响评估。
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path

from tu_assistant.config import load_synth_config
from tu_assistant.kb.store import open_kb
from tu_assistant.synth.llm import from_config

KB_PATH = Path("artifacts/kb/kb-20261119-045641.sqlite")
OUT_PATH = Path("artifacts/logs/t019/p1_heading_diagnosis.md")

RE_PAREN_ONLY = re.compile(r"^[（(【\[][^）)】\]]{1,30}[）)】\]]$")


def _load_dotenv_key() -> None:
    if os.environ.get("TU_EXTERNAL_LLM_API_KEY"):
        return
    env_path = Path(".env")
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() == "TU_EXTERNAL_LLM_API_KEY":
            os.environ["TU_EXTERNAL_LLM_API_KEY"] = v.strip().strip('"').strip("'")
            return


def main() -> None:
    _load_dotenv_key()
    conn = open_kb(KB_PATH)
    try:
        docs = dict(conn.execute("SELECT doc_id, title FROM legal_documents").fetchall())
        p1_rows = conn.execute(
            "SELECT doc_id, article_no, clause_id, number_text, text "
            "FROM clauses WHERE paragraph_no=1 AND item_no IS NULL "
            "ORDER BY doc_id, article_no"
        ).fetchall()

        hit_by_doc: Counter[str] = Counter()
        total_by_doc: Counter[str] = Counter()
        samples_for_llm: list[dict] = []

        for did, art_no, _cid, _nt, txt in p1_rows:
            total_by_doc[did] += 1
            if RE_PAREN_ONLY.match(txt.strip()):
                hit_by_doc[did] += 1
                # 每个命中文件抽前 2 条，且确保包含 9fc301cd90566af9 的第 27、43 条
                want = (did == "9fc301cd90566af9" and art_no in (27, 43)) or (
                    hit_by_doc[did] <= 2
                )
                if want:
                    art_rows = conn.execute(
                        "SELECT clause_id, paragraph_no, item_no, number_text, text "
                        "FROM clauses WHERE doc_id=? AND article_no=? "
                        "ORDER BY paragraph_no, ifnull(item_no, 0)",
                        (did, art_no),
                    ).fetchall()
                    samples_for_llm.append(
                        {
                            "doc_id": did,
                            "title": docs[did],
                            "article_no": art_no,
                            "rows": [
                                {
                                    "clause_id": r[0],
                                    "paragraph_no": r[1],
                                    "item_no": r[2],
                                    "number_text": r[3],
                                    "text": r[4],
                                }
                                for r in art_rows
                            ],
                        }
                    )

        # 也核对 v1 评测集 gold 和已确认关系中有多少落在这些受影响文件里
        affected_docs = set(hit_by_doc.keys())
        v1_hits: dict[str, list[str]] = {}
        for f in sorted(Path("eval/cases/v1").glob("*.jsonl")):
            matched = []
            for line in f.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                d = json.loads(line)
                for cid in (d.get("gold") or {}).get("clauses") or []:
                    if cid.split(":")[0] in affected_docs:
                        matched.append(f"{d['case_id']}:{cid}")
            v1_hits[f.name] = matched

        rel_hits = conn.execute(
            "SELECT relation_type, COUNT(*) FROM clause_relations WHERE confirmed=1 "
            "AND (substr(from_clause_id, 1, 16) IN ({q}) OR substr(to_clause_id, 1, 16) IN ({q})) "
            "GROUP BY relation_type".format(
                q=",".join("?" for _ in affected_docs) or "''"
            ),
            tuple(affected_docs) * 2 if affected_docs else (),
        ).fetchall()
    finally:
        conn.close()

    cfg = load_synth_config("configs/synth.yaml")
    llm = from_config(cfg)
    prompt = (
        "你是中国法律文本结构解析审查专家。下面是从 SQLite 知识库抽出的若干条文切分结果。\n"
        "请判断：\n"
        "1. 这些条文的 paragraph_no=1 是否实际是“条旨 / 括号小标题”（如“（鉴定程序）”），"
        "而被切分器误切成了第1款，从而导致后面每一款的款号整体顺延 +1？\n"
        "2. 重点核对《上海市工伤保险实施办法》第27条和第43条的真实法律款号结构（比如第43条的"
        "“第一款第二项”在当前切分里掉到了哪一款）。\n"
        "3. 给出简明、结构化的诊断结论（200字以内，不要大段复述原文）。\n\n"
        + json.dumps(samples_for_llm, ensure_ascii=False)
    )
    diagnosis = llm.chat(
        [{"role": "user", "content": prompt}],
        input_source="kb_clause",
        temperature=0.0,
        max_tokens=600,
    )

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# T019 条旨（括号小标题）被误切为第 1 款的诊断报告",
        "",
        "## 1. 全库扫描统计（24 篇，p1 原文仅为括号/方括号短标题）",
        "",
        "| `doc_id` | 法规名称 | 命中条数 / 该文件总条数 |",
        "|---|---|---:|",
    ]
    for did, cnt in hit_by_doc.most_common():
        lines.append(f"| `{did}` | {docs[did]} | {cnt} / {total_by_doc[did]} |")
    if not hit_by_doc:
        lines.append("| — | 无命中 | 0 |")

    lines.extend(
        [
            "",
            "## 2. 受影响范围（评测集 v1 与当前已确认关系）",
            "",
            f"- 涉及文件数：**{len(affected_docs)}** 篇，总计 **{sum(hit_by_doc.values())}** 条。",
            f"- `eval/cases/v1/reviewed.jsonl` 命中题数：**{len(v1_hits.get('reviewed.jsonl', []))}** 题",
            f"- `eval/cases/v1/articles.jsonl` 命中 gold 数：**{len(v1_hits.get('articles.jsonl', []))}** 条",
            f"- 当前已确认关系命中：{rel_hits}",
            "",
            "## 3. DeepSeek 诊断结论",
            "",
            diagnosis.strip(),
            "",
            f"（调用次数：{llm.usage.calls}，prompt {llm.usage.prompt_tokens} / "
            f"completion {llm.usage.completion_tokens} tokens）",
        ]
    )
    OUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    print("Affected docs:", {docs[d]: f"{c}/{total_by_doc[d]}" for d, c in hit_by_doc.items()})
    print("v1 hits:", {k: len(v) for k, v in v1_hits.items()})
    print("DeepSeek diagnosis:\n" + diagnosis.strip())


if __name__ == "__main__":
    main()
