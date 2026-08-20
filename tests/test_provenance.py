from grow_trade_assistant.domain.provenance import ClaimType, DataProvenance, build_report_provenance


def test_claim_type_values():
    assert ClaimType.REPORTED.value == "reported"
    assert ClaimType.LLM_INTERPRETATION.value == "llm_interpretation"


def test_data_provenance_to_dict():
    p = DataProvenance(
        field="test.field",
        claim_type=ClaimType.CALCULATED,
        source="unit_test",
        source_url="https://example.com",
    )
    d = p.to_dict()
    assert d["claim_type"] == "calculated"
    assert d["source_url"] == "https://example.com"


def test_build_report_provenance_has_disclaimer():
    prov = build_report_provenance(
        generated_at="2026-08-20T00:00:00+05:30",
        benchmark_symbol="NIFTY",
        has_groww=True,
        has_yahoo=True,
        has_mf=False,
        has_news=False,
    )
    assert "disclaimer" in prov
    assert "guarantee" in prov["disclaimer"].lower()
    fields = {r["field"] for r in prov["records"]}
    assert "portfolio.holdings" in fields
    assert "recommendations" in fields
