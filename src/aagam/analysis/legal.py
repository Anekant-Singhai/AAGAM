"""Litigation and proceedings: forum, case number, parties, sections invoked, status and amounts at stake.

A matter is found in one of two ways. Where a case number is written ("C.P. (IB) No. 45/MB/2023", "ITA No.
1234/Mum/2022", "Adjudication Order No. ROC/MUM/454/2024-25"), every mention of that number is one matter, and
the sentences that follow it (the cause title, the prayer, the operative part of an order) fill in what the
number's own sentence leaves out. Where no number is given, as in an annual report's contingent liabilities
note ("income-tax demand of ₹2.5 crore for AY 2019-20, against which an appeal is pending before the CIT(A)"),
a sentence counts as a matter only when it names a proceeding and either a forum, or a status and an amount.

What is left alone: cases cited as precedent (the law analyser keeps those), the Act's own wording ("shall be
liable to a penalty"), denials ("no proceedings are pending"), investor complaints, and words like "Hon'ble"
or "subject to the approval of the members" that sound legal but are no matter of hers to track.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from . import Doc, result
from .text import amounts, dates, key_sentences, relevance, rupees, sentences

KIND = "legal"
TITLE = "Legal matters"
COLUMNS = [
    {"key": "forum", "label": "Forum", "type": "text"},
    {"key": "case_no", "label": "Case no.", "type": "text"},
    {"key": "parties", "label": "Parties", "type": "text"},
    {"key": "nature", "label": "Nature", "type": "text"},
    {"key": "sections", "label": "Sections", "type": "list"},
    {"key": "status", "label": "Status", "type": "text"},
    {"key": "amount", "label": "Amount at stake", "type": "money"},
    {"key": "next_date", "label": "Next date", "type": "date"},
]

LEXICON = {
    "petition": 2.0, "petitioner": 2.5, "respondent": 2.5, "appellant": 2.5, "applicant": 1.0, "complainant": 2.0,
    "national company law tribunal": 3.0, "nclt": 3.0, "nclat": 3.0, "high court": 2.0, "supreme court": 2.0,
    "itat": 3.0, "cit(a)": 3.0, "cestat": 3.0, "debts recovery tribunal": 3.0, "arbitral tribunal": 3.0,
    "adjudicating officer": 3.0, "adjudication order": 3.0, "adjudication": 2.0, "show cause notice": 3.0,
    "show-cause notice": 3.0, "litigation": 3.0, "legal proceedings": 3.0, "pending before": 3.0, "sub judice": 3.0,
    "contingent liabilities": 2.5, "not acknowledged as debts": 3.0, "tax demand": 2.5, "demand notice": 2.5,
    "penalty": 1.5, "appeal": 1.5, "next date of hearing": 3.0, "hearing": 1.5, "order dated": 1.5,
    "disposed of": 2.0, "dismissed": 1.5, "learned counsel": 3.0, "oppression": 3.0, "mismanagement": 2.5,
    "corporate insolvency resolution process": 3.0, "corporate debtor": 2.5, "financial creditor": 2.0,
    "operational creditor": 2.0, "insolvency and bankruptcy code": 2.5, "winding up": 2.0, "compounding": 2.5,
    "writ petition": 3.0, "special leave petition": 3.0, "civil appeal": 3.0, "suit": 1.5, "decree": 2.0,
    "interim order": 2.5, "stay": 1.0, "quashed": 2.5, "prosecution": 2.0, "summons": 2.0, "dishonour": 2.0,
    "negotiable instruments act": 2.5, "arbitration": 1.5,
}

# Case numbers. The long names are matched in any case; the short ones only in capitals, so "ca" or "os"
# in running text is never a case.
_CASE_WORDS = (
    r"Company\s+Petition|Company\s+Appeal|Company\s+Application|Comp\.?\s*App\.?|Writ\s+Petition|Civil\s+Appeal|"
    r"Criminal\s+Appeal|Crl\.?\s*A\.?|Special\s+Leave\s+Petition|Original\s+Application|"
    r"Arbitration\s+(?:Petition|Application|Appeal|Case)|Arb\.?\s*P(?:et)?\.?|Compounding\s+Application|"
    r"Execution\s+(?:Petition|Application)|Review\s+Petition|Contempt\s+Petition|Adjudication\s+Order|"
    r"Show[\s-]+Cause\s+Notice|Consumer\s+Complaint|Complaint\s+Case|Criminal\s+Complaint|"
    r"(?:Income[\s-]?tax|Service\s+Tax|Excise|Customs|GST)\s+Appeal|(?:Commercial|Civil|Summary|Original|Money)\s+Suit|"
    r"Appeal|Petition|Complaint|Case|Suit"
)
_CASE_ABBR = (
    r"C\.\s?P\.|CP|C\.\s?A\.|CA|W\.\s?P\.|WP|S\.\s?L\.\s?P\.|SLP|O\.\s?A\.|OA|T\.\s?A\.|TA|S\.\s?C\.\s?N\.|SCN|"
    r"I\.\s?T\.\s?A\.|ITA|O\.\s?S\.|OS|C\.\s?S\.|CS|C\.\s?C\.|CC|M\.\s?A\.|MA"
)
CASE_NO = re.compile(
    rf"\b(?P<type>(?i:{_CASE_WORDS})|{_CASE_ABBR})(?P<qual>(?:\s*\(\s*[A-Za-z][A-Za-z.&\s]{{0,20}}\))*)\s*"
    rf"(?:(?i:No|Nos|Number)\s*\.?\s*[:.\-–]?\s*|[-–]\s*)"
    rf"(?P<id>[A-Za-z0-9(][A-Za-z0-9()/\-.]{{0,40}})(?P<year>\s+of\s+(?:19|20)\d{{2}})?"
)
# Short forms that also mean other things (a CA's or CS's membership number): a case only with a bench or year.
_AMBIGUOUS = {"CA", "CS", "CC", "MA", "TA", "OS"}
_TYPE_ABBR = [
    (r"(?i)company\s+petition|c\.?\s?p\.?$", "CP"), (r"(?i)company\s+appeal|comp\.?\s*app", "Comp. App."),
    (r"(?i)writ|w\.?\s?p\.?$", "WP"), (r"(?i)special\s+leave|s\.?\s?l\.?\s?p", "SLP"), (r"(?i)civil\s+appeal", "CA"),
    (r"(?i)original\s+application|o\.?\s?a\.?$", "OA"), (r"(?i)show|s\.?\s?c\.?\s?n", "SCN"),
    (r"(?i)income[\s-]?tax\s+appeal|i\.?\s?t\.?\s?a", "ITA"), (r"(?i)arb", "Arb"), (r"(?i)adjudication", "Adj"),
]

# Where a case is cited as authority rather than being one of hers.
_CITED_BEFORE = re.compile(r"(?i)(?:relied\s+(?:up)?on|reliance|in\s+the\s+case\s+of|judgments?\s+(?:of|in)|held\s+in|reported\s+(?:in|as)|"
                           r"\bcited\b|decision\s+in|followed\s+in|referred\s+to)[^.;]{0,80}$")
_CITED_AFTER = re.compile(r"^[^.;]{0,60}?(?:\(\d{4}\)\s*\d+\s*SCC|\d{4}\s+SCC|SCC\s+OnLine|\bAIR\s+\d{4}|Comp\s*Cas|\bITR\b|Taxmann|\bSCR\b)")

_CITIES = (r"Mumbai|New\s+Delhi|Delhi|Chennai|Kolkata|Ahmedabad|Hyderabad|Bengaluru|Bangalore|Chandigarh|Allahabad|Prayagraj|"
           r"Guwahati|Cuttack|Jaipur|Kochi|Amaravati|Indore|Principal|Pune|Nagpur|Lucknow|Patna|Bhopal|Gwalior|Coimbatore|"
           r"Kanpur|Shillong|Ranchi|Raipur|Jabalpur|Gujarat|Bombay|Calcutta|Madras|Karnataka|Kerala|Rajasthan")
_BENCH = re.compile(rf"(?i)\b({_CITIES})(?:\s+Bench)?\b")

# Forums, most specific first. A label with {0} takes the place or bench named next to it.
_FORUMS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)\bSupreme\s+Court(?:\s+of\s+India)?|\bApex\s+Court"), "Supreme Court"),
    (re.compile(r"(?i)\bNational\s+Company\s+Law\s+Appellate\s+Tribunal|\bNCLAT\b"), "NCLAT"),
    (re.compile(r"(?i)\bNational\s+Company\s+Law\s+Tribunal|\bNCLT\b"), "NCLT"),
    (re.compile(r"(?i)\bSecurities\s+Appellate\s+Tribunal|\bSAT\b(?=[\s,.)]*(?:Mumbai|order|appeal|in\b|vide|has|had|on\b|\.))"), "SAT"),
    (re.compile(r"(?i)\bIncome[\s-]?tax\s+Appellate\s+Tribunal|\bITAT\b"), "ITAT"),
    (re.compile(r"(?i)\bCIT\s*\(\s*A\s*\)|\bCommissioner\s+of\s+Income[\s-]?tax\s*\(\s*Appeals\s*\)|\bNFAC\b"), "CIT(A)"),
    (re.compile(r"(?i)\bAssessing\s+Officer|\bIncome[\s-]?tax\s+(?:Department|authorities)|\bDeputy\s+Commissioner\s+of\s+Income"), "Income-tax authorities"),
    (re.compile(r"(?i)\bCESTAT\b|\bCustoms,?\s+Excise\s+(?:and|&)\s+Service\s+Tax\s+Appellate\s+Tribunal"), "CESTAT"),
    (re.compile(r"(?i)\bGSTAT\b|\bGST\s+Appellate\s+Tribunal|\bGoods\s+and\s+Services\s+Tax\s+Appellate\s+Tribunal"), "GST Appellate Tribunal"),
    (re.compile(r"(?i)\b(?:GST|CGST|SGST)\s+(?:authorities|department|officer|commissionerate)|\bCommissioner\s+(?:of\s+)?(?:CGST|SGST|Central\s+Tax|State\s+Tax|GST)|"
                r"\bSuperintendent\s+(?:of\s+)?(?:CGST|Central\s+Tax)|\bDirectorate\s+General\s+of\s+GST\s+Intelligence|\bDGGI\b|\bProper\s+Officer"), "GST authorities"),
    (re.compile(r"(?i)\bDebts?\s+Recovery\s+Appellate\s+Tribunal|\bDRAT\b"), "DRAT"),
    (re.compile(r"(?i)\bDebts?\s+Recovery\s+Tribunal|\bDRT\b"), "DRT"),
    (re.compile(r"(?i)\b(?:National|State|District)\s+Consumer\s+Disputes\s+Redressal\s+Commission|\bConsumer\s+(?:Disputes\s+Redressal\s+)?(?:Commission|Forum)|\bNCDRC\b"), "Consumer Commission"),
    (re.compile(r"(?i)\bArbitral\s+Tribunal|\bsole\s+arbitrator|\blearned\s+arbitrator"), "Arbitral Tribunal"),
    (re.compile(r"(?i)\bCompetition\s+Commission\s+of\s+India"), "Competition Commission"),
    (re.compile(r"(?i)\bRegional\s+Director"), "Regional Director"),
    (re.compile(r"(?i)\bRegistrar\s+of\s+Companies|\bRoC\b|\bROC\b"), "ROC"),
    (re.compile(r"(?i)\bOfficial\s+Liquidator"), "Official Liquidator"),
    (re.compile(r"\bSecurities\s+and\s+Exchange\s+Board\s+of\s+India\b(?!\s*\(|\s+Act)|\bSEBI\b(?!\s*\(|\s+(?:Listing|LODR|ICDR|SAST|PIT|Regulations|Act|Circular|SCORES))|"
                r"(?i:\bWhole[\s-]+Time\s+Member)"), "SEBI"),
    (re.compile(r"(?i)\bAdjudicating\s+Officer"), "Adjudicating Officer"),
    (re.compile(r"(?i)\bEnforcement\s+Directorate|\bDirectorate\s+of\s+Enforcement"), "Enforcement Directorate"),
    (re.compile(r"(?i)\b(?:Chief\s+)?(?:Metropolitan|Judicial)\s+Magistrate|\bSessions\s+Court|\bCourt\s+of\s+Session|\bSpecial\s+Court"), "Criminal court"),
    (re.compile(r"(?i)\b(?:City\s+)?Civil\s+Court|\bCourt\s+of\s+(?:the\s+)?Civil\s+Judge|\bDistrict\s+Court|\bCommercial\s+Court|\bSmall\s+Causes\s+Court"), "Civil court"),
    (re.compile(r"(?i)\bLabour\s+Court|\bIndustrial\s+Tribunal"), "Labour court"),
]
_HIGH_COURT = re.compile(r"(?i)\bHigh\s+Court\b(?:\s+of\s+(?:Judicature\s+(?:at|of|for)\s+)?|\s+at\s+)?([A-Za-z]+(?:\s+(?:and|&)\s+[A-Za-z]+)?)?")
_HIGH_COURT_BEFORE = re.compile(r"\b([A-Z][a-z]+)\s+High\s+Court\b")
_NOT_PLACES = {"the", "its", "a", "an", "in", "on", "for", "which", "and", "has", "is", "was", "dated", "vide", "by", "of", "had",
               "order", "judgment", "stayed", "while", "against", "where", "with", "to", "hon", "honble", "under", "at", "that"}
_BEFORE = re.compile(r"(?i)\b(?:before|pending\s+(?:with|at|in)|filed\s+(?:with|in)|preferred\s+(?:with|to))\s+(?:the\s+)?(?:Hon'?ble\s+|learned\s+|Office\s+of\s+the\s+)?$")

# Kinds of proceeding, most telling first; IBC sections only count when the IBC is in view.
_IBC = re.compile(r"(?i)Insolvency\s+and\s+Bankruptcy|\bIBC\b|\bI\s?&\s?B\s+Code|\bCIRP\b|corporate\s+insolvency|financial\s+creditor|operational\s+creditor|\(\s*IB\s*\)")
_NATURES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)oppression|mismanagement|\b(?:sections?|ss?\.|u/s\.?)\s*241\b"), "Oppression and mismanagement (ss.241-242)"),
    (re.compile(r"(?i)\bcompound(?:ing|ed)\b|\b(?:section|u/s\.?|s\.)\s*441\b"), "Compounding (s.441)"),
    (re.compile(r"(?i)cheque[s]?\s+(?:bounce|dishono)|dishono(?:u)?r(?:ed)?\s+(?:of\s+)?cheque|Negotiable\s+Instruments"), "Cheque dishonour (s.138 NI Act)"),
    (re.compile(r"(?i)winding[\s-]+up|\b(?:section|u/s\.?)\s*271\b"), "Winding up"),
    (re.compile(r"(?i)\badjudicat\w*|\b(?:section|u/s\.?|s\.)\s*454\b"), "Adjudication of penalty"),
    (re.compile(r"(?i)\barbitra(?:l|tion|tor)"), "Arbitration"),
    (re.compile(r"(?i)\bGST\b|goods\s+and\s+services\s+tax|\bDRC[\s-]?0?1\b|\bCGST\b|\bIGST\b"), "GST demand"),
    (re.compile(r"(?i)income[\s-]?tax|assessment\s+year|\bA\.?\s?Y\.?\s*\d{4}|\bITAT\b|\bCIT\s*\(\s*A\s*\)|\bITA\b"), "Income-tax dispute"),
    (re.compile(r"(?i)service\s+tax|central\s+excise|customs\s+duty|\bCESTAT\b|\bVAT\b|sales\s+tax|stamp\s+duty"), "Indirect tax dispute"),
    (re.compile(r"(?i)\bSARFAESI|\bDRT\b|recovery\s+(?:suit|of\s+(?:dues|money|amount))|money\s+suit|summary\s+suit"), "Recovery"),
    (re.compile(r"(?i)\bwrit\b|Article\s+(?:226|32)\b"), "Writ"),
    (re.compile(r"(?i)insider\s+trading|\bSEBI\b|\bSAT\b|listing\s+regulations|\bLODR\b"), "SEBI proceedings"),
    (re.compile(r"(?i)consumer\s+complaint|deficiency\s+in\s+service"), "Consumer complaint"),
    (re.compile(r"(?i)\bprosecution|criminal\s+complaint|\bsummons\b"), "Prosecution"),
    (re.compile(r"(?i)\bsuit\b|\bplaint\b|injunction|\bdecree\b"), "Civil suit"),
    (re.compile(r"(?i)show[\s-]+cause"), "Show-cause notice"),
]
# Natures a later sentence may still make more precise.
_GENERIC = {"", "Insolvency (IBC)", "Show-cause notice"}

# Status words with a rank: an outcome outranks "pending", so an order's operative part wins over its recital.
_STATUSES: list[tuple[re.Pattern[str], str, int]] = [
    (re.compile(r"(?i)\bcompounded\b"), "compounded", 7),
    (re.compile(r"(?i)\bsettled\b|\bamicabl[ey]\b|\bsettlement\s+(?:was\s+|has\s+been\s+)?(?:reached|arrived|recorded)"), "settled", 7),
    (re.compile(r"(?i)\bwithdrawn\b|\bwithdrew\b|permitted\s+to\s+withdraw"), "withdrawn", 7),
    (re.compile(r"(?i)\bdismiss(?:ed|al)\b"), "dismissed", 6),
    (re.compile(r"(?i)\b(?:is|are|was|were|stands|been|hereby|accordingly|partly|partially)\s+allowed\b|\ballowed\s+in\s+favour|\bset\s+aside\b|\bquashed\b|decided\s+in\s+favour"), "allowed", 6),
    (re.compile(r"(?i)\bdisposed\b"), "disposed", 5),
    (re.compile(r"(?i)\bimpos(?:e|es|ed|ing)\b[^.;]{0,60}?\bpenalt|\bpenalt(?:y|ies)\b[^.;]{0,60}?\b(?:imposed|levied)\b"), "penalty imposed", 5),
    (re.compile(r"(?i)\badmitted\b|\badmission\s+of\s+the\s+(?:petition|application)"), "admitted", 4),
    (re.compile(r"(?i)\bstay(?:ed)?\b(?!\s+(?:in|at|with)\b)|\binterim\s+(?:order|relief|protection)"), "stayed", 3),
    (re.compile(r"(?i)reserved\s+for\s+(?:orders|judgment|pronouncement)|(?:orders?|judgment)\s+(?:is\s+|are\s+|was\s+)?reserved"), "reserved", 3),
    (re.compile(r"(?i)\bpending\s+(?:before|with|in|at|adjudication|disposal|hearing|decision|final)|\b(?:is|are|remains?|still|currently|presently)\s+pending\b|"
                r"\bpending\s*[.;,)]|\bsub[\s-]?judice\b|\byet\s+to\s+be\s+(?:heard|decided|disposed|adjudicated)|\bunder\s+(?:appeal|adjudication|litigation)\b|"
                r"\b(?:filed|preferred)\s+(?:an?\s+)?(?:appeal|reply|objection)|\bcontest(?:ed|ing)\b|\bnext\s+date\s+of\s+hearing|\badjourned\b|\blisted\s+(?:on|for)\b"), "pending", 1),
]
_NOT_BEFORE = re.compile(r"(?i)\b(?:not|never|yet\s+to\s+be)\s+(?:been\s+|be\s+)?$")

# A sentence about a proceeding (needed before a sentence without a case number counts as a matter).
_PROCEEDING = re.compile(
    r"(?i)\b(?:petitions?|appeals?|suits?|show[\s-]+cause|writ|(?<!investor\s)(?<!shareholder\s)complaints?\s+(?:filed|under|before|against)|"
    r"prosecution|adjudicat\w+|penalt(?:y|ies)\s+(?:of|amounting|imposed|levied|aggregating)|proceedings?\s+(?:before|initiated|against|under|pending|filed)|"
    r"legal\s+proceedings|litigation|arbitration|summons|insolvency\s+(?:petition|application|proceedings)|winding[\s-]+up|compounding|"
    r"demand\s+(?:notice|order)|(?:tax|duty|GST|income[\s-]?tax)\s+demands?|demands?\s+(?:of|raised|amounting|aggregating|confirmed)|"
    r"notices?\s+(?:under|u/s|issued)|claims?\s+(?:against|by)\s+the\s+company|assessment\s+order)"
)
_ELSEWHERE = re.compile(r"(?i)\b(?:before|filed|preferred|instituted|pending|initiated|approached)\b")
# An agreement's dispute clause speaks of arbitration that may come, not a proceeding that exists.
_CLAUSE_VOICE = re.compile(r"(?i)\b(?:any|all)\s+(?:disputes?|differences?|controvers(?:y|ies))\b|\bshall\s+be\s+(?:referred|settled|resolved|submitted)\s+(?:to|by)\b"
                           r"|\bin\s+the\s+event\s+of\s+(?:any\s+)?(?:dispute|difference)|\bdisputes?\s+arising\b")
# A new item of a list ("(c) The Directorate…", "3. A winding up petition…") starts another matter.
_ITEM_BREAK = re.compile(r"\n[ \t]*(?:\(?[a-z]{1,3}\)|\(?\d{1,2}[.)]|\(?[ivx]{1,5}[.)]|[•●▪\-–])\s")
_STATUTE_VOICE = re.compile(r"(?i)\bappeal\s+(?:shall\s+)?lies?\b|\bmay\s+(?:prefer|file)\s+an\s+appeal|\bliberty\s+to\b|\bshall\s+be\s+(?:liable|punishable)|\bmay\s+extend\s+to\b|\bwhoever\b|\bwhere\s+any\s+company\b|\bshall\s+be\s+punished\b")
_DENIAL = re.compile(r"(?i)\b(?:no|nil|none|neither|nor)\b(?!\.)(?!\s*\d)[^.;]{0,60}?\b(?:proceedings?|litigation|cases?|petitions?|appeals?|penalt|orders?|notices?|demands?|complaints?)|"
                     r"\bnot\s+(?:been\s+)?(?:subject|party|any|received|imposed|initiated|filed|passed)\b|\bno\s+(?:significant|material)\b")

_SECTION = re.compile(r"\b(?:[Ss]ections?|SECTIONS?|[Ss]ecs?\.|[Ss]s?\.|[Uu]/[Ss]\.?)\s*(\d{1,3}[A-Z]?(?:\s?\(\s?[0-9a-zA-Z]{1,4}\s?\))*)")
_SECTION_MORE = re.compile(r"\s*(?:,|and|&|/|to|-|–|read\s+with|r/w)\s*(\d{1,3}[A-Z]?(?:\s?\(\s?[0-9a-zA-Z]{1,4}\s?\))*)\b")
_ACTS = [
    (re.compile(r"(?i)^[^.;]{0,50}?\b(?:Insolvency\s+and\s+Bankruptcy|IBC\b|I\s?&\s?B\s+Code)"), "IBC"),
    (re.compile(r"(?i)^[^.;]{0,50}?\bNegotiable\s+Instruments|^[^.;]{0,50}?\bN\.?\s?I\.?\s+Act"), "NI Act"),
    (re.compile(r"(?i)^[^.;]{0,50}?\bIncome[\s-]?tax\s+Act|^[^.;]{0,50}?\bIT\s+Act"), "IT Act"),
    (re.compile(r"(?i)^[^.;]{0,50}?\b(?:Central\s+Goods\s+and\s+Services|CGST|SGST|IGST|GST)\b"), "CGST Act"),
    (re.compile(r"(?i)^[^.;]{0,50}?\bSecurities\s+and\s+Exchange\s+Board\s+of\s+India\s+Act|^[^.;]{0,50}?\bSEBI\s+Act"), "SEBI Act"),
    (re.compile(r"(?i)^[^.;]{0,50}?\bArbitration\s+and\s+Conciliation"), "A&C Act"),
    (re.compile(r"(?i)^[^.;]{0,50}?\bForeign\s+Exchange\s+Management|^[^.;]{0,50}?\bFEMA\b"), "FEMA"),
    (re.compile(r"(?i)^[^.;]{0,50}?\bSARFAESI|^[^.;]{0,50}?\bSecuritisation"), "SARFAESI"),
    (re.compile(r"(?i)^[^.;]{0,50}?\bCode\s+of\s+Civil\s+Procedure|^[^.;]{0,50}?\bCPC\b"), "CPC"),
    (re.compile(r"(?i)^[^.;]{0,50}?\bConstitution"), "Constitution"),
]
_IBC_SECTIONS = {"7", "9", "10", "12A", "33", "60", "61", "65", "66", "95"}

_AMOUNT_CUE = re.compile(r"(?i)penalt|demand|claim|disput|default|dues|outstanding|\btax\b|liabilit|sum\s+of|amount|compounding\s+fee|"
                         r"\bfine\b|interest|recover|debt|principal|award|compensation|at\s+stake|involved")
_NEXT_CUE = re.compile(r"(?i)next\s+date\s+of\s+hearing|next\s+(?:hearing\s+)?date|next\s+hearing|listed\s+(?:on|for|before)|adjourned\s+(?:to|till)|"
                       r"posted\s+(?:to|for|on)|fixed\s+for\s+(?:hearing|arguments)|(?:matter|case|petition|appeal)\s+is\s+(?:now\s+)?(?:listed|fixed|posted)|"
                       r"come\s+up\s+(?:for\s+hearing\s+)?on|stands\s+over\s+to")

_VERSUS = re.compile(r"\s(?:v\.|v/s\.?|(?i:vs\.?|versus))\s")
_ROLE = r"(?:Petitioner|Respondent|Appellant|Applicant|Complainant|Opposite\s+Part(?:y|ies)|Corporate\s+Debtor|Financial\s+Creditor|Operational\s+Creditor|Plaintiff|Defendant|Noticee)s?(?:\s*No\.?\s*\d+)?"
_ROLE_TAIL = re.compile(rf"(?:\.{{2,}}|…|,|-|–)?\s*\(?\s*{_ROLE}\s*\)?\s*$", re.IGNORECASE)
_ROLE_CUT = re.compile(rf"\.{{2,}}|…|\b{_ROLE}\b", re.IGNORECASE)
_LEFT_CUT = re.compile(r"(?i)\b(?:in\s+the\s+matter\s+of|matter\s+of|titled|captioned|styled|between|case\s+of)\b|[:;]")
_FILED_BY = re.compile(r"(?i)\b(?:filed|instituted|preferred|initiated|moved)\s+by\s+(?:the\s+)?")
_AGAINST = re.compile(r"(?i)\bagainst\s+(?:the\s+)?")
_JOINERS = {"&", "and", "of", "the", "(india)", "(i)", "ors.", "ors", "anr.", "anr", "others", "another", "m/s.", "m/s", "-", "–", "for", "&amp;"}


def analyse(doc: Doc) -> dict[str, Any] | None:
    score = relevance(doc.pages, LEXICON)
    matters = _matters(doc)
    if not matters and score < 0.3:
        return None
    items = [_finish(m) for m in matters]
    highlights = key_sentences(doc.pages, LEXICON, 4)
    if not items and not highlights:
        return None
    tags = ["legal", "litigation"] if items else ["legal"]
    return result(KIND, TITLE, COLUMNS, items, score, _summary(items), tags, highlights, _facts(items))


# --- finding matters -------------------------------------------------------------------------------------------

def _matters(doc: Doc) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    order: list[dict[str, Any]] = []
    ibc_doc = bool(_IBC.search(doc.text[:200_000]))
    # Count distinct numbers first: in a document about a single case (an order, a petition), everything after
    # its number belongs to it, however far down the operative part comes.
    distinct = {key for _, text in doc.pages for _, key, _, _ in _case_numbers(text)}
    single = len(distinct) == 1
    anchor: dict[str, Any] | None = None
    anchor_at = 0
    offset = 0
    for page, text in doc.pages:
        cases = _case_numbers(text)
        prev: tuple[int, int, str] | None = None  # the sentence before, on this page, if it began no matter
        last: tuple[dict[str, Any], int] | None = None  # the matter without a number begun last on this page
        for start, end, sentence in sentences(text):
            here = [c for c in cases if start <= c[0] < end]
            if here:
                prev, last = None, None
                for position, key, shown, _ in here:
                    matter = by_key.get(key)
                    if matter is None:
                        matter = _new(page, sentence, shown)
                        by_key[key] = matter
                        order.append(matter)
                    # The number itself is no evidence of forum: "ROC/MUM/ADJ/454" is not the ROC speaking.
                    _fill(matter, CASE_NO.sub(lambda c: c.group(0)[: c.start("id") - c.start()], sentence), ibc_doc, text[start : end + 60])
                    if not matter["forum"]:
                        # The court's name heads an order, above the number: look back, but not past another number.
                        floor = max([c[0] for c in cases if c[0] < position and c[1] != key] or [0])
                        matter["forum"] = _forum(text[max(floor, position - 600) : position])
                    anchor, anchor_at = matter, offset + start
                continue
            if _cited(sentence):
                prev = None
                continue
            own = _own_matter(sentence)
            near = anchor is not None and (single or offset + start - anchor_at < 2500)
            # Inside a case's stretch, a sentence is another matter only if it takes a proceeding to another forum
            # ("had earlier filed a writ before the High Court"), not if it names the officer deciding this one.
            elsewhere = bool(own and own not in ("-", "Adjudicating Officer") and anchor is not None and own != anchor["forum"]
                             and _ELSEWHERE.search(sentence))
            if near and anchor is not None and not elsewhere:
                _fill(anchor, sentence, ibc_doc, text[start : end + 60])
            elif own:
                matter = _new(page, sentence, "")
                # A contingent liabilities note often tells one matter over two sentences: the demand and its amount
                # ("has received a demand of ₹1.86 crore under s.143(3)"), then the forum ("has filed an appeal before
                # the CIT(A), which is pending").
                if prev and _same_item(text, prev[1], start) and _PROCEEDING.search(prev[2]) and not _DENIAL.search(prev[2]):
                    _fill(matter, prev[2], ibc_doc, text[prev[0] : prev[1] + 60])
                _fill(matter, sentence, ibc_doc, text[start : end + 60])
                twin = next((m for m in order if not m["case_no"] and m["forum"] == matter["forum"] and m["nature"] == matter["nature"]
                             and m["page"] == page and (not m["amount"] or not matter["amount"] or m["amount"] == matter["amount"])), None)
                if twin:
                    _fill(twin, sentence, ibc_doc, text[start : end + 60])
                else:
                    order.append(matter)
                last, prev = (twin or matter, end), None
                continue
            elif last and _same_item(text, last[1], start) and (_status(sentence)[0] or _next_date(text[start : end + 60]) or _amount(sentence)):
                # …and then where it stands: "The Company has filed its reply and the matter is pending adjudication."
                _fill(last[0], sentence, ibc_doc, text[start : end + 60])
                last = (last[0], end)
            prev = (start, end, sentence)
        offset += len(text) + 1
    return order


def _same_item(text: str, earlier_end: int, later_start: int) -> bool:
    """Whether two sentences are close and in the same item of a list, not the next "(c)" or "3."."""
    return 0 <= later_start - earlier_end < 300 and not _ITEM_BREAK.search(text, earlier_end, later_start + 1)


def _case_numbers(text: str) -> list[tuple[int, str, str, int]]:
    """(start, merge key, as shown, end) for each case number in the text that is hers, not cited as authority."""
    out = []
    for m in CASE_NO.finditer(text):
        kind, qual, ident, year = m.group("type"), m.group("qual") or "", m.group("id"), m.group("year") or ""
        ident = ident.rstrip(".-/")
        while ident.endswith(")") and ident.count(")") > ident.count("("):
            ident = ident[:-1]
        if not re.search(r"\d", ident) or len(re.sub(r"\D", "", ident)) > 12:
            continue
        compact = re.sub(r"[\s.]", "", kind).upper()
        if compact in _AMBIGUOUS and not (qual.strip() or "/" in ident or year):
            continue
        if kind.lower() in ("case", "complaint", "suit", "petition", "appeal") and not ("/" in ident or year):
            continue  # "case no. 3" in a list of agenda items; a real one carries its year
        before, after = text[max(0, m.start() - 160) : m.start()], text[m.end() : m.end() + 70]
        if _CITED_BEFORE.search(before) or _CITED_AFTER.search(after):
            continue
        abbr = next((a for pattern, a in _TYPE_ABBR if re.search(pattern, kind.strip())), compact)
        number = re.sub(r"\s+", "", f"{ident}{year}".upper().replace(" OF ", "/"))
        key = f"{abbr}{re.sub(r'[^A-Z]', '', qual.upper())}:{number}"
        shown = " ".join(f"{kind}{(' ' + ' '.join(qual.split())) if qual.strip() else ''} No. {ident}{' ' + ' '.join(year.split()) if year else ''}".split())
        out.append((m.start(), key, shown, m.end()))
    return out


def _cited(sentence: str) -> bool:
    return bool(re.search(r"(?i)\brelied\s+(?:up)?on\b|\bplaced\s+reliance\b|\bin\s+the\s+case\s+of\b|\bheld\s+that\b", sentence)
                or _CITED_AFTER.search(sentence[-200:]) or re.search(r"\(\d{4}\)\s*\d+\s*SCC|SCC\s+OnLine|\bAIR\s+\d{4}", sentence))


def _own_matter(sentence: str) -> str | None:
    """The forum (or "-" when none is named) if the sentence is about a proceeding of hers; None otherwise."""
    if not _PROCEEDING.search(sentence) or _STATUTE_VOICE.search(sentence) or _CLAUSE_VOICE.search(sentence):
        return None
    has_amount = any(True for _ in amounts(sentence))
    if _DENIAL.search(sentence) and not has_amount:
        return None
    forum = _forum(sentence)
    if forum:
        return forum
    return "-" if has_amount and _status(sentence)[0] else None


def _new(page: int, sentence: str, case_no: str) -> dict[str, Any]:
    return {"forum": "", "case_no": case_no, "parties": "", "nature": "", "sections": [], "status": "", "amount": None,
            "next_date": None, "page": page, "context": sentence[:600], "_rank": 0, "_hits": 0}


def _fill(matter: dict[str, Any], sentence: str, ibc_doc: bool, reach: str = "") -> None:
    """Fill what the matter still lacks from one more sentence about it; an outcome replaces a lesser status.

    `reach` runs a little past the sentence, since "Next date of hearing: 22/11/2026" splits at the colon.
    """
    matter["_hits"] += 1
    if not matter["forum"]:
        matter["forum"] = _forum(sentence)
    if not matter["parties"]:
        matter["parties"] = _parties(sentence)
    old = matter["nature"]
    if old in _GENERIC or "(" not in old:
        new = _nature(sentence, ibc_doc)
        # Only a sharper reading of the same kind: "Insolvency (IBC)" becomes "Insolvency (s.7 IBC, ...)".
        if new and (old in _GENERIC or (new != old and new.startswith(old))):
            matter["nature"] = new
    for section in _sections(sentence, ibc_doc):
        if section not in matter["sections"] and len(matter["sections"]) < 10:
            matter["sections"].append(section)
    status, rank = _status(sentence)
    if status and rank >= matter["_rank"]:
        matter["status"], matter["_rank"] = status, rank
    if matter["amount"] is None:
        matter["amount"] = _amount(sentence)
    if matter["next_date"] is None:
        matter["next_date"] = _next_date(reach or sentence)


def _forum(text: str) -> str:
    found: list[tuple[int, int, str]] = []
    for pattern, label in _FORUMS:
        for m in pattern.finditer(text):
            found.append((m.start(), m.end(), _place(label, text, m.start(), m.end())))
    for m in _HIGH_COURT.finditer(text):
        place = (m.group(1) or "").split()[0] if m.group(1) else ""
        name = " ".join(m.group(1).split()) if place and place.lower() not in _NOT_PLACES else ""
        if not name:
            before = _HIGH_COURT_BEFORE.search(text, max(0, m.start() - 20), m.end())
            name = before.group(1) if before and before.group(1).lower() not in _NOT_PLACES else ""
        found.append((m.start(), m.end(), f"High Court of {name.title()}" if name else "High Court"))
    if not found:
        return ""
    found.sort()
    for start, _, label in found:
        if _BEFORE.search(text[max(0, start - 45) : start]):
            return label
    # The tribunals before the officers: "the ROC's order was appealed to the Regional Director" is before the RD.
    return found[0][2]


def _place(label: str, text: str, start: int, end: int) -> str:
    if label in ("NCLT", "NCLAT", "ROC", "DRT", "ITAT"):
        near = _BENCH.search(text[end : end + 45]) or _BENCH.search(text[max(0, start - 30) : start])
        if near:
            city = " ".join(near.group(1).split()).title()
            return f"{label} {'Principal Bench' if city == 'Principal' else city}"
    return label


def _parties(sentence: str) -> str:
    m = _VERSUS.search(sentence)
    if m:
        left = _LEFT_CUT.split(_ROLE_TAIL.sub("", sentence[max(0, m.start() - 160) : m.start()]))[-1]
        right = _ROLE_CUT.split(sentence[m.end() : m.end() + 160])[0]
        first, second = _name_run(left.split(), backwards=True), _name_run(right.split())
        if first and second:
            return f"{first} v. {second}"
    by = _FILED_BY.search(sentence)
    if by:
        first = _name_run(sentence[by.end() : by.end() + 120].split())
        against = _AGAINST.search(sentence, by.end())
        second = _name_run(sentence[against.end() : against.end() + 120].split()) if against else ""
        if first and second:
            return f"{first} v. {second}"
    return ""


def _name_run(words: list[str], backwards: bool = False) -> str:
    """The run of capitalised words (with "&", "of", "Ors.") at the end or start of a stretch of text: a party's name."""
    seq = list(reversed(words)) if backwards else words
    taken: list[str] = []
    for word in seq[:14]:
        bare = word.strip(",")
        if not bare:
            break
        if backwards and word.endswith(","):
            break  # "Ramesh, a shareholder, v." is rare; a comma before the name usually ends the clause before it
        if not (bare[0].isupper() or bare.lower() in _JOINERS or bare.startswith("(")):
            break
        taken.append(bare)
        if word.endswith(","):
            break
    if backwards:
        taken.reverse()
    while taken and taken[0].lower() in _JOINERS:
        taken.pop(0)
    while taken and taken[-1].lower() in _JOINERS - {"ors.", "ors", "anr.", "anr", "others", "another"}:
        taken.pop()
    name = " ".join(taken).strip(" ,;:")
    if name.endswith(".") and not re.search(r"(?i)\b(?:Ors|Anr|Ltd|Pvt|Co|Inc|Corpn)\.$", name):
        name = name[:-1]
    return name if len(name) > 2 and len(taken) <= 12 else ""


