"""T052 小批验收。从仓库根目录运行，产物与正式数据集隔离。"""

import argparse
import json
import sqlite3
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from statistics import median

from tu_assistant.config import load_synth_config, load_yaml
from tu_assistant.synth.articles import ARTICLE_PROMPT_VERSION, TRAIN_CONFIG, ArticleStats, generate
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kb", type=Path, required=True)
    parser.add_argument("--requests", type=int, default=12)
    parser.add_argument(
        "--modes",
        nargs="+",
        choices=("default", "1", "2", "3"),
        default=["default", "1", "2", "3"],
        help="按顺序循环的篇数模式",
    )
    parser.add_argument("--train-config", type=Path, default=TRAIN_CONFIG)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    cfg = load_synth_config()
    llm = from_config(cfg)
    out = args.out or Path("artifacts/synth/articles") / datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
    out.mkdir(parents=True, exist_ok=False)
    stats = ArticleStats()
    train = load_yaml(args.train_config)
    conn = sqlite3.connect(args.kb.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        with (out / "responses.jsonl").open("x", encoding="utf-8") as stream:
            samples = generate(
                conn,
                RecordingClient(llm, stream),
                cfg,
                n_requests=args.requests,
                request_modes=tuple(None if m == "default" else int(m) for m in args.modes),
                stats=stats,
                train_config=args.train_config,
            )
    finally:
        conn.close()
    with (out / "samples.jsonl").open("w", encoding="utf-8") as f:
        for sample in samples:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")
    sizes = [s["meta"]["tokens"] for s in samples]
    report = {
        "kb": str(args.kb),
        "synth_config": "configs/synth.yaml",
        "train_config": str(args.train_config),
        "base_model": train["base_model"],
        "max_seq_length": train["max_seq_length"],
        "requests": args.requests,
        "modes": args.modes,
        "article_prompt_version": ARTICLE_PROMPT_VERSION,
        "generator": llm.meta(),
        **asdict(stats),
        "materials": dict(stats.materials),
        "token_lengths": {"min": min(sizes), "median": median(sizes), "max": max(sizes)} if sizes else None,
    }
    (out / "manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(f"{out}  保留 {stats.kept}/{stats.total}  丢弃 {stats.reasons}", flush=True)


if __name__ == "__main__":
    main()
