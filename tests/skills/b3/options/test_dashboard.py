"""Tests for the dashboard mode of skills/b3/options.

Simplified pattern (2 tests):
  1. test_dashboard_no_underlying — error path (empty underlying → status=error)
  2. test_dashboard_tab_structure — returns 6 tabs with correct names + groups

[v1.2] Bumped from 4 tabs → 5 tabs (+ "Volatilidade Implícita" in the Análise group).
[v1.3] Bumped from 5 tabs → 6 tabs (+ "Posições em Aberto" in the new Posições
      group). Also verifies the new tab has the expected chart + 3 tables
      (KPI summary + CALL/PUT comparison + detail) + that the Cadeia de Opções
      chain tables have the new OI/Coberta/Descoberta columns.
[v3]    Issue 3: the CALL vs PUT summary table now shows "CALL" / "PUT"
      (uppercase) instead of "Call" / "Put". The detail table in Tab 6 is
      now split into 2 collapsible tables (Posições — CALL + Posições — PUT),
      so the tab has 1 chart + 4 tables (KPI + summary + Calls detail +
      Puts detail). All tables are now sortable.
"""
from __future__ import annotations


class TestDashboardMode:
    def test_dashboard_no_underlying(self):
        """Empty underlying → status=error."""
        from skills.b3.options.modes.dashboard import dashboard
        result = dashboard(underlying="")
        assert result["status"] == "error"
        assert "underlying" in result["error"].lower()

    def test_dashboard_tab_structure(self, options_env):
        """Dashboard returns 6 tabs with correct names + groups."""
        from skills.b3.options.modes.dashboard import dashboard
        result = dashboard(underlying="PETR")
        assert result["status"] == "ok"
        assert "tabs" in result
        assert len(result["tabs"]) == 6

        names = [t["name"] for t in result["tabs"]]
        assert names == [
            "Cadeia de Opções",
            "Put/Call Ratio",
            "Volume por Strike",
            "Exercicios",
            "Volatilidade Implícita",
            "Posições em Aberto",
        ]

        groups = [t["group"] for t in result["tabs"]]
        assert groups == [
            "Opções",
            "Análise",
            "Análise",
            "Opções",
            "Análise",
            "Posições",
        ]

        # Each tab has a non-empty sections list.
        for tab in result["tabs"]:
            assert "sections" in tab
            assert isinstance(tab["sections"], list)
            assert len(tab["sections"]) >= 1

    def test_open_positions_tab_has_chart_and_tables(self, options_env):
        """[v1.3] The Posições em Aberto tab has 1 chart + 4 tables.

        [v3] The detail table was split into 2 (Posições — CALL + Posições —
        PUT), so the tab now has 1 chart + 4 tables (KPI summary + CALL/PUT
        comparison + Calls detail + Puts detail).
        """
        from skills.b3.options.modes.dashboard import dashboard
        result = dashboard(underlying="PETR")
        assert result["status"] == "ok"
        op_tab = result["tabs"][5]
        assert op_tab["name"] == "Posições em Aberto"

        chart_sections = [s for s in op_tab["sections"] if s.get("type") == "chart"]
        table_sections = [s for s in op_tab["sections"] if s.get("type") == "table"]
        assert len(chart_sections) >= 1, "expected OI-by-strike bar chart"
        assert len(table_sections) >= 4, (
            f"expected >= 4 tables (KPI + summary + Calls detail + Puts detail); "
            f"got {len(table_sections)}"
        )

        # The summary table should have CALL + PUT rows.
        summary_table = next(
            (s for s in table_sections
             if "CALL" in (s.get("title") or "") and "PUT" in (s.get("title") or "")),
            None,
        )
        assert summary_table is not None, "expected a CALL vs PUT summary table"
        assert len(summary_table["rows"]) == 2  # CALL + PUT rows
        # [v3] Issue 3: Tipo labels are uppercase ("CALL" / "PUT").
        assert summary_table["rows"][0][0] == "CALL"
        assert summary_table["rows"][1][0] == "PUT"

    def test_open_positions_detail_split_into_calls_and_puts(self, options_env):
        """[v3] Issue 2: the Tab 6 detail table is split into CALL + PUT.

        Previously a single mixed table had calls followed by puts (puts
        were "buried" after 1,256 call rows). Now there are 2 collapsible
        tables: "Posições — CALL" + "Posições — PUT" — both expanded by
        default, both sorted by Strike ASC, both sortable.
        """
        from skills.b3.options.modes.dashboard import dashboard
        result = dashboard(underlying="PETR")
        assert result["status"] == "ok"
        op_tab = result["tabs"][5]

        table_sections = [s for s in op_tab["sections"] if s.get("type") == "table"]
        # Find the 2 split detail tables by title.
        call_detail = next(
            (s for s in table_sections
             if (s.get("title") or "").startswith("Posições — CALL")),
            None,
        )
        put_detail = next(
            (s for s in table_sections
             if (s.get("title") or "").startswith("Posições — PUT")),
            None,
        )
        assert call_detail is not None, (
            "expected a 'Posições — CALL' detail table"
        )
        assert put_detail is not None, (
            "expected a 'Posições — PUT' detail table"
        )

        # Both tables should be collapsible + expanded + sortable.
        for tbl in (call_detail, put_detail):
            assert tbl.get("collapsible") is True
            assert tbl.get("collapsible_open") is True
            assert tbl.get("sortable") is True
            assert tbl.get("default_sort") == {"column": 2, "direction": "asc"}

        # Both tables should have at least 1 row (the conftest has 4 calls +
        # 4 puts, with 1 zero-position call filtered out → 3 calls + 4 puts).
        assert len(call_detail["rows"]) >= 1, "CALL detail table is empty"
        assert len(put_detail["rows"]) >= 1, "PUT detail table is empty"

        # Every row in the CALL table should have Tipo == "Call" (title case
        # in the Tipo column — Issue 3 only changed the summary table).
        for row in call_detail["rows"]:
            assert row[1] == "Call", (
                f"CALL detail row has wrong Tipo: {row[1]!r} (expected 'Call')"
            )
        for row in put_detail["rows"]:
            assert row[1] == "Put", (
                f"PUT detail row has wrong Tipo: {row[1]!r} (expected 'Put')"
            )

    def test_all_tables_are_sortable(self, options_env):
        """[v3] Issue 1: every table in every tab should be sortable."""
        from skills.b3.options.modes.dashboard import dashboard
        result = dashboard(underlying="PETR")
        assert result["status"] == "ok"

        non_sortable = []
        for tab in result["tabs"]:
            for sec in tab["sections"]:
                if sec.get("type") == "table":
                    if not sec.get("sortable"):
                        non_sortable.append(
                            f"{tab['name']}/{sec.get('title', '?')}"
                        )
        assert not non_sortable, (
            f"these tables are NOT sortable: {non_sortable}"
        )

    def test_chain_tab_has_oi_columns(self, options_env):
        """[v1.3] The Cadeia de Opções chain tables have OI/Coberta/Descoberta columns."""
        from skills.b3.options.modes.dashboard import dashboard
        result = dashboard(underlying="PETR")
        assert result["status"] == "ok"
        chain_tab = result["tabs"][0]
        assert chain_tab["name"] == "Cadeia de Opções"

        # Find the Calls + Puts chain tables (collapsible).
        chain_tables = [
            s for s in chain_tab["sections"]
            if s.get("type") == "table" and "Calls" in (s.get("title") or "")
                or s.get("type") == "table" and "Puts" in (s.get("title") or "")
        ]
        assert len(chain_tables) >= 2, (
            f"expected >= 2 chain tables (Calls + Puts); got {len(chain_tables)}"
        )
        for tbl in chain_tables:
            assert "OI" in tbl["columns"], (
                f"chain table missing 'OI' column: {tbl['columns']}"
            )
            assert "Coberta" in tbl["columns"], (
                f"chain table missing 'Coberta' column: {tbl['columns']}"
            )
            assert "Descoberta" in tbl["columns"], (
                f"chain table missing 'Descoberta' column: {tbl['columns']}"
            )
            # Each row should have 10 cells (Papel | Exercício | Vencimento |
            # Último | Volume | Bid | Ask | OI | Coberta | Descoberta).
            for row in tbl["rows"]:
                assert len(row) == 10, (
                    f"chain row should have 10 cells; got {len(row)}: {row}"
                )