def _nature(text: str, ibc_doc: bool) -> str:
    if ibc_doc or _IBC.search(text):
        if re.search(r"(?i)\b(?:section|u/s\.?|s\.)\s*7\b|financial\s+creditor", text):
            return "Insolvency (s.7 IBC, financial creditor)"
        if re.search(r"(?i)\b(?:section|u/s\.?|s\.)\s*9\b|operational\s+creditor", text):
            return "Insolvency (s.9 IBC, operational creditor)"
        if re.search(r"(?i)\b(?:section|u/s\.?|s\.)\s*10\b|corporate\s+applicant", text):
            return "Insolvency (s.10 IBC, corporate applicant)"
        if re.search(r"(?i)\b(?:section|u/s\.?|s\.)\s*95\b|personal\s+guarantor", text):
            return "Insolvency (s.95 IBC, personal guarantor)"
        if _IBC.search(text):
            return "Insolvency (IBC)"
    for pattern, label in _NATURES:
        if pattern.search(text):
            if label == "Adjudication of penalty" and re.search(r"\bSEBI\b|Securities\s+and\s+Exchange", text):
                return "SEBI adjudication"
            if label == "Adjudication of penalty" and re.search(r"(?i)\b(?:section|u/s\.?|s\.)\s*454\b|Companies\s+Act", text):
                return "Adjudication of penalty (s.454)"
            if label in ("GST demand", "Income-tax dispute", "Indirect tax dispute") and re.search(r"(?i)show[\s-]+cause", text):
                return f"{label} (show-cause notice)"
            return label
    return ""


