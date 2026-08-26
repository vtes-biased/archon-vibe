"""The BCP playtest NDA: canonical document text, template fill, and the sealed
PDF a signature produces. Keep the template ASCII — its sha256 is signature
evidence, so its bytes must be encoding-unambiguous.
"""

import hashlib
from datetime import UTC, datetime
from importlib import resources

from fpdf import FPDF
from fpdf.enums import XPos, YPos

NDA_VERSION = 1

NDA_TEMPLATE = """\
# BLACK CHANTRY PRODUCTIONS

## CONFIDENTIALITY AND NONDISCLOSURE AGREEMENT

Black Chantry Productions, 13 East Crescent, Beeston, Nottingham, NG9 1PZ, \
United Kingdom

It is understood and agreed to, that this [DATE], Black Chantry Productions, \
Ltd., a company registered in England & Wales at 13 Crescent, Beeston, \
Nottingham NG9 1PZ (the "Discloser") and [RECIPIENT] (the "Recipient") would \
like to exchange certain information that may be considered confidential. To \
ensure the protection of such information and in consideration of the \
agreement to exchange said information, the parties agree as follows:

**1.** The confidential information to be disclosed by Discloser under this \
Agreement ("Confidential Information") can be described as and includes: \
Technical and business information relating to Discloser's proprietary ideas, \
patentable ideas copyrights and/or trade secrets, existing and/or contemplated \
products and services, software, schematics, research and development, \
production, costs, profit and margin information, finances and financial \
projections, customers, clients, marketing, and current or future business \
plans and models, regardless of whether such information is designated as \
"Confidential Information" at the time of its disclosure.

In addition to the above, Confidential Information shall also include, and the \
Recipient shall have a duty to protect, other confidential and/or sensitive \
information which is (a) disclosed by Discloser in writing and marked as \
confidential (or with other similar designation) at the time of disclosure; \
and/or (b) disclosed by Discloser in any other manner and identified as \
confidential at the time of disclosure and is also summarized and designated \
as confidential in a written memorandum delivered to Recipient within thirty \
(30) days of the disclosure.

**2.** Recipient shall use the Confidential Information only for the purpose \
to test and/or translate games developed by Discloser or write a review or \
preview in a blog or related press release about the games developed by \
Discloser.

**3.** Recipient shall limit disclosure of Confidential Information within \
its own organization to its directors, officers, partners, members and/or \
employees having a need to know and shall not disclose Confidential \
Information to any third party (whether an individual, corporation, or other \
entity) without the prior written consent of Discloser. Recipient shall have \
satisfied its obligations under this paragraph if it takes affirmative \
measures to ensure compliance with these confidentiality obligations by its \
employees, agents, consultants and others who are permitted access to or use \
of the Confidential Information.

**4.** This Agreement imposes no obligation upon Recipient with respect to \
any Confidential Information (a) that was in Recipient's possession before \
receipt from Discloser; (b) is or becomes a matter of public knowledge \
through no fault of Recipient; (c) is rightfully received by Recipient from a \
third party not owing a duty of confidentiality to the Discloser; (d) is \
disclosed without a duty of confidentiality to a third party by, or with the \
authorization of, Discloser; or (e) is independently developed by Recipient.

**5.** Discloser warrants that he/she has the right to make the disclosures \
under this Agreement.

**6.** This Agreement shall not be construed as creating, conveying, \
transferring, granting or conferring upon the Recipient any rights, license \
or authority in or to the information exchanged, except the limited right to \
use Confidential Information specified in paragraph 2. Furthermore and \
specifically, no license or conveyance of any intellectual property rights is \
granted or implied by this Agreement.

**7.** Neither party has an obligation under this Agreement to purchase any \
service, goods, or intangibles from the other party. Discloser may, at its \
sole discretion, using its own information, offer such products and/or \
services for sale and modify them or discontinue sale at any time. \
Furthermore, both parties acknowledge and agree that the exchange of \
information under this Agreement shall not commit or bind either party to any \
present or future contractual relationship (except as specifically stated \
herein), nor shall the exchange of information be construed as an inducement \
to act or not to act in any given manner.

**8.** Neither party shall be liable to the other in any manner whatsoever \
for any decisions, obligations, costs or expenses incurred, changes in \
business practices, plans, organization, products, services, or otherwise, \
based on either party's decision to use or rely on any information exchanged \
under this Agreement.

**9.** If there is a breach or threatened breach of any provision of this \
Agreement, it is agreed and understood that Discloser shall have no adequate \
remedy in money or other damages and accordingly shall be entitled to \
injunctive relief; provided however, no specification in this Agreement of \
any particular remedy shall be construed as a waiver or prohibition of any \
other remedies in the event of a breach or threatened breach of this \
Agreement.

**10.** The Discloser will have the right to credit the Recipient for their \
work as applicable in rulebooks and marketing materials as applicable.

**11.** This Agreement states the entire agreement between the parties \
concerning the disclosure of Confidential Information and supersedes any \
prior agreements, understandings, or representations with respect thereto. \
Any addition or modification to this Agreement must be made in writing and \
signed by authorized representatives of both parties. This Agreement is made \
under and shall be construed according to the laws of England and Wales. In \
the event that this agreement is breached, any and all disputes must be \
settled in a court of competent jurisdiction in England and Wales.

**12.** If any of the provisions of this Agreement are found to be \
unenforceable, the remainder shall be enforced as fully as possible and the \
unenforceable provision(s) shall be deemed modified to the limited extent \
required to permit enforcement of the Agreement as a whole.

WHEREFORE, the parties acknowledge that they have read and understand this \
Agreement and voluntarily accept the duties and obligations set forth herein \
as of the day and date first above written.

BLACK CHANTRY PRODUCTIONS, Ltd. -- Hugh Angseesing, Chief Executive Officer
"""


