import pytest
from helpers import ACME, BALANCE_SHEET_ROWS, PROFIT_LOSS_ROWS, USER, write_financials_pdf, write_financials_xlsx

from aagam import finance, library
from aagam.db import open_db
from aagam.finance.applicability import assess
from aagam.finance.ratios import derived
from aagam.finance.statements import figures, read_statements, unit_of

LAKH = 100_000


@pytest.fixture
def db(settings):
    with open_db(settings.db_path, actor="test") as vault:
        yield vault


def statement():
    return read_statements([(1, "\n".join(BALANCE_SHEET_ROWS)), (2, "\n".join(PROFIT_LOSS_ROWS))])[0]


def test_figures_skip_the_note_and_read_brackets_as_negative():
    assert figures(" 3 1,250.00 1,100.00") == [1250.0, 1100.0]
    assert figures(" 21 (40.00) (20.00)") == [-40.0, -20.0]
    assert figures(" (III - IV) 260.00 200.00") == [260.0, 200.0]
    assert figures(" 1,520.00 1,330.00") == [1520.0, 1330.0]
    assert figures(" - 25.00") == [0.0, 25.0]
    assert unit_of("(Rs. in lakhs)") == ("Rs. in lakhs", LAKH)
    assert unit_of("All amounts in ₹ crore unless stated")[1] == 10_000_000
    assert unit_of("Amount in INR thousands")[1] == 1_000


def test_the_statements_are_read_line_by_line_by_section():
    st = statement()
    assert (st.basis, st.period_end, st.prior_period_end, st.unit_factor) == ("standalone", "2026-03-31", "2025-03-31", LAKH)
    v = lambda key, col="current": st.value(key, col)  # noqa: E731
    assert v("long_term_borrowings") == 400 * LAKH and v("short_term_borrowings") == 250 * LAKH  # same caption, two sections
    assert v("long_term_provisions") == 30 * LAKH and v("short_term_provisions") == 40 * LAKH
    assert v("non_current_investments") == 300 * LAKH and "current_investments" not in st.items
    assert v("msme_dues") == 45 * LAKH and v("other_payables") == 395 * LAKH
    assert v("other_current_liabilities", "previous") == 90 * LAKH
    assert v("inventory_change") == -40 * LAKH
    assert v("profit_before_tax") == 260 * LAKH and v("profit_after_tax") == 192 * LAKH
    assert v("eps_basic") == 4  # rupees per share, not scaled (3.84 rounds in whole rupees)
    assert st.items["ppe"]["page"] == 1 and st.items["revenue"]["page"] == 2


def test_the_eleven_ratios_and_what_needs_explaining(db, settings, tmp_path):
    info = library.add_document(db, settings, write_financials_pdf(tmp_path / "Acme FS 2025-26.pdf"), queue_ai=False)
    doc = library.document(db, info["document_id"])
    assert doc["doc_type"] == "financial_statements" and "financials" in {t["name"] for t in doc["tags"]}
    result = finance.analysis(db, doc["financials"][0]["id"])
    r = {x["key"]: x for x in result["ratios"]}
    assert r["current_ratio"]["current"] == 1.35 and r["current_ratio"]["previous"] == 1.68
    assert r["debt_equity"]["current"] == 0.43
    assert r["roe"]["current"] == 13.47  # 192 / average(1,520, 1,330)
    assert r["inventory_turnover"]["current"] == 9.15  # (3,700 - 40) / average(420, 380)
    assert r["receivables_turnover"]["current"] == 10.97
    assert r["payables_turnover"]["current"] == 9.74  # 3,700 / average(440, 320)
    assert r["net_capital_turnover"]["current"] == 20.13 and r["net_capital_turnover"]["explain"]  # up 60%: explain in the notes
    assert r["net_profit_ratio"]["current"] == 3.1
    assert r["roce"]["current"] == 15.44  # (260 + 75) / (1,520 + 650)
    assert r["dscr"]["current"] is None and "principal" in r["dscr"]["missing"]
    parts = {p["name"]: p for p in result["liabilities"]["parts"]}
    assert parts["Equity"]["share"] == 53.9 and parts["Borrowings and leases"]["amount"] == 650 * LAKH
    assert any("micro and small" in c["text"] for c in result["checks"])


