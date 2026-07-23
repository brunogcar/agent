"""
skills/news/__init__.py -- News domain manifest (standalone, no sub-domains).
"""
from __future__ import annotations
import inspect
from skills.news.news import headlines, corporate_actions

MANIFEST = {
    "domain":          "news",
    "has_sub_domains": False,
    "description":     "Brazilian financial news and corporate action notices. Sources: infomoney, valor, B3, CVM.",

    "modes": {
        "headlines": {
            "fn":             headlines,
            "description":    "Latest financial news headlines from selected source.",
            "include_in_all": False,
            "params": {
                "source": "str. 'infomoney' | 'valor' | 'b3' | 'cvm'. Default: infomoney.",
                "query":  "str. Keyword filter. Default: all news.",
                "limit":  "int. Max headlines. Default: 10.",
            },
            "examples": [
                'skill(domain="news", mode="headlines", params=\'{"source":"infomoney","query":"PETR4"}\')',
                'skill(domain="news", mode="headlines", params=\'{"source":"cvm","limit":5}\')',
            ],
        },
        "corporate_actions": {
            "fn":             corporate_actions,
            "description":    "Corporate action notices: dividends declared, splits, IPOs.",
            "include_in_all": False,
            "params": {
                "ticker": "str. Filter by ticker e.g. PETR4. Default: all.",
                "limit":  "int. Max results. Default: 20.",
            },
            "examples": [
                'skill(domain="news", mode="corporate_actions", params=\'{"ticker":"PETR4"}\')',
            ],
        },
    },
}


def route(sub_domain: str = "", mode: str = "", **kwargs) -> dict:
    """
    News is standalone -- sub_domain is ignored.
    Routes directly by mode.
    """
    if not mode:
        return {"status": "error",
                "error": f"mode is required for news. Options: {list(MANIFEST['modes'].keys())}"}
    if mode not in MANIFEST["modes"]:
        return {"status": "error",
                "error": f"Unknown mode '{mode}' for news. Available: {list(MANIFEST['modes'].keys())}"}
    fn       = MANIFEST["modes"][mode]["fn"]
    sig      = inspect.signature(fn)
    accepted = set(sig.parameters.keys())
    filtered = {k: v for k, v in kwargs.items() if k in accepted}
    try:
        return fn(**filtered)
    except Exception as e:
        return {"status": "error", "domain": "news", "mode": mode, "error": str(e)}
