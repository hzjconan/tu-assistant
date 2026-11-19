"""T057 步骤 3a 补充：为《公司法》定向补跑 3 条初稿（n2、n3_vague、n1_case）。"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from tu_assistant.config import load_synth_config
from tu_assistant.synth.articles import ArticleStats, generate, generate_from_case
from tu_assistant.synth.llm import from_config

KB_PATH = Path("artifacts/kb/kb-20261119-045641.sqlite")
OUT_DIR = Path("artifacts/synth/articles/t057-expand-company")
COMPANY_DOC_ID = "f603773a50aeb8a5"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cfg = load_synth_config()
    llm = from_config(cfg)
    conn = sqlite3.connect(KB_PATH.resolve().as_uri() + "?mode=ro", uri=True)
    rows: list[dict] = []
    try:
        st1 = ArticleStats()
        r1 = generate(
            conn,
            llm,
            {**cfg, "seed": 142},
            n_requests=2,
            request_modes=(2, "vague"),
            stats=st1,
            doc_ids={COMPANY_DOC_ID},
        )
        print(f"[company theme] kept {st1.kept}/{st1.total} drops={st1.reasons}", flush=True)
        rows.extend(r1)

        st2 = ArticleStats()
        r2 = generate_from_case(
            conn,
            llm,
            {**cfg, "seed": 242},
            n_requests=1,
            stats=st2,
            doc_ids={COMPANY_DOC_ID},
        )
        print(f"[company case] kept {st2.kept}/{st2.total} drops={st2.reasons}", flush=True)
        rows.extend(r2)
    finally:
        conn.close()

    for idx, r in enumerate(rows, 1):
        r["meta"]["source_batch"] = "t057-expand-company"
        r["meta"]["request"] = idx
    out = OUT_DIR / "samples.jsonl"
    out.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rows), encoding="utf-8")
    print(f"DONE {out}: {len(rows)} rows", flush=True)


if __name__ == "__main__":
    main()
