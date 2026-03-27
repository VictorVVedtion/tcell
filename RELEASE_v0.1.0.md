# v0.1.0 — First Light

The cognitive immune system is online. This release includes the complete v1 skeleton: detection infrastructure, 5 seed critics, an evolution loop, and the tools to start building your canary library.

## What's included

### Core Infrastructure
- **prepare.py** — Fixed infrastructure: self-test, session-score, hook-check, data validation, recovery
- **evolve.py** — Evolution controller: select, mutate, replay, keep/discard, leaderboard
- **review.sh** — One-click review script for auditing data files

### 5 Seed Critics
- `homogenization.md` v3 — Detects value clustering and zero-variance distributions
- `position_bias.md` v2 — Catches position-bound label assignments
- `premature_closure.md` v2 — Identifies 180° flip patterns lacking partial corrections
- `coverage_gaps.md` v2 — Finds missing critical categories
- `overconfidence.md` v2 — Flags zero-discrimination scorers and inflated pass rates

### Evolution Loop
- 6 mutation operators: threshold_shift, focus_expand, focus_narrow, strategy_rewrite, example_inject, simplify
- Canary replay with 3x majority voting
- Keep threshold: +5% detection rate AND ≤10% FP rate
- Cold start gate: pauses evolution until 20+ canaries accumulated

### Data
- 9 seed canaries from real SFT data generation sessions
- 5 clean samples for false positive rate calculation

### Integration
- Claude Code hook configuration for real-time monitoring
- Subagent definitions for context-isolated review

## Quick Start

```bash
git clone https://github.com/VictorVVedtion/tcell.git
cd tcell
python3 prepare.py self-test
python3 evolve.py leaderboard
./review.sh <your-data.jsonl>
```

## What's Next
- Fully unattended evolution loops
- Cross-project critic migration
- Community canary network
- Meta-evolution (auto-tune program.md parameters)
