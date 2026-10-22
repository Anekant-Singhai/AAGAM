from aagam.checks import crore, inr, loans_and_borrowing

CRORE = 10_000_000


def test_indian_digit_grouping():
    assert inr(1_000_000_000) == "₹1,00,00,00,000"
    assert inr(172_500) == "₹1,72,500"
    assert inr(999) == "₹999"
    assert crore(1_000_000_000) == "₹100.00 crore"


def test_the_100_crore_question():
    # Paid-up 10 cr, free reserves 50 cr, securities premium 20 cr: limit is the higher of 48 cr and 70 cr.
    result = loans_and_borrowing(10 * CRORE, 50 * CRORE, 20 * CRORE, proposed_loans_investments=100 * CRORE)
    s186 = result["s186"]
    assert s186["limit"] == 70 * CRORE and s186["status"] == "special_resolution"
    assert "Over the limit by ₹30,00,00,000 (₹30.00 crore)" in s186["needs"]
    assert s186["steps"][3] == "Limit under s.186(2) = the higher of (a) and (b) = ₹70,00,00,000 (₹70.00 crore)"
    assert "s.186(3)" in s186["basis"]


def test_within_the_limit_counts_what_is_outstanding():
    result = loans_and_borrowing(50 * CRORE, 100 * CRORE, 0, proposed_loans_investments=20 * CRORE, outstanding_loans_investments=60 * CRORE)
    assert result["s186"]["limit"] == 100 * CRORE and result["s186"]["status"] == "board_resolution"
    assert "₹20.00 crore" in result["s186"]["needs"]


def test_wholly_owned_subsidiary_and_borrowing():
    result = loans_and_borrowing(10 * CRORE, 10 * CRORE, 0, proposed_loans_investments=50 * CRORE, to_wholly_owned_subsidiary=True,
                                 proposed_borrowing=100 * CRORE, company_class="public")
    assert result["s186"]["status"] == "check" and "wholly owned subsidiary" in result["s186"]["needs"]
    assert result["s180"]["status"] == "special_resolution" and result["s180"]["limit"] == 20 * CRORE


def test_private_company_exemptions_are_flagged_for_her_to_confirm():
    result = loans_and_borrowing(1 * CRORE, 1 * CRORE, proposed_borrowing=5 * CRORE, company_class="private", include_director_loans=True)
    assert result["s180"]["status"] == "check" and "doesn't apply to a private company" in result["s180"]["needs"]
    assert result["s185"]["status"] == "check" and "₹50 crore" in result["s185"]["notes"][-1]