def _sections(text: str, ibc_doc: bool) -> list[str]:
    out: list[str] = []
    for m in _SECTION.finditer(text):
        numbers = [m.group(1)]
        tail = m.end()
        while len(numbers) < 8:
            more = _SECTION_MORE.match(text, tail)
            if not more:
                break
            numbers.append(more.group(1))
            tail = more.end()
        act = next((name for pattern, name in _ACTS if pattern.search(text[tail : tail + 90])), "")
        for raw in numbers:
            number = re.sub(r"\s+", "", raw)
            this_act = act or ("IBC" if ibc_doc and number.split("(")[0] in _IBC_SECTIONS else "")
            label = f"{number} {this_act}" if this_act else number
            if label not in out:
                out.append(label)
    return out


def _status(text: str) -> tuple[str, int]:
    best, rank = "", 0
    for pattern, label, weight in _STATUSES:
        for m in pattern.finditer(text):
            if _NOT_BEFORE.search(text[max(0, m.start() - 20) : m.start()]):
                continue
            if weight > rank:
                best, rank = label, weight
            break
    return best, rank


def _amount(text: str) -> int | None:
    for value, start, end, _ in amounts(text):
        if _AMOUNT_CUE.search(text[max(0, start - 90) : end + 60]):
            return value
    return None


