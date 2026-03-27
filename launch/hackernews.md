# Hacker News — Show HN

**Title:** Show HN: tcell – A self-evolving cognitive immune system for AI agents

**URL:** https://github.com/VictorVVedtion/tcell

**Text (for "Show HN" text post):**

When AI agents work in long sessions, they evaluate their own outputs within the same reasoning context that generated them. This creates structural self-assessment bias.

Real example: Opus 4.6 generated 107 SFT training samples and self-evaluated them at "100% pass rate, quality 1.000." An independent review (same model, fresh context) scored them 5.5/10 and found 5 critical issues — including 45.8% of confidence values stuck at exactly 0.62.

The fix isn't using a different model. It's context isolation. Same model + fresh context catches the blindspots.

tcell is an independent reviewer that sits alongside your AI agent session. It:

- Uses fresh-context subagents for every review (no shared history)
- Evolves its review strategies through an autoresearch-style loop (mutate → replay on known blindspots → keep/discard)
- Respects a noise budget (max 1 alert per 10 tool calls — silence = trust)
- Tracks a single metric: detection rate on confirmed blindspots

It's inspired by Karpathy's autoresearch — same three-file architecture (fixed infra / evolvable strategies / human meta-instructions), but applied to cognitive bias detection rather than model training.

Currently in cold start mode (8 confirmed blindspots, need 20 for autonomous evolution). MIT licensed, pure Python, zero dependencies beyond Claude Code.

Curious about: has anyone else run into the "agent grades its own homework" problem? What approaches have you tried?
