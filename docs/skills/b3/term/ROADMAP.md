<- Back to [TERM](../TERM.md)

# Roadmap

## 📋 Quick View

| Priority | Item | Description |
|----------|------|-------------|
| P3 | Forward skill (new) | BDI 46/48 — forward contracts. Same architecture. |
| P3 | Index options skill (new) | BDI 83/84 — index options. Same architecture. |
| P4 | Open interest | DerivativesOpenPosition API investigation (broken). |

> **Note:** Recently completed items are in [CHANGELOG.md](CHANGELOG.md).

## 📋 Backlog

### Forward skill
BDI 46/48 (derivative_type = "FORWARD"). Forward with continuous movement + gain retention. Same architecture as term — query `cotahist_derivatives` table, separate `skills/b3/forward/` skill.

### Index options skill
BDI 83/84. Index calls + puts. Cash-settled (no physical delivery). Same architecture as the stock options skill.

### Open interest
Needs DerivativesOpenPosition API (B3 API changed — investigate). Would show open interest per strike + by maturity.

---

*Last updated: 2026-08-16 (v1.0). See [CHANGELOG.md](CHANGELOG.md) for version history.*
