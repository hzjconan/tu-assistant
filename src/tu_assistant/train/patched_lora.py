"""带数值稳定性补丁的 ``mlx_lm lora`` 入口（E001 尝试 4 修复 1+2）。

等价于 ``python -m mlx_lm lora -c <config>``，但在调起训练前安装：

1. **fp32 注意力**：包装 ``mx.fast.scaled_dot_product_attention``，调用前把
   q/k/v（及可选的 mask / sinks，若为数组）转 ``mx.float32``，调用原函数后
   输出转回输入 dtype。修复 fp16 反向中间量溢出（根因见
   ``docs/experiments/E001-1.5b-citation-failure.md`` 尝试 4"NaN 根因诊断"H5：
   实测同一份 q/k/v 转 fp32 反向 0 个 NaN，bf16 仍 NaN 故不用）。
   补丁点在 ``mx.fast`` 模块属性上，``mlx_lm.models.base`` 及各模型文件
   （如 qwen2）都是调用时做 ``mx.fast.scaled_dot_product_attention``
   属性查找，天然全部覆盖。
2. **NaN 守卫**：包装 ``mlx.optimizers.Optimizer.update``，对 grads 做
   ``tree_flatten`` + ``isfinite`` 检查。存在非有限值时把该步参数更新回滚
   （等价跳过本步 update），并把"非有限元素数 / 跳过步数"累计进
   ``optimizer.state``——它随 ``outputs=state`` 穿过 ``mx.compile`` 的训练
   循环，每步 ``mx.eval`` 时随之物化，由 ``TrainUI.report_train`` 的包装
   在打 iter 行时顺带输出 ``[NaN-guard]`` 告警。
   注意 ``step`` 在 ``mx.compile`` 内执行，守卫全程只做惰性数组运算
   （``mx.where`` 回滚），不做值依赖的 Python 分支。

只影响训练进程：本模块是训练专用入口，serve/chat/eval 不经过这里。

用法::

    python -m tu_assistant.train.patched_lora -c <mlx_config.yaml>
    python -m tu_assistant.train.patched_lora --selftest   # 补丁自检
"""

from __future__ import annotations

import functools
import sys

import mlx.core as mx
from mlx.utils import tree_flatten, tree_map, tree_unflatten

_GUARD_BAD_KEY = "_nan_guard_bad"  # 累计非有限梯度元素数
_GUARD_SKIP_KEY = "_nan_guard_skips"  # 累计被回滚（跳过）的步数

_ORIG_SDPA = None
_ORIG_OPT_UPDATE = None
_ORIG_REPORT_TRAIN = None
_INSTALLED = False

_STATE = {
    "sdpa_calls": 0,  # fp32 SDPA 包装被调用次数（验证补丁生效用）
    "guard_reported": 0,  # 上次已告警的累计跳过步数
}
_LAST_OPT = None  # 最近一次经过守卫的 optimizer（供 report_train 告警读计数）


def _sdpa_fp32(q, k, v, *, scale, mask=None, sinks=None, **kwargs):
    """fp32 版 ``mx.fast.scaled_dot_product_attention`` 包装。"""
    _STATE["sdpa_calls"] += 1
    out_dtype = q.dtype
    q = q.astype(mx.float32)
    k = k.astype(mx.float32)
    v = v.astype(mx.float32)
    if isinstance(mask, mx.array):
        mask = mask.astype(mx.float32)
    if isinstance(sinks, mx.array):
        sinks = sinks.astype(mx.float32)
    out = _ORIG_SDPA(q, k, v, scale=scale, mask=mask, sinks=sinks, **kwargs)
    return out.astype(out_dtype)


def _guarded_opt_update(self, model, gradients):
    """``Optimizer.update`` 的 NaN 守卫包装（compile 安全：只做数组运算）。

    - 统计本步梯度中非有限元素数 ``bad``，累计进 ``self.state``；
    - 非有限梯度置零后照常调用原 update（置零防止 NaN 传入 Adam）；
    - ``bad > 0`` 时对新参数做 ``mx.where(bad>0, old, new)`` 回滚，
      等价于跳过本步参数更新（惰性标量，compiled graph 内可用）。
    """
    global _LAST_OPT
    _LAST_OPT = self

    grad_leaves = [g for _, g in tree_flatten(gradients)]
    if not grad_leaves:
        return _ORIG_OPT_UPDATE(self, model, gradients)

    bad = functools.reduce(
        mx.add,
        (mx.sum(mx.logical_not(mx.isfinite(g)).astype(mx.int32)) for g in grad_leaves),
        mx.array(0, mx.int32),
    )
    prev_bad = self.state.get(_GUARD_BAD_KEY)
    self.state[_GUARD_BAD_KEY] = bad if prev_bad is None else prev_bad + bad
    skip = (bad > 0).astype(mx.int32)
    prev_skips = self.state.get(_GUARD_SKIP_KEY)
    self.state[_GUARD_SKIP_KEY] = skip if prev_skips is None else prev_skips + skip

    # 更新前的旧参数引用（MLX 数组不可变，旧引用保持旧值）
    old_params = dict(tree_flatten(model.trainable_parameters()))

    gradients = tree_map(lambda g: mx.where(mx.isfinite(g), g, mx.zeros_like(g)), gradients)
    _ORIG_OPT_UPDATE(self, model, gradients)

    # bad > 0 时回滚本步参数更新（等价跳过 update）
    new_params = dict(tree_flatten(model.trainable_parameters()))
    reverted = tree_unflatten(
        [(k, mx.where(bad > 0, old_params[k], new_params[k])) for k in new_params if k in old_params]
    )
    model.update(reverted)


