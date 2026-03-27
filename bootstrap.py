#!/usr/bin/env python3
"""
tcell 自适应冷启动器 — 让 tcell 部署到任意项目时一条命令完成冷启动。

子命令:
  detect          检测目标项目类型/语言/框架
  seed-critics    根据 project_profile 从模板生成 seed critics
  seed-canaries   从 git 历史挖掘初始 canaries
  full            一键冷启动（detect → seed-critics → seed-canaries）

用法:
  python3 bootstrap.py detect [--target /path/to/project]
  python3 bootstrap.py seed-critics [--target /path/to/project]
  python3 bootstrap.py seed-canaries [--target /path/to/project]
  python3 bootstrap.py full [--target /path/to/project]
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── 路径常量 ────────────────────────────────────────────
SIDEBAR_ROOT = Path(__file__).resolve().parent
STATE_FILE = SIDEBAR_ROOT / ".claude" / "sidebar.local.json"
CANARIES_FILE = SIDEBAR_ROOT / "canaries.jsonl"
CRITICS_DIR = SIDEBAR_ROOT / "critics"
TEMPLATES_DIR = SIDEBAR_ROOT / "critics_templates"

# ── 状态管理（复用 prepare.py 的逻辑）──────────────────
def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            pass
    return {}


def save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ══════════════════════════════════════════════════════════
# Phase 1: detect — 项目检测
# ══════════════════════════════════════════════════════════

# 语言特征文件
LANG_MARKERS = {
    "python":     {"globs": ["*.py"], "configs": ["pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "Pipfile"]},
    "typescript": {"globs": ["*.ts", "*.tsx"], "configs": ["tsconfig.json"]},
    "javascript": {"globs": ["*.js", "*.jsx"], "configs": ["package.json"]},
    "go":         {"globs": ["*.go"], "configs": ["go.mod"]},
    "rust":       {"globs": ["*.rs"], "configs": ["Cargo.toml"]},
    "java":       {"globs": ["*.java"], "configs": ["pom.xml", "build.gradle", "build.gradle.kts"]},
    "swift":      {"globs": ["*.swift"], "configs": ["Package.swift", "*.xcodeproj"]},
    "c_cpp":      {"globs": ["*.c", "*.cpp", "*.h", "*.hpp"], "configs": ["CMakeLists.txt", "Makefile"]},
}

# 框架检测规则: (框架名, 检测文件, 检测内容正则)
FRAMEWORK_RULES = [
    # JavaScript/TypeScript 框架
    ("react",      "package.json", r'"react"'),
    ("next.js",    "package.json", r'"next"'),
    ("vue",        "package.json", r'"vue"'),
    ("angular",    "package.json", r'"@angular/core"'),
    ("express",    "package.json", r'"express"'),
    ("nestjs",     "package.json", r'"@nestjs/core"'),
    ("svelte",     "package.json", r'"svelte"'),
    # Python 框架
    ("django",     "requirements.txt", r"(?i)django"),
    ("flask",      "requirements.txt", r"(?i)flask"),
    ("fastapi",    "requirements.txt", r"(?i)fastapi"),
    ("pytorch",    "requirements.txt", r"(?i)torch"),
    ("tensorflow", "requirements.txt", r"(?i)tensorflow"),
    ("django",     "pyproject.toml", r"(?i)django"),
    ("flask",      "pyproject.toml", r"(?i)flask"),
    ("fastapi",    "pyproject.toml", r"(?i)fastapi"),
    ("pytorch",    "pyproject.toml", r"(?i)torch"),
    ("tensorflow", "pyproject.toml", r"(?i)tensorflow"),
    # Go 框架
    ("gin",        "go.mod", r"github\.com/gin-gonic/gin"),
    ("echo",       "go.mod", r"github\.com/labstack/echo"),
    ("fiber",      "go.mod", r"github\.com/gofiber/fiber"),
    # Java 框架
    ("spring-boot", "pom.xml", r"spring-boot"),
    ("spring-boot", "build.gradle", r"spring-boot"),
    # Rust 框架
    ("actix-web",  "Cargo.toml", r"actix-web"),
    ("axum",       "Cargo.toml", r'axum'),
    ("tokio",      "Cargo.toml", r'tokio'),
]

# 测试框架检测
TEST_FRAMEWORK_RULES = [
    ("jest",        "package.json", r'"jest"'),
    ("vitest",      "package.json", r'"vitest"'),
    ("playwright",  "package.json", r'"@playwright/test"'),
    ("cypress",     "package.json", r'"cypress"'),
    ("mocha",       "package.json", r'"mocha"'),
    ("pytest",      "pyproject.toml", r"(?i)pytest"),
    ("pytest",      "requirements.txt", r"(?i)pytest"),
    ("unittest",    None, None),  # 内置，通过 import 检测
    ("go-test",     "go.mod", None),  # Go 内置测试
    ("cargo-test",  "Cargo.toml", None),  # Rust 内置测试
    ("junit",       "pom.xml", r"junit"),
    ("junit",       "build.gradle", r"junit"),
    ("xctest",      "Package.swift", None),  # Swift 内置测试
]

# CI 系统检测
CI_MARKERS = {
    "github-actions": ".github/workflows",
    "gitlab-ci":      ".gitlab-ci.yml",
    "jenkins":        "Jenkinsfile",
    "circleci":       ".circleci/config.yml",
    "travis":         ".travis.yml",
}

# 项目类型分类规则
PROJECT_TYPE_RULES = [
    # (类型, 条件函数)
    ("sft-training",   lambda p: "pytorch" in p.get("frameworks", []) or "tensorflow" in p.get("frameworks", [])),
    ("web-frontend",   lambda p: any(f in p.get("frameworks", []) for f in ["react", "next.js", "vue", "angular", "svelte"])),
    ("web-backend",    lambda p: any(f in p.get("frameworks", []) for f in ["express", "nestjs", "django", "flask", "fastapi", "gin", "echo", "fiber", "spring-boot", "actix-web", "axum"])),
    ("mobile-app",     lambda p: "swift" in p.get("languages", []) or "kotlin" in p.get("languages", [])),
    ("cli-tool",       lambda p: len(p.get("frameworks", [])) == 0 and len(p.get("languages", [])) <= 2),
    ("data-pipeline",  lambda p: "python" in p.get("languages", []) and any(f in p.get("frameworks", []) for f in ["pytorch", "tensorflow"])),
]


def _file_exists(root: Path, name: str) -> bool:
    """检查文件或 glob 模式是否存在。"""
    if "*" in name:
        return bool(list(root.glob(name)))
    return (root / name).exists()


def _file_contains(root: Path, name: str, pattern: str) -> bool:
    """检查文件内容是否匹配正则。"""
    target = root / name
    if not target.exists():
        return False
    try:
        content = target.read_text(errors="replace")
        return bool(re.search(pattern, content))
    except Exception:
        return False


def _count_files(root: Path, glob_pattern: str, max_depth: int = 3) -> int:
    """快速统计匹配文件数（限制深度避免大仓库卡顿）。"""
    count = 0
    for p in root.rglob(glob_pattern):
        # 跳过 node_modules, .git, vendor 等
        parts = p.relative_to(root).parts
        if any(skip in parts for skip in (".git", "node_modules", "vendor", ".venv", "__pycache__", "dist", "build")):
            continue
        if len(parts) > max_depth:
            continue
        count += 1
        if count >= 100:  # 够了，不需要精确计数
            break
    return count


def detect_project(target_root: Path) -> dict:
    """检测目标项目的类型/语言/框架/测试框架/CI。"""
    profile = {
        "detected_at": now_iso(),
        "target_root": str(target_root),
        "project_type": "generic",
        "languages": [],
        "frameworks": [],
        "test_frameworks": [],
        "ci_system": None,
        "data_fields": [],
        "bootstrap_threshold": 8,
        "auto_bootstrapped": True,
    }

    # 1. 语言检测
    lang_counts = {}
    for lang, markers in LANG_MARKERS.items():
        # 检查配置文件
        has_config = any(_file_exists(target_root, cfg) for cfg in markers["configs"])
        # 检查源文件
        file_count = sum(_count_files(target_root, g) for g in markers["globs"])
        if has_config or file_count > 3:
            lang_counts[lang] = file_count
    # 按文件数排序
    profile["languages"] = sorted(lang_counts.keys(), key=lambda l: lang_counts[l], reverse=True)

    # 2. 框架检测（含 monorepo 子目录扫描）
    detected_frameworks = set()
    # 搜索路径：根目录 + 一级子目录 + apps/*/  + packages/*/
    search_dirs = [target_root]
    for sub in ["apps", "packages", "services", "modules"]:
        subdir = target_root / sub
        if subdir.is_dir():
            search_dirs.extend(p for p in subdir.iterdir() if p.is_dir())

    for fw_name, config_file, pattern in FRAMEWORK_RULES:
        if not config_file:
            continue
        for search_dir in search_dirs:
            if _file_exists(search_dir, config_file):
                if pattern is None or _file_contains(search_dir, config_file, pattern):
                    detected_frameworks.add(fw_name)
                    break  # 找到即可
    profile["frameworks"] = sorted(detected_frameworks)

    # 3. 测试框架检测（含 monorepo 子目录扫描）
    detected_tests = set()
    for tf_name, config_file, pattern in TEST_FRAMEWORK_RULES:
        if config_file is None:
            continue  # 内置测试框架，后续通过语言推断
        for search_dir in search_dirs:
            if _file_exists(search_dir, config_file):
                if pattern is None:
                    detected_tests.add(tf_name)
                    break
                elif _file_contains(search_dir, config_file, pattern):
                    detected_tests.add(tf_name)
                    break
    # 推断内置测试框架
    if "go" in profile["languages"]:
        detected_tests.add("go-test")
    if "rust" in profile["languages"]:
        detected_tests.add("cargo-test")
    profile["test_frameworks"] = sorted(detected_tests)

    # 4. CI 检测
    for ci_name, ci_marker in CI_MARKERS.items():
        if _file_exists(target_root, ci_marker):
            profile["ci_system"] = ci_name
            break

    # 5. 项目类型分类
    for ptype, condition in PROJECT_TYPE_RULES:
        if condition(profile):
            profile["project_type"] = ptype
            break

    # 6. 领域数据字段映射
    profile["data_fields"] = _infer_data_fields(profile)

    return profile


def _infer_data_fields(profile: dict) -> list[str]:
    """根据项目类型推断 review.sh 应该搜索的数据字段。"""
    ptype = profile["project_type"]
    field_map = {
        "web-frontend":   ["test_results", "coverage", "bundle_size", "accessibility", "render_output"],
        "web-backend":    ["test_results", "coverage", "response_status", "error_rate", "latency"],
        "sft-training":   ["confidence", "action", "bias", "quality_score", "synthesis"],
        "ml-pipeline":    ["loss", "accuracy", "predictions", "confidence", "metrics"],
        "data-pipeline":  ["row_count", "schema", "null_rate", "distribution", "outliers"],
        "mobile-app":     ["test_results", "coverage", "crash_rate", "memory_usage"],
        "cli-tool":       ["exit_code", "output", "error_message", "test_results"],
        "api-service":    ["status_code", "response_body", "latency", "error_rate"],
        "generic":        ["confidence", "action", "bias"],  # 回退到原始字段
    }
    return field_map.get(ptype, field_map["generic"])


# ══════════════════════════════════════════════════════════
# Phase 2: seed-critics — 模板实例化
# ══════════════════════════════════════════════════════════

# 领域规则映射
DOMAIN_RULES = {
    "web-frontend": {
        "overconfidence": (
            '- 如果声称"所有组件正常渲染"但仅有 snapshot tests、无交互测试或 a11y 测试，标记 severity 2\n'
            '- 如果声称"响应式完美"但未提供多分辨率测试证据，标记 severity 2'
        ),
        "homogenization": (
            '- 对组件 props 分布做多样性检查：如果所有组件传入相同 props 模式，标记\n'
            '- 对测试用例输入做覆盖分析：如果测试全部使用相同的 mock 数据模式，标记'
        ),
        "position_bias": (
            '- 检查列表渲染是否依赖数组索引作为 key（可能掩盖排序敏感 bug）\n'
            '- 检查表单验证是否只测试了第一个字段的边界条件'
        ),
        "coverage_gaps": (
            '- 必需覆盖：浏览器兼容性（Chrome/Firefox/Safari）、移动端/桌面端、深色/浅色模式\n'
            '- a11y 覆盖：键盘导航、屏幕阅读器、色彩对比度\n'
            '- 边界情况：空状态、加载状态、错误状态、超长文本'
        ),
        "premature_closure": (
            '- 检查 code review 反馈是否被完全接受或完全拒绝，缺少部分采纳\n'
            '- 检查 bug fix 是否直接用最简方案而未考虑根因'
        ),
        "whack_a_mole": (
            '- CSS 修复是否通过 !important 覆盖而非修正层叠关系\n'
            '- 状态 bug 是否通过添加 useEffect 而非修正数据流'
        ),
        "root_cause_blindness": (
            '- 组件重渲染问题是否只加了 React.memo 而未修正父组件的 props 传递\n'
            '- 样式问题是否只改了具体值而未修正设计系统 token'
        ),
        "overcorrection": (
            '- 修复 XSS 是否过度转义导致合法 HTML 内容无法显示\n'
            '- 修复性能是否移除了必要的功能（如去掉了动画但降低了 UX）'
        ),
    },
    "web-backend": {
        "overconfidence": (
            '- 如果声称"所有 API 正常"但无 error path 测试、无边界输入测试，标记 severity 2\n'
            '- 如果声称"安全"但未提供 injection/XSS/CSRF 测试证据，标记 severity 2'
        ),
        "homogenization": (
            '- 对 API 响应做多样性检查：如果所有 error response 使用相同 status code 和 message 模板，标记\n'
            '- 对测试数据做检查：如果所有测试用例使用相同 fixture，标记'
        ),
        "position_bias": (
            '- 检查中间件/拦截器是否按注册顺序产生不同行为\n'
            '- 检查数据库查询是否因 ORDER BY 缺失导致结果不确定'
        ),
        "coverage_gaps": (
            '- 必需覆盖：认证/授权路径、错误处理路径、并发场景\n'
            '- 边界情况：空输入、超大 payload、超时、重试逻辑\n'
            '- 安全覆盖：SQL injection、XSS、CSRF、rate limiting'
        ),
        "premature_closure": (
            '- 性能问题是否只加了缓存而未分析慢查询根因\n'
            '- 错误处理是否只 catch-all 而未区分可恢复/不可恢复错误'
        ),
        "whack_a_mole": (
            '- 数据库死锁是否通过 retry 而非修正事务顺序\n'
            '- 内存泄漏是否通过重启而非修正资源释放'
        ),
        "root_cause_blindness": (
            '- N+1 查询问题是否只加了 eager loading 而未修正数据访问模式\n'
            '- 认证 bug 是否只打了 patch 而未审计整个 auth 流程'
        ),
        "overcorrection": (
            '- 修复安全漏洞是否过度限制导致合法请求被拒绝\n'
            '- 修复性能是否去掉了必要的验证步骤'
        ),
    },
    "sft-training": {
        "overconfidence": (
            '- SFT 质量评分器对所有样本给出同分，评分器形同虚设\n'
            '- 苏格拉底蒸馏被称为"教科书级"但未提供量化标准'
        ),
        "homogenization": (
            '- confidence 字段分布异常集中（如 45.8% = 0.62），卡方检验 p ≈ 0\n'
            '- 所有 synthesis 长度/结构高度相似，模板化生成'
        ),
        "position_bias": (
            '- Challenge 位置与 bias 类型强绑定（如 C1→confirmation_bias 48%）\n'
            '- 模型学到"第一个 challenge 就用 X"的快捷方式'
        ),
        "coverage_gaps": (
            '- 必需偏差类型完全缺席（如 loss_aversion 在清算场景中缺席）\n'
            '- 事件类型分布极端不均'
        ),
        "premature_closure": (
            '- Synthesis 总是完全翻转或完全坚持，缺少部分修正中间态\n'
            '- 被质疑后 100% 改变立场（sycophancy 问题）'
        ),
        "whack_a_mole": (
            '- 修复 bias 类型缺失时创造了新的覆盖盲区\n'
            '- 修复 confidence 分布时破坏了其他指标的校准'
        ),
        "root_cause_blindness": (
            '- 用禁止规则解决质量问题而非修正 prompt 结构\n'
            '- 治标（删除低质量样本）不治本（改善生成逻辑）'
        ),
        "overcorrection": (
            '- 禁止某个 bias 类型导致该类型从训练集完全消失\n'
            '- 过度过滤导致有效样本被误删'
        ),
    },
    "generic": {
        "overconfidence": "",
        "homogenization": "",
        "position_bias": "",
        "coverage_gaps": "",
        "premature_closure": "",
        "whack_a_mole": "",
        "root_cause_blindness": "",
        "overcorrection": "",
    },
}

# 通用领域回退 — 缺少映射时使用
for ptype in ["ml-pipeline", "data-pipeline", "mobile-app", "cli-tool", "api-service"]:
    if ptype not in DOMAIN_RULES:
        DOMAIN_RULES[ptype] = DOMAIN_RULES["generic"]


def seed_critics(target_root: Path, profile: dict) -> list[str]:
    """从模板生成 seed critics，写入 critics/ 目录。"""
    if not TEMPLATES_DIR.exists():
        print(json.dumps({"error": f"Templates directory not found: {TEMPLATES_DIR}"}))
        return []

    ptype = profile.get("project_type", "generic")
    domain_rules = DOMAIN_RULES.get(ptype, DOMAIN_RULES["generic"])
    timestamp = now_iso()
    created = []

    for template_file in sorted(TEMPLATES_DIR.glob("*.template.md")):
        critic_name = template_file.stem.replace(".template", "")
        target_file = CRITICS_DIR / f"{critic_name}.md"

        # 不覆盖已有 critic（保护进化过的版本）
        if target_file.exists():
            continue

        template = template_file.read_text()

        # 填充占位符
        rules = domain_rules.get(critic_name, "")
        source_case = _generate_source_case(critic_name, ptype)

        content = template.replace("{{timestamp}}", timestamp)

        # 领域规则：有内容时渲染整个区块，无内容时删除区块
        if rules:
            content = content.replace("{{#domain_rules}}", "")
            content = content.replace("{{/domain_rules}}", "")
            content = content.replace("{{domain_rules}}", rules)
        else:
            # 删除整个条件区块
            content = re.sub(
                r"\{\{#domain_rules\}\}.*?\{\{/domain_rules\}\}",
                "",
                content,
                flags=re.DOTALL,
            )

        content = content.replace("{{source_case}}", source_case)

        CRITICS_DIR.mkdir(parents=True, exist_ok=True)
        target_file.write_text(content)
        created.append(critic_name)

    return created


def _generate_source_case(critic_name: str, project_type: str) -> str:
    """为指定 critic + 项目类型生成占位来源案例。"""
    cases = {
        "overconfidence": f"(auto-bootstrap for {project_type}): 尚无领域来源案例。进化循环将从 canaries 中学习并填充。",
        "homogenization": f"(auto-bootstrap for {project_type}): 尚无领域来源案例。等待进化循环发现具体统计模式。",
        "position_bias": f"(auto-bootstrap for {project_type}): 尚无领域来源案例。等待进化循环发现位置依赖模式。",
        "coverage_gaps": f"(auto-bootstrap for {project_type}): 尚无领域来源案例。等待进化循环发现覆盖盲区。",
        "premature_closure": f"(auto-bootstrap for {project_type}): 尚无领域来源案例。等待进化循环发现思维闭合模式。",
        "whack_a_mole": f"(auto-bootstrap for {project_type}): 尚无领域来源案例。git 考古可能已挖掘到相关 canary。",
        "root_cause_blindness": f"(auto-bootstrap for {project_type}): 尚无领域来源案例。git hotspot 分析可能已挖掘到相关 canary。",
        "overcorrection": f"(auto-bootstrap for {project_type}): 尚无领域来源案例。测试删除考古可能已挖掘到相关 canary。",
    }
    return cases.get(critic_name, f"(auto-bootstrap for {project_type}): 尚无来源案例。")


# ══════════════════════════════════════════════════════════
# Phase 3: seed-canaries — Git 历史挖掘
# ══════════════════════════════════════════════════════════

def _run_git(target_root: Path, args: list[str], timeout: int = 15) -> str:
    """在目标项目运行 git 命令，安静失败。"""
    try:
        result = subprocess.run(
            ["git", "-C", str(target_root)] + args,
            capture_output=True, text=True, timeout=timeout,
        )
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def seed_canaries(target_root: Path, profile: dict) -> list[dict]:
    """从 git 历史挖掘初始 canaries。"""
    canaries = []
    existing_ids = _load_existing_canary_ids()
    next_id = _next_canary_id(existing_ids)

    # 策略 1: Git 考古 — revert/undo 模式 → whack_a_mole
    canaries.extend(_mine_reverts(target_root, next_id))
    next_id += len(canaries)

    # 策略 2: Git hotspot — 同文件频繁修改 → root_cause_blindness
    hotspot_canaries = _mine_hotspots(target_root, next_id)
    canaries.extend(hotspot_canaries)
    next_id += len(hotspot_canaries)

    # 策略 3: 测试删除 → overcorrection
    test_canaries = _mine_deleted_tests(target_root, next_id)
    canaries.extend(test_canaries)
    next_id += len(test_canaries)

    # 策略 4: 声明-证据差距 → overconfidence
    claim_canaries = _mine_claim_gaps(target_root, next_id)
    canaries.extend(claim_canaries)
    next_id += len(claim_canaries)

    # 写入 canaries.jsonl（追加模式）
    if canaries:
        with open(CANARIES_FILE, "a") as f:
            for c in canaries:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")

    return canaries


def _load_existing_canary_ids() -> set:
    if not CANARIES_FILE.exists():
        return set()
    ids = set()
    for line in CANARIES_FILE.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                ids.add(json.loads(line).get("id", ""))
            except json.JSONDecodeError:
                pass
    return ids


def _next_canary_id(existing_ids: set) -> int:
    """从已有 ID 中提取最大序号。"""
    max_n = 0
    for cid in existing_ids:
        m = re.search(r"(\d+)$", cid)
        if m:
            max_n = max(max_n, int(m.group(1)))
    return max_n + 1


def _make_canary(n: int, blindspot_type: str, claim: str, finding: str, source: str) -> dict:
    return {
        "id": f"canary-auto-{n:03d}",
        "timestamp": now_iso(),
        "source": source,
        "main_agent_claim": claim,
        "actual_finding": finding,
        "severity": 1,
        "blindspot_type": blindspot_type,
        "discovered_by": "bootstrap-git-mining",
        "confirmed_by": "auto-bootstrap",
    }


def _mine_reverts(target_root: Path, start_id: int) -> list[dict]:
    """策略 1: 查找 revert/undo commit → whack_a_mole canary。"""
    canaries = []
    output = _run_git(target_root, [
        "log", "--all", "--oneline", "-20",
        "--grep=revert", "--grep=Revert", "--grep=undo", "--grep=re-fix",
        "--grep=again",
    ])
    if not output:
        return []

    n = start_id
    for line in output.splitlines()[:5]:  # 最多 5 条
        parts = line.split(None, 1)
        if len(parts) < 2:
            continue
        commit_hash, message = parts
        canaries.append(_make_canary(
            n, "whack_a_mole",
            claim=f"Original fix was complete (reverted in {commit_hash})",
            finding=f"Commit '{message}' indicates the previous fix shifted the problem rather than solving it",
            source=f"git-archaeology:{commit_hash}",
        ))
        n += 1

    return canaries


def _mine_hotspots(target_root: Path, start_id: int) -> list[dict]:
    """策略 2: 查找频繁修改的文件 → root_cause_blindness canary。"""
    canaries = []
    output = _run_git(target_root, [
        "log", "--all", "--name-only", "--pretty=format:", "-30",
    ])
    if not output:
        return []

    from collections import Counter
    files = [f.strip() for f in output.splitlines() if f.strip()]
    counts = Counter(files)

    n = start_id
    for filepath, count in counts.most_common(3):
        if count >= 5:
            canaries.append(_make_canary(
                n, "root_cause_blindness",
                claim=f"Each fix to {filepath} resolved the issue",
                finding=f"{filepath} was modified {count} times in recent 30 commits, suggesting surface fixes without addressing root cause",
                source=f"git-hotspot:{filepath}",
            ))
            n += 1

    return canaries


def _mine_deleted_tests(target_root: Path, start_id: int) -> list[dict]:
    """策略 3: 查找被删除的测试文件 → overcorrection canary。"""
    canaries = []
    output = _run_git(target_root, [
        "log", "--all", "--oneline", "--diff-filter=D", "-20", "--",
        "*test*", "*spec*", "*_test.*",
    ])
    if not output:
        return []

    n = start_id
    for line in output.splitlines()[:3]:  # 最多 3 条
        parts = line.split(None, 1)
        if len(parts) < 2:
            continue
        commit_hash, message = parts
        canaries.append(_make_canary(
            n, "overcorrection",
            claim=f"Bug fix in {commit_hash} was correct and complete",
            finding=f"Test files were deleted in '{message}', suggesting the fix over-corrected by removing test coverage",
            source=f"git-test-deletion:{commit_hash}",
        ))
        n += 1

    return canaries


def _mine_claim_gaps(target_root: Path, start_id: int) -> list[dict]:
    """策略 4: 查找 'all tests pass' 后跟 'fix' → overconfidence canary。"""
    canaries = []
    # 获取最近 50 条 commit
    output = _run_git(target_root, [
        "log", "--all", "--oneline", "-50",
    ])
    if not output:
        return []

    lines = output.splitlines()
    claim_pattern = re.compile(r"(?i)all tests|100%|fully tested|完成|通过|no issues|verified")
    fix_pattern = re.compile(r"(?i)fix|bug|hotfix|patch|修复|修正")

    n = start_id
    for i, line in enumerate(lines):
        if not claim_pattern.search(line):
            continue
        # 检查后续 3 个 commit 是否有 fix
        for j in range(1, min(4, len(lines) - i)):
            if fix_pattern.search(lines[i + j]):
                claim_hash = line.split(None, 1)[0]
                fix_line = lines[i + j]
                fix_hash = fix_line.split(None, 1)[0]
                canaries.append(_make_canary(
                    n, "overconfidence",
                    claim=f"Commit {claim_hash}: {line.split(None, 1)[1] if len(line.split(None, 1)) > 1 else ''}",
                    finding=f"Within 3 commits, a fix was needed: {fix_hash}: {fix_line.split(None, 1)[1] if len(fix_line.split(None, 1)) > 1 else ''}",
                    source=f"git-claim-gap:{claim_hash}→{fix_hash}",
                ))
                n += 1
                break  # 每个 claim 只生成一个 canary

        if n - start_id >= 3:  # 最多 3 条
            break

    return canaries


# ══════════════════════════════════════════════════════════
# CLI 入口
# ══════════════════════════════════════════════════════════

def cmd_detect(args):
    """执行项目检测。"""
    target = Path(args.target).resolve()
    if not target.is_dir():
        print(f"Error: {target} is not a directory", file=sys.stderr)
        sys.exit(1)

    profile = detect_project(target)

    # 保存到状态文件
    state = load_state()
    state["project_profile"] = profile
    save_state(state)

    # 输出结果
    print(json.dumps({
        "status": "detected",
        "project_type": profile["project_type"],
        "languages": profile["languages"],
        "frameworks": profile["frameworks"],
        "test_frameworks": profile["test_frameworks"],
        "ci_system": profile["ci_system"],
        "bootstrap_threshold": profile["bootstrap_threshold"],
    }, indent=2, ensure_ascii=False))


def cmd_seed_critics(args):
    """生成 seed critics。"""
    state = load_state()
    profile = state.get("project_profile")
    if not profile:
        print("Error: No project profile found. Run 'detect' first.", file=sys.stderr)
        sys.exit(1)

    created = seed_critics(Path(args.target).resolve(), profile)
    print(json.dumps({
        "status": "seeded",
        "created_critics": created,
        "skipped": "existing critics preserved",
    }, indent=2, ensure_ascii=False))


def cmd_seed_canaries(args):
    """从 git 挖掘初始 canaries。"""
    state = load_state()
    profile = state.get("project_profile", {})
    target = Path(args.target).resolve()

    canaries = seed_canaries(target, profile)
    print(json.dumps({
        "status": "mined",
        "canaries_created": len(canaries),
        "blindspot_types": sorted(set(c["blindspot_type"] for c in canaries)),
        "canary_ids": [c["id"] for c in canaries],
    }, indent=2, ensure_ascii=False))


def cmd_full(args):
    """一键冷启动：detect → seed-critics → seed-canaries。"""
    target = Path(args.target).resolve()
    print(f"=== tcell bootstrap: {target} ===\n")

    # Step 1: Detect
    print("Step 1/3: Detecting project...")
    profile = detect_project(target)
    state = load_state()
    state["project_profile"] = profile
    save_state(state)
    print(f"  type: {profile['project_type']}")
    print(f"  languages: {', '.join(profile['languages']) or 'none detected'}")
    print(f"  frameworks: {', '.join(profile['frameworks']) or 'none detected'}")
    print(f"  threshold: {profile['bootstrap_threshold']}")
    print()

    # Step 2: Seed Critics
    print("Step 2/3: Seeding critics from templates...")
    created = seed_critics(target, profile)
    if created:
        print(f"  created: {', '.join(created)}")
    else:
        print("  skipped (all critics already exist)")
    print()

    # Step 3: Seed Canaries
    print("Step 3/3: Mining canaries from git history...")
    canaries = seed_canaries(target, profile)
    if canaries:
        types = sorted(set(c["blindspot_type"] for c in canaries))
        print(f"  mined: {len(canaries)} canaries")
        print(f"  types: {', '.join(types)}")
    else:
        print("  no canaries mined (git history too short or no patterns found)")
    print()

    # Summary
    total_canaries = len(list(CANARIES_FILE.open().readlines())) if CANARIES_FILE.exists() else 0
    threshold = profile["bootstrap_threshold"]
    status = "ready" if total_canaries >= threshold else f"need {threshold - total_canaries} more canaries"
    print(f"=== Bootstrap complete ===")
    print(f"  canaries: {total_canaries}/{threshold} ({status})")
    print(f"  critics: {len(list(CRITICS_DIR.glob('*.md')))} active")


def main():
    parser = argparse.ArgumentParser(
        description="tcell adaptive cold-start bootstrapper",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    for name, help_text in [
        ("detect", "Detect project type/language/framework"),
        ("seed-critics", "Generate seed critics from templates"),
        ("seed-canaries", "Mine initial canaries from git history"),
        ("full", "Full cold-start: detect + seed-critics + seed-canaries"),
    ]:
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--target", default=".", help="Target project directory (default: .)")

    args = parser.parse_args()

    dispatch = {
        "detect": cmd_detect,
        "seed-critics": cmd_seed_critics,
        "seed-canaries": cmd_seed_canaries,
        "full": cmd_full,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
