"""tu 命令入口。"""

from __future__ import annotations

import typer

app = typer.Typer(help="工会法律条款智能助手（POC）命令行工具")


@app.callback()
def _main() -> None:
    """工会法律条款智能助手（POC）命令行工具。"""


@app.command()
def version() -> None:
    """显示版本。"""
    typer.echo("tu-assistant 0.1.0")


if __name__ == "__main__":
    app()
