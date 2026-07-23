# 🧩 Skills Architecture & Domain Guide

Skills are domain-specific knowledge packages that extend the agent's capabilities beyond general-purpose tools. Unlike core meta-tools (which implement atomic actions), skills encapsulate **domain expertise, data pipelines, and specialized workflows** for specific industries or use cases.

## 🏗️ Skill Creation Guidelines

### The Hub-and-Spoke Pattern

Skills do **not** use the `@tool` decorator on every function. Instead, they rely on `skills/dispatcher.py` to auto-discover **Domain Hubs**.

**The Hub** (`<domain>.py`): A single entry-point file that acts as the MCP tool. It receives the user's intent and routes it to the correct subdomain.

**The Subdomains**: Pure Python modules containing the actual business logic, API wrappers, and data processing. They are **not** exposed directly to the LLM.

**The Dispatcher**: `skills/dispatcher.py` scans the `skills/` directory, identifies these Hubs, and registers them as top-level tools (e.g., a tool named `b3` and a tool named `cvm`).

### Step-by-Step: Adding a New Skill Domain

1. **Create the Domain Folder**: `skills/my_domain/`
2. **Create the Hub**: Create `skills/my_domain/my_domain.py`. This file must implement the main execution logic that `dispatcher.py` expects.
3. **Create Subdomains**: Create modules like `skills/my_domain/api_client.py` or `skills/my_domain/analytics.py`.
4. **Wire the Hub**: Inside `my_domain.py`, import your subdomains and route the `action` argument to them.

```python
# skills/my_domain/my_domain.py (The Hub)
from . import api_client, analytics

def execute(action: str, **kwargs) -> dict:
    """Main entry point registered by skills/dispatcher.py"""
    if action == "fetch_data":
        return api_client.fetch(**kwargs)
    elif action == "analyze":
        return analytics.run(**kwargs)
    return {"status": "error", "error": f"Unknown action: {action}"}
```

### ⚠️ AI Agent Constraints for Skills

- **Hub Responsibility**: The Hub is responsible for input validation and error handling before passing data to subdomains.
- **No Direct MCP Decorators**: Do **not** use `@tool` inside subdomain files. Only the Hub is registered as a tool.
- **Logging**: Use `core.tracer` for all logging. Never use `print()`.
- **Data Lake**: Store downloaded datasets in `WORKSPACE_ROOT/data/<domain>/` for persistence across sessions.

---

## 📈 Current Skill Domains

### 1. B3 (Brasil, Bolsa, Balcão)

**Location**: `skills/b3/`  
**Purpose**: Ingest, sync, and query Brazilian stock market data from Brasil, Bolsa, Balcão (Brazilian Stock Exchange).

#### 🏛️ Domain Hub: `skills/b3/b3.py`

The central router for all B3-related operations. It exposes a single `b3` tool to the LLM.

**Routing Logic**: Inspects the `action` and `subdomain` parameters to delegate tasks.

**Data Lake Management**: Manages the local CSV cache in `WORKSPACE_ROOT/data/b3/`.

**Modes**:
- **`sync`**: Triggers background downloaders to update local datasets (daily CSVs from B3 endpoints).
- **`query`**: Executes pandas/SQL logic against local data for analysis.
- **`status`**: Reports on data freshness and cache health.

#### 📂 Subdomains

**`b3_api`**:
- **Function**: Core data ingestion and management.
- **Capabilities**: Handles direct HTTP interaction with B3 endpoints, manages daily CSV downloads, file parsing, and local storage synchronization.
- **Data Types**: Daily trading volumes, price histories, corporate actions.

**`b3_dividends`**:
- **Function**: Dividend and payout tracking.
- **Capabilities**: Tracks dividend payouts, yield histories, ex-dividend dates, and corporate actions (splits, bonuses).
- **Use Case**: "Show me all stocks with dividend yield > 5% in the last 12 months."

**`b3_cvm`** (Cross-domain bridge):
- **Function**: Maps B3 tickers to CVM regulatory IDs (CNPJ/CVM codes).
- **Capabilities**: Handles data integration logic that requires context from both the stock exchange and the securities commission.
- **Use Case**: Linking market data with regulatory filings.

#### 💡 Example Usage

```python
# Sync latest B3 data
b3(action="sync", subdomain="dividends", date_range="2024-01-01_to_2024-12-31")

# Query high-yield stocks
b3(action="query", subdomain="dividends", 
   query="SELECT ticker, dividend_yield FROM dividends WHERE yield > 0.05 ORDER BY yield DESC")

# Check data freshness
b3(action="status")
```

---

### 2. CVM (Comissão de Valores Mobiliários)

**Location**: `skills/cvm/`  
**Purpose**: Regulatory, financial statement, and shareholder data from the Brazilian SEC equivalent.

#### 🏛️ Domain Hub: `skills/cvm/cvm.py`

The central router for all CVM regulatory data. It exposes a single `cvm` tool to the LLM.

**Routing Logic**: Directs requests to specific subdomains based on the data type required (e.g., financials vs. shareholders).

**Rate Limiting**: Implements global rate limiting for CVM portal requests to avoid IP bans (CVM has strict scraping policies).

**Integration**: Orchestrates data fetching between `cvm_dfp_itr` (raw data) and analytical subdomains.

#### 📂 Subdomains

