#!/usr/bin/env python3
"""
prepare.py — tcell 固定基础设施
不可被 critic 修改。等价于 autoresearch 的 prepare.py。

命令：
  hook-check   轻量 hook 检查（实时触发）
  evaluate     在 canaries + clean_samples 上评估 critic
  validate     验证数据文件完整性
  recover      从 git history 恢复损坏的数据文件
  status       输出当前状态摘要
  log          追加日志条目到 sidebar.log.md
"""

from __future__ import annotations

import json
import sys
import os
import re
import argparse
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter
from typing import Optional

# ── 常量 ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent
CANARIES_FILE = PROJECT_ROOT / "canaries.jsonl"
CLEAN_SAMPLES_FILE = PROJECT_ROOT / "clean_samples.jsonl"
RESULTS_FILE = PROJECT_ROOT / "results.tsv"
LOG_FILE = PROJECT_ROOT / "sidebar.log.md"
STATE_FILE = PROJECT_ROOT / ".claude" / "sidebar.local.json"
PROGRAM_FILE = PROJECT_ROOT / "program.md"
CRITICS_DIR = PROJECT_ROOT / "critics"
REPORTS_DIR = PROJECT_ROOT / "reports"

# 质量声明关键词（中英文）
CLAIM_KEYWORDS = [
    r"\b100%\b", r"全部通过", r"满分", r"没有问题",
    r"\bPASS\b", r"\bDONE\b", r"\bverified\b",
    r"高质量", r"完成", r"通过",
]
CLAIM_PATTERN = re.compile("|".join(CLAIM_KEYWORDS), re.IGNORECASE)

