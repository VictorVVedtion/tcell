# tcell

<p align="center">
  <img src="assets/tcell-hero.png" alt="tcell — A cognitive immune system for AI agents" width="600">
</p>

<p align="center">
  <strong>A cognitive immune system for AI agents.</strong><br>
  <em>Like T-cells in your body: silent when healthy, lethal when threats appear, and constantly evolving.</em>
</p>

<p align="center">
  <a href="README.zh-CN.md">中文版</a> · <a href="CONTRIBUTING.md">Contributing</a> · <a href="examples/quickstart.md">Quickstart</a>
</p>

When an AI agent works in a long session, it generates output AND evaluates that output within the same reasoning context. This creates structural self-assessment bias. The agent says "100% pass rate" ... that's not evidence, that's a claim.

tcell is an independent cognitive reviewer. It uses fresh context to audit the main agent's quality claims, detecting thinking pattern biases rather than just code bugs. Its review strategies self-evolve through an [autoresearch](https://github.com/karpathy/autoresearch)-style evolution loop.

## Why This Exists

Real case: Opus 4.6 generated 107 SFT training samples and self-evaluated:

| Metric | Main agent self-eval | Independent review |
|---|---|---|
| Pass rate | 100% | — |
| Quality score | All 1.000 (perfect) | 5.5/10 |
| Assessment | "Extremely high quality" | 5 critical issues found |

What the independent review found:
- **45.8% of confidence values homogenized at 0.62** (std = 0)
- **Bias labels position-bound** (C1 was always confirmation_bias)
- **loss_aversion completely absent** (the most critical bias for trading scenarios)
- **Quality scorer non-discriminating** (107 samples all scored 1.000)
- **Synthesis always fully flipped** (no partial corrections)

The key insight: **both reviews used the same model (Opus 4.6).** The problem isn't model capability. It's context isolation. The same model with independent context catches the structural blindspots.

## Architecture

Built on [Karpathy's autoresearch](https://github.com/karpathy/autoresearch) philosophy: humans program the meta-instructions, agents evolve the review strategies.

```
                    ┌──────────────┐
                    │  Main Agent  │  ← monitored Claude Code session
                    └──────┬───────┘
                           │ Write/Edit/Bash
              ┌────────────┼────────────┐
              ▼            ▼            ▼
         ┌────────┐  ┌────────┐  ┌────────┐
         │  Hook  │  │  Cron  │  │Evolve  │
         │signals │  │ deep   │  │  loop  │
         └───┬────┘  └───┬────┘  └───┬────┘
             │           │           │
             ▼           ▼           ▼
         ┌─────────────────────────────┐
         │  Critics (evolvable review  │
         │  strategies in .md files)   │
         └─────────────────────────────┘
                    │
         ┌──────────┴──────────┐
         ▼                     ▼
    canaries.jsonl        clean_samples.jsonl
    (confirmed            (confirmed clean
     blindspots)           samples for FP)
```

**Three-file mapping (mirrors autoresearch):**

| autoresearch | tcell | role |
|---|---|---|
| `prepare.py` | `prepare.py` | Fixed infrastructure. Critics cannot modify this. |
| `train.py` | `critics/*.md` | Evolvable review strategies. |
| `program.md` | `program.md` | Human-authored meta-instructions. |

## Quick Start

```bash
git clone <repo-url> tcell
cd tcell

# 1. Verify system integrity
python3 prepare.py self-test

# 2. See the critic leaderboard
python3 evolve.py leaderboard

# 3. Check cognitive health score
python3 prepare.py session-score

# 4. Review your data
./review.sh <your-data.jsonl>
```

See [examples/quickstart.md](examples/quickstart.md) for a full walkthrough.

## Core Concepts

**Canary** — A confirmed blindspot. The main agent claimed high quality, but independent review found a real problem. Canaries are the training data for the evolution loop.

**Critic** — A `.md` file containing detection rules. Critics self-evolve through mutation → replay → keep/discard cycles.

**Detection Rate** — Operational metric. How well a critic catches known blindspots (canaries). Used for evolution decisions.

**Self-Certification Regret** — Retrospective metric. What proportion of problems the sidebar itself also missed. Requires external confirmation, not used for automated decisions.

**Noise Budget** — Max 1 alert per 10 tool calls. Silence is proof of trust.

**Cold Start** — When canaries < 20, evolution pauses. The system only collects data.

## Evolution Loop

<p align="center">
  <img src="assets/tcell-evolution.png" alt="tcell evolution loop — critics mutate, replay against canaries, keep or discard" width="500">
</p>

```
select → mutate → replay → keep/discard → record
  │         │        │          │            │
  ▼         ▼        ▼          ▼            ▼
pick the  change    run on     detection↑    results.tsv
oldest    ONE       canaries   and FP≤10%    sidebar.log
critic    dimension 3x vote    → keep, else
                               → discard
```

Mutation operators: `threshold_shift` | `focus_expand` | `focus_narrow` | `strategy_rewrite` | `example_inject` | `simplify`

## Iron Rules (summary)

1. **Never trust self-assessment** — "100% pass" is a claim, not evidence
2. **Silence is proof of trust** — No evidence, no alert
3. **Only speak with evidence** — Numbers or nothing
4. **Always use fresh eyes** — Context isolation is the lifeline
5. **Audit thinking patterns, not just output** — Catch the bias, not just the bug
6. **Evolve, don't ossify** — Static reviewers give false security
7. **Noise budget is sacred** — Better to miss a small issue than cry wolf three times

Full iron rules: [CLAUDE.md](CLAUDE.md) | Evolution rules: [program.md](program.md)

## Project Structure

```
README.md              Project documentation
CLAUDE.md              Iron rules + engineering philosophy
program.md             Human-authored meta-instructions
prepare.py             Fixed infrastructure (self-test, session-score, hook-check)
evolve.py              Evolution controller (select, evaluate, leaderboard)
review.sh              One-click review script
critics/               Evolvable critic prompt files
canaries.jsonl         Confirmed blindspots (evolution training data)
clean_samples.jsonl    Confirmed clean samples (FP rate calculation)
results.tsv            Evolution history
sidebar.log.md         Human-readable activity log
.claude/agents/        Subagent definitions
.claude/settings.json  Hook configuration
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Every canary you add makes the whole system smarter.

## Roadmap

- [x] v1 skeleton (prepare.py, evolve.py, 5 critics)
- [x] Evolution loop (select → mutate → replay → keep/discard)
- [x] Self-test command
- [x] Session score (cognitive health 0-10)
- [x] Critic leaderboard
- [x] Cold start gate
- [x] One-click review script (review.sh)
- [ ] Evolution replay (watch critic evolution like a Go game replay)
- [ ] Fully unattended evolution (/loop integration)
- [ ] Meta-evolution (auto-tune program.md parameters)
- [ ] Cross-project critic migration
- [ ] Community canary network

## License

MIT
