"""webui/services/ipe.py — Informações Periódicas e Eventuais (IPE).

[v1.26 fix 1] The company page's 12th tab — SPLIT from Governança (the
user's verdict: "both provide info, but they are not supposed to be
together, different purpose"). The split:

  - Governança (tab_governance.html, webui/services/governance.py) =
    CGVN — the Código de Melhores Práticas SELF-ASSESSMENT: how the
    company SAYS it is governed (score, 54 práticas, evolution).
  - Informações Periódicas (tab_ipe.html, THIS service) = IPE — the
    EVENT INDEX: what the company FILED with the market over the years
    (AGO/AGE, avisos aos acionistas, fatos relevantes, calendário de
    eventos corporativos…).

events() → the faceted explorer (the same payload the first v1.26
build served under /governance/events — moved, unchanged contract):
Categoria/Tipo/Espécie/Ano selects driven by data (SELECT DISTINCT per
ticker — never a hardcoded list that drifts), cascading facets, quick
chips (Assembleias · AGO · AGE · Aviso aos Acionistas · Fato Relevante ·
Calendário de Eventos), busca, server-side pagination (a PETR4 carries
~4.700 events over 2015-2026). The anos facet ships CHRONOLOGICAL,
newest first ([v1.26 fix 1] — the count-ordered select the user
reported: "ano is completely out of order").
"""
from __future__ import annotations

from typing import Any

# The quick chips (label, field, value). Curated against the real
# categoria/tipo vocabulary; rendered ONLY when the value exists in the
# ticker's facets (data-driven, no dead chips).
CHIP_PRESETS = [
    ("🏛️ Assembleias", "categoria", "Assembleia"),
    ("AGO", "tipo", "AGO"),
    ("AGE", "tipo", "AGE"),
    ("📢 Aviso aos Acionistas", "categoria", "Aviso aos Acionistas"),
    ("⚡ Fato Relevante", "categoria", "Fato Relevante"),
    ("📅 Calendário de Eventos", "categoria",
     "Calendário de Eventos Corporativos"),
]


class IpeService:
    """The Informações Periódicas tab payload (IPE events, faceted)."""

    def events(self, ticker: str, categoria: str = "", tipo: str = "",
               especie: str = "", ano: str = "", q: str = "",
               page: int = 1, per_page: int = 25) -> dict[str, Any]:
        """One faceted page of the ticker's IPE events (see
        data_sources/cvm/ipe/query_engine.browse)."""
        try:
            from data_sources.cvm.ipe import query_engine as ipe
        except Exception as e:  # pragma: no cover — import-time failure
            return self._err(ticker, f"falha ao carregar a fonte ipe: {e}")

        try:
            data = ipe.browse(company=ticker, categoria=categoria,
                              tipo=tipo, especie=especie, keyword=q,
                              ano=ano, page=page, per_page=per_page)
        except FileNotFoundError:
            return self._err(
                ticker, "Base ipe não encontrada — sincronize a fonte ipe "
                "na página Sincronização.")
        except Exception as e:
            return self._err(ticker, f"erro ao consultar ipe: {e}")

        if data.get("status") != "ok":
            msg = data.get("message") or data.get("error") or (
                "Sem eventos IPE para este ticker.")
            return self._err(ticker, msg)

        data["ticker"] = ticker.upper()
        data["chips"] = [
            {"label": label, "field": field, "value": value}
            for label, field, value in CHIP_PRESETS
        ]
        data["filters"] = {"categoria": categoria, "tipo": tipo,
                           "especie": especie, "ano": str(ano or ""),
                           "q": q}
        return data

    # ── helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _err(ticker: str, message: str) -> dict[str, Any]:
        """Canonical error shape — the client renderers show it verbatim."""
        return {"ticker": (ticker or "").upper(), "_error": message}
