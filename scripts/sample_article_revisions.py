"""T053 小批验收：基于已通过人工复审的 1–2 篇初稿生成多轮修改样本。"""

import argparse
import json
import sqlite3
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from statistics import median

from tu_assistant.config import load_synth_config, load_yaml
from tu_assistant.synth.articles import (
    MAX_DRAFT_TOKENS,
    REVISION_PROMPT_VERSION,
    REVISION_TYPES,
    TRAIN_CONFIG,
    ArticleStats,
    generate_revisions,
)
from tu_assistant.synth.llm import CompletionTruncatedError, from_config


class RecordingClient:
    """保存本批原始回复，方便复审拒收原因和离线复放。"""

    def __init__(self, client, stream):
        self.client = client
        self.stream = stream

    def chat(self, messages, **kwargs):
        try:
            text = self.client.chat(messages, **kwargs)
        except CompletionTruncatedError:
            self.stream.write('{"truncated":true}\n')
            self.stream.flush()
            raise
        self.stream.write(json.dumps({"text": text}, ensure_ascii=False) + "\n")
        self.stream.flush()
        return text


def _load_drafts(paths: list[Path]) -> list[dict]:
    drafts: list[dict] = []
    for p in paths:
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                drafts.append(json.loads(line))
    return drafts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kb", type=Path, required=True)
    parser.add_argument(
        "--drafts",
        type=Path,
        nargs="+",
        required=True,
        help="已通过人工复审的初稿 JSONL（禁止传未审的 samples.jsonl）",
    )
    parser.add_argument("--requests", type=int, default=None)
    parser.add_argument(
        "--types",
        nargs="+",
        choices=REVISION_TYPES,
        default=list(REVISION_TYPES),
        help="按顺序循环的修改类型",
    )
    parser.add_argument("--max-draft-tokens", type=int, default=MAX_DRAFT_TOKENS)
    parser.add_argument("--train-config", type=Path, default=TRAIN_CONFIG)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    drafts = _load_drafts(args.drafts)
    cfg = load_synth_config()
    llm = from_config(cfg)
    out = args.out or Path("artifacts/synth/articles") / (
        "revisions-" + datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
    )
    out.mkdir(parents=True, exist_ok=False)
    stats = ArticleStats()
    train = load_yaml(args.train_config)
    conn = sqlite3.connect(args.kb.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        with (out / "responses.jsonl").open("x", encoding="utf-8") as stream:
            samples = generate_revisions(
                conn,
                RecordingClient(llm, stream),
                cfg,
                drafts,
                revision_types=tuple(args.types),
                n_requests=args.requests,
                stats=stats,
                train_config=args.train_config,
                max_draft_tokens=args.max_draft_tokens,
            )
    finally:
        conn.close()

    with (out / "samples.jsonl").open("w", encoding="utf-8") as f:
        for sample in samples:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")

    sizes = [s["meta"]["tokens"] for s in samples]
    by_type: dict[str, int] = {}
    for s in samples:
        rt = s["meta"]["revision_type"]
        by_type[rt] = by_type.get(rt, 0) + 1

    report = {
        "kb": str(args.kb),
        "draft_files": [str(p) for p in args.drafts],
        "draft_count": len(drafts),
        "synth_config": "configs/synth.yaml",
        "train_config": str(args.train_config),
        "base_model": train["base_model"],
        "max_seq_length": train["max_seq_length"],
        "max_draft_tokens": args.max_draft_tokens,
        "requests": stats.total,
        "revision_types": args.types,
        "revision_prompt_version": REVISION_PROMPT_VERSION,
        "generator": llm.meta(),
        **asdict(stats),
        "kept_by_type": by_type,
        "materials": dict(stats.materials),
        "token_lengths": {"min": min(sizes), "median": median(sizes), "max": max(sizes)} if sizes else None,
    }
    (out / "manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(f"{out}  保留 {stats.kept}/{stats.total}  分类型 {by_type}  丢弃 {stats.reasons}", flush=True)


if __name__ == "__main__":
    main()
