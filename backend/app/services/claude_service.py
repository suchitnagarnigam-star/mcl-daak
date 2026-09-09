from app.config import anthropic_client
import json
import logging

logger = logging.getLogger(__name__)

DEPARTMENTS = [
        {"department": "Accounts & Audit Branch", "description": "Manages municipal funds, financial audits, annual budgets, and expense approvals."},
        {"department": "Advertisement Branch", "description": "Regulates outdoor hoarding spaces, commercial banners, and collects public advertisement taxes."},
        {"department": "AMRUT Cell Branch", "description": "Implements centrally funded infrastructure upgrades for water supply and sewerage networks."},
        {"department": "Building & Roads (B&R) Branch", "description": "Constructs, paves, and maintains public roads, bridges, and municipal buildings."},
        {"department": "Computerization Branch", "description": "Maintains digital infrastructure, the official portal, and online citizen services."},
        {"department": "Complaints & Enquiry Branch", "description": "Receives public grievances, logs citizen feedback, and tracks resolution progress."},
        {"department": "Drawing Branch", "description": "Prepares structural blueprints, engineering layouts, and mapping for civic projects."},
        {"department": "Estate & Property Branch", "description": "Oversees corporation-owned land, handles properties on lease, and collects rent."},
        {"department": "Establishment Branch", "description": "Handles internal human resources, payroll, transfers, and municipal staff administration."},
        {"department": "Fire Brigade Branch", "description": "Provides emergency firefighting services, disaster rescue, and issues fire safety certificates."},
        {"department": "Health & Sanitation Branch", "description": "Manages daily city garbage collection, street sweeping, and vector control drives."},
        {"department": "Horticulture Branch", "description": "Develops and maintains public parks, green belts, and city landscaping."},
        {"department": "House Tax / Property Tax Branch", "description": "Assesses property values, processes yearly evaluations, and collects property taxes."},
        {"department": "Land & Tehbazari Branch", "description": "Removes illegal street encroachments and regulates public vending zones."},
        {"department": "Legal Branch", "description": "Handles court cases, statutory compliance, and legal drafting for the corporation."},
        {"department": "Licensing Branch", "description": "Issues and renews trade licenses for businesses operating within city limits."},
        {"department": "Lights / Electrical Branch", "description": "Installs and repairs public streetlights, timers, and high-mast lights."},
        {"department": "Operations & Maintenance (O&M) Branch", "description": "Operates tubewells, maintains drinking water supply, and clears sewage systems."},
        {"department": "Projects Division Branch", "description": "Plans and monitors large-scale urban development schemes across the city."},
        {"department": "Slum Clearance Branch", "description": "Works on rehabilitation programs and basic service provisioning for slum areas."},
        {"department": "Town Planning / Building Branch", "description": "Enforces building bylaws, demolishes illegal structures, and approves building plans."},
        {"department": "Workshop Branch", "description": "Services, repairs, and maintains the fleet of municipal vehicles and machinery."}
    ]

CATEGORIES = [
    {"category": "Public Grievance", "description": "Citizen complaints on water supply, sewerage, sanitation, potholes, streetlights, encroachment, stray animals"},
    {"category": "Development & Ward Work", "description": "Resident or councillor demands for new roads, parks, community halls, drainage works"},
    {"category": "RTI Application", "description": "Right to Information requests requiring statutory responses within legal deadlines"},
    {"category": "Legal & Court Correspondence", "description": "Court orders, litigation notices, contempt petitions, PIL-related communication"},
    {"category": "Inter-Department Reference", "description": "Letters from PWD, PSPCL, Water Supply & Sanitation, Local Government Department, or other state agencies"},
    {"category": "Building Plan & Construction", "description": "Building plan approvals, objections, unauthorized construction complaints"},
    {"category": "Property Tax", "description": "Assessment objections, exemption or rebate requests, tax disputes"},
    {"category": "VIP & Political Reference", "description": "Letters from MLAs, MPs, or councillors forwarding constituent complaints"},
    {"category": "Trade & Fire License", "description": "New license applications, renewals, NOC requests for trade or fire safety"},
    {"category": "Vigilance & Misconduct", "description": "Corruption or misconduct allegations against MCL staff or contractors"},
    {"category": "Tender & Contractor", "description": "Bid disputes, bill payment follow-ups, work quality complaints"},
    {"category": "HR & Service Matter", "description": "Employee transfer requests, appointments, service-related applications"},
    {"category": "Audit Para", "description": "Replies due to CAG or local audit objections"},
    {"category": "Council Matter", "description": "Resolutions passed, agenda items requiring Commissioner action"},
    {"category": "General Correspondence", "description": "Anything that does not fit the above categories"}
]


def process_document(ocr_output: str) -> dict:

    if anthropic_client is None:
        logger.error("Anthropic client is not configured.")
        return {"error": "Anthropic client is not configured."}

    prompt = f"""You are a language expert fluent in Hindi, Punjabi, and English with deep experience in translating official municipal documents.

        Your job is to translate the document text below into English, preserving the original meaning and context without altering it and there will be conditions when there will be multiple images which will be indicated with page starting and ending lines added with the text.. Then extract the following fields from the translated content.

        DEPARTMENTS LIST:
        {DEPARTMENTS}
        
        CATEGORIES LIST:
        {CATEGORIES}

        FIELDS TO EXTRACT:
        - date: the date the document was published or written
        - subject: the topic or reason for this letter
        - summary: - summary: a concise 3-5 line prose summary of the document body only. 
                    Do not repeat the date, sender name, receiver, or subject — those are captured separately. 
                    Focus on the core issue, context, and what action is being requested.
                    Write as flowing prose, not numbered points or bullet points.
        - department: the MCL department this document belongs to, chosen strictly from the DEPARTMENTS LIST above
        - category: the type of document, chosen strictly from the CATEGORIES LIST above
        - sender_name: full name of the sender
        - sender_contact: phone or email of the sender if mentioned, otherwise null
        - receiver: full name or designation of the receiver
        - reference_number: the document reference number if present, otherwise null

        RULES:
        - If a field is not found in the document after careful reading, return null for that field
        - Do not invent or guess any information
        - Department must be chosen from the provided list only. If no match found, return null
        - Category must be chosen from the provided list only. If no match found, return null
        - Return only a valid JSON object, no explanation, no extra text, no markdown code fences

        DOCUMENT TEXT:
        {ocr_output}

        Return this exact JSON structure:
        {{
            "date": "",
            "subject": "",
            "summary": "",
            "department": "",
            "category":"",
            "sender_name": "",
            "sender_contact": null,
            "receiver": "",
            "reference_number": null
        }}"""

    response = anthropic_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text
    logger.info(f"Claude raw response:\n{raw}")

    # strip markdown code fences if present
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    try:
        llm_output = json.loads(cleaned)
        logger.info(f"Claude parsed output: {llm_output}")
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error: {e} | Raw: {raw}")
        llm_output = {"error": "Unable to parse Claude response as JSON.", "raw": raw}

    return llm_output