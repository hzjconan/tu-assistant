"""MLX 训练封装（T032）：`tu train --config`。

调用 ``mlx_lm lora``，把 ExperimentRun 清单写入
``artifacts/train/<exp_id>/manifest.json``（宪章原则 VI）。
"""

from __future__ import annotations

import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import yaml

from ..manifest import write_manifest


def run_training(config_path: str | Path, artifacts_dir: str | Path = "artifacts") -> dict:
    cfg = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    data_dir = cfg["data"]
    exp_id = cfg.get("exp_id") or datetime.now(UTC).strftime("exp-%Y%m%d-%H%M%S")
    exp_dir = Path(artifacts_dir) / "train" / exp_id
    exp_dir.mkdir(parents=True, exist_ok=True)
    adapter_dir = exp_dir / "adapters"
    log_path = exp_dir / "train.log"

    lora = cfg.get("lora", {})

    # epochs → iters：mlx_lm lora 用迭代次数；1 epoch ≈ 训练集条数 / batch
    train_file = Path(data_dir) / "train.jsonl"
    n_train = (
        sum(1 for _ in train_file.open(encoding="utf-8")) if train_file.exists() else 0
    )
    iters = cfg.get("iters")
    if not iters:
        iters = int(n_train * cfg.get("epochs", 2) / cfg.get("batch_size", 1))

    mlx_cfg = {
        "model": cfg["base_model"],
        "data": str(data_dir),
        "train": True,
        "fine_tune_type": "lora",
        "adapter_path": str(adapter_dir),
        "batch_size": cfg.get("batch_size", 1),
        "iters": iters,
        "val_batches": cfg.get("val_batches", 25),
        "learning_rate": cfg.get("learning_rate", 1e-5),
        "num_layers": lora.get("num_layers", 16),
        "lora_parameters": {
            "rank": lora.get("rank", 8),
            "alpha": lora.get("alpha", 16),
            "dropout": lora.get("dropout", 0.0),
            "scale": lora.get("scale", 10.0),
        },
        "seed": cfg.get("seed", 42),
        "max_seq_length": cfg.get("max_seq_length", 2048),
        "grad_checkpoint": cfg.get("grad_checkpoint", True),
        "steps_per_report": cfg.get("steps_per_report", 50),
        "steps_per_eval": cfg.get("steps_per_eval", 200),
        "save_every": cfg.get("save_every", max(1, iters)),
    }
    mlx_cfg_path = exp_dir / "mlx_config.yaml"
    mlx_cfg_path.write_text(yaml.safe_dump(mlx_cfg), encoding="utf-8")

    cmd = [sys.executable, "-m", "mlx_lm", "lora", "-c", str(mlx_cfg_path)]

    started = time.time()
    with log_path.open("w", encoding="utf-8") as log:
        proc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT)
    duration_s = int(time.time() - started)

    write_manifest(
        exp_dir,
        artifact_id=exp_id,
        artifact_type="experiment",
        inputs={"data": str(data_dir)},
        config={
            "base_model": cfg["base_model"],
            "base_license": cfg.get("base_license", ""),
            "batch_size": cfg.get("batch_size"),
            "iters": iters,
            "epochs": cfg.get("epochs"),
            "learning_rate": cfg.get("learning_rate"),
            "lora": lora,
            "max_seq_length": cfg.get("max_seq_length"),
            "grad_checkpoint": cfg.get("grad_checkpoint", True),
        },
        seed=cfg.get("seed", 42),
        extra={
            "method": "mlx_qlora",
            "hardware": cfg.get("hardware", "M1 Pro / 32GB"),
            "duration_s": duration_s,
            "log": str(log_path),
            "adapter_dir": str(adapter_dir),
            "returncode": proc.returncode,
        },
    )
    return {
        "exp_id": exp_id,
        "returncode": proc.returncode,
        "duration_s": duration_s,
        "log": str(log_path),
        "adapters": str(adapter_dir),
    }