def _next_date(text: str) -> str | None:
    found = list(dates(text))
    for cue in _NEXT_CUE.finditer(text):
        after = [d for d in found if cue.end() <= d[1] <= cue.end() + 80]
        if after:
            return min(after, key=lambda d: d[1])[0]
    return None


# --- shaping the result --------------------------------------------------------------------------------------

def _finish(matter: dict[str, Any]) -> dict[str, Any]:
    confidence = 0.3 + (0.3 if matter["case_no"] else 0)
    confidence += sum(0.08 for key in ("forum", "nature", "status", "parties", "amount") if matter[key])
    confidence += 0.05 if matter["_hits"] > 1 else 0
    item = {k: v for k, v in matter.items() if not k.startswith("_")}
    item["forum"] = item["forum"] if item["forum"] != "-" else ""
    item["confidence"] = round(min(confidence, 0.95), 2)
    return item


def _summary(items: list[dict[str, Any]]) -> str:
    if not items:
        return "Discusses legal proceedings, but names no particular matter."
    groups = Counter((i["status"] or "", i["forum"] or "") for i in items)
    parts = []
    for (status, forum), count in groups.most_common(4):
        words = f"{count} {status}" if status else f"{count}"
        words += f" before {forum}" if forum else ("" if status else " other")
        parts.append(words)
    if len(groups) > 4:
        parts.append(f"{sum(c for _, c in groups.most_common()[4:])} more")
    total = sum(i["amount"] or 0 for i in items)
    noun = "matter" if len(items) == 1 else "matters"
    stake = f"; {rupees(total)} at stake" if total else ""
    return f"{len(items)} {noun}: {', '.join(parts)}{stake}."


def _facts(items: list[dict[str, Any]]) -> dict[str, Any]:
    upcoming = sorted(i["next_date"] for i in items if i["next_date"])
    return {
        "matters": len(items),
        "with_case_no": sum(1 for i in items if i["case_no"]),
        "by_forum": dict(Counter(i["forum"] or "not stated" for i in items)),
        "by_status": dict(Counter(i["status"] or "not stated" for i in items)),
        "total_amount": sum(i["amount"] or 0 for i in items),
        "next_date": upcoming[0] if upcoming else None,
    }
