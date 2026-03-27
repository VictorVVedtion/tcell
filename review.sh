#!/usr/bin/env bash
# review.sh — 一键 tcell 审查
# 用法: ./review.sh <SFT数据路径> [主agent的质量声明]
#
# 示例:
#   ./review.sh path/to/your-data.jsonl
#   ./review.sh path/to/your-data.jsonl "248 samples all passed, quality score mean 0.95"
#
# 完整 4 步流程:
#   Step 1: 分析 SFT 数据，自动生成质量声明摘要
#   Step 2: Hook 检查（轻量模式匹配）
#   Step 3: 输出独立审查 prompt（需要在 Claude Code 中用 subagent 执行）
#   Step 4: 追加结果到 sidebar.log.md

set -euo pipefail

SIDEBAR_ROOT="$(cd "$(dirname "$0")" && pwd)"
SFT_PATH="${1:?用法: ./review.sh <SFT数据路径> [质量声明]}"
CLAIM="${2:-}"
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
CLAIM_FILE="/tmp/sidebar-claim-$(date +%s).json"

# ── 颜色 ──
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}═══════════════════════════════════════════════${NC}"
echo -e "${CYAN}🐕 tcell — 完整审查流程${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════${NC}"
echo ""

# ── Step 1: 分析 SFT 数据 ──────────────────────────
echo -e "${YELLOW}Step 1/4: 分析 SFT 数据...${NC}"

if [ ! -f "$SFT_PATH" ]; then
    echo -e "${RED}错误: 文件不存在 — $SFT_PATH${NC}"
    exit 1
fi

SAMPLE_COUNT=$(wc -l < "$SFT_PATH" | tr -d ' ')
echo "  文件: $SFT_PATH"
echo "  样本数: $SAMPLE_COUNT"