def nda_sha256() -> str:
    return hashlib.sha256(NDA_TEMPLATE.encode("utf-8")).hexdigest()


def _ordinal(n: int) -> str:
    if 11 <= n % 100 <= 13:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


def fill_template(recipient_name: str, on: datetime) -> str:
    date_words = f"{_ordinal(on.day)} day of {on.strftime('%B %Y')}"
    return NDA_TEMPLATE.replace("[DATE]", date_words).replace(
        "[RECIPIENT]", recipient_name
    )


def build_sealed_pdf(
    *,
    recipient_name: str,
    signer_email: str,
    signer_address: str,
    signer_phone: str,
    member_uid: str,
    vekn_id: str,
    requested_by: str,
    record_uid: str,
    signed_at: datetime,
) -> bytes:
    pdf = FPDF()
    pdf.set_title("Black Chantry Productions - Confidentiality and NDA")
    pdf.set_auto_page_break(auto=True, margin=18)
    # Unicode fonts, not the core (latin-1) ones: the signer's name, address and
    # e-mail are evidence and must never degrade to "?".
    fonts = resources.files(__package__) / "data" / "fonts"
    pdf.add_font("DejaVu", "", str(fonts / "DejaVuSans.ttf"))
    pdf.add_font("DejaVu", "B", str(fonts / "DejaVuSans-Bold.ttf"))
    pdf.add_page()

    for block in fill_template(recipient_name, signed_at).split("\n\n"):
        text = block.replace("\n", " ").strip()
        if text.startswith("## "):
            pdf.set_font("DejaVu", style="B", size=13)
            pdf.multi_cell(0, 7, text[3:], align="C")
        elif text.startswith("# "):
            pdf.set_font("DejaVu", style="B", size=15)
            pdf.multi_cell(0, 8, text[2:], align="C")
        else:
            pdf.set_font("DejaVu", size=10)
            pdf.multi_cell(0, 5, text.replace("**", ""), align="J")
        pdf.ln(3)

    pdf.add_page()
    pdf.set_font("DejaVu", style="B", size=13)
    pdf.multi_cell(0, 7, "ELECTRONIC SIGNATURE RECORD", align="C")
    pdf.ln(4)
    pdf.set_font("DejaVu", size=10)
    pdf.multi_cell(
        0,
        5,
        "This agreement was signed electronically on the VEKN Archon platform "
        "(archon.vekn.net) by the authenticated member identified below, who "
        "typed their name as signature after reading the document above.",
        align="J",
    )
    pdf.ln(4)
    rows = [
        ("Signed by (typed name)", recipient_name),
        ("E-mail", signer_email),
        ("Address", signer_address),
        ("Phone", signer_phone),
        ("VEKN ID", vekn_id),
        ("Member account", member_uid),
        ("Requested by", requested_by),
        ("Signed at (UTC)", signed_at.astimezone(UTC).isoformat()),
        ("Record ID", record_uid),
        ("Document version", str(NDA_VERSION)),
        ("Document SHA-256", nda_sha256()),
    ]
    for label, value in rows:
        pdf.set_font("DejaVu", style="B", size=9)
        pdf.cell(55, 6, label)
        pdf.set_font("DejaVu", size=9)
        pdf.multi_cell(0, 6, value or "-", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    return bytes(pdf.output())
