# Contributing to tcell

Thanks for your interest in making AI agents more trustworthy.

## How to Contribute

### Adding a Canary (confirmed blindspot)

When you discover that a main agent's self-assessment was wrong, record it:

1. Add an entry to `canaries.jsonl`:

```json
{
  "id": "canary-NNN",
  "timestamp": "2026-03-26T12:00:00Z",
  "source": "your-project/batch-id",
  "main_agent_claim": "The exact quality claim the agent made",
  "actual_finding": "What independent review actually found, with numbers",
  "severity": 3,
  "blindspot_type": "matching critic name (e.g., overconfidence, homogenization)",
  "discovered_by": "how it was discovered",
  "confirmed_by": "how it was confirmed (human-review, dual-critic, etc.)"
}
```

2. Run `python3 prepare.py self-test` to verify the entry is valid
3. Submit a PR

**Requirements:**
- `confirmed_by` is mandatory. Unconfirmed findings go to `pending_canaries/`
- `severity` must be 1-3 (1=medium, 2=serious, 3=fatal)
- `actual_finding` must include quantitative evidence

### Adding a Critic (detection strategy)

Create `critics/your_critic.md`:

```markdown
---
name: your_critic
version: 1
detection_rate: 0.00
fp_rate: 0.00
last_evolved: 2026-01-01T00:00:00Z
---

# Your Critic Name

## Detection Target
What cognitive bias or pattern does this critic detect?

## Detection Rules
1. Specific rule with threshold...
2. Another rule...

## Source Case
The real-world case that motivated this critic.

## Output Format
{"detected": true/false, "severity": 0-3, "evidence": "...", "reasoning": "..."}
```

### Validation

Before submitting:
```bash
python3 prepare.py self-test      # System integrity
python3 prepare.py validate       # Data file validation
python3 evolve.py leaderboard     # Check critic stats
```

### PR Guidelines

- One canary or one critic per PR (keep reviews focused)
- Include the real-world context that motivated the contribution
- Canaries from different domains (not just SFT) are especially valuable

## Code of Conduct

Be kind. Be specific. Be honest about what you don't know.
