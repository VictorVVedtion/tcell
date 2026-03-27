#!/usr/bin/env python3
"""
evolve.py — Critic 进化循环的数据层
等价于 autoresearch 的实验循环控制器。

这个脚本不直接执行 critic（那是 Claude Code subagent 的工作）。
它负责：
  1. 选择下一个要进化的 critic
  2. 选择变异算子
  3. 准备回放数据
  4. 接收 subagent 的评估结果
  5. 做 keep/discard 决策
  6. 记录到 results.tsv
  7. 检查停止条件

用法：
  python3 evolve.py select          # 选择下一个 critic + 变异算子
  python3 evolve.py evaluate <json> # 接收评估结果，做 keep/discard 决策
  python3 evolve.py stop-check      # 检查是否满足停止条件
  python3 evolve.py summary         # 输出进化摘要
"""

from __future__ import annotations

import json
import sys
import os
import random
import argparse
import subprocess
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional

# 复用 prepare.py 的基础设施
sys.path.insert(0, str(Path(__file__).parent))
from prepare import (
    PROJECT_ROOT, CANARIES_FILE, CLEAN_SAMPLES_FILE, RESULTS_FILE,
    LOG_FILE, CRITICS_DIR, REPORTS_DIR,
    load_jsonl, evaluate_regret, evaluate_fp_rate, log_entry,
    _get_cold_start_threshold,
)

MUTATION_OPERATORS = [
    "threshold_shift",
    "focus_expand",
    "focus_narrow",
    "strategy_rewrite",
    "example_inject",
    "simplify",
]


# ── Critic 元数据解析 ─────────────────────────────────
def parse_critic_frontmatter(path: Path) -> dict:
    """解析 critic .md 文件的 YAML frontmatter。"""
    text = path.read_text()
    if not text.startswith("---"):
        return {"name": path.stem, "version": 0, "detection_rate": 0.0, "fp_rate": 0.0}

    end = text.index("---", 3)
    frontmatter = text[3:end].strip()
    meta = {}
    for line in frontmatter.splitlines():
        if ":" in line:
            key, val = line.split(":", 1)
            key = key.strip()
            val = val.strip()
            # 简单类型推断
            if val.replace(".", "").replace("-", "").isdigit():
                try:
                    val = int(val) if "." not in val else float(val)
                except ValueError:
                    pass
            meta[key] = val
    return meta


def update_critic_frontmatter(path: Path, updates: dict):
    """更新 critic .md 文件的 frontmatter 字段。"""
    text = path.read_text()
    if not text.startswith("---"):
        return

    end = text.index("---", 3)
    frontmatter = text[3:end].strip()
    body = text[end + 3:]

    # 解析现有字段
    lines = []
    for line in frontmatter.splitlines():
        if ":" in line:
            key = line.split(":")[0].strip()
            if key in updates:
                val = updates[key]
                lines.append(f"{key}: {val}")
                del updates[key]
                continue
        lines.append(line)

    # 追加新字段
    for key, val in updates.items():
        lines.append(f"{key}: {val}")

    new_frontmatter = "\n".join(lines)
    path.write_text(f"---\n{new_frontmatter}\n---{body}")


