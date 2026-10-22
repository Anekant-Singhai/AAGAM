"""Test fixtures that don't need outside files."""

from __future__ import annotations

import asyncio
import contextlib
import subprocess
from pathlib import Path

import pytest

from csdesk.browser import chrome
from csdesk.errors import NotFound
from csdesk.validators import verhoeff_digit
from csdesk.vault import Source

USER = Source("user", "test")
ACME = {"name": "Acme Widgets Private Limited", "cin": "U74999MH2015PTC123456", "date_of_incorporation": "2015-06-01"}


def write_pdf(path: Path, pages: list[str]) -> Path:
    """A minimal PDF with one Helvetica text block per page. An empty string makes a page with no text
    layer, which is what a scanned page looks like to the reader."""
    objects: list[bytes] = [b"", b""]  # catalog and page tree, filled in below
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    font = len(objects)
    kids = []
    for text in pages:
        ops = []
        if text:
            ops = ["BT", "/F1 11 Tf", "14 TL", "60 760 Td"]
            for line in text.split("\n"):
                escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
                ops.append(f"({escaped}) Tj T*")
            ops.append("ET")
        stream = "\n".join(ops).encode("latin-1")
        objects.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
        content = len(objects)
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 %d 0 R >> >>"
            b" /Contents %d 0 R >>" % (font, content)
        )
        kids.append(len(objects))
    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (b" ".join(b"%d 0 R" % k for k in kids), len(kids))

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    path.write_bytes(bytes(out))
    return path


NOTICE_PAGES = [
    # Page 1: a cover letter to the exchange, as listed companies file it.
    "Acme Widgets Limited\nCIN: L74999MH2015PLC123456\nTo, BSE Limited\nSub: Notice of 10th Annual General Meeting\n"
    "Dear Sir/Madam, please find enclosed the Notice of the AGM.\nFor Acme Widgets Limited",
    # Page 2: the notice. Special business is numbered from 1 again, as in many real notices.
    "Acme Widgets Limited | Notice of AGM\n"
    "NOTICE OF 10TH ANNUAL GENERAL MEETING\n"
    "NOTICE is hereby given that the 10th Annual General Meeting of the Members of Acme Widgets Limited\n"
    "will be held on Monday, 30th September, 2026 at 11.00 A.M. to transact the following businesses:\n"
    "ORDINARY BUSINESS:\n"
    "1. To receive, consider and adopt the Audited Financial Statements for the year ended 31st March, 2026.\n"
    "2. To appoint a Director in place of Mr. Asha Rao (DIN: 01234567), who retires by rotation and being\n"
    "eligible, offers herself for re-appointment.\n"
    "SPECIAL BUSINESS:\n"
    "1. Approval for giving loans or guarantees under Section 185 of the Companies Act, 2013\n"
    "To consider and if thought fit, to pass the following resolution as a Special Resolution:\n"
    "RESOLVED THAT pursuant to Section 185 of the Companies Act, 2013, consent of the members be and is\n"
    "hereby accorded to give loans to Acme Holdings Private Limited in which a director is interested,\n"
    "up to an aggregate of Rs. 25 Crores, provided the loans are utilised for its principal business activities.\n"
    "2. Approval for making investments, giving loans, guarantees and security under Section 186\n"
    "To consider and if thought fit, to pass the following resolution as a Special Resolution:\n"
    "RESOLVED THAT pursuant to Section 186(3) of the Companies Act, 2013, the consent of the members be and\n"
    "is hereby accorded to the Board to give loans, guarantees and make investments up to `100 Crores\n"
    "(Rupees One Hundred Crores only) over and above the limits under Section 186(2).",
    # Page 3: the signature, then numbered notes that must not be read as business.
    "Acme Widgets Limited | Notice of AGM\n"
    "RESOLVED FURTHER THAT the Board be and is hereby authorised to do all acts to give effect to this resolution.\n"
    "By order of the Board of Directors\nFor Acme Widgets Limited\nRavi Kumar\nCompany Secretary M. No. A12345\n"
    "NOTES:\n"
    "1. A member entitled to attend and vote is entitled to appoint a proxy.\n"
    "2. Members are requested to register their email addresses with the depository.\n"
    "3. The register of members will remain closed from 24th September, 2026.",
    # Page 4: the statement, numbering the special business from 1, as Godha Cabcon's 2024 notice does.
    "Acme Widgets Limited | Notice of AGM\n"
    "EXPLANATORY STATEMENT\n"
    "(Pursuant to Section 102 of the Companies Act, 2013)\n"
    "ITEM NO: 1\n"
    "Section 185 allows loans to entities in which directors are interested with a special resolution.\n"
    "Acme Holdings Private Limited needs working capital for its principal business activities.\n"
    "ITEM NO: 2\n"
    "The proposed loans and investments of Rs. 100 crore exceed the limit under section 186(2), which is\n"
    "sixty per cent of paid-up capital, free reserves and securities premium.\n"
    "The Board recommends the resolution for approval of the members.",
]


def write_notice_pdf(path: Path) -> Path:
    return write_pdf(path, NOTICE_PAGES)


