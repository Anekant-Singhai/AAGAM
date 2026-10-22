import pytest

from csdesk.browser.guard import check_click, check_url
from csdesk.browser.session import DEMO_FORM, check_allowed
from csdesk.errors import Blocked


@pytest.mark.parametrize(
    "name",
    ["Submit", "SUBMIT FORM", "Final Submission", "Pay Now", "Proceed to Pay", "Affix DSC", "Sign",
     "Upload DSC affixed PDF", "Generate Challan", "e-Sign"],
)
def test_submit_sign_and_pay_are_hers(name):
    with pytest.raises(Blocked, match="hers to press"):
        check_click(name)


@pytest.mark.parametrize("name", ["Save", "Save as draft", "Next", "Previous", "Add row", "Pre-fill", "Upload"])
def test_harmless_buttons_are_allowed(name):
    check_click(name)


def test_buttons_not_on_the_list_are_not_pressed():
    with pytest.raises(Blocked, match="isn't on the list"):
        check_click("Proceed")


def test_a_submit_hiding_behind_a_harmless_label_is_caught():
    with pytest.raises(Blocked):
        check_click("Save", "submit")  # e.g. text "Save" but value or aria-label "submit"


def test_a_control_without_a_name_is_not_pressed():
    with pytest.raises(Blocked, match="can't read"):
        check_click("", None)


def test_payment_pages_are_not_opened():
    check_url("https://www.mca.gov.in/content/mca/global/en/mca/master-data/display-page.html")
    with pytest.raises(Blocked):
        check_url("https://www.mca.gov.in/mcafoportal/payment/challan.do")


@pytest.mark.parametrize(
    "url",
    ["https://www.mca.gov.in/content/mca/global/en/home.html", "https://services.gst.gov.in/services/searchtp", DEMO_FORM.as_uri()],
)
def test_allowed_sites(url):
    check_allowed(url)


@pytest.mark.parametrize(
    "url",
    ["http://www.mca.gov.in/", "https://example.com/mca.gov.in", "https://mca.gov.in.example.com/", "file:///C:/Windows/win.ini"],
)
def test_other_sites_are_not_opened(url):
    with pytest.raises(Blocked):
        check_allowed(url)