def _report_train_guarded(ui, it, train_loss, tokens_sec, trained_tokens):
    """``TrainUI.report_train`` 包装：打 iter 行后顺带输出 NaN 守卫告警。"""
    _ORIG_REPORT_TRAIN(ui, it, train_loss, tokens_sec, trained_tokens)
    try:
        if _LAST_OPT is not None and _GUARD_SKIP_KEY in _LAST_OPT.state:
            total_skips = int(_LAST_OPT.state[_GUARD_SKIP_KEY].item())
            total_bad = int(_LAST_OPT.state[_GUARD_BAD_KEY].item())
            delta = total_skips - _STATE["guard_reported"]
            if delta > 0:
                _STATE["guard_reported"] = total_skips
                print(
                    f"[NaN-guard] skip step x{delta} since last report "
                    f"(total skipped {total_skips}, non-finite grad elems {total_bad})"
                )
    except Exception:
        # 告警失败不能影响训练
        pass


def install() -> None:
    """安装全部补丁（幂等）。只应在训练入口调用。"""
    global _ORIG_SDPA, _ORIG_OPT_UPDATE, _ORIG_REPORT_TRAIN, _INSTALLED
    if _INSTALLED:
        return
    from mlx.optimizers import Optimizer
    from mlx_lm import cli_ui

    _ORIG_SDPA = mx.fast.scaled_dot_product_attention
    mx.fast.scaled_dot_product_attention = _sdpa_fp32

    _ORIG_OPT_UPDATE = Optimizer.update
    Optimizer.update = _guarded_opt_update

    _ORIG_REPORT_TRAIN = cli_ui.TrainUI.report_train
    cli_ui.TrainUI.report_train = _report_train_guarded

    _INSTALLED = True


def nan_guard_stats() -> dict:
    """返回守卫累计计数（已物化；供自检/调试）。"""
    stats = {"sdpa_calls": _STATE["sdpa_calls"]}
    if _LAST_OPT is not None:
        for key in (_GUARD_BAD_KEY, _GUARD_SKIP_KEY):
            if key in _LAST_OPT.state:
                stats[key] = int(_LAST_OPT.state[key].item())
    return stats


def _selftest() -> int:
    """补丁自检：验证 fp32 SDPA 包装生效、NaN 守卫能跳过坏梯度。"""
    import mlx.nn as nn
    import mlx.optimizers as optim

    failures = []

    # --- 1. fp32 SDPA 包装：经 mlx_lm.models.base 的调用链走到包装 ---
    from mlx_lm.models import base as lm_base

    calls_before = _STATE["sdpa_calls"]
    q = mx.random.normal((1, 4, 8, 16)).astype(mx.float16)
    k = mx.random.normal((1, 4, 8, 16)).astype(mx.float16)
    v = mx.random.normal((1, 4, 8, 16)).astype(mx.float16)
    out = lm_base.scaled_dot_product_attention(q, k, v, None, scale=0.35, mask="causal")
    mx.eval(out)
    if _STATE["sdpa_calls"] != calls_before + 1:
        failures.append("sdpa wrapper not invoked via mlx_lm.models.base")
    if out.dtype != mx.float16:
        failures.append(f"sdpa output dtype {out.dtype} != float16")
    if not bool(mx.isfinite(out).all()):
        failures.append("sdpa fp32 output non-finite")

    # --- 2. NaN 守卫：全 NaN 梯度 → 参数不变、skip 计数 +1 ---
    lin = nn.Linear(4, 4, bias=False)
    opt = optim.Adam(learning_rate=1e-2)
    w_before = lin.weight
    nan_grads = {"weight": mx.full(w_before.shape, float("nan"))}
    opt.update(lin, nan_grads)
    mx.eval(lin.parameters())
    if not bool(mx.allclose(lin.weight, w_before)):
        failures.append("NaN-grad step was not skipped (params changed)")
    stats = nan_guard_stats()
    if stats.get(_GUARD_SKIP_KEY, 0) < 1:
        failures.append("guard skip counter did not increase")

    # --- 3. 正常梯度：参数照常更新 ---
    w_prev = lin.weight
    opt.update(lin, {"weight": mx.ones_like(w_prev)})
    mx.eval(lin.parameters())
    if bool(mx.allclose(lin.weight, w_prev)):
        failures.append("healthy grad did not update params")

    if failures:
        for f in failures:
            print(f"[selftest] FAIL: {f}")
        return 1
    print(f"[selftest] OK  stats={nan_guard_stats()}")
    return 0


def main() -> None:
    install()
    if "--selftest" in sys.argv:
        sys.argv.remove("--selftest")
        raise SystemExit(_selftest())
    from mlx_lm.lora import main as lora_main

    lora_main()


if __name__ == "__main__":
    main()
