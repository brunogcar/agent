"""Tests for the dashboard mode of skills/b3/term.

Simplified pattern (3 tests):
  1. test_dashboard_no_ticker — error path (empty ticker → status=error)
  2. test_dashboard_tab_structure — returns 3 tabs with correct names + groups
  3. test_dashboard_shows_forward_fallback — when COTAHIST has no term data
     but b3.api derivatives.db has an EQUITY FORWARD position, the dashboard
     shows the forward snapshot table (not just "Sem dados").
"""
from __future__ import annotations


class TestDashboardMode:
    def test_dashboard_no_ticker(self):
        """Empty ticker → status=error."""
        from skills.b3.term.modes.dashboard import dashboard
        result = dashboard(ticker="")
        assert result["status"] == "error"

    def test_dashboard_tab_structure(self):
        """Dashboard returns 3 tabs with correct names + groups.

        Uses graceful degradation — if no DB, tabs get error sections.
        """
        from skills.b3.term.modes.dashboard import dashboard
        result = dashboard(ticker="PETR4")
        assert result["status"] == "ok"
        assert "tabs" in result
        assert len(result["tabs"]) == 3

        # Just check tabs have names + sections (no hardcoded names).
        for tab in result["tabs"]:
            assert "name" in tab
            assert "sections" in tab
            assert isinstance(tab["sections"], list)
            assert len(tab["sections"]) >= 1

        for tab in result["tabs"]:
            assert "sections" in tab
            assert isinstance(tab["sections"], list)
            assert len(tab["sections"]) >= 1

    def test_dashboard_shows_forward_fallback(self, monkeypatch):
        """When COTAHIST has no term data + b3.api has a forward position,
        the dashboard shows the forward snapshot table (not 'Sem dados').

        Mocks:
          - term_chain → not_found (simulates stock: BDI 26 = 0 rows)
          - term_history → not_found
          - _spot_query → 3 synthetic spot closes
          - _forward_positions → ok with PETR4T forward snapshot
        """
        from skills.b3.term.modes import dashboard as dash_mod

        # Mock COTAHIST term queries → not_found (the stock case).
        def mock_term_chain(ticker="", **kw):
            return {"status": "not_found", "ticker": ticker,
                    "error": "no term contracts (stock routed to BTC)"}

        def mock_term_history(ticker="", days=90, **kw):
            return {"status": "not_found", "ticker": ticker,
                    "error": "no term history (stock routed to BTC)"}

        # Mock spot query → 3 synthetic closes (last is 41.79).
        def mock_spot_query(ticker="", **kw):
            return {
                "status": "ok",
                "rows": [
                    {"refdate": "2026-08-19", "close": 41.50},
                    {"refdate": "2026-08-20", "close": 41.65},
                    {"refdate": "2026-08-21", "close": 41.79},
                ],
            }

        # Mock forward_positions → ok with the canonical PETR4T snapshot.
        def mock_forward_positions(ticker="", **kw):
            return {
                "status": "ok",
                "ticker": "PETR4T",
                "underlying": "PETR4",
                "refdate": "2026-08-21",
                "company": "PETROLEO BRASILEIRO S.A. PETROBRAS",
                "isin": "BRPETRTNP008",
                "security_category": "COMMON EQUITIES FORWARD",
                "specification": "PN      N2",
                "open_interest": 1196,
                "total_quantity": 1_358_721,
                "forward_price_aggregate": 58_828_062.67,
                "forward_price_per_share": 43.32,
                "instruments_ok": True,
            }

        monkeypatch.setattr(dash_mod, "term_chain", mock_term_chain)
        monkeypatch.setattr(dash_mod, "term_history", mock_term_history)
        monkeypatch.setattr(dash_mod, "_spot_query", mock_spot_query)
        monkeypatch.setattr(dash_mod, "_forward_positions", mock_forward_positions)

        result = dash_mod.dashboard(ticker="PETR4")
        assert result["status"] == "ok"
        assert len(result["tabs"]) == 3

        # ── Tab 1 (Contratos Ativos): forward snapshot KPI table ───────
        tab1 = result["tabs"][0]
        tab1_titles = [s.get("title", "") for s in tab1["sections"]]
        # The forward snapshot table title contains "Snapshot Forward".
        assert any("Snapshot Forward" in t for t in tab1_titles), (
            f"Tab 1 should have a 'Snapshot Forward' section; got: {tab1_titles}"
        )
        # Spot price snapshot table is still present.
        assert any("Preco Spot Recente" in t for t in tab1_titles), (
            f"Tab 1 should still have the spot price snapshot; got: {tab1_titles}"
        )
        # Forward-vs-spot spread row is present (since spot_close=41.79 + fwd=43.32).
        assert any("Spread Forward vs Spot" in t for t in tab1_titles), (
            f"Tab 1 should have a 'Spread Forward vs Spot' section; got: {tab1_titles}"
        )
        # Find the forward snapshot table and verify the company name row.
        fwd_section = next(
            s for s in tab1["sections"] if "Snapshot Forward" in s.get("title", "")
        )
        fwd_rows = fwd_section.get("rows", [])
        # Row format: [Campo, Valor]. Find the Empresa row.
        empresa_vals = [r[1] for r in fwd_rows if r[0] == "Empresa"]
        assert empresa_vals, f"Empresa row not found in forward snapshot: {fwd_rows}"
        assert "PETROLEO BRASILEIRO" in empresa_vals[0]
        # Find the Contrato row.
        contrato_vals = [r[1] for r in fwd_rows if r[0] == "Contrato"]
        assert contrato_vals == ["PETR4T"]
        # Find the Preco Forward row — should be R$ 43,32 (PT-BR format).
        preco_vals = [r[1] for r in fwd_rows if r[0] == "Preco Forward (poracao)"]
        assert preco_vals == ["R$ 43,32"], f"Expected R$ 43,32, got {preco_vals}"

        # ── Tab 2 (Spread Termo vs Spot): forward-vs-spot comparison table ─
        tab2 = result["tabs"][1]
        tab2_titles = [s.get("title", "") for s in tab2["sections"]]
        assert any("Forward vs Spot" in t for t in tab2_titles), (
            f"Tab 2 should have a 'Forward vs Spot' section; got: {tab2_titles}"
        )
        # Spot price chart is still present (90-day reference).
        assert any("Preco Spot" in t for t in tab2_titles), (
            f"Tab 2 should still have the spot price chart; got: {tab2_titles}"
        )

        # ── Tab 3 (Volume Historico): open position details table ───────
        tab3 = result["tabs"][2]
        tab3_titles = [s.get("title", "") for s in tab3["sections"]]
        assert any("Posicao em Aberto" in t for t in tab3_titles), (
            f"Tab 3 should have a 'Posicao em Aberto' section; got: {tab3_titles}"
        )
        # Find the open position table and verify the OI + total quantity.
        pos_section = next(
            s for s in tab3["sections"] if "Posicao em Aberto" in s.get("title", "")
        )
        pos_rows = pos_section.get("rows", [])
        # Row format: [Data, Contrato, OI, Qtde, Valor, Preco/acao]
        assert len(pos_rows) == 1
        row = pos_rows[0]
        assert row[1] == "PETR4T"  # Contrato
        # OI formatted as PT-BR int: "1.196"
        assert "1.196" in str(row[2]), f"Expected OI '1.196', got {row[2]}"
        # Qtde formatted as PT-BR int: "1.358.721"
        assert "1.358.721" in str(row[3]), f"Expected Qtde '1.358.721', got {row[3]}"

    def test_dashboard_forward_fallback_no_forward_data(self, monkeypatch):
        """When both COTAHIST + b3.api forward fail, show the legacy fallback.

        Mocks term_chain → not_found, _forward_positions → not_synced.
        Verifies the dashboard still returns 3 tabs with the legacy
        'Sem dados' info text (graceful degradation).
        """
        from skills.b3.term.modes import dashboard as dash_mod

        def mock_term_chain(ticker="", **kw):
            return {"status": "not_found", "ticker": ticker, "error": "no term"}

        def mock_term_history(ticker="", days=90, **kw):
            return {"status": "not_found", "ticker": ticker, "error": "no term"}

        def mock_spot_query(ticker="", **kw):
            return {"status": "ok", "rows": [
                {"refdate": "2026-08-21", "close": 41.79}]}

        def mock_forward_positions(ticker="", **kw):
            return {"status": "not_synced", "error": "derivatives.db missing"}

        monkeypatch.setattr(dash_mod, "term_chain", mock_term_chain)
        monkeypatch.setattr(dash_mod, "term_history", mock_term_history)
        monkeypatch.setattr(dash_mod, "_spot_query", mock_spot_query)
        monkeypatch.setattr(dash_mod, "_forward_positions", mock_forward_positions)

        result = dash_mod.dashboard(ticker="PETR4")
        assert result["status"] == "ok"
        assert len(result["tabs"]) == 3

        # Tab 1 should have the "Sem dados" text section (forward not synced).
        tab1 = result["tabs"][0]
        tab1_titles = [s.get("title", "") for s in tab1["sections"]]
        assert any("Sem dados" in t for t in tab1_titles), (
            f"Tab 1 should fall back to 'Sem dados' text; got: {tab1_titles}"
        )
        # Should NOT have a "Snapshot Forward" section.
        assert not any("Snapshot Forward" in t for t in tab1_titles), (
            f"Tab 1 should NOT have a forward snapshot (forward not synced); "
            f"got: {tab1_titles}"
        )