# ── 数据加载 ────────────────────────────────────────
def load_jsonl(path: Path) -> list[dict]:
    """加载 JSONL 文件，跳过空行和损坏行。"""
    if not path.exists():
        return []
    entries = []
    for line_num, line in enumerate(path.read_text().splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            print(f"[warn] {path.name}:{line_num} JSON parse failed, skipped", file=sys.stderr)
    return entries


def load_state() -> dict:
    """加载运行时状态，不存在则初始化。"""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            pass
    return {
        "hook_call_count": 0,
        "hook_alert_count_window": [],
        "last_hook_trigger": None,
        "last_cron_run": None,
        "pending_alerts": [],
        "cold_start": True,
        "canary_count": 0,
    }


def save_state(state: dict):
    """持久化运行时状态。"""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


# ── 核心评估函数（不可修改）──────────────────────────
#
# 指标体系说明：
#   - detection_rate: 操作性指标，用于进化循环的 keep/discard 决策。
#     可实时计算，不需要外部 oracle。
#   - regret: 回顾性指标，衡量 sidebar 自己也漏掉的问题。
#     需要外部 oracle（人类确认或后续 critic 发现遗漏）才能计算。
#     不用于进化决策，仅用于周期性健康评估。
#
def evaluate_regret(canaries: list[dict], critic_results: list[dict]) -> float:
    """
    回顾性指标：在已知 canaries 上的遗漏率。
    regret = Σ(severity × missed) / total_canaries
    missed = critic 未能在已知盲区上检出问题

    注意：这不是进化循环的决策指标（那是 detection_rate）。
    这是一个回顾性健康指标，用于评估 critic 群体的整体能力。
    真正的 regret（sidebar 自己也漏掉的未知问题）需要外部 oracle，不可自动计算。
    """
    total = len(canaries)
    if total == 0:
        return 0.0

    missed_score = 0
    for canary in canaries:
        caught = any(
            r.get("canary_id") == canary["id"] and r.get("detected") is True
            for r in critic_results
        )
        if not caught:
            missed_score += canary.get("severity", 1)

    return missed_score / total


def evaluate_fp_rate(clean_samples: list[dict], critic_results: list[dict]) -> float:
    """
    计算假阳性率：critic 在干净样本上误报的比例。
    """
    if not clean_samples:
        return 0.0
    false_positives = sum(
        1 for s in clean_samples
        if any(
            r.get("sample_id") == s["id"] and r.get("detected") is True
            for r in critic_results
        )
    )
    return false_positives / len(clean_samples)


# ── Hook 检查（信号收集器，非审查器）──────────────────
#
# Hook 层的定位：信号收集器。
# 它做的事：用关键词模式匹配检测主 agent 的质量声明，记录到 pending。
# 它不做的事：独立审查、深度分析、做出判断。
# 深度审查由 Cron 层的独立 subagent 执行（真正的新鲜上下文审查）。
# Hook 的价值：低成本收集信号，为 Cron 深度审查提供审查目标。
#
def hook_check(event: str, payload_file: str | None):
    """
    信号收集器。异步调用，不阻塞主 agent。
    用关键词模式匹配检测质量声明，写入 pending 队列。
    不做深度审查——那是 Cron 层 subagent 的工作。
    """
    state = load_state()
    now = datetime.now(timezone.utc).isoformat()
    state["hook_call_count"] += 1
    state["last_hook_trigger"] = now

    # 读取 payload
    payload_text = ""
    if payload_file and os.path.exists(payload_file):
        try:
            payload_text = Path(payload_file).read_text()
        except Exception:
            pass

    # 检测质量声明
    claims = CLAIM_PATTERN.findall(payload_text)
    if not claims:
        # 静默通过
        log_entry(f"🔇 Hook — 静默通过 · {event} · 预算: {_budget_status(state)}")
        save_state(state)
        return

    # 发现质量声明，运行轻量分析
    alert = {
        "timestamp": now,
        "event": event,
        "claims_found": claims,
        "severity": 1,  # 默认中等，具体 severity 由 critic 决定
        "status": "pending",
    }

    # 噪声预算检查（滑动窗口 10 次调用内 ≤ 1 次警报）
    window = state.get("hook_alert_count_window", [])
    # 只保留最近 10 次调用内的警报
    call_count = state["hook_call_count"]
    window = [w for w in window if call_count - w <= 10]

    if len(window) >= 1:
        # 预算已满，写入 pending 不打扰
        state["pending_alerts"].append(alert)
        log_entry(f"🔇 Hook — 声明检测但预算已满，写入 pending · claims: {claims}")
    else:
        # 在预算内，标记为待上报
        window.append(call_count)
        state["hook_alert_count_window"] = window
        state["pending_alerts"].append(alert)
        log_entry(f"🔔 Hook Alert · {event}\n"
                  f"  claims: {claims}\n"
                  f"  status: pending confirmation\n"
                  f"  预算: {_budget_status(state)}")

    save_state(state)


def _budget_status(state: dict) -> str:
    """返回当前噪声预算状态。"""
    window = state.get("hook_alert_count_window", [])
    call_count = state["hook_call_count"]
    active = [w for w in window if call_count - w <= 10]
    return f"{len(active)}/1 (last 10 calls)"


# ── 日志 ──────────────────────────────────────────────
def log_entry(message: str):
    """追加一条日志到 sidebar.log.md。"""
    now = datetime.now().strftime("%H:%M")
    date = datetime.now().strftime("%Y-%m-%d")
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    # 检查是否需要新的日期标题
    existing = LOG_FILE.read_text() if LOG_FILE.exists() else ""
    date_header = f"## {date}"

    if date_header not in existing:
        entry = f"\n{date_header}\n\n### {now} · {message}\n"
    else:
        entry = f"\n### {now} · {message}\n"

    with open(LOG_FILE, "a") as f:
        f.write(entry)

    # 归档检查：超过 500 行时归档
    if LOG_FILE.exists():
        lines = LOG_FILE.read_text().splitlines()
        if len(lines) > 500:
            archive_log(date)


def archive_log(date: str):
    """归档日志到 reports/ 目录。"""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = REPORTS_DIR / f"log-{date}.md"
    content = LOG_FILE.read_text()
    archive_path.write_text(content)
    # 保留最后 50 行作为新日志的开始
    lines = content.splitlines()
    LOG_FILE.write_text("# tcell Log\n\n---\n\n" + "\n".join(lines[-50:]))


# ── 验证 ──────────────────────────────────────────────
def validate():
    """验证数据文件完整性。"""
    issues = []

    # canaries.jsonl
    if CANARIES_FILE.exists():
        canaries = load_jsonl(CANARIES_FILE)
        for c in canaries:
            if "id" not in c or "severity" not in c:
                issues.append(f"canaries: entry missing id or severity: {c}")
    else:
        issues.append("canaries.jsonl does not exist")

    # clean_samples.jsonl
    if CLEAN_SAMPLES_FILE.exists():
        samples = load_jsonl(CLEAN_SAMPLES_FILE)
        for s in samples:
            if "id" not in s:
                issues.append(f"clean_samples: entry missing id: {s}")
    else:
        issues.append("clean_samples.jsonl does not exist")

    # results.tsv
    if RESULTS_FILE.exists():
        lines = RESULTS_FILE.read_text().splitlines()
        if not lines or "iteration" not in lines[0]:
            issues.append("results.tsv: missing or invalid header")
    else:
        issues.append("results.tsv does not exist")

    # critics/
    if CRITICS_DIR.exists():
        critics = list(CRITICS_DIR.glob("*.md"))
        if not critics:
            issues.append("critics/: no critic files found")
    else:
        issues.append("critics/ directory does not exist")

    if issues:
        print("VALIDATION FAILED:")
        for i in issues:
            print(f"  - {i}")
        return False
    else:
        print("VALIDATION PASSED: all data files intact")
        return True


# ── Self-Test ─────────────────────────────────────────
COLD_START_THRESHOLD = 20

def _parse_frontmatter(path: Path) -> dict:
    """解析 critic .md 文件的 YAML frontmatter（简化版，prepare.py 内部使用）。"""
    text = path.read_text()
    if not text.startswith("---"):
        return {"name": path.stem}
    try:
        end = text.index("---", 3)
    except ValueError:
        return {"name": path.stem}
    meta = {}
    for line in text[3:end].strip().splitlines():
        if ":" in line:
            key, val = line.split(":", 1)
            key, val = key.strip(), val.strip()
            try:
                val = int(val) if "." not in val else float(val)
            except (ValueError, TypeError):
                pass
            meta[key] = val
    if "name" not in meta:
        meta["name"] = path.stem
    return meta


def self_test(json_mode: bool = False):
    """
    纯本地、确定性的系统完整性检查。不需要 LLM 调用。
    6 项检查：数据完整性、critic 文件、覆盖矩阵、冷启动状态、进化健康、hook 配置。
    """
    results = []

    # 1. 数据完整性
    canaries = load_jsonl(CANARIES_FILE)
    clean = load_jsonl(CLEAN_SAMPLES_FILE)
    data_ok = len(canaries) > 0 and len(clean) > 0
    missing_fields = []
    for c in canaries:
        if "id" not in c or "severity" not in c or "blindspot_type" not in c:
            missing_fields.append(c.get("id", "unknown"))
    for s in clean:
        if "id" not in s:
            missing_fields.append(s.get("id", "unknown"))

    if data_ok and not missing_fields:
        results.append(("PASS", f"Data integrity: {len(canaries)} canaries, {len(clean)} clean_samples"))
    elif missing_fields:
        results.append(("FAIL", f"Data integrity: schema errors in {missing_fields}"))
    else:
        results.append(("FAIL", f"Data integrity: canaries={len(canaries)}, clean={len(clean)}"))

    # 2. Critic 文件完整性
    critics = list(CRITICS_DIR.glob("*.md")) if CRITICS_DIR.exists() else []
    critic_meta = {}
    critic_errors = []
    for c in critics:
        meta = _parse_frontmatter(c)
        critic_meta[c.stem] = meta
        required = ["name", "detection_rate", "fp_rate"]
        for req in required:
            if req not in meta:
                critic_errors.append(f"{c.stem}: missing {req}")

    if critics and not critic_errors:
        names = [f"{m.get('name', '?')} v{m.get('version', '?')}" for m in critic_meta.values()]
        results.append(("PASS", f"Critics: {len(critics)}/{len(critics)} valid ({', '.join(names)})"))
    elif not critics:
        results.append(("FAIL", "Critics: no critic files found"))
    else:
        results.append(("FAIL", f"Critics: {'; '.join(critic_errors)}"))

    # 3. 覆盖矩阵
    blindspot_types = set(c.get("blindspot_type", "") for c in canaries if c.get("blindspot_type"))
    critic_names = set(c.stem for c in critics)
    uncovered = blindspot_types - critic_names
    unused = critic_names - blindspot_types

    if not uncovered:
        results.append(("PASS", f"Coverage matrix: {len(blindspot_types)}/{len(blindspot_types)} blindspot types have critics"))
    else:
        results.append(("WARN", f"Coverage matrix: uncovered blindspot types: {uncovered}"))

    if unused:
        results.append(("INFO", f"Critics without canaries: {unused} (no test data yet)"))

    # 4. 冷启动状态
    if len(canaries) >= COLD_START_THRESHOLD:
        results.append(("PASS", f"Evolution: {len(canaries)}/{COLD_START_THRESHOLD} canaries (evolution unlocked)"))
    else:
        need = COLD_START_THRESHOLD - len(canaries)
        results.append(("WARN", f"Cold start: {len(canaries)}/{COLD_START_THRESHOLD} canaries (need {need} more for evolution)"))

    # 5. 进化健康
    if RESULTS_FILE.exists():
        lines = RESULTS_FILE.read_text().splitlines()[1:]
        total = len(lines)
        keeps = sum(1 for l in lines if "\tkeep\t" in l)
        discards = total - keeps
        if total > 0:
            results.append(("PASS", f"Evolution: {total} iterations ({keeps} keep / {discards} discard)"))
        else:
            results.append(("PASS", "Evolution: 0 iterations (awaiting canaries)"))
    else:
        results.append(("WARN", "Evolution: results.tsv not found"))

    # 6. Hook 配置
    hook_config = PROJECT_ROOT / ".claude" / "settings.json"
    if hook_config.exists():
        try:
            config = json.loads(hook_config.read_text())
            hooks = config.get("hooks", {})
            if hooks:
                results.append(("PASS", f"Hook config: {len(hooks)} hook types configured"))
            else:
                results.append(("WARN", "Hook config: settings.json exists but no hooks defined"))
        except json.JSONDecodeError:
            results.append(("FAIL", "Hook config: settings.json is invalid JSON"))
    else:
        results.append(("WARN", "Hook config: .claude/settings.json not found"))

    # 输出
    passes = sum(1 for s, _ in results if s == "PASS")
    warns = sum(1 for s, _ in results if s == "WARN")
    fails = sum(1 for s, _ in results if s == "FAIL")
    infos = sum(1 for s, _ in results if s == "INFO")
    total_checks = passes + warns + fails

    if json_mode:
        print(json.dumps({
            "results": [{"status": s, "message": m} for s, m in results],
            "summary": {"pass": passes, "warn": warns, "fail": fails, "info": infos},
            "healthy": fails == 0,
            "cold_start": len(canaries) < COLD_START_THRESHOLD,
        }, ensure_ascii=False, indent=2))
    else:
        icons = {"PASS": "[PASS]", "WARN": "[WARN]", "FAIL": "[FAIL]", "INFO": "[INFO]"}
        print("═══ tcell Self-Test ═══\n")
        for s, m in results:
            print(f"  {icons[s]} {m}")
        print(f"\nResult: {passes}/{total_checks} PASS, {warns}/{total_checks} WARN, {fails}/{total_checks} FAIL")
        if fails == 0 and len(canaries) >= COLD_START_THRESHOLD:
            print("Status: HEALTHY (evolution mode)")
        elif fails == 0:
            print("Status: HEALTHY (cold start mode)")
        else:
            print("Status: UNHEALTHY")

    log_entry(f"🧪 Self-Test · {passes}/{total_checks} PASS, {warns} WARN, {fails} FAIL · "
              f"{'cold_start' if len(canaries) < COLD_START_THRESHOLD else 'normal'}({len(canaries)}/{COLD_START_THRESHOLD})")

    return fails == 0


# ── Session Score ─────────────────────────────────────
def session_score(json_mode: bool = False):
    """
    0-10 认知健康分。评估的是免疫系统本身的健康，不是主 agent 的健康。
    6 维度：fleet_detection, canary_coverage, fp_discipline, evolution_health,
    critic_diversity, data_freshness。
    """
    canaries = load_jsonl(CANARIES_FILE)
    clean = load_jsonl(CLEAN_SAMPLES_FILE)
    critics = list(CRITICS_DIR.glob("*.md")) if CRITICS_DIR.exists() else []

    # 加载 critic 元数据
    critic_stats = []
    for c in critics:
        meta = _parse_frontmatter(c)
        critic_stats.append({
            "name": meta.get("name", c.stem),
            "detection_rate": float(meta.get("detection_rate", 0.0)),
            "fp_rate": float(meta.get("fp_rate", 0.0)),
            "version": int(meta.get("version", 0)),
        })

    # 进化统计
    keeps, discards = 0, 0
    if RESULTS_FILE.exists():
        for line in RESULTS_FILE.read_text().splitlines()[1:]:
            if "\tkeep\t" in line:
                keeps += 1
            elif "\tdiscard\t" in line:
                discards += 1
    total_iters = keeps + discards

    # 维度计算（每个 0.0-1.0）
    dimensions = {}

    # 1. Fleet detection rate (30%) — TUNABLE
    fleet_det = (sum(s["detection_rate"] for s in critic_stats) / len(critic_stats)) if critic_stats else 0
    dimensions["detection"] = {"score": min(fleet_det / 0.80, 1.0), "weight": 0.30,
                               "value": f"{fleet_det:.2f}", "label": "fleet avg"}

    # 2. Canary coverage (20%) — TUNABLE
    canary_score = min(len(canaries) / COLD_START_THRESHOLD, 1.0)
    dimensions["canaries"] = {"score": canary_score, "weight": 0.20,
                              "value": f"{len(canaries)}/{COLD_START_THRESHOLD}",
                              "label": "cold start" if len(canaries) < COLD_START_THRESHOLD else "normal"}

    # 3. FP discipline (15%) — TUNABLE
    fleet_fp = (sum(s["fp_rate"] for s in critic_stats) / len(critic_stats)) if critic_stats else 0
    fp_score = max(1.0 - (fleet_fp / 0.10), 0.0)  # 0.10 以上 = 0 分
    dimensions["fp_control"] = {"score": fp_score, "weight": 0.15,
                                "value": f"{fleet_fp:.2f}",
                                "label": "perfect" if fleet_fp == 0 else f"{fleet_fp:.0%}"}

    # 4. Evolution health (15%) — TUNABLE
    if total_iters == 0:
        evo_score = 0.5  # 没跑过进化，中性分
    else:
        keep_rate = keeps / total_iters
        # 健康的 keep_rate 在 30-70%（太高=标准太松，太低=变异无效）
        if 0.3 <= keep_rate <= 0.7:
            evo_score = 1.0
        elif keep_rate > 0.7:
            evo_score = max(0, 1.0 - (keep_rate - 0.7) / 0.3)
        else:
            evo_score = max(0, keep_rate / 0.3)
    dimensions["evolution"] = {"score": evo_score, "weight": 0.15,
                               "value": f"{total_iters} iter, {keeps}/{total_iters} keep" if total_iters else "no data",
                               "label": ""}

    # 5. Critic diversity (10%) — TUNABLE
    blindspot_types = set(c.get("blindspot_type", "") for c in canaries if c.get("blindspot_type"))
    diversity_target = 7  # TUNABLE
    diversity_score = min(len(blindspot_types) / diversity_target, 1.0)
    dimensions["diversity"] = {"score": diversity_score, "weight": 0.10,
                               "value": f"{len(blindspot_types)} types", "label": ""}

    # 6. Data freshness (10%) — TUNABLE
    freshness_score = 0.0
    if canaries:
        try:
            latest_ts = max(c.get("timestamp", "") for c in canaries)
            latest_dt = datetime.fromisoformat(latest_ts.replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - latest_dt).days
            if age_days <= 3:
                freshness_score = 1.0
            elif age_days <= 14:
                freshness_score = max(0, 1.0 - (age_days - 3) / 11)
            else:
                freshness_score = 0.0
            freshness_label = f"< {age_days + 1} day{'s' if age_days > 0 else ''}"
        except (ValueError, TypeError):
            freshness_label = "unknown"
    else:
        freshness_label = "no data"
    dimensions["freshness"] = {"score": freshness_score, "weight": 0.10,
                               "value": freshness_label, "label": ""}

    # 总分
    total_score = sum(d["score"] * d["weight"] for d in dimensions.values()) * 10

    # 健康等级
    if total_score >= 8:
        grade = "ROBUST"
    elif total_score >= 6:
        grade = "ADEQUATE"
    elif total_score >= 4:
        grade = "DEVELOPING"
    elif total_score >= 2:
        grade = "FRAGILE"
    else:
        grade = "CRITICAL"

    # 诊断建议
    weakest = min(dimensions.items(), key=lambda x: x[1]["score"])
    diagnosis = _diagnose(weakest[0], weakest[1], len(canaries))

    if json_mode:
        print(json.dumps({
            "score": round(total_score, 1),
            "grade": grade,
            "dimensions": {k: {"score": round(v["score"], 2), "weight": v["weight"],
                               "value": v["value"]} for k, v in dimensions.items()},
            "diagnosis": diagnosis,
            "cold_start": len(canaries) < COLD_START_THRESHOLD,
        }, ensure_ascii=False, indent=2))
    else:
        grade_icons = {"ROBUST": "", "ADEQUATE": "", "DEVELOPING": "", "FRAGILE": "", "CRITICAL": ""}
        print(f"═══ Session Cognitive Health Score ═══\n")
        print(f"Score: {total_score:.1f} / 10.0  {grade}\n")
        for key, dim in dimensions.items():
            bar_filled = int(dim["score"] * 10)
            bar = "█" * bar_filled + "░" * (10 - bar_filled)
            val_str = f"{dim['value']}"
            if dim["label"]:
                val_str += f"  ({dim['label']})"
            print(f"  {key:<12s} {bar}  {val_str}")
        print(f"\nDiagnosis: {diagnosis}")

    log_entry(f"📊 Session Score · {total_score:.1f}/10 · {grade} · "
              f"detection={fleet_det:.2f} canaries={len(canaries)}/{COLD_START_THRESHOLD}")

    return total_score


def _diagnose(weakest_key: str, weakest_dim: dict, canary_count: int) -> str:
    """根据最弱维度生成诊断建议。"""
    if weakest_key == "detection":
        return "Fleet detection rate 偏低。优先运行更多进化迭代提升 critics 的检出能力。"
    elif weakest_key == "canaries":
        need = COLD_START_THRESHOLD - canary_count
        return f"Canary 数量不足（还需 {need} 条）。运行 ./review.sh 审查更多数据来积累 canaries。"
    elif weakest_key == "fp_control":
        return "假阳性率偏高。检查 critics 的检测规则是否过于宽泛，考虑 focus_narrow 变异。"
    elif weakest_key == "evolution":
        return "进化健康度异常。keep_rate 过高可能意味着标准太松，过低可能意味着变异策略无效。"
    elif weakest_key == "diversity":
        return "Critic 多样性不足。添加覆盖新盲区类型的 critics 或贡献新类型的 canaries。"
    elif weakest_key == "freshness":
        return "数据陈旧。运行新一轮审查来刷新 canary 数据。"
    return "系统运行正常。"


# ── 状态 ──────────────────────────────────────────────
def status():
    """输出当前状态摘要。"""
    state = load_state()
    canaries = load_jsonl(CANARIES_FILE)
    clean = load_jsonl(CLEAN_SAMPLES_FILE)
    critics = list(CRITICS_DIR.glob("*.md")) if CRITICS_DIR.exists() else []

    cold_start = len(canaries) < 20

    print(f"🐕 tcell Status")
    print(f"  canaries: {len(canaries)} {'(cold start)' if cold_start else '(normal mode)'}")
    print(f"  clean_samples: {len(clean)}")
    print(f"  critics: {len(critics)}")
    print(f"  hook_calls: {state.get('hook_call_count', 0)}")
    print(f"  pending_alerts: {len(state.get('pending_alerts', []))}")
    print(f"  last_hook: {state.get('last_hook_trigger', 'never')}")
    print(f"  last_cron: {state.get('last_cron_run', 'never')}")

    # results.tsv 统计
    if RESULTS_FILE.exists():
        lines = RESULTS_FILE.read_text().splitlines()[1:]  # skip header
        keeps = sum(1 for l in lines if "\tkeep\t" in l)
        discards = sum(1 for l in lines if "\tdiscard\t" in l)
        print(f"  evolution: {len(lines)} iterations ({keeps} keep / {discards} discard)")


# ── CLI ───────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="tcell 固定基础设施")
    sub = parser.add_subparsers(dest="command")

    # hook-check
    hook_parser = sub.add_parser("hook-check", help="轻量 hook 检查")
    hook_parser.add_argument("--event", required=True, help="触发事件类型")
    hook_parser.add_argument("--payload", default=None, help="Payload 文件路径")

    # evaluate
    eval_parser = sub.add_parser("evaluate", help="评估 critic")
    eval_parser.add_argument("--critic", required=True, help="critic 名称")

    # self-test
    st_parser = sub.add_parser("self-test", help="系统完整性自检")
    st_parser.add_argument("--json", action="store_true", help="JSON 输出")

    # session-score
    ss_parser = sub.add_parser("session-score", help="认知健康分 (0-10)")
    ss_parser.add_argument("--json", action="store_true", help="JSON 输出")

    # validate
    sub.add_parser("validate", help="验证数据文件完整性")

    # status
    sub.add_parser("status", help="输出当前状态摘要")

    # log
    log_parser = sub.add_parser("log", help="追加日志条目")
    log_parser.add_argument("message", help="日志消息")

    args = parser.parse_args()

    if args.command == "hook-check":
        hook_check(args.event, args.payload)
    elif args.command == "evaluate":
        # 评估逻辑会在 critic 进化循环中使用
        print(f"Evaluating critic: {args.critic}")
        canaries = load_jsonl(CANARIES_FILE)
        clean = load_jsonl(CLEAN_SAMPLES_FILE)
        print(f"  canaries: {len(canaries)}")
        print(f"  clean_samples: {len(clean)}")
        print(f"  (full evaluation requires critic subagent execution)")
    elif args.command == "self-test":
        success = self_test(json_mode=getattr(args, 'json', False))
        sys.exit(0 if success else 1)
    elif args.command == "session-score":
        session_score(json_mode=getattr(args, 'json', False))
    elif args.command == "validate":
        success = validate()
        sys.exit(0 if success else 1)
    elif args.command == "status":
        status()
    elif args.command == "log":
        log_entry(args.message)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
