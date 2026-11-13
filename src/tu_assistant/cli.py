"""tu 命令入口。"""

from __future__ import annotations

from pathlib import Path

import typer

app = typer.Typer(help="工会法律条款智能助手（POC）命令行工具")
kb_app = typer.Typer(help="知识库：导入、查看、关联")
app.add_typer(kb_app, name="kb")


@app.callback()
def _main() -> None:
    """工会法律条款智能助手（POC）命令行工具。"""


@app.command()
def version() -> None:
    """显示版本。"""
    typer.echo("tu-assistant 0.1.0")


def _latest_kb(artifacts_dir: str) -> Path:
    files = sorted(Path(artifacts_dir, "kb").glob("kb-*.sqlite"))
    if not files:
        typer.secho("没有知识库版本，请先运行 tu kb import", fg="red")
        raise typer.Exit(1)
    return files[-1]


@kb_app.command("import")
def kb_import(
    directory: str = typer.Argument(..., help="文档目录（如 inputs/project/）"),
    artifacts: str = typer.Option("artifacts", help="产物目录"),
) -> None:
    """整批导入文档，拆分条款并入库校验，生成新知识库版本。"""
    from .kb.ingest import import_directory

    result = import_directory(directory, artifacts)
    typer.echo(
        f"kb_version={result['kb_version']}  文件 {result['files']} 篇 / "
        f"条款 {result['clauses']} 条 / 问题 {result['issues']} 个"
    )
    typer.echo(f"校验报告：{result['report']}")


@kb_app.command("list")
def kb_list(
    kb_version: str | None = typer.Option(None, help="知识库版本，默认最新"),
    artifacts: str = typer.Option("artifacts"),
) -> None:
    """列出知识库中的文件（供人工核对）。"""
    from .kb.store import list_documents, open_kb

    kb_path = (
        Path(artifacts, "kb", f"{kb_version}.sqlite")
        if kb_version
        else _latest_kb(artifacts)
    )
    conn = open_kb(kb_path)
    for d in list_documents(conn):
        typer.echo(
            f"{d['title']}（{d['version_label'] or '无版本'}）"
            f"[{d['status']}] 条款 {d['clauses']} 条"
        )
    conn.close()


@kb_app.command("show")
def kb_show(
    title: str = typer.Argument(..., help="文件全称（不含书名号）"),
    article_no: int = typer.Argument(..., help="条号（整数）"),
    paragraph: int | None = typer.Option(None, "--paragraph", "-p"),
    item: int | None = typer.Option(None, "--item", "-i"),
    kb_version: str | None = typer.Option(None),
    artifacts: str = typer.Option("artifacts"),
) -> None:
    """查看某条款原文，便于人工核对。"""
    from .kb.store import article_clauses, get_clause, open_kb

    kb_path = (
        Path(artifacts, "kb", f"{kb_version}.sqlite")
        if kb_version
        else _latest_kb(artifacts)
    )
    conn = open_kb(kb_path)
    if paragraph is None and item is None:
        rows = article_clauses(conn, title, article_no)
    else:
        c = get_clause(conn, title, article_no, paragraph, item)
        rows = [c] if c else []
    conn.close()
    if not rows:
        typer.secho("未找到该条款", fg="red")
        raise typer.Exit(1)
    for c in rows:
        typer.echo(f"{c.number_text}\n{c.text}\n")


relations_app = typer.Typer(help="条款关联：抽取与人工确认")
kb_app.add_typer(relations_app, name="relations")


