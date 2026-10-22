import pytest
from helpers import valid_aadhaar

from csdesk import validators as v
from csdesk.errors import Invalid


def test_cin_tells_class_listing_and_year():
    info = v.parse_cin("u74999mh2015ptc123456")
    assert info["company_class"] == "private"
    assert info["listed"] is False
    assert (info["nic_code"], info["state_code"], info["year"]) == ("74999", "MH", 2015)


def test_cin_with_a_missing_digit_is_rejected():
    with pytest.raises(Invalid, match="21 characters"):
        v.cin("U74999MH2015PTC12345")


def test_llpin_is_accepted_where_a_cin_is():
    assert v.cin_or_llpin("aab-1234") == "AAB-1234"
    assert v.is_llpin("AAB-1234")


def test_pan_holder_letter():
    assert v.pan_holder("abcpe1234f") == "individual"
    assert v.pan_holder("AABCE1234F") == "company"
    with pytest.raises(Invalid):
        v.pan("ABCXE1234F")  # X is not a holder type


def test_din_typed_as_a_number_keeps_its_leading_zero():
    assert v.din(1234567) == "01234567"
    with pytest.raises(Invalid):
        v.din("1234567")


def test_aadhaar_check_digit_catches_a_misread_digit():
    good = valid_aadhaar()
    assert v.aadhaar(good[:4] + " " + good[4:8] + " " + good[8:]) == good
    with pytest.raises(Invalid):
        v.aadhaar(good[:-1] + str((int(good[-1]) + 1) % 10))


def test_gstin_check_character():
    assert v.gstin("27aapfu0939f1zv") == "27AAPFU0939F1ZV"
    with pytest.raises(Invalid, match="check character"):
        v.gstin("27AAPFU0939F1ZA")


@pytest.mark.parametrize("text", ["2026-09-26", "26/09/2026", "26-09-2026", "26.09.2026", "26th September 2026", "September 26, 2026"])
def test_dates_in_the_usual_indian_styles(text):
    assert v.iso_date(text) == "2026-09-26"


def test_unreadable_date():
    with pytest.raises(Invalid):
        v.iso_date("end of September")


def test_rupees():
    assert v.rupees("Rs. 1,00,000/-") == 100000
    assert v.rupees("₹ 2,50,00,000") == 25000000
    with pytest.raises(Invalid, match="paise"):
        v.rupees("12.50")


def test_financial_year():
    assert v.fin_year("2025-2026") == "2025-26"
    assert v.fin_year("2025-26") == "2025-26"
    with pytest.raises(Invalid):
        v.fin_year("2025-27")


def test_mobile_drops_country_code():
    assert v.mobile("+91 98765 43210") == "9876543210"
