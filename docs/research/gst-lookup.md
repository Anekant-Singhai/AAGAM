# GST number lookup

Last updated: 2026-10-09

Question this note answers: can you get a firm's GST number from its name, and which portals do that?

## Short answer

Yes, there is an official public lookup, but it does not take a firm name.

The government site is [gst.gov.in](https://www.gst.gov.in/). Open **Search Taxpayer**. You can search by **GSTIN** or by **PAN**. You cannot search by firm name or trade name. That name search used to exist on the portal and was later removed.

A name-only search is only available on private directory sites. Those are leads. The GSTIN they show still has to be checked on gst.gov.in.

## What a GST number is

The GST number is the **GSTIN** (Goods and Services Tax Identification Number). GSTN issues it when a business registers on gst.gov.in. It is 15 characters. Format is in Rule 10 of the CGST Rules, 2017 (with section 25 of the CGST Act).

Example: `27ABCDE1234F1Z5`

| Characters | Meaning | In the example |
|---|---|---|
| 1–2 | State or Union Territory code | `27` = Maharashtra |
| 3–12 | PAN of the business or the proprietor | `ABCDE1234F` |
| 13 | Which registration this is for that PAN in that state (`1–9`, then letters) | `1` |
| 14 | Default character, usually `Z` | `Z` |
| 15 | Check character | `5` |

Consequences that matter for a search:

- Characters 3–12 of any GSTIN **are** the PAN. From a GSTIN you can read the PAN. From a PAN you can ask the portal for every GSTIN on that PAN.
- One business often has **more than one GSTIN**: normally one per state, and sometimes more than one in the same state (another business vertical, or an SEZ unit).
- **Legal name** (the name on the PAN) and **trade name** (the name on the signboard or the invoice) can differ. A search has to match the right one.
- The same trade name can belong to unrelated firms. A name match is not proof.

A few state codes used often: `07` Delhi, `09` Uttar Pradesh, `24` Gujarat, `27` Maharashtra, `29` Karnataka, `33` Tamil Nadu, `36` Telangana, `37` Andhra Pradesh. Code `97` is Other Territory. `38` is Ladakh.

## Official portal

No login is required for the public search.

- Home: [https://www.gst.gov.in/](https://www.gst.gov.in/)
- Direct GSTIN search: [https://services.gst.gov.in/services/searchtp](https://services.gst.gov.in/services/searchtp)
- Official manual (GSTIN/UIN search): [Search Taxpayer manual](https://tutorial.gst.gov.in/userguide/taxpayersdashboard/Search_Taxpayer_manual.htm)
- Official FAQ: [Search Taxpayer FAQ](https://tutorial.gst.gov.in/userguide/taxpayersdashboard/Search_Taxpayer.htm)

Menu under **Search Taxpayer**, as documented from the portal's own manual and from current guides checked on 2026-10-09:

1. **Search by GSTIN/UIN.** Needs the 15-character number. UIN is the equivalent for UN bodies, embassies, and some government offices. This is the search the official manual describes.
2. **Search by PAN.** Enter the 10-character PAN and the captcha. The result lists each GSTIN on that PAN, with state and status. Open a GSTIN for the full profile. Widely documented as a live menu item. The official manual page checked on this date describes the GSTIN/UIN search in detail and does not itself walk through the PAN screen, so the PAN path should be confirmed once in a browser.
3. **Search by Temporary ID.** For an application that does not yet have a GSTIN.
4. **Search Composition Taxpayer.** Checks composition-scheme status. This is not a name search.

### What the public GSTIN search shows

Without login:

- GSTIN / UIN
- Legal name of business
- Trade name
- Effective date of registration
- Constitution of business (proprietorship, partnership, company, and so on)
- GSTIN status (Active, Suspended, Cancelled) and cancellation date if there is one
- Taxpayer type (regular, composition, SEZ, and so on)
- Administrative office and other office (jurisdiction)
- Principal place of business
- Nature of business activities
- Goods and services dealt in (HSN / SAC)
- Return filing table (pick a financial year)

After login with your own GST account, the same taxpayer search can also show promoter, director, or proprietor names, contact details of places of business, e-way bill history, and figures such as aggregate turnover and the share of tax paid in cash. Those extra fields are not on the public page. Source: the GST portal FAQ linked above.

### What the official portal will not do

It will not take a firm name, brand, or trade name and return a GSTIN. Typing a company name into Search Taxpayer is not a supported search.

## If you only have the firm name

Use one of these, then verify on the official portal.

1. **Take the number from the business.** A tax invoice has to show the supplier's GSTIN. It is also often on quotations, letterheads, and the firm's website. This is the cleanest source.
2. **Get the PAN, then search the PAN.** For a company, [mca.gov.in](https://www.mca.gov.in/) identifies the legal entity (CIN, registered name, directors). The PAN sometimes appears in filings. For a proprietorship, the PAN is the owner's personal PAN. Search that PAN on gst.gov.in. It lists every GSTIN.
3. **Private name-search sites.** Sites such as ClearTax and Razorpay, and other GST directories, let you type a trade name and see possible GSTINs. They are not the government database. Records go stale, and common names collide. Treat any hit as a candidate only.

Verification checklist once a candidate GSTIN is in hand:

- Search that exact GSTIN on gst.gov.in.
- Status is **Active** if the firm is supposed to be charging GST now. Suspended or cancelled is a reason not to treat its invoices as a normal input-tax-credit source.
- Legal name or trade name matches the party on the invoice or contract.
- State code matches the state they claim to be registered in.
- If they operate in several states, Search by PAN is the way to see the full set, not a single GSTIN.

## How the registration system fits together

- Identity is the **PAN**. GST registration sits on top of it.
- Registration is applied for on gst.gov.in. Approval produces the GSTIN for that state.
- The business then files returns (GSTR-1 for outward supplies, GSTR-3B for the summary return, and others depending on the scheme). The filing table on Search Taxpayer shows whether those returns were filed.
- A buyer checks the supplier's GSTIN before relying on input tax credit. A wrong, cancelled, or suspended GSTIN is the usual thing this search is meant to catch.

## Sources checked on 2026-10-09

- GSTN manual: tutorial.gst.gov.in, "Search Taxpayers using GSTIN/UIN" (page dated as updated in the October 2026 crawl).
- GSTN FAQ: tutorial.gst.gov.in, "Search Taxpayers".
- Live search page: services.gst.gov.in/services/searchtp (GSTIN/UIN field).
- Secondary guides on the removed name search and the PAN menu: registerkaro.in, taxque.in, whizseed.com, cashflo.io. These agree that name search is gone and that PAN search is a separate menu item. They are not a substitute for clicking the menu.

## Not yet done

- Open gst.gov.in in a browser and confirm the live **Search Taxpayer** menu labels (GSTIN/UIN, PAN, Temporary ID, Composition).
- Run one known GSTIN through the public search and record exactly which fields come back.
- Run one known PAN through Search by PAN and record the result layout.
- Decide whether any private name-search site is worth using as a first pass, after comparing it with the official result.