**`cvm_dfp_itr`**:
- **Function**: Low-level HTTP wrapper for the CVM Open Data portal.
- **Capabilities**: Handles session management, ZIP extraction, and raw CSV parsing for DFP (Demonstrações Financeiras Padronizadas) and ITR (Informações Trimestrais) filings.
- **Data Types**: Balance sheets, income statements, cash flow statements.

**`cvm_dividends`**:
- **Function**: Financial analysis module.
- **Capabilities**: Cross-references CVM financial statements (DFP/ITR) with B3 data to verify dividend declarations and payout ratios.
- **Use Case**: "Verify if Company X's declared dividend matches their reported net income."

**`cvm_shareholders`**:
- **Function**: Ownership tracking.
- **Capabilities**: Parses FRE (Formulário de Referência) data to track institutional ownership changes, insider trading disclosures, and major shareholder movements.
- **Use Case**: "Show me all insider transactions for PETR4 in the last 90 days."

#### 💡 Example Usage

```python
# Fetch latest financial statements
cvm(action="fetch", subdomain="dfp_itr", company="PETROBRAS", year=2024)

# Analyze dividend sustainability
cvm(action="analyze", subdomain="dividends", 
    ticker="PETR4", metric="payout_ratio", period="5y")

# Track insider trading
cvm(action="query", subdomain="shareholders", 
    query="SELECT * FROM insider_trades WHERE ticker='VALE3' AND date > '2024-01-01'")
```

---

## 🔄 Skill Integration with Workflows

Skills are automatically discovered and can be invoked by workflows:

- **Research Workflow**: May call `b3(action="query")` to gather market data before synthesizing a report.
- **Data Workflow**: Can use `cvm(action="analyze")` to perform financial analysis on datasets.
- **Autocode Workflow**: May reference skill documentation when generating code that interacts with Brazilian market APIs.

### Data Lake Structure

All skills store persistent data in `WORKSPACE_ROOT/data/`:

```
workspace/data/
├── b3/
│   ├── dividends_2024.csv
│   ├── trading_volumes_2024.csv
│   └── corporate_actions.csv
└── cvm/
    ├── dfp_petrobras_2024.zip
    ├── itr_vale_2024_q3.csv
    └── shareholders_insider_trades.csv
```

This structure allows:
- **Offline analysis**: Query historical data without re-downloading.
- **Incremental updates**: Only fetch new data since last sync.
- **Cross-session persistence**: Data survives agent restarts.

---

## 🐛 Troubleshooting & Common Patterns

### Rate Limiting Issues

**Problem**: CVM or B3 endpoints return 429 (Too Many Requests).

**Solution**: Skills implement automatic backoff. If you see rate limit errors in logs:
- Increase delay between requests in the subdomain config.
- Use `sync` mode during off-peak hours (late night/weekends).
- Check if your IP is temporarily banned (wait 24h).

### Data Freshness

**Problem**: Query returns stale data.

**Solution**: Run `b3(action="status")` or `cvm(action="status")` to check last sync date. If outdated, trigger a manual sync:
```python
b3(action="sync", force=True)  # Force re-download even if recent
```

### Missing Subdomain

**Problem**: LLM tries to call a subdomain that doesn't exist.

**Solution**: Check the Hub's routing logic. The Hub should return a clear error listing valid subdomains:
```python
return {
    "status": "error", 
    "error": f"Unknown subdomain '{subdomain}'. Valid: dividends, api, cvm"
}
```

---

## 📊 Current Skills (v1.0 — implemented)

The skills layer is now live. Skills are analytical views that combine multiple
data sources with domain reasoning. They are read-only (no sync) and sit on top
of `data_sources/`.

### Entry point

```
skill(domain, sub_domain, mode, params)  # @tool in skills/dispatcher.py
```

Identical pattern to `data_source()` — JSON params string, auto-discovery.

### CVM Skills

| Sub-domain | Modes | Data Sources |
|------------|-------|--------------|
| `shareholders` | shareholders, free_float, equity_structure, summary | FRE (posicao_acionaria, distribuicao_capital) + DFP (BPP 2.03.*) |
| `dividends` | history, annual, payable, announcements, summary | B3 dividends + DFP (DVA 7.08.04.*, BPP 2.01.05.02.*) + IPE |

See [docs/skills/cvm/SKILLS.md](skills/cvm/SKILLS.md) for details.

### Architecture

```
LLM → skill(domain, sub_domain, mode, params)  [skills/dispatcher.py @tool]
       └→ skills/<domain>/__init__.py route()
          └→ skills/<domain>/<skill>/__init__.py route(mode)
             └→ skills/<domain>/<skill>/<skill>.py  (calls data_source query engines)
                └→ data_sources/...
```

Skills call data_source query engines directly (no JSON round-trip). The bridge
auto-syncs on first ticker query (`resolve_company(auto_sync=True)`).

---

## 🚀 Future Skill Domains (Planned)

- **`ibge`**: Brazilian Institute of Geography and Statistics (macroeconomic indicators, census data).
- **`bacen`**: Central Bank of Brazil (interest rates, exchange rates, monetary policy).
- **`receita_federal`**: Brazilian IRS (tax regulations, corporate tax filings).
- **`ans`**: National Agency of Supplementary Health (healthcare market data).

Each new domain follows the same Hub-and-Spoke pattern, making it easy to extend the agent's domain expertise without modifying core infrastructure.