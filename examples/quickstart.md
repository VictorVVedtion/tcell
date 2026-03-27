# Quickstart: Your First tcell Review

This walkthrough takes ~5 minutes.

## 1. Verify Installation

```bash
cd tcell
python3 prepare.py self-test
```

Expected output:
```
═══ tcell Self-Test ═══

  [PASS] Data integrity: 8 canaries, 5 clean_samples
  [PASS] Critics: 5/5 valid
  [PASS] Coverage matrix: 5/5 blindspot types have critics
  [WARN] Cold start: 8/20 canaries (need 12 more for evolution)
  [PASS] Evolution: 5 iterations (5 keep / 0 discard)
  [PASS] Hook config: 1 hook types configured

Status: HEALTHY (cold start mode)
```

## 2. Check System Health

```bash
python3 prepare.py session-score
```

This gives you a 0-10 score of the immune system's readiness.

## 3. See the Critic Leaderboard

```bash
python3 evolve.py leaderboard
```

Shows which critics are strongest and which need more evolution.

## 4. Review Your Data

```bash
./review.sh path/to/your-data.jsonl
```

This runs Steps 1-2 and 4 automatically, and outputs a prompt for Step 3
(the independent subagent review that requires Claude Code).

## 5. Turn a Finding into a Canary

When the review finds a real problem, record it:

```bash
# Add to canaries.jsonl
echo '{"id":"canary-009","timestamp":"2026-03-27T10:00:00Z","source":"my-project","main_agent_claim":"All tests passing","actual_finding":"3 edge cases untested, 2 fail on boundary values","severity":2,"blindspot_type":"overconfidence","discovered_by":"sidebar-review","confirmed_by":"human-review"}' >> canaries.jsonl

# Verify
python3 prepare.py self-test
```

Every canary you add makes the whole system smarter.

## What's Next

- **More canaries** → Once you reach 20, evolution mode unlocks automatically
- **New critics** → See [CONTRIBUTING.md](../CONTRIBUTING.md) for how to add detection strategies
- **Hook integration** → Configure `.claude/settings.json` in your project for real-time monitoring