# ── 选择下一个 critic ─────────────────────────────────
def select_next() -> dict:
    """
    选择下一个要进化的 critic 和变异算子。
    策略：最久未进化的 critic 优先。
    """
    # 冷启动门控：canaries < threshold 时禁止进化（阈值自适应）
    canaries = load_jsonl(CANARIES_FILE)
    COLD_START_THRESHOLD = _get_cold_start_threshold()
    if len(canaries) < COLD_START_THRESHOLD:
        print(json.dumps({
            "error": "cold_start",
            "message": f"Evolution paused: {len(canaries)} canaries < {COLD_START_THRESHOLD} threshold. "
                       f"Sidebar is in data collection mode. Add more canaries to unlock evolution.",
            "canaries_count": len(canaries),
            "threshold": COLD_START_THRESHOLD,
        }, ensure_ascii=False))
        sys.exit(1)

    critics = list(CRITICS_DIR.glob("*.md"))
    if not critics:
        print(json.dumps({"error": "no critics found"}))
        sys.exit(1)

    # 按 last_evolved 排序，最旧的优先
    scored = []
    for c in critics:
        meta = parse_critic_frontmatter(c)
        last = meta.get("last_evolved", "1970-01-01T00:00:00Z")
        scored.append((last, c, meta))
    scored.sort(key=lambda x: x[0])

    target_path = scored[0][1]
    target_meta = scored[0][2]

    # 选变异算子（随机，但 simplify 概率低一些）
    weights = [1.0] * len(MUTATION_OPERATORS)
    weights[MUTATION_OPERATORS.index("simplify")] = 0.3  # simplify 不常用
    operator = random.choices(MUTATION_OPERATORS, weights=weights, k=1)[0]

    # 加载回放数据
    canaries = load_jsonl(CANARIES_FILE)
    clean_samples = load_jsonl(CLEAN_SAMPLES_FILE)

    # 找最新的 canary 用于 example_inject
    latest_canary = None
    if canaries:
        latest_canary = max(canaries, key=lambda c: c.get("timestamp", ""))

    result = {
        "critic_name": target_meta.get("name", target_path.stem),
        "critic_path": str(target_path),
        "critic_content": target_path.read_text(),
        "current_version": target_meta.get("version", 0),
        "current_detection_rate": target_meta.get("detection_rate", 0.0),
        "current_fp_rate": target_meta.get("fp_rate", 0.0),
        "mutation_operator": operator,
        "canaries_count": len(canaries),
        "clean_samples_count": len(clean_samples),
        "canaries": canaries,
        "clean_samples": clean_samples,
        "latest_canary": latest_canary,
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


# ── 评估结果处理 ──────────────────────────────────────
def process_evaluation(result_json: str) -> dict:
    """
    接收 subagent 的评估结果，做 keep/discard 决策。

    期望输入格式：
    {
      "critic_name": "overconfidence",
      "mutation_operator": "threshold_shift",
      "mutation_description": "同质化比例从 30% 改为 33%",
      "canary_results": [
        {"canary_id": "canary-001", "detected": true, "severity": 3, ...},
        ...
      ],
      "clean_results": [
        {"sample_id": "clean-001", "detected": false, ...},
        ...
      ],
      "mutated_content": "变异后的完整 critic 内容"
    }
    """
    try:
        result = json.loads(result_json)
    except json.JSONDecodeError:
        print(json.dumps({"error": "invalid JSON input"}))
        sys.exit(1)

    critic_name = result["critic_name"]
    operator = result["mutation_operator"]
    mutation_desc = result.get("mutation_description", "")
    canary_results = result.get("canary_results", [])
    clean_results = result.get("clean_results", [])
    mutated_content = result.get("mutated_content", "")

    # 加载数据
    canaries = load_jsonl(CANARIES_FILE)
    clean_samples = load_jsonl(CLEAN_SAMPLES_FILE)

    # 计算新指标
    new_detection = _calc_detection_rate(canaries, canary_results)
    new_fp = _calc_fp_rate(clean_samples, clean_results)

    # 读取旧指标
    critic_path = CRITICS_DIR / f"{critic_name}.md"
    old_meta = parse_critic_frontmatter(critic_path) if critic_path.exists() else {}
    old_detection = float(old_meta.get("detection_rate", 0.0))
    old_fp = float(old_meta.get("fp_rate", 0.0))
    old_version = int(old_meta.get("version", 0))

    # keep/discard 决策
    detection_improved = (new_detection - old_detection) >= 0.05  # ≥ 5% 提升
    fp_within_budget = new_fp <= 0.10  # ≤ 10%

    if detection_improved and fp_within_budget:
        decision = "keep"
        reason = f"+{(new_detection - old_detection)*100:.1f}% detection, FP {new_fp*100:.1f}% within budget"

        # 更新 critic 文件
        if mutated_content and critic_path.exists():
            critic_path.write_text(mutated_content)
            update_critic_frontmatter(critic_path, {
                "version": old_version + 1,
                "detection_rate": f"{new_detection:.2f}",
                "fp_rate": f"{new_fp:.2f}",
                "last_evolved": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            })

        # git commit
        _git_commit(critic_name, operator, reason)

        log_entry(
            f"🧬 Critic Evolution · {critic_name}\n"
            f"  mutation: {operator} ({mutation_desc})\n"
            f"  result: detection {old_detection:.2f} → {new_detection:.2f} (+{(new_detection-old_detection)*100:.1f}%), FP {new_fp:.2f}\n"
            f"  decision: ✅ keep"
        )
    else:
        decision = "discard"
        reasons = []
        if not detection_improved:
            reasons.append(f"detection {old_detection:.2f} → {new_detection:.2f} (<5% improvement)")
        if not fp_within_budget:
            reasons.append(f"FP {new_fp*100:.1f}% exceeded 10% constraint")
        reason = "; ".join(reasons)

        # git reset（如果有未提交的变更）
        _git_reset()

        log_entry(
            f"🧬 Critic Evolution · {critic_name}\n"
            f"  mutation: {operator} ({mutation_desc})\n"
            f"  result: detection {old_detection:.2f} → {new_detection:.2f}, FP {new_fp:.2f}\n"
            f"  decision: ❌ discard — {reason}"
        )

    # 记录到 results.tsv
    iteration = _next_iteration()
    tsv_line = "\t".join([
        str(iteration),
        critic_name,
        operator,
        f"{old_detection:.2f}",
        f"{new_detection:.2f}",
        f"{new_fp:.2f}",
        decision,
        reason,
    ])
    with open(RESULTS_FILE, "a") as f:
        f.write(tsv_line + "\n")

    output = {
        "critic_name": critic_name,
        "iteration": iteration,
        "decision": decision,
        "reason": reason,
        "detection_before": old_detection,
        "detection_after": new_detection,
        "fp_rate": new_fp,
        "version": old_version + 1 if decision == "keep" else old_version,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return output


def _calc_detection_rate(canaries: list[dict], results: list[dict]) -> float:
    """计算在 canaries 上的检出率。"""
    if not canaries:
        return 0.0
    detected = sum(
        1 for c in canaries
        if any(r.get("canary_id") == c["id"] and r.get("detected") is True for r in results)
    )
    return detected / len(canaries)


def _calc_fp_rate(clean_samples: list[dict], results: list[dict]) -> float:
    """计算在 clean_samples 上的假阳性率。"""
    if not clean_samples:
        return 0.0
    false_pos = sum(
        1 for s in clean_samples
        if any(r.get("sample_id") == s["id"] and r.get("detected") is True for r in results)
    )
    return false_pos / len(clean_samples)


def _next_iteration() -> int:
    """获取下一个迭代编号。"""
    if not RESULTS_FILE.exists():
        return 1
    lines = RESULTS_FILE.read_text().splitlines()
    return len(lines)  # header 占一行，所以 len(lines) = 下一个编号


def _git_commit(critic_name: str, operator: str, reason: str):
    """git commit 进化结果。"""
    try:
        subprocess.run(
            ["git", "add", str(CRITICS_DIR / f"{critic_name}.md")],
            cwd=PROJECT_ROOT, capture_output=True, timeout=10,
        )
        msg = f"evolve: {critic_name} {operator} — {reason}"
        subprocess.run(
            ["git", "commit", "-m", msg],
            cwd=PROJECT_ROOT, capture_output=True, timeout=10,
        )
    except Exception:
        pass  # git 失败不阻塞进化


def _git_reset():
    """git reset 回上一个 commit（discard 变更）。"""
    try:
        subprocess.run(
            ["git", "checkout", "--", str(CRITICS_DIR)],
            cwd=PROJECT_ROOT, capture_output=True, timeout=10,
        )
    except Exception:
        pass


# ── 停止条件检查 ──────────────────────────────────────
def stop_check() -> dict:
    """检查是否满足停止条件。"""
    if not RESULTS_FILE.exists():
        result = {"should_stop": False, "reason": "no iterations yet"}
        print(json.dumps(result))
        return result

    lines = RESULTS_FILE.read_text().splitlines()[1:]  # skip header
    if not lines:
        result = {"should_stop": False, "reason": "no iterations yet"}
        print(json.dumps(result))
        return result

    # 解析最近的结果
    recent = []
    for line in lines[-50:]:  # 最近 50 次
        parts = line.split("\t")
        if len(parts) >= 7:
            recent.append({
                "iteration": parts[0],
                "critic": parts[1],
                "detection_before": float(parts[3]) if parts[3] else 0,
                "detection_after": float(parts[4]) if parts[4] else 0,
                "fp_rate": float(parts[5]) if parts[5] else 0,
                "decision": parts[6],
            })

    reasons = []

    # 条件 1：detection_rate 连续 20 次提升 < 1%
    if len(recent) >= 20:
        last_20 = recent[-20:]
        improvements = [
            r["detection_after"] - r["detection_before"]
            for r in last_20
        ]
        if all(imp < 0.01 for imp in improvements):
            reasons.append("convergence: detection improvement < 1% for 20 consecutive iterations")

    # 条件 2：fp_rate 连续 3 次 > 15%
    if len(recent) >= 3:
        last_3_fp = [r["fp_rate"] for r in recent[-3:]]
        if all(fp > 0.15 for fp in last_3_fp):
            reasons.append("overfitting: FP rate > 15% for 3 consecutive iterations")

    # 条件 3：canaries 无新增超过 7 天
    canaries = load_jsonl(CANARIES_FILE)
    if canaries:
        latest_ts = max(c.get("timestamp", "") for c in canaries)
        try:
            latest_dt = datetime.fromisoformat(latest_ts.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            if (now - latest_dt) > timedelta(days=7):
                reasons.append(f"data hunger: no new canaries for {(now - latest_dt).days} days")
        except (ValueError, TypeError):
            pass

    # 条件 4：连续 50 次 discard
    if len(recent) >= 50:
        last_50_decisions = [r["decision"] for r in recent[-50:]]
        if all(d == "discard" for d in last_50_decisions):
            reasons.append("bottleneck: 50 consecutive discards")

    should_stop = len(reasons) > 0
    result = {"should_stop": should_stop, "reasons": reasons}

    if should_stop:
        log_entry(
            f"⏸️ Evolution Paused\n"
            f"  reasons: {'; '.join(reasons)}\n"
            f"  resume: add new canaries to canaries.jsonl"
        )

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


# ── 进化摘要 ──────────────────────────────────────────
def summary():
    """输出进化摘要。"""
    if not RESULTS_FILE.exists():
        print("No evolution data yet.")
        return

    lines = RESULTS_FILE.read_text().splitlines()[1:]
    total = len(lines)
    keeps = sum(1 for l in lines if "\tkeep\t" in l)
    discards = sum(1 for l in lines if "\tdiscard\t" in l)

    # 每个 critic 的当前状态
    critics = list(CRITICS_DIR.glob("*.md"))
    print(f"═══ Evolution Summary ═══")
    print(f"Total iterations: {total} ({keeps} keep / {discards} discard)")
    print(f"Keep rate: {keeps/total*100:.1f}%" if total > 0 else "Keep rate: N/A")
    print()

    for c in sorted(critics):
        meta = parse_critic_frontmatter(c)
        name = meta.get("name", c.stem)
        ver = meta.get("version", 0)
        det = meta.get("detection_rate", 0.0)
        fp = meta.get("fp_rate", 0.0)
        print(f"  {name:20s}  v{ver:3d}  detection: {float(det):.2f}  FP: {float(fp):.2f}")

    # 总体 regret
    canaries = load_jsonl(CANARIES_FILE)
    if canaries:
        # 用最新的 detection_rates 估算
        total_severity = sum(c.get("severity", 1) for c in canaries)
        total_detected = sum(
            c.get("severity", 1) for c in canaries
            for cr in critics
            if float(parse_critic_frontmatter(cr).get("detection_rate", 0)) > 0.5
            and parse_critic_frontmatter(cr).get("name") == c.get("blindspot_type")
        )
        print(f"\nEstimated regret: ~{(total_severity - total_detected) / len(canaries):.2f}")


# ── Leaderboard ───────────────────────────────────────
def _load_critic_stats() -> list[dict]:
    """加载所有 critic 的统计数据，按 detection_rate 降序排列。"""
    critics = list(CRITICS_DIR.glob("*.md")) if CRITICS_DIR.exists() else []
    canaries = load_jsonl(CANARIES_FILE)

    # 每个 blindspot_type 的 canary 数量
    type_counts = {}
    for c in canaries:
        bt = c.get("blindspot_type", "")
        type_counts[bt] = type_counts.get(bt, 0) + 1

    # results.tsv 中每个 critic 的 keep/discard 统计
    critic_history = {}
    if RESULTS_FILE.exists():
        for line in RESULTS_FILE.read_text().splitlines()[1:]:
            parts = line.split("\t")
            if len(parts) >= 7:
                name = parts[1]
                if name not in critic_history:
                    critic_history[name] = {"keep": 0, "discard": 0}
                if parts[6] == "keep":
                    critic_history[name]["keep"] += 1
                else:
                    critic_history[name]["discard"] += 1

    stats = []
    for c in critics:
        meta = parse_critic_frontmatter(c)
        name = meta.get("name", c.stem)
        det = float(meta.get("detection_rate", 0.0))
        fp = float(meta.get("fp_rate", 0.0))
        ver = int(meta.get("version", 0))
        canary_count = type_counts.get(name, 0)
        hist = critic_history.get(name, {"keep": 0, "discard": 0})

        stats.append({
            "name": name,
            "version": ver,
            "detection_rate": det,
            "fp_rate": fp,
            "canary_count": canary_count,
            "total_canaries": len(canaries),
            "keeps": hist["keep"],
            "discards": hist["discard"],
            "last_evolved": meta.get("last_evolved", "unknown"),
        })

    # 排序：detection_rate 降序 → fp_rate 升序 → version 降序
    stats.sort(key=lambda x: (-x["detection_rate"], x["fp_rate"], -x["version"]))
    return stats


def leaderboard(json_mode: bool = False):
    """Critic 排行榜。"""
    stats = _load_critic_stats()
    canaries = load_jsonl(CANARIES_FILE)
    cold_start = len(canaries) < 20

    if not stats:
        print("No critics found.")
        return

    # Fleet 指标（加权平均，权重 = canary_count）
    total_weight = sum(s["canary_count"] for s in stats) or 1
    fleet_det = sum(s["detection_rate"] * s["canary_count"] for s in stats) / total_weight
    fleet_fp = sum(s["fp_rate"] * s["canary_count"] for s in stats) / total_weight

    if json_mode:
        print(json.dumps({
            "critics": [{"rank": i + 1, **s} for i, s in enumerate(stats)],
            "fleet_detection_rate": round(fleet_det, 4),
            "fleet_fp_rate": round(fleet_fp, 4),
            "cold_start": cold_start,
            "canaries_total": len(canaries),
            "canaries_needed": max(0, 20 - len(canaries)),
        }, ensure_ascii=False, indent=2))
        return

    print("═══ Critic Leaderboard ═══\n")
    print(f"{'#':>2}  {'Critic':<20s}  {'Ver':>4s}  {'Detection':>9s}  {'FP Rate':>7s}  {'Canaries':>8s}  Trend")
    for i, s in enumerate(stats):
        bar_filled = int(s["detection_rate"] * 10)
        bar = "━" * bar_filled + "░" * (10 - bar_filled)
        print(f"{i+1:>2}  {s['name']:<20s}  v{s['version']:>3d}  {s['detection_rate']:>8.2f}  {s['fp_rate']:>7.2f}  {s['canary_count']:>3d}/{s['total_canaries']:<3d}  {bar}")

    print(f"\nFleet detection: {fleet_det:.2f} | Fleet FP: {fleet_fp:.2f}")
    if cold_start:
        print(f"Canaries: {len(canaries)} (cold start: need {20 - len(canaries)} more for evolution)")
    else:
        print(f"Canaries: {len(canaries)} (evolution unlocked)")


# ── CLI ───────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Critic 进化循环控制器")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("select", help="选择下一个 critic + 变异算子")

    eval_parser = sub.add_parser("evaluate", help="处理评估结果")
    eval_parser.add_argument("result_json", help="评估结果 JSON（文件路径或字符串）")

    sub.add_parser("stop-check", help="检查停止条件")
    sub.add_parser("summary", help="进化摘要")

    lb_parser = sub.add_parser("leaderboard", help="Critic 排行榜")
    lb_parser.add_argument("--json", action="store_true", help="JSON 输出")

    args = parser.parse_args()

    if args.command == "select":
        select_next()
    elif args.command == "leaderboard":
        leaderboard(json_mode=getattr(args, 'json', False))
    elif args.command == "evaluate":
        # 支持文件路径或直接 JSON
        if os.path.isfile(args.result_json):
            result_json = Path(args.result_json).read_text()
        else:
            result_json = args.result_json
        process_evaluation(result_json)
    elif args.command == "stop-check":
        stop_check()
    elif args.command == "summary":
        summary()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
