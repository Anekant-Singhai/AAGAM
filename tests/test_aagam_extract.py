from aagam.extract import find_mentions, largest_amount, sections_of


def facts(text: str) -> dict[str, list]:
    out: dict[str, list] = {}
    for m in find_mentions([(1, text)]):
        out.setdefault(m.kind, []).append(m)
    return out


def values(text: str, kind: str) -> list[str]:
    return [m.value for m in facts(text).get(kind, [])]


def test_identifiers_are_checked_not_just_shaped():
    text = "CIN: L74999MH2015PLC123456. GSTIN 27AAPFU0939F1ZV and 27AAPFU0939F1ZA. PAN ABCPE1234F, PAN ABCXE1234F."
    found = facts(text)
    assert [m.value for m in found["cin"]] == ["L74999MH2015PLC123456"]
    assert [m.value for m in found["gstin"]] == ["27AAPFU0939F1ZV"]  # the second fails its check character
    pan = found["pan"]
    assert len(pan) == 1 and pan[0].shown == "XXXXXX234F" and "ABCPE1234F" not in pan[0].context
    assert pan[0].detail == "individual"


def test_a_din_is_paired_with_the_person_before_it():
    found = facts("re-appoint Mr. Dipesh Godha (DIN: 07529876) and Ms. Pooja Hemant Goyal (DIN 07813296) as directors")
    assert [(m.value, m.detail) for m in found["din"]] == [("07529876", "Dipesh Godha"), ("07813296", "Pooja Hemant Goyal")]


def test_amounts_in_crore_lakh_and_the_backtick_rupee():
    text = "up to Rs. 100 Crores, `6,000 Crores (Rupees Six Thousand Crores), Rs.1,72,500 and INR 25 lakhs"
    assert values(text, "amount") == ["1000000000", "60000000000", "172500", "2500000"]
    assert largest_amount(text) == 60_000_000_000
    assert values("up to ‘100 Crores, quoted ‘100’ items", "amount") == ["1000000000"]


def test_dates_in_the_ways_notices_write_them():
    text = "held on Monday, 30th September, 2024; dated August 13, 2024; on 31.03.2026 and 2026-10-09"
    assert values(text, "date") == ["2024-09-30", "2024-08-13", "2026-03-31", "2026-10-09"]


def test_section_lists_and_the_act_they_belong_to():
    found = facts("pursuant to Sections 139, 142 and 143 of the Companies Act, 2013 and section 10(23C) of the Income-tax Act, 1961")
    assert [m.value for m in found["section"]] == ["139", "142", "143", "10(23C)"]
    assert found["section"][0].detail == "Companies Act, 2013"
    assert found["section"][-1].detail == "Income-tax Act, 1961"
    assert sections_of("under Section 186(3) of the Companies Act, 2013 and section 10 of the Income-tax Act, 1961") == ["186", "186(3)"]


def test_firms_members_and_companies():
    text = (
        "M/s. Parin Patwari & Company, Chartered Accountants (Firm Registration No. 154571W); Ankita Mehra, M. No. A33288. "
        "To, National Stock Exchange of India Limited. For GODHA CABCON & INSULATION LIMITED"
    )
    found = facts(text)
    assert [m.value for m in found["frn"]] == ["154571W"]
    assert [m.value for m in found["membership_no"]] == ["A33288"]
    assert "Godha Cabcon & Insulation Limited" in [m.value for m in found["company"]]
