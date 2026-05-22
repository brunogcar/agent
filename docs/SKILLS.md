# 🧩 Skills Architecture & Domain Guide

Skills are domain-specific clusters of logic that extend the agent's capabilities beyond general-purpose tools. Unlike core meta-tools (which are flat and generic), skills are organized into **Domains** and **Subdomains** using a **Hub-and-Spoke architecture**.

## 🏗️ Skill Creation Guidelines

### The Hub-and-Spoke Pattern
Skills do **not** use the `@tool` decorator on every function. Instead, they rely on `skills/dispatcher.py` to auto-discover **Domain Hubs**.

1.  **The Hub (`<domain>.py`)**: A single entry-point file (e.g., `b3.py`) that acts as the MCP tool. It receives the user's intent and routes it to the correct subdomain.
2.  **The Subdomains**: Pure Python modules (e.g., `b3_api.py`) containing the actual business logic, API wrappers, and data processing. They are **not** exposed directly to the LLM.
3.  **The Dispatcher**: `skills/dispatcher.py` scans the `skills/` directory, identifies these Hubs, and registers them as top-level tools (e.g., a tool named `b3` and a tool named `cvm`).

### Step-by-Step: Adding a New Skill Domain

1.  **Create the Domain Folder**: `skills/my_domain/`
2.  **Create the Hub**: Create `skills/my_domain/my_domain.py`. This file must implement the main execution logic that `dispatcher.py` expects (typically a function that accepts `action`, `params`, etc.).
3.  **Create Subdomains**: Create modules like `skills/my_domain/api_client.py` or `skills/my_domain/analytics.py`.
4.  **Wire the Hub**: Inside `my_domain.py`, import your subdomains and route the `action` argument to them.

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
- **No Direct MCP Decorators**: Do not use `@tool` inside subdomain files. Only the Hub is registered as a tool.
- **Logging**: Use `core.tracer` for all logging. Never use `print()`.

---

## 📈 Current Skill Domains

### 1. B3 (Brasil, Bolsa, Balcão)
**Location:** `skills/b3/`
**Purpose:** Ingest, sync, and query Brazilian stock market data.

#### 🏛️ Domain Hub: `skills/b3/b3.py`
The central router for all B3-related operations. It exposes a single `b3` tool to the LLM.
- **Routing Logic**: Inspects the `action` and `subdomain` parameters to delegate tasks.
- **Data Lake Management**: Manages the local CSV cache in `WORKSPACE_ROOT/data/b3/`.
- **Modes**:
    - `sync`: Triggers background downloaders to update local datasets.
    - `query`: Executes pandas/SQL logic against local data.
    - `status`: Reports on data freshness and cache health.

#### 📂 Subdomains
- **`b3_api`**:
    - **Function**: Core data ingestion and management.
    - **Capabilities**: Handles direct HTTP interaction with B3 endpoints, manages daily CSV downloads, file parsing, and local storage synchronization.
- **`b3_cvm`**:
    - **Function**: Cross-domain bridge and reconciliation.
    - **Capabilities**: Maps B3 tickers to CVM regulatory IDs (CNPJ/CVM codes) and handles data integration logic that requires context from both the stock exchange and the securities commission.

---

### 2. CVM (Comissão de Valores Mobiliários)
**Location:** `skills/cvm/`
**Purpose:** Regulatory, financial statement, and shareholder data from the Brazilian SEC equivalent.

#### 🏛️ Domain Hub: `skills/cvm/cvm.py`
The central router for all CVM regulatory data. It exposes a single `cvm` tool to the LLM.
- **Routing Logic**: Directs requests to specific subdomains based on the data type required (e.g., financials vs. shareholders).
- **Rate Limiting**: Implements global rate limiting for CVM portal requests to avoid IP bans.
- **Integration**: Orchestrates data fetching between `cvm_api` (raw data) and analytical subdomains.

#### 📂 Subdomains
- **`cvm_api`**:
    - **Function**: Low-level HTTP wrapper for the CVM Open Data portal.
    - **Capabilities**: Handles session management, ZIP extraction, and raw CSV parsing.
- **`cvm_dividends`**:
    - **Function**: Financial analysis module.
    - **Capabilities**: Cross-references CVM financial statements (DFP/ITR) with B3 data to verify dividend declarations and payout ratios.
- **`cvm_shareholders`**:
    - **Function**: Ownership tracking.
    - **Capabilities**: Parses FRE (Reference Form) data to track institutional ownership changes and insider trading disclosures.