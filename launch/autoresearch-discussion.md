# autoresearch GitHub Discussion Post

**Title:** tcell: applying the autoresearch loop to cognitive bias detection in AI agents

**Body:**

Hey everyone,

autoresearch showed that an autonomous loop of modify → train → evaluate → keep/discard can produce real gains on val_bpb overnight. I've been wondering: can the same loop work for a different problem — catching cognitive biases in AI agent outputs?

**The problem I ran into:** I was using Opus 4.6 to generate SFT training data. The agent self-evaluated: "100% pass rate, quality score 1.000." I spawned an independent subagent (same model, fresh context) to double-check. It scored the data 5.5/10 and found 5 critical issues:

- 45.8% of confidence values homogenized at 0.62 (std=0)
- Bias labels were position-bound (C1 was always confirmation_bias)
- loss_aversion was completely absent from trading scenarios
- Quality scorer gave identical 1.000 to all 107 samples

The key realization: **context isolation, not model diversity, is what matters.** Same model, fresh context, catches the blindspots.

**What I built:** tcell maps the autoresearch architecture to cognitive review:

| autoresearch | tcell | role |
|---|---|---|
| `prepare.py` | `prepare.py` | Fixed evaluation infrastructure |
| `train.py` | `critics/*.md` | Evolvable review strategies |
| `program.md` | `program.md` | Human meta-instructions |
| `val_bpb` | `detection_rate` | Single metric to optimize |
| `results.tsv` | `results.tsv` | Evolution history |

Critics self-evolve through mutation → replay on known blindspots (canaries) → keep/discard based on detection rate improvement. Same loop, different domain.

After 5 evolution iterations, the overconfidence critic reached 80% detection rate on canaries with 0% false positives. Still in cold start (8 canaries, need 20 for full evolution mode).

**Open question for this community:** autoresearch optimizes a fixed metric (val_bpb) on a fixed eval set. tcell's "eval set" (canaries) grows over time as new blindspots are discovered. How do you think about evolving the evaluation criteria alongside the system being optimized? Is that a feature or a bug?

Repo: https://github.com/VictorVVedtion/tcell

Would love feedback from anyone who's thought about applying the autoresearch pattern outside of model training.