@relations_app.command("extract")
def relations_extract(
    kb_version: str | None = typer.Option(None),
    artifacts: str = typer.Option("artifacts"),
) -> None:
    """用规则抽取条款关联候选，输出 relations_pending.jsonl 待人工确认。"""
    import json as _json
    from itertools import groupby

    from .kb.relations import extract_relations
    from .kb.store import all_clauses, open_kb

    kb_path = (
        Path(artifacts, "kb", f"{kb_version}.sqlite")
        if kb_version
        else _latest_kb(artifacts)
    )
    conn = open_kb(kb_path)
    clauses = all_clauses(conn)
    conn.close()

    pending = []
    for _doc_id, group in groupby(clauses, key=lambda c: c.doc_id):
        pending.extend(extract_relations(list(group)))

    out = Path(artifacts, "kb", f"{kb_path.stem}-relations_pending.jsonl")
    with out.open("w", encoding="utf-8") as f:
        for r in pending:
            f.write(
                _json.dumps(
                    {
                        "from_clause_id": r.from_clause_id,
                        "to_clause_id": r.to_clause_id,
                        "relation_type": r.relation_type,
                        "origin": r.origin,
                        "confirmed": False,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    typer.echo(f"候选关联 {len(pending)} 条 → {out}")
    typer.echo("请逐条把 confirmed 改为 true/false，然后运行 tu kb relations confirm")


@relations_app.command("confirm")
def relations_confirm(
    file: str = typer.Argument(..., help="人工确认后的 jsonl 文件"),
    kb_version: str | None = typer.Option(None),
    artifacts: str = typer.Option("artifacts"),
) -> None:
    """导入人工确认的条款关联。"""
    import json as _json

    from .kb.models import ClauseRelation
    from .kb.store import insert_relation, open_kb

    kb_path = (
        Path(artifacts, "kb", f"{kb_version}.sqlite")
        if kb_version
        else _latest_kb(artifacts)
    )
    conn = open_kb(kb_path)
    n_confirmed = n_rejected = 0
    with conn:
        for line in Path(file).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            d = _json.loads(line)
            if d.get("confirmed"):
                insert_relation(
                    conn,
                    ClauseRelation(
                        d["from_clause_id"],
                        d["to_clause_id"],
                        d["relation_type"],
                        d.get("origin", "manual"),
                        confirmed=True,
                    ),
                )
                n_confirmed += 1
            else:
                n_rejected += 1
    conn.close()
    typer.echo(f"已确认 {n_confirmed} 条关联入库；{n_rejected} 条被拒绝/未确认")


serve_app = typer.Typer(help="模型服务")
app.add_typer(serve_app, name="serve")


@serve_app.command("model")
def serve_model(
    exp: str = typer.Option(..., "--exp", help="实验 ID（artifacts/train/<exp>）"),
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(8080),
    artifacts: str = typer.Option("artifacts"),
) -> None:
    """启动本地模型端点（mlx_lm.server，只监听本机）。"""
    import json as _json
    import subprocess
    import sys

    if host not in {"127.0.0.1", "localhost"}:
        typer.secho("模型端点只监听本机（127.0.0.1 / localhost）", fg="red")
        raise typer.Exit(1)

    exp_dir = Path(artifacts, "train", exp)
    manifest = _json.loads((exp_dir / "manifest.json").read_text(encoding="utf-8"))
    base = manifest["config"]["base_model"]
    adapter = exp_dir / "adapters"
    if not adapter.exists():
        typer.secho(f"适配器不存在：{adapter}", fg="red")
        raise typer.Exit(1)

    cmd = [
        sys.executable, "-m", "mlx_lm.server",
        "--model", base,
        "--adapter-path", str(adapter),
        "--host", host,
        "--port", str(port),
    ]
    typer.echo("启动：" + " ".join(cmd))
    subprocess.run(cmd)


synth_app = typer.Typer(help="数据合成（唯一使用外部大模型的命令组）")
eval_app = typer.Typer(help="评测")
app.add_typer(synth_app, name="synth")
app.add_typer(eval_app, name="eval")


@synth_app.command("evalcases")
def synth_evalcases(
    kb_version: str | None = typer.Option(None),
    n: int = typer.Option(40, help="候选用例数"),
    artifacts: str = typer.Option("artifacts"),
    synth_config: str = typer.Option("configs/synth.yaml"),
) -> None:
    """生成评测候选用例（调用外部大模型，需 TU_EXTERNAL_LLM_API_KEY）。"""
    from .config import load_synth_config
    from .kb.store import open_kb
    from .synth.evalcases import generate_candidates
    from .synth.llm import from_config

    kb_path = (
        Path(artifacts, "kb", f"{kb_version}.sqlite")
        if kb_version
        else _latest_kb(artifacts)
    )
    conn = open_kb(kb_path)
    llm = from_config(load_synth_config(synth_config))
    result = generate_candidates(conn, llm, n=n)
    conn.close()
    typer.echo(f"候选用例 {result['written']} 条 → {result['path']}")


@app.command("train")
def train(
    config: str = typer.Option(..., "--config", help="训练配置 yaml"),
    artifacts: str = typer.Option("artifacts"),
) -> None:
    """本机 MLX QLoRA 训练。"""
    from .train.mlx_train import run_training

    result = run_training(config, artifacts)
    typer.echo(
        f"exp_id={result['exp_id']}  退出码 {result['returncode']}  "
        f"耗时 {result['duration_s']}s  日志 {result['log']}"
    )


@eval_app.command("run")
def eval_run(
    cases: str = typer.Option(..., "--cases", help="评测集目录或 jsonl"),
    kb_version: str | None = typer.Option(None),
    exp: str | None = typer.Option(None, "--exp", help="实验 ID（记录用）"),
    config: str = typer.Option("configs/app.yaml"),
    artifacts: str = typer.Option("artifacts"),
) -> None:
    """运行评测（temperature=0，不调用外部服务）。"""
    from .config import get, load_app_config
    from .eval.runner import run_eval

    cfg = load_app_config(config)
    kb_path = (
        Path(artifacts, "kb", f"{kb_version}.sqlite")
        if kb_version
        else _latest_kb(artifacts)
    )
    result = run_eval(
        cases_path=cases,
        kb_path=kb_path,
        endpoint=get(cfg, "runtime.model_endpoint"),
        allowed_hosts=get(cfg, "runtime.allowed_hosts"),
        model_name=get(cfg, "runtime.model_name", "default"),
        artifacts_dir=artifacts,
        exp_id=exp,
    )
    typer.echo(f"run_id={result['run_id']}  用例 {result['cases']} 条 → {result['dir']}")
    if result["gold_issues"]:
        typer.secho(
            f"注意：{len(result['gold_issues'])} 个 gold 条款在知识库中不存在",
            fg="yellow",
        )


if __name__ == "__main__":
    app()
