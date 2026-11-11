"""Body text for the demo SOPs, so the assistant can be tried before SharePoint is connected.

This is illustrative sample content, NOT Avion procedure. Every document is marked as a demo.
"""

from __future__ import annotations

DEMO_BANNER = (
    "DEMO DOCUMENT - sample content for demonstrating Avi.Intelligence. "
    "This is not an Avion controlled document and must not be used for study work."
)

DEMO_SOP_TEXT: dict[str, str] = {
    "SOP-011": """\
1 Purpose
This SOP describes how a clinical site is activated for a study, from site selection to the site \
activation notice.

2 Scope
Applies to all Phase I-IV studies where Avion manages site activation for a sponsor.

3 Responsibilities
The Clinical Project Manager (CPM) owns the activation plan. The Clinical Research Associate (CRA) \
collects site documents and conducts the site initiation visit. The Clinical Trial Associate (CTA) \
files documents in the Trial Master File (TMF).

4 Procedure
4.1 Site readiness
Confirm the site has signed the confidentiality agreement and completed the feasibility questionnaire.
Confirm ethics committee approval and regulatory authorisation are in place for the protocol version.
Confirm the clinical trial agreement and budget are fully executed.
4.2 Essential documents
Collect the investigator CV, GCP training certificate and medical licence for each investigator.
Collect the signed protocol signature page, delegation log and laboratory certification.
The CTA files all essential documents in the TMF before activation.
4.3 Site initiation visit
The CRA conducts the site initiation visit (SIV) using the approved SIV checklist.
The SIV covers the protocol, informed consent process, safety reporting, investigational product \
handling and EDC data entry.
All site staff on the delegation log must complete protocol training before performing study tasks.
4.4 EDC and systems access
Confirm EDC accounts are created for all delegated staff and that data entry training is documented.
4.5 Activation
The CPM issues the site activation notice only when sections 4.1 to 4.4 are complete and verified.
Investigational product may be shipped only after the activation notice is issued.

5 Records
Site activation checklist, SIV report and activation notice are filed in the TMF.
""",
    "SOP-012": """\
1 Purpose
This SOP describes how monitoring visits are planned, conducted and reported.

2 Scope
Applies to on-site and remote monitoring visits for all studies monitored by Avion.

3 Procedure
3.1 Planning
Monitoring visit frequency follows the study monitoring plan. The CRA confirms the visit date with \
the site at least 10 working days in advance and sends a confirmation letter with the agenda.
3.2 Conducting the visit
The CRA performs source data verification as defined in the monitoring plan, reviews the investigator \
site file, checks investigational product accountability and reviews protocol deviations.
3.3 Monitoring visit report
The CRA completes the monitoring visit report within 5 working days of the visit.
The report includes visit attendees, subject status, findings, protocol deviations, action items \
with owners and due dates, and safety events identified.
The CPM reviews and approves the report within 5 working days of submission.
3.4 Follow-up letter
A follow-up letter summarising findings and action items is sent to the site within 10 working days \
of the visit.

4 Records
Confirmation letters, visit reports and follow-up letters are filed in the TMF.
""",
    "SOP-014": """\
1 Purpose
This SOP describes how protocol deviations are identified, classified, reported and tracked.

2 Definitions
A protocol deviation is any change, divergence or departure from the approved protocol. An important \
protocol deviation is one that may significantly affect data reliability or subject safety, rights \
or wellbeing.

3 Procedure
3.1 Identification
Deviations may be identified during monitoring, data review or reported by the site.
3.2 Classification
The CRA proposes a classification of important or not important. The CPM confirms the classification.
3.3 Reporting
Important protocol deviations are reported to the sponsor within 2 working days of identification.
The site reports deviations to the ethics committee according to local requirements.
3.4 Tracking
All deviations are recorded in the study deviation log and reviewed at each study team meeting.
""",
    "SOP-015": """\
1 Purpose
This SOP describes how the Trial Master File (TMF) is set up, maintained and closed.

2 Procedure
2.1 Set-up
The CTA sets up the electronic TMF using the TMF Reference Model index within 30 days of study award.
2.2 Filing
Documents are filed within 10 working days of finalisation. Each filed document is checked for \
completeness, signatures and correct placement.
2.3 Quality review
A TMF quality review of a sample of documents is performed every quarter. Findings are tracked to \
closure.
2.4 Closure
At study close the CTA performs a final TMF reconciliation and transfers the TMF to the sponsor or \
archive as defined in the contract.
""",
    "SOP-020": """\
1 Purpose
This SOP describes the data management plan and the steps to lock the study database.

2 Procedure
2.1 Data management plan
The data manager writes the data management plan before first subject in. It defines data review, \
query management, coding and reconciliation.
2.2 Pre-lock activities
Before database lock: all data are entered and source verified as required, all queries are \
resolved, medical coding is complete, SAE reconciliation between the safety database and EDC is \
complete, and external data are reconciled.
2.3 Lock approval
The database lock checklist is signed by the data manager, the CPM and the sponsor representative.
2.4 Lock
The data manager locks the database in the EDC system and removes edit access. Unlocking requires \
documented sponsor approval.
""",
    "SOP-030": """\
1 Purpose
This SOP describes how serious adverse events (SAEs) and suspected unexpected serious adverse \
reactions (SUSARs) are reported.

2 Procedure
2.1 Site reporting
The investigator reports an SAE to Avion Safety within 24 hours of becoming aware of it, using the \
SAE report form.
2.2 Safety review
Avion Safety checks the report for completeness and requests missing information from the site \
within 1 working day.
2.3 Expedited reporting
SUSARs that are fatal or life-threatening are reported to regulators within 7 calendar days of \
first knowledge. Other SUSARs are reported within 15 calendar days.
2.4 Follow-up
Follow-up information is collected until the event resolves or stabilises.
2.5 Reconciliation
SAEs in the safety database are reconciled with the EDC before database lock.
""",
}


def demo_text_for(sop_number: str | None, title: str, version: str | None) -> str:
    body = DEMO_SOP_TEXT.get(sop_number or "", "1 Purpose\nDemo content is not available for this SOP.\n")
    return f"{DEMO_BANNER}\n\n{sop_number or ''} {title}\nVersion {version or 'unknown'}\n\n{body}"
