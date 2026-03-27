# X/Twitter English Thread

## Tweet 1 (Hook — attach tcell-hero.png)

AI agents are terrible at checking their own work.

Opus 4.6 self-evaluated 107 synthetic training samples:
→ "100% pass rate, quality score 1.000"

An independent review scored it 5.5/10 and found 5 critical flaws.

Both reviews used the exact same model.

Meet tcell: a cognitive immune system for AI agents. 🧬🔽

## Tweet 2 (The Problem)

The problem isn't model capability. It's context isolation.

When an agent generates output AND evaluates it in the same context, it develops structural blindspots:
- 45.8% of confidence values stuck at 0.62
- Bias labels position-bound (C1 always = confirmation_bias)
- Quality scorer gave 1.000 to everything

The agent literally cannot see its own biases.

## Tweet 3 (The Insight)

The fix isn't "use a smarter model."

Same model + fresh context = catches the blindspots.

Context isolation, not model diversity, is what matters.

This is why pair programming works. Your partner doesn't need to be smarter than you. They just need different context.

## Tweet 4 (The Solution — attach tcell-evolution.png)

tcell applies @karpathy's autoresearch philosophy to cognitive review:

- Critics (review strategies) self-evolve via mutation → replay → keep/discard
- Canaries (confirmed blindspots) are the training data
- Humans program the meta-instructions, not the critics
- One metric: detection rate on known blindspots

program.md for cognition.

## Tweet 5 (Iron Rules)

tcell's 7 Iron Rules:

1. Never trust self-assessment
2. Silence is proof of trust
3. Only speak with numbers
4. Always use fresh eyes
5. Audit thinking, not just output
6. Evolve or die
7. Noise budget is sacred (1 alert / 10 calls max)

Rule 2 is key: if 50% of your alerts are false positives, you're a dog that barks at nothing.

## Tweet 6 (CTA)

tcell is open source, MIT licensed, zero dependencies.

Clone → self-test → review your data in 5 minutes.

Every canary (confirmed blindspot) you contribute makes the whole immune system smarter.

github.com/VictorVVedtion/tcell

Built with Claude Code. Inspired by @karpathy's autoresearch.