# 提取关键统计
STATS=$(python3 -c "
import json, sys
from collections import Counter

data = []
with open('$SFT_PATH') as f:
    for line in f:
        line = line.strip()
        if line:
            try:
                data.append(json.loads(line))
            except:
                pass

if not data:
    print(json.dumps({'error': 'no data', 'count': 0}))
    sys.exit(0)

# 尝试提取常见字段的统计
stats = {'count': len(data)}

# confidence 分布
confs = []
for d in data:
    # 递归搜索 confidence 字段
    def find_conf(obj, depth=0):
        if depth > 5: return
        if isinstance(obj, dict):
            for k, v in obj.items():
                if 'confidence' in k.lower() and isinstance(v, (int, float)):
                    confs.append(v)
                elif isinstance(v, (dict, list)):
                    find_conf(v, depth+1)
        elif isinstance(obj, list):
            for item in obj:
                find_conf(item, depth+1)
    find_conf(d)

if confs:
    from statistics import mean, stdev
    stats['confidence_mean'] = round(mean(confs), 4)
    stats['confidence_std'] = round(stdev(confs), 4) if len(confs) > 1 else 0
    stats['confidence_count'] = len(confs)
    # 最高频值
    counter = Counter(round(c, 2) for c in confs)
    most_common = counter.most_common(1)[0]
    stats['confidence_mode'] = most_common[0]
    stats['confidence_mode_pct'] = round(most_common[1] / len(confs) * 100, 1)

# action 分布
actions = []
for d in data:
    def find_action(obj, depth=0):
        if depth > 5: return
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == 'action' and isinstance(v, str):
                    actions.append(v)
                elif isinstance(v, (dict, list)):
                    find_action(v, depth+1)
        elif isinstance(obj, list):
            for item in obj:
                find_action(item, depth+1)
    find_action(d)

if actions:
    stats['action_distribution'] = dict(Counter(actions))

# bias type 分布
biases = []
for d in data:
    def find_bias(obj, depth=0):
        if depth > 5: return
        if isinstance(obj, dict):
            for k, v in obj.items():
                if 'bias' in k.lower() and isinstance(v, str):
                    biases.append(v)
                elif isinstance(v, (dict, list)):
                    find_bias(v, depth+1)
        elif isinstance(obj, list):
            for item in obj:
                find_bias(item, depth+1)
    find_bias(d)

if biases:
    stats['bias_distribution'] = dict(Counter(biases))

print(json.dumps(stats, ensure_ascii=False))
" 2>/dev/null || echo '{"count": 0, "error": "parse failed"}')

echo "  统计: $STATS"

# 自动生成 claim（如果未提供）
if [ -z "$CLAIM" ]; then
    CLAIM="SFT 数据生成完成，共 ${SAMPLE_COUNT} 条样本"
fi

# 写入 claim 文件
python3 -c "
import json
claim = {
    'timestamp': '$TIMESTAMP',
    'claim': '$CLAIM',
    'data_path': '$SFT_PATH',
    'sample_count': $SAMPLE_COUNT,
    'stats': $STATS
}
with open('$CLAIM_FILE', 'w') as f:
    json.dump(claim, f, ensure_ascii=False, indent=2)
print('  claim 文件:', '$CLAIM_FILE')
"

echo ""

# ── Step 2: Hook 检查 ─────────────────────────────
echo -e "${YELLOW}Step 2/4: Hook 检查（轻量模式匹配）...${NC}"
python3 "$SIDEBAR_ROOT/prepare.py" hook-check --event "SFT-review" --payload "$CLAIM_FILE"
echo "  ✓ Hook 检查完成"
echo ""

# ── Step 3: 输出独立审查 prompt ──────────────────
echo -e "${YELLOW}Step 3/4: 生成独立审查 Prompt${NC}"
echo ""
echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}将以下 prompt 复制到 Claude Code 中用 Agent subagent 执行：${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
echo ""

cat << PROMPT_END
你是一个独立的认知审查员。你没有看过主 agent 的对话，你的上下文是干净的。

## 待审查数据
- SFT 数据: $SFT_PATH ($SAMPLE_COUNT 条)
- 主 agent 声明: $CLAIM_FILE
- 数据统计: $STATS

## 审查规则
读取以下文件作为你的审查指南：
- $SIDEBAR_ROOT/program.md
- $SIDEBAR_ROOT/canaries.jsonl（历史盲区，避免重蹈覆辙）

## 审查步骤
1. 读取 SFT 数据文件，抽样 10-20 条进行深度分析
2. 按 critics/ 目录下的 5 个 critic 逐一检查：
   - $SIDEBAR_ROOT/critics/overconfidence.md
   - $SIDEBAR_ROOT/critics/homogenization.md
   - $SIDEBAR_ROOT/critics/coverage_gaps.md
   - $SIDEBAR_ROOT/critics/position_bias.md
   - $SIDEBAR_ROOT/critics/premature_closure.md
3. 对每个 critic，输出结构化 JSON 结果
4. 魔鬼辩护：对主 agent 的每个质量声明，列出 3 个可能是错的理由
5. 综合评分（0-10）并输出发现摘要

## 输出格式
```json
{
  "overall_score": 7.5,
  "findings": [
    {"critic": "...", "detected": true/false, "severity": 0-3, "evidence": "...", "reasoning": "..."}
  ],
  "devils_advocate": [
    {"claim": "...", "reasons_might_be_wrong": ["...", "...", "..."]}
  ],
  "summary": "一段话总结"
}
```

重点关注历史盲区（canaries.jsonl 中的模式）是否再次出现。
PROMPT_END

echo ""
echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
echo ""

# ── Step 4: 追加日志 ─────────────────────────────
echo -e "${YELLOW}Step 4/4: 追加审查记录到日志...${NC}"
python3 "$SIDEBAR_ROOT/prepare.py" log "🔍 Review initiated · $SFT_PATH · ${SAMPLE_COUNT} samples · claim: $CLAIM"
echo "  ✓ 日志已更新: $SIDEBAR_ROOT/sidebar.log.md"
echo ""

echo -e "${GREEN}═══════════════════════════════════════════════${NC}"
echo -e "${GREEN}🐕 审查流程 Step 1-2, 4 已完成${NC}"
echo -e "${GREEN}   Step 3 需要手动在 Claude Code 中用 subagent 执行${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════${NC}"
