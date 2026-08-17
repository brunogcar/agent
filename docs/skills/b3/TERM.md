<- Back to [B3 Skills](../B3.md)

# Term Skill

B3 term (a termo) contracts dashboard. Queries the `cotahist_derivatives` table
(same DB as equities + options) for term contract data (BDI 26/74).

## Quick Start

```
skill(domain="b3", sub_domain="term", mode="dashboard", params='{"ticker":"PETR4"}')
```

## Configuration

- Required sources: `["cotahist"]` (shared DB — derivatives table populated during COTAHIST sync)
- No separate sync needed — derivatives data is stored during the standard COTAHIST sync

## Subfile Directory

| File | Description |
|------|-------------|
| [ARCHITECTURE.md](term/ARCHITECTURE.md) | File map, data flow, query inventory |
| [API.md](term/API.md) | Dashboard mode signature, response shape |
| [CHANGELOG.md](term/CHANGELOG.md) | Version history |
| [INSTRUCTIONS.md](term/INSTRUCTIONS.md) | AI editing rules |
| [ROADMAP.md](term/ROADMAP.md) | Backlog + future features |