def test_what_applies_and_the_work_it_means(db, settings, tmp_path):
    company_id = db.save("company", ACME, USER)  # a private company
    info = library.add_document(db, settings, write_financials_pdf(tmp_path / "fs.pdf"), company_id=company_id, queue_ai=False)
    fid = library.document(db, info["document_id"])["financials"][0]["id"]
    applies = {a["key"]: a for a in finance.analysis(db, fid)["applicability"]}
    assert applies["small_company"]["status"] == "check" and "holding or subsidiary" in applies["small_company"]["missing"]
    assert applies["csr"]["status"] == "no"  # net profit ₹2.6 crore is under ₹5 crore
    assert applies["xbrl"]["status"] == "yes"  # paid-up ₹5 crore
    assert applies["whole_time_cs"]["status"] == "no"
    assert applies["tax_audit"]["status"] == "yes" and "s.63" in applies["tax_audit"]["basis"]
    assert applies["msme_1"]["status"] == "check" and applies["dpt_3"]["status"] == "yes"
    assert applies["internal_audit"]["status"] == "no"
    settled = {a["key"]: a for a in finance.set_facts(db, fid, {"holding_or_subsidiary": False})["applicability"]}
    assert settled["small_company"]["status"] == "yes" and "MGT-7A" in settled["small_company"]["work"]


def test_thresholds_at_the_edges():
    crore = 10_000_000
    big = {"share_capital": 12 * crore, "revenue": 1200 * crore, "pbt": 60 * crore, "equity": 300 * crore, "borrowings": 150 * crore,
           "msme_dues": None}
    applies = {a["key"]: a for a in assess({"company_class": "public"}, big, {"bank_borrowings": 150 * crore})}
    assert applies["csr"]["status"] == "yes" and "turnover" in applies["csr"]["why"]
    assert applies["secretarial_audit"]["status"] == "yes"  # turnover over ₹250 crore
    assert applies["whole_time_cs"]["status"] == "yes" and applies["independent_directors"]["status"] == "yes"
    assert applies["woman_director"]["status"] == "yes" and applies["internal_audit"]["status"] == "yes"
    small_limit = {"share_capital": 10 * crore, "revenue": 100 * crore, "pbt": 1 * crore, "equity": 15 * crore, "borrowings": 0}
    assert {a["key"]: a for a in assess({"company_class": "private"}, small_limit, {"holding_or_subsidiary": False})}["small_company"]["status"] == "yes"


def test_her_corrections_survive_reading_again(db, settings, tmp_path):
    info = library.add_document(db, settings, write_financials_pdf(tmp_path / "fs.pdf"), queue_ai=False)
    fid = library.document(db, info["document_id"])["financials"][0]["id"]
    finance.correct(db, fid, "trade_receivables", 600 * LAKH, 520 * LAKH)
    library.index_document(db, info["document_id"], keep_type=True)
    items = finance.get(db, fid)["items"]
    assert items["trade_receivables"]["current"] == 600 * LAKH and items["trade_receivables"]["by"] == "her"
    assert items["inventories"]["by"] == "auto"
    inputs = finance.s186_inputs(db, fid)
    assert inputs["paid_up_capital"] == 500 * LAKH and inputs["free_reserves"] == 1020 * LAKH


def test_a_spreadsheet_from_the_accountant_reads_the_same(db, settings, tmp_path):
    info = library.add_document(db, settings, write_financials_xlsx(tmp_path / "FS FY26.xlsx"), doc_type="financial_statements", queue_ai=False)
    fid = library.document(db, info["document_id"])["financials"][0]["id"]
    now = derived(finance.get(db, fid)["items"], "current")
    assert now["revenue"] == 6200 * LAKH and now["equity"] == 1520 * LAKH and now["trade_payables"] == 440 * LAKH
