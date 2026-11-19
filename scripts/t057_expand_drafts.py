"""T057 步骤 3a：按法规缺口与问法桶（含 n4、n3_vague、n1_case）定向扩量生成新 KB 初稿。"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from statistics import median

from tu_assistant.config import load_synth_config, load_yaml
from tu_assistant.synth.articles import (
    ARTICLE_PROMPT_VERSION,
    TRAIN_CONFIG,
    ArticleStats,
    _materials,
    generate,
    generate_from_case,
)
from tu_assistant.synth.llm import from_config

KB_PATH = Path("artifacts/kb/kb-20261119-045641.sqlite")
OUT_DIR = Path("artifacts/synth/articles/t057-expand-drafts")

# 定向补齐缺口法规与问法桶（不新增已有 4 篇初稿的妇女权益保障法）
THEME_BATCHES: list[tuple[str, str, tuple[int | str | None, ...]]] = [
    ("company", "f603773a50aeb8a5", (1, 2, 3, None, "vague")),
    ("female_labor", "cd730370ca29c4df", (1, 2, 3, "vague", 4)),
    ("collective", "40124ed5e360acee", (1, 3, None, 4)),
    ("employment", "c2699265cef115bb", (2, None, "vague")),
    ("union", "4b6c1f293f717293", (3, "vague", 4)),
]

CASE_BATCHES: list[tuple[str, str, int]] = [
    ("company", "f603773a50aeb8a5", 1),
    ("female_labor", "cd730370ca29c4df", 1),
    ("collective", "40124ed5e360acee", 1),
    ("employment", "c2699265cef115bb", 1),
]


def _build_whitelist(conn: sqlite3.Connection) -> set[tuple[tuple[str, str], tuple[str, str]]]:
    pool = _materials(conn, ArticleStats())
    wl: set[tuple[tuple[str, str], tuple[str, str]]] = set()
    for j, a in enumerate(pool):
        for b in pool[j + 1 :]:
            if a.doc_id != b.doc_id or a.basis == b.basis or a.liability == b.liability:
                continue
            pair_ids = {a.basis, b.basis}
            if "a98741e9ca9f6fa1:a22:p2" in pair_ids:
                continue
            if "a98741e9ca9f6fa1:a26:p1" in pair_ids and any(
                x.startswith(("a98741e9ca9f6fa1:a43:", "a98741e9ca9f6fa1:a48:")) for x in pair_ids
            ):
                continue
            wl.add(((a.basis, a.liability), (b.basis, b.liability)))
    return wl


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cfg = load_synth_config()
    llm = from_config(cfg)
    train = load_yaml(TRAIN_CONFIG)
    conn = sqlite3.connect(KB_PATH.resolve().as_uri() + "?mode=ro", uri=True)
    all_samples: list[dict] = []
    stats_all = ArticleStats()
    req_seq = 0

    try:
        wl = _build_whitelist(conn)
        for tag, doc_id, modes in THEME_BATCHES:
            st = ArticleStats()
            batch_cfg = {**cfg, "seed": cfg.get("seed", 42) + len(all_samples) + 1}
            rows = generate(
                conn,
                llm,
                batch_cfg,
                n_requests=len(modes),
                request_modes=modes,
                stats=st,
                doc_ids={doc_id},
                multi_whitelist=wl,
            )
            stats_all.total += st.total
            stats_all.kept += st.kept
            stats_all.dropped += st.dropped
            for k, v in st.reasons.items():
                stats_all.reasons[k] = stats_all.reasons.get(k, 0) + v
            for r in rows:
                req_seq += 1
                r["meta"]["source_batch"] = "t057-expand-drafts"
                r["meta"]["request"] = req_seq
                r["meta"]["batch_tag"] = tag
                all_samples.append(r)
            print(f"[theme:{tag}] kept {st.kept}/{st.total} drops={st.reasons}", flush=True)

        for tag, doc_id, n_req in CASE_BATCHES:
            st = ArticleStats()
            batch_cfg = {**cfg, "seed": cfg.get("seed", 42) + len(all_samples) + 50}
            rows = generate_from_case(
                conn,
                llm,
                batch_cfg,
                n_requests=n_req,
                stats=st,
                doc_ids={doc_id},
                multi_whitelist=wl,
            )
            stats_all.total += st.total
            stats_all.kept += st.kept
            stats_all.dropped += st.dropped
            for k, v in st.reasons.items():
                stats_all.reasons[k] = stats_all.reasons.get(k, 0) + v
            for r in rows:
                req_seq += 1
                r["meta"]["source_batch"] = "t057-expand-drafts"
                r["meta"]["request"] = req_seq
                r["meta"]["batch_tag"] = f"case_{tag}"
                all_samples.append(r)
            print(f"[case:{tag}] kept {st.kept}/{st.total} drops={st.reasons}", flush=True)
    finally:
        conn.close()

    out_jsonl = OUT_DIR / "samples.jsonl"
    with out_jsonl.open("w", encoding="utf-8") as f:
        for s in all_samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    sizes = [s["meta"]["tokens"] for s in all_samples]
    by_kind = Counter(s["meta"]["kind"] for s in all_samples)
    by_doc = Counter(s["meta"]["doc_id"] for s in all_samples)
    manifest = {
        "kb": str(KB_PATH),
        "article_prompt_version": ARTICLE_PROMPT_VERSION,
        "base_model": train["base_model"],
        "max_seq_length": train["max_seq_length"],
        "generator": llm.meta(),
        **asdict(stats_all),
        "by_kind": dict(by_kind),
        "by_doc": dict(by_doc),
        "token_lengths": {"min": min(sizes), "median": median(sizes), "max": max(sizes)} if sizes else None,
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(
        f"DONE {OUT_DIR}: kept {stats_all.kept}/{stats_all.total} "
        f"by_kind={dict(by_kind)} tokens={min(sizes) if sizes else 0}..{max(sizes) if sizes else 0}",
        flush=True,
    )


if __name__ == "__main__":
    main()