# A Schedule III (Division II) balance sheet and P&L in lakhs. The totals add up, so ratios can be checked by hand.
BALANCE_SHEET_ROWS = [
    "Acme Widgets Private Limited",
    "Balance Sheet as at 31st March, 2026",
    "(Rs. in lakhs)",
    "Particulars Note As at 31.03.2026 As at 31.03.2025",
    "ASSETS",
    "Non-current assets",
    "(a) Property, plant and equipment 3 1,250.00 1,100.00",
    "(b) Capital work-in-progress 3 80.00 40.00",
    "(c) Investments 4 300.00 250.00",
    "(d) Deferred tax assets (net) 5 12.00 10.00",
    "Total non-current assets 1,642.00 1,400.00",
    "Current assets",
    "(a) Inventories 6 420.00 380.00",
    "(b) Trade receivables 7 610.00 520.00",
    "(c) Cash and cash equivalents 8 95.00 70.00",
    "(d) Other current assets 9 53.00 30.00",
    "Total current assets 1,178.00 1,000.00",
    "Total assets 2,820.00 2,400.00",
    "EQUITY AND LIABILITIES",
    "Equity",
    "(a) Equity share capital 10 500.00 500.00",
    "(b) Other equity 11 1,020.00 830.00",
    "Total equity 1,520.00 1,330.00",
    "Non-current liabilities",
    "(a) Borrowings 12 400.00 450.00",
    "(b) Provisions 13 30.00 25.00",
    "Total non-current liabilities 430.00 475.00",
    "Current liabilities",
    "(a) Borrowings 14 250.00 150.00",
    "(b) Trade payables 15",
    "(A) total outstanding dues of micro enterprises and small enterprises 45.00 30.00",
    "(B) total outstanding dues of creditors other than micro enterprises and small enterprises 395.00 290.00",
    "(c) Other current liabilities 16 140.00 90.00",
    "(d) Provisions 17 40.00 35.00",
    "Total current liabilities 870.00 595.00",
    "Total equity and liabilities 2,820.00 2,400.00",
]
PROFIT_LOSS_ROWS = [
    "Acme Widgets Private Limited",
    "Statement of Profit and Loss for the year ended 31st March, 2026",
    "(Rs. in lakhs)",
    "Particulars Note Year ended 31.03.2026 Year ended 31.03.2025",
    "I Revenue from operations 18 6,200.00 5,100.00",
    "II Other income 19 45.00 30.00",
    "III Total income (I + II) 6,245.00 5,130.00",
    "IV Expenses",
    "Cost of materials consumed 20 3,700.00 3,050.00",
    "Changes in inventories of finished goods 21 (40.00) (20.00)",
    "Employee benefits expense 22 820.00 700.00",
    "Finance costs 23 75.00 70.00",
    "Depreciation and amortisation expense 3 140.00 120.00",
    "Other expenses 24 1,290.00 1,010.00",
    "Total expenses (IV) 5,985.00 4,930.00",
    "V Profit before tax (III - IV) 260.00 200.00",
    "VI Tax expense",
    "(1) Current tax 70.00 55.00",
    "(2) Deferred tax (2.00) (3.00)",
    "VII Profit for the year (V - VI) 192.00 148.00",
    "Earnings per equity share",
    "(1) Basic 3.84 2.96",
]


def write_financials_pdf(path: Path) -> Path:
    return write_pdf(path, ["\n".join(BALANCE_SHEET_ROWS), "\n".join(PROFIT_LOSS_ROWS)])


def write_financials_xlsx(path: Path) -> Path:
    """The same statements as a client's accountant sends them: label, note and the two years in separate cells."""
    import re

    from openpyxl import Workbook

    book = Workbook()
    for index, (title, rows) in enumerate((("Balance Sheet", BALANCE_SHEET_ROWS), ("P&L", PROFIT_LOSS_ROWS))):
        sheet = book.active if index == 0 else book.create_sheet()
        sheet.title = title
        for row in rows:
            m = re.match(r"^(.*?)\s((?:\d{1,2}\s)?\(?[\d,]+\.\d{2}\)?)\s(\(?[\d,]+\.\d{2}\)?)$", row)
            if not m:
                sheet.append([row])
                continue
            label, first, second = m.groups()
            parts = first.split()
            note = parts[0] if len(parts) == 2 else None
            amount = parts[-1]
            number = lambda s: -float(s.strip("()").replace(",", "")) if s.startswith("(") else float(s.replace(",", ""))  # noqa: E731
            sheet.append([label, note, number(amount), number(second)])
    book.save(path)
    return path


def valid_aadhaar(first11: str = "23456789012") -> str:
    return first11 + verhoeff_digit(first11)


def browser_or_skip() -> Path:
    try:
        return chrome.find_browser("chrome")
    except NotFound:
        pytest.skip("needs Chrome or Edge")


async def close_browser(port: int) -> None:
    """Shut down a browser that was started with a debugging port, by force if a dialog keeps it from answering."""
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        try:
            browser = await playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}", timeout=5_000)
        except Exception:
            kill_browser(port)
            return
        session = await browser.new_browser_cdp_session()
        with contextlib.suppress(Exception):  # the connection drops as the browser exits
            await session.send("Browser.close")


def kill_browser(port: int) -> None:
    script = (
        "Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('chrome.exe','msedge.exe') -and "
        f"$_.CommandLine -match 'remote-debugging-port={port}' }} | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", script], check=False, capture_output=True, timeout=60)


def run(coro):
    return asyncio.run(coro)
