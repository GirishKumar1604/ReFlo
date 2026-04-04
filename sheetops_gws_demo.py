#!/usr/bin/env python3

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from copy import deepcopy
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen


DEFAULT_PROMPT = "We're behind on collections. Build today's collections queue and fix the follow-ups."
DEFAULT_PROMPT_PROFILE = {
    "business_context": "",
    "business_logic": "",
    "operating_style": "",
}
WATCH_POLL_RANGE = "A1:ZZ2000"
RAW_SHEET_NAME = "Receivables Raw"
PROPOSED_CHANGES_SHEET_NAME = "Proposed Changes"
COLLECTIONS_QUEUE_SHEET_NAME = "Collections Queue"
REPORT_SHEET_NAME = "Report"
ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
POLICY_MEMORY_PATH = ARTIFACTS_DIR / "policy_memory.json"
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"
DEFAULT_OPENAI_TIMEOUT_SECONDS = 180
LOCAL_ENV_PATH = Path(__file__).resolve().parent / ".env"


def load_local_env(path: Path = LOCAL_ENV_PATH) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or key in os.environ:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value


load_local_env()

MAPPING_SYSTEM_PROMPT = """
You are a spreadsheet operations AI for Accounts Receivable collections.
Task: map messy column headers to canonical business fields.
Return JSON only:
{
  "mapping": {
    "customer": "...",
    "invoice_amount": "...",
    "due_date": "...",
    "days_overdue": "...",
    "last_follow_up": "...",
    "owner": "...",
    "risk": "...",
    "status": "...",
    "region": "..."
  },
  "confidence": 0.0,
  "ambiguities": ["..."]
}
Rules:
- Mapping values must be exact header strings from the provided header list.
- Include only keys you are confident about.
- Do not invent headers.
""".strip()

ROW_REASONING_SYSTEM_PROMPT = """
You are an operations patch planner for AR collections.
Given normalized rows and an operator prompt, return row-level actions.
Return JSON only:
{
  "rows": [
    {
      "sheet_row_number": 2,
      "priority": "Critical|High|Medium|Low|Done",
      "assigned_owner": "...",
      "next_action": "...",
      "follow_up_eta": "YYYY-MM-DD|-",
      "reason": "...",
      "confidence": 0.0
    }
  ]
}
Rules:
- Keep output business-operational and actionable.
- Respect payment status: if paid, prefer Done/no action.
- Do not include fields outside the schema.
""".strip()

REVIEW_INTELLIGENCE_SYSTEM_PROMPT = """
You are reviewing operational spreadsheet patches before apply.
Return JSON only:
{
  "summary": "...",
  "risky_items": [
    {
      "patch_id": "...",
      "risk": "...",
      "tradeoff": "...",
      "review_focus": "..."
    }
  ]
}
Rules:
- Focus on risk, ambiguity, or business tradeoffs.
- Keep risky_items concise and high signal.
""".strip()

ANOMALY_SYSTEM_PROMPT = """
You are an AR operations analyst.
Find notable anomalies from receivables rows for executive review.
Return JSON only:
{
  "anomalies": [
    {
      "title": "...",
      "detail": "...",
      "severity": "high|medium|low"
    }
  ]
}
Rules:
- Focus on unusual collection risk signals.
- Keep titles short and details concrete.
- Max 8 anomalies.
""".strip()

DEMO_SECTOR_NAME = "Diagnostic Lab Network Receivables"
SAMPLE_ROW_COUNT = 180

SAMPLE_HEADERS = [
    "Invoice Ref",
    "Client Label",
    "Inv Amt (INR)",
    "Due Dt",
    "Days Late",
    "Last Touch",
    "Collector",
    "Payment Risk",
    "A/R State",
    "Region",
    "City Cluster",
    "Payer Type",
    "Test Mix",
    "Escalation Note",
    "Promised Dt",
]

DEMO_ACCOUNT_BASES = [
    "Aarohan Diagnostics",
    "Beacon Path Labs",
    "Crestline Imaging",
    "Drishti Molecular",
    "Everwell Pathology",
    "Frontier Radiology",
    "GenomeCare Labs",
    "Helix Preventive",
    "InSight Diagnostics",
    "Janani Path Network",
    "Keystone Imaging",
    "Lifespan Labs",
    "MetroScan Diagnostics",
    "Nucleus Path Services",
    "Optima Radiology",
    "PulsePoint Labs",
    "QuestBridge Imaging",
    "RapidSure Diagnostics",
    "Spectrum BioLabs",
    "TrueNorth Pathology",
]

DEMO_CITY_CLUSTERS = {
    "west": ["Mumbai", "Pune", "Ahmedabad", "Surat", "Nagpur"],
    "south": ["Bengaluru", "Chennai", "Hyderabad", "Coimbatore", "Kochi"],
    "north": ["Delhi", "Gurugram", "Noida", "Jaipur", "Lucknow"],
    "east": ["Kolkata", "Bhubaneswar", "Patna", "Ranchi", "Guwahati"],
}

DEMO_PAYER_TYPES = [
    "Hospital Chain",
    "Standalone Clinic",
    "Insurance TPA",
    "Corporate Wellness",
    "Diagnostic Franchise",
]

DEMO_TEST_MIXES = [
    "Routine Pathology",
    "Radiology Panels",
    "Oncology Markers",
    "Preventive Health",
    "Microbiology",
    "Cardiac Panels",
]

DEMO_COLLECTORS = ["Riya", "Arjun", "Megha", "Karan", "Sana", "Vikram", "", ""]

COLUMN_SYNONYMS = {
    "customer": {"customer", "client", "client label", "account", "account name", "company"},
    "invoice_amount": {"invoice amount", "inv amt", "inv amt inr", "amount", "amount due", "amt due", "invoice value"},
    "due_date": {"due date", "due dt", "payment due", "due"},
    "days_overdue": {"days overdue", "days late", "overdue days", "days past due", "late days"},
    "last_follow_up": {"last follow-up", "last follow up", "last touch", "last reminder", "last contact"},
    "owner": {"owner", "collector", "agent", "assigned to", "account manager"},
    "risk": {"risk", "payment risk", "collection risk", "churn risk"},
    "status": {"status", "payment status", "a/r state", "a r state", "state"},
    "region": {"region", "territory", "zone"},
}

PATCHABLE_LOGICAL_FIELDS = [
    "owner",
    "status",
    "priority",
    "assigned_owner",
    "next_action",
    "follow_up_eta",
    "reason",
    "projected_recoverable_cash",
]

CANONICAL_COLUMNS = {
    "priority": "Priority",
    "assigned_owner": "Assigned Owner",
    "next_action": "Next Action",
    "follow_up_eta": "Follow-up ETA",
    "reason": "Reason",
    "projected_recoverable_cash": "Projected Recoverable Cash",
}

REGION_OWNER_FALLBACK = {
    "west": "Riya",
    "south": "Arjun",
    "north": "Megha",
    "east": "Karan",
}

PRIORITY_ORDER = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1, "Done": 0}


def build_sample_rows(row_count: int = SAMPLE_ROW_COUNT, anchor: date | None = None) -> list[list[Any]]:
    anchor = anchor or date.today()
    regions = list(REGION_OWNER_FALLBACK.keys())
    rows: list[list[Any]] = []

    for idx in range(row_count):
        region = regions[idx % len(regions)]
        city = DEMO_CITY_CLUSTERS[region][(idx // len(regions)) % len(DEMO_CITY_CLUSTERS[region])]
        account_base = DEMO_ACCOUNT_BASES[idx % len(DEMO_ACCOUNT_BASES)]
        customer = f"{account_base} {city}"
        payer_type = DEMO_PAYER_TYPES[idx % len(DEMO_PAYER_TYPES)]
        test_mix = DEMO_TEST_MIXES[(idx * 2) % len(DEMO_TEST_MIXES)]
        invoice_ref = f"DL-AR-{anchor.year % 100:02d}-{1001 + idx}"

        amount = 28000 + (idx % 9) * 14500 + (idx % 5) * 6200 + (idx // 6) * 1800
        collector = DEMO_COLLECTORS[idx % len(DEMO_COLLECTORS)]

        if idx % 19 == 0:
            status = "Paid"
            risk = "Low"
            days_late = 0
            last_touch_gap = 1
            escalation_note = "Closed after remittance confirmation"
            promised_date = ""
            if not collector:
                collector = "Riya"
        elif idx % 17 == 0:
            status = "Disputed"
            risk = "High"
            days_late = 34 + (idx % 21)
            last_touch_gap = 11 + (idx % 5)
            escalation_note = "Rate mismatch on bundled diagnostics"
            promised_date = ""
        elif idx % 11 == 0:
            status = "Promise to Pay"
            risk = "Medium"
            days_late = 14 + (idx % 13)
            last_touch_gap = 3 + (idx % 4)
            escalation_note = "Finance SPOC promised release this week"
            promised_date = (anchor + timedelta(days=(idx % 4) + 1)).isoformat()
        elif idx % 7 == 0:
            status = "Partial Payment"
            risk = "Medium"
            days_late = 18 + (idx % 11)
            last_touch_gap = 5 + (idx % 6)
            escalation_note = "Part-payment posted, balance still open"
            promised_date = (anchor + timedelta(days=(idx % 6) + 2)).isoformat()
        else:
            status = "Overdue"
            risk = "High" if idx % 5 == 0 else "Medium" if idx % 3 == 0 else "Low"
            days_late = 6 + ((idx * 3) % 41)
            last_touch_gap = 2 + (idx % 9)
            escalation_note = "No payment confirmation from accounts team"
            promised_date = ""

        if idx % 8 == 0:
            collector = ""
        if idx % 10 == 0 and status == "Overdue":
            last_touch = ""
        else:
            last_touch = (anchor - timedelta(days=last_touch_gap)).isoformat()

        due_date = (anchor - timedelta(days=days_late)).isoformat()
        rows.append(
            [
                invoice_ref,
                customer,
                amount,
                due_date,
                days_late,
                last_touch,
                collector,
                risk,
                status,
                region.title(),
                city,
                payer_type,
                test_mix,
                escalation_note,
                promised_date,
            ]
        )

    return rows


@dataclass
class RowPlan:
    row_index: int
    sheet_row_number: int
    customer: str
    invoice_amount: float
    days_overdue: int
    risk: str
    normalized_status: str
    priority: str
    assigned_owner: str
    next_action: str
    follow_up_eta: str
    reason: str
    projected_recoverable_cash: int
    rule: str
    confidence: float


@dataclass
class Patch:
    patch_id: str
    row_index: int
    sheet_row_number: int
    customer: str
    field: str
    before: str
    after: str
    reason: str
    rule: str
    confidence: float
    projected_impact: int
    risk_level: str = "medium"
    is_data_cleanup: bool = False
    review_note: str = ""
    context_status: str = "new"


def run_gws(*parts: str, params: dict[str, Any] | None = None, body: dict[str, Any] | None = None) -> dict[str, Any]:
    cmd = ["gws", *parts]
    if params is not None:
        cmd.extend(["--params", json.dumps(params)])
    if body is not None:
        cmd.extend(["--json", json.dumps(body)])

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        message = "\n".join(item for item in [stderr, stdout] if item) or "gws command failed"
        raise RuntimeError(message)

    payload = extract_json(result.stdout)
    if payload is None:
        raise RuntimeError(f"Could not parse JSON from gws output:\n{result.stdout}")
    return payload


def extract_json(stdout: str) -> dict[str, Any] | list[Any] | None:
    start = stdout.find("{")
    if start == -1:
        start = stdout.find("[")
    if start == -1:
        return None
    return json.loads(stdout[start:])


def normalize_header(header: str) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in str(header)).split())


def normalize_spreadsheet_id(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""

    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9\-_]+)", raw)
    if match:
        return match.group(1)

    return raw


def ai_enabled() -> bool:
    return bool(os.getenv("OPENAI_API_KEY", "").strip())


def require_ai_configured() -> None:
    if ai_enabled():
        return
    raise RuntimeError(
        "OpenAI is required for proposal generation. Set OPENAI_API_KEY in your environment or repo .env file and restart the server."
    )


def openai_model() -> str:
    return os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL).strip() or DEFAULT_OPENAI_MODEL


def openai_timeout_seconds() -> int:
    raw = os.getenv("OPENAI_TIMEOUT_SECONDS", "").strip()
    try:
        value = int(raw) if raw else DEFAULT_OPENAI_TIMEOUT_SECONDS
    except ValueError:
        value = DEFAULT_OPENAI_TIMEOUT_SECONDS
    return max(value, 30)


def sanitize_prompt_profile(raw_profile: Any) -> dict[str, str]:
    if not isinstance(raw_profile, dict):
        return dict(DEFAULT_PROMPT_PROFILE)

    return {
        "business_context": str(raw_profile.get("business_context") or raw_profile.get("businessContext") or "").strip(),
        "business_logic": str(raw_profile.get("business_logic") or raw_profile.get("businessLogic") or "").strip(),
        "operating_style": str(raw_profile.get("operating_style") or raw_profile.get("operatingStyle") or "").strip(),
    }


def compose_effective_prompt(prompt: str, prompt_profile: dict[str, str] | None = None) -> str:
    normalized_prompt = str(prompt or "").strip() or DEFAULT_PROMPT
    profile = sanitize_prompt_profile(prompt_profile)
    sections = [normalized_prompt]

    if profile["business_context"]:
        sections.append(f"Business context:\n{profile['business_context']}")
    if profile["business_logic"]:
        sections.append(f"Business logic and SOP:\n{profile['business_logic']}")
    if profile["operating_style"]:
        sections.append(f"Employee operating style:\n{profile['operating_style']}")

    return "\n\n".join(sections)


def assess_prompt_specificity(prompt: str, prompt_profile: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized_prompt = str(prompt or "").strip()
    profile = sanitize_prompt_profile(prompt_profile)
    words = re.findall(r"[a-z0-9]+", normalized_prompt.lower())
    has_profile = any(profile.values())
    action_tokens = {
        "prioritize",
        "build",
        "fix",
        "escalate",
        "queue",
        "assign",
        "collect",
        "follow",
        "recover",
        "risk",
        "overdue",
        "dispute",
        "owner",
    }
    has_action_signal = any(token in action_tokens for token in words)
    needs_decision = False
    details: list[str] = []

    if len(words) < 7:
        needs_decision = True
        details.append("Prompt is short and may not set optimization priority.")
    if not has_action_signal:
        needs_decision = True
        details.append("Prompt does not clearly specify an operational objective.")
    if has_profile:
        needs_decision = bool(len(words) < 5)
        if needs_decision and not details:
            details.append("Task prompt is too short even with business context configured.")

    details = details[:3]
    return {
        "needs_decision": needs_decision,
        "details": details,
    }


def parse_embedded_json(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        raise RuntimeError("Empty AI response.")

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise RuntimeError("Could not parse JSON object from AI response.")

    candidate = text[start : end + 1]
    parsed = json.loads(candidate)
    if not isinstance(parsed, dict):
        raise RuntimeError("AI response was not a JSON object.")
    return parsed


def call_openai_json(system_prompt: str, payload: dict[str, Any], temperature: float = 0.1) -> dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    body = {
        "model": openai_model(),
        "temperature": temperature,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=True)},
        ],
    }
    data = json.dumps(body).encode("utf-8")
    request = Request(
        OPENAI_API_URL,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=openai_timeout_seconds()) as response:  # noqa: S310
            raw = response.read().decode("utf-8")
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"OpenAI API request failed: {exc}") from exc

    parsed = json.loads(raw)
    choices = parsed.get("choices", [])
    if not choices:
        raise RuntimeError("OpenAI API returned no choices.")

    content = choices[0].get("message", {}).get("content", "")
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return parse_embedded_json(content)


def load_policy_memory() -> dict[str, Any]:
    ensure_artifacts_dir()
    if not POLICY_MEMORY_PATH.exists():
        return {
            "total_proposals": 0,
            "total_applies": 0,
            "total_selected": 0,
            "total_rejected": 0,
            "field_stats": {},
            "updated_at": None,
        }

    try:
        parsed = json.loads(POLICY_MEMORY_PATH.read_text(encoding="utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("invalid policy payload")
        parsed.setdefault("field_stats", {})
        return parsed
    except Exception:  # noqa: BLE001
        return {
            "total_proposals": 0,
            "total_applies": 0,
            "total_selected": 0,
            "total_rejected": 0,
            "field_stats": {},
            "updated_at": None,
        }


def save_policy_memory(policy: dict[str, Any]) -> None:
    ensure_artifacts_dir()
    POLICY_MEMORY_PATH.write_text(json.dumps(policy, indent=2, ensure_ascii=True), encoding="utf-8")


def policy_hints(policy: dict[str, Any]) -> list[dict[str, Any]]:
    field_stats = policy.get("field_stats", {})
    hints: list[dict[str, Any]] = []
    for field, stats in field_stats.items():
        selected = int(stats.get("selected", 0))
        rejected = int(stats.get("rejected", 0))
        total = selected + rejected
        if total == 0:
            continue
        hints.append(
            {
                "field": field,
                "acceptance_rate": round(selected / total, 3),
                "selected": selected,
                "rejected": rejected,
            }
        )
    hints.sort(key=lambda item: item["acceptance_rate"], reverse=True)
    return hints[:8]


def map_headers(headers: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    canonical_headers = {header: normalize_header(header) for header in headers}

    for logical_name, synonyms in COLUMN_SYNONYMS.items():
        for actual_header, normalized in canonical_headers.items():
            if normalized in synonyms:
                mapping[logical_name] = actual_header
                break

    required = {"customer", "invoice_amount"}
    missing = sorted(required - set(mapping))
    if missing:
        raise RuntimeError(f"Could not map required columns: {', '.join(missing)}")

    return mapping


def validate_ai_mapping(headers: list[str], candidate: dict[str, Any], fallback: dict[str, str]) -> dict[str, str]:
    valid_headers = set(headers)
    validated = dict(fallback)

    for logical_name in COLUMN_SYNONYMS:
        proposed = candidate.get(logical_name)
        if isinstance(proposed, str) and proposed in valid_headers:
            validated[logical_name] = proposed

    required = {"customer", "invoice_amount"}
    if not required.issubset(set(validated)):
        return fallback
    return validated


def map_headers_with_ai(
    headers: list[str],
    rows: list[dict[str, Any]],
    prompt: str,
    policy: dict[str, Any],
    workflow_context: dict[str, Any] | None = None,
    require_ai: bool = False,
) -> tuple[dict[str, str], dict[str, Any]]:
    fallback = map_headers(headers)
    meta = {
        "source": "rules",
        "confidence": 0.72,
        "ambiguities": [],
        "error": None,
    }

    if not ai_enabled():
        if require_ai:
            require_ai_configured()
        return fallback, meta

    sample_rows = rows[:5]
    payload = {
        "task": "Map messy headers to canonical AR fields for patch planning.",
        "operator_prompt": prompt,
        "headers": headers,
        "sample_rows": sample_rows,
        "canonical_fields": list(COLUMN_SYNONYMS.keys()),
        "policy_hints": policy_hints(policy),
        "workflow_context": workflow_context or {},
    }

    try:
        ai_result = call_openai_json(MAPPING_SYSTEM_PROMPT, payload, temperature=0.0)
        ai_mapping_raw = ai_result.get("mapping", {})
        if not isinstance(ai_mapping_raw, dict):
            ai_mapping_raw = {}
        mapping = validate_ai_mapping(headers, ai_mapping_raw, fallback)
        confidence = float(ai_result.get("confidence", 0.75))
        ambiguities = ai_result.get("ambiguities", [])
        if not isinstance(ambiguities, list):
            ambiguities = []
        return mapping, {
            "source": "ai+rules",
            "confidence": max(0.0, min(confidence, 1.0)),
            "ambiguities": [str(item) for item in ambiguities[:8]],
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        if require_ai:
            raise RuntimeError(f"OpenAI header mapping failed: {exc}") from exc
        meta["error"] = str(exc)
        return fallback, meta


def parse_dateish(value: Any) -> date | None:
    if isinstance(value, (int, float)):
        base = date(1899, 12, 30)
        return date.fromordinal(base.toordinal() + int(value))

    text = str(value or "").strip()
    if not text:
        return None

    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%d-%b-%y", "%d-%b-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_number(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip().replace(",", "").replace("₹", "")
    if not text:
        return 0.0
    return float(text)


def parse_days_overdue(row: dict[str, Any], mapping: dict[str, str]) -> int:
    direct_header = mapping.get("days_overdue")
    if direct_header:
        value = row.get(direct_header, "")
        if str(value).strip():
            return int(float(value))

    due_header = mapping.get("due_date")
    due_date = parse_dateish(row.get(due_header, "")) if due_header else None
    if due_date is None:
        return 0
    return max((date.today() - due_date).days, 0)


def normalize_status(value: str) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return "Overdue"
    if any(token in raw for token in ["paid", "settled", "closed"]):
        return "Paid"
    if "promise" in raw:
        return "Promise to Pay"
    if "disput" in raw:
        return "Disputed"
    if "partial" in raw:
        return "Partial Payment"
    if any(token in raw for token in ["await", "open", "overdue", "escalat"]):
        return "Overdue"
    return "Overdue"


def classify_priority(score: float) -> str:
    if score >= 78:
        return "Critical"
    if score >= 52:
        return "High"
    if score >= 30:
        return "Medium"
    return "Low"


def projected_recoverable_cash(amount: float, priority: str) -> int:
    multipliers = {
        "Critical": 0.84,
        "High": 0.70,
        "Medium": 0.52,
        "Low": 0.28,
        "Done": 0.0,
    }
    return int(round(amount * multipliers[priority]))


def owner_fallback(region_value: str) -> str:
    return REGION_OWNER_FALLBACK.get(str(region_value or "").strip().lower(), "Collections Queue")


def plan_row(row: dict[str, Any], mapping: dict[str, str], row_index: int, prompt: str) -> RowPlan:
    customer = str(row.get(mapping["customer"], "")).strip() or "Unknown account"
    amount = parse_number(row.get(mapping["invoice_amount"], 0))
    days_late = parse_days_overdue(row, mapping)

    owner_header = mapping.get("owner")
    risk_header = mapping.get("risk")
    status_header = mapping.get("status")
    last_follow_up_header = mapping.get("last_follow_up")
    region_header = mapping.get("region")

    owner = str(row.get(owner_header, "")).strip() if owner_header else ""
    risk = str(row.get(risk_header, "Medium")).strip().title() if risk_header else "Medium"
    region = str(row.get(region_header, "")).strip() if region_header else ""
    normalized = normalize_status(row.get(status_header, "") if status_header else "")

    if normalized == "Paid":
        return RowPlan(
            row_index=row_index,
            sheet_row_number=row_index + 2,
            customer=customer,
            invoice_amount=amount,
            days_overdue=days_late,
            risk=risk,
            normalized_status="Paid",
            priority="Done",
            assigned_owner=owner or "-",
            next_action="No action",
            follow_up_eta="-",
            reason="Invoice already settled.",
            projected_recoverable_cash=0,
            rule="skip_settled",
            confidence=0.98,
        )

    last_touch = parse_dateish(row.get(last_follow_up_header, "")) if last_follow_up_header else None
    last_touch_gap = (date.today() - last_touch).days if last_touch else 999

    score = min(days_late, 60) * 1.5
    score += min(amount / 12000, 28)
    score += {"High": 24, "Medium": 12, "Low": 5}.get(risk, 10)
    if last_touch_gap >= 10:
        score += 16
    elif last_touch_gap >= 5:
        score += 8
    if not owner:
        score += 12
    if normalized == "Disputed":
        score += 6

    priority = classify_priority(score)
    assigned_owner = owner or owner_fallback(region)

    if normalized == "Disputed":
        next_action = "Call finance and log dispute blocker"
    elif priority in {"Critical", "High"}:
        next_action = "Call today and secure payment date"
    elif priority == "Medium":
        next_action = "Send reminder and confirm payment timeline"
    else:
        next_action = "Send gentle reminder and monitor"

    eta_days = {
        "Critical": 1,
        "High": 2,
        "Medium": 3,
        "Low": 5,
    }[priority]
    eta = (date.today() + timedelta(days=eta_days)).isoformat()

    reason_bits = [f"{days_late} days overdue", f"₹{int(amount):,} open"]
    reason_bits.append(f"{risk} risk")
    if last_touch_gap >= 5:
        reason_bits.append(f"last follow-up {last_touch_gap} days ago")
    if not owner:
        reason_bits.append("missing owner")
    if normalized == "Disputed":
        reason_bits.append("requires dispute closure")

    reason = "; ".join(reason_bits)
    projected_cash = projected_recoverable_cash(amount, priority)

    rule = "ar_collections_priority_pack"
    if not owner:
        rule = "ar_owner_assignment_and_priority_pack"

    confidence = 0.74
    if priority in {"Critical", "High"}:
        confidence = 0.88
    if normalized == "Disputed":
        confidence = 0.81

    return RowPlan(
        row_index=row_index,
        sheet_row_number=row_index + 2,
        customer=customer,
        invoice_amount=amount,
        days_overdue=days_late,
        risk=risk,
        normalized_status=normalized,
        priority=priority,
        assigned_owner=assigned_owner,
        next_action=next_action,
        follow_up_eta=eta,
        reason=reason,
        projected_recoverable_cash=projected_cash,
        rule=rule,
        confidence=confidence,
    )


def apply_ai_row_overrides(plans: list[RowPlan], ai_rows: list[dict[str, Any]]) -> list[RowPlan]:
    by_row = {plan.sheet_row_number: plan for plan in plans}
    allowed_priorities = {"Critical", "High", "Medium", "Low", "Done"}

    for item in ai_rows:
        if not isinstance(item, dict):
            continue
        try:
            row_number = int(item.get("sheet_row_number"))
        except Exception:  # noqa: BLE001
            continue

        current = by_row.get(row_number)
        if current is None:
            continue

        priority = str(item.get("priority", current.priority)).strip().title()
        if priority not in allowed_priorities:
            priority = current.priority

        assigned_owner = str(item.get("assigned_owner", current.assigned_owner)).strip() or current.assigned_owner
        next_action = str(item.get("next_action", current.next_action)).strip() or current.next_action
        follow_up_eta = str(item.get("follow_up_eta", current.follow_up_eta)).strip() or current.follow_up_eta
        reason = str(item.get("reason", current.reason)).strip() or current.reason
        confidence_raw = item.get("confidence", current.confidence)
        try:
            confidence = max(0.0, min(float(confidence_raw), 1.0))
        except Exception:  # noqa: BLE001
            confidence = current.confidence

        projected_cash = projected_recoverable_cash(current.invoice_amount, priority) if priority != "Done" else 0
        by_row[row_number] = RowPlan(
            row_index=current.row_index,
            sheet_row_number=current.sheet_row_number,
            customer=current.customer,
            invoice_amount=current.invoice_amount,
            days_overdue=current.days_overdue,
            risk=current.risk,
            normalized_status=current.normalized_status,
            priority=priority,
            assigned_owner=assigned_owner,
            next_action=next_action if priority != "Done" else "No action",
            follow_up_eta=follow_up_eta if priority != "Done" else "-",
            reason=reason,
            projected_recoverable_cash=projected_cash,
            rule="ai_row_reasoning_v1",
            confidence=confidence,
        )

    return [by_row[plan.sheet_row_number] for plan in plans]


def refine_plans_with_ai(
    plans: list[RowPlan],
    rows: list[dict[str, Any]],
    mapping: dict[str, str],
    prompt: str,
    policy: dict[str, Any],
    workflow_context: dict[str, Any] | None = None,
    require_ai: bool = False,
) -> tuple[list[RowPlan], dict[str, Any]]:
    meta = {
        "source": "rules",
        "error": None,
    }
    if not ai_enabled():
        if require_ai:
            require_ai_configured()
        return plans, meta

    owner_header = mapping.get("owner")
    status_header = mapping.get("status")
    payload_rows: list[dict[str, Any]] = []
    for plan in plans:
        source_row = rows[plan.row_index]
        payload_rows.append(
            {
                "sheet_row_number": plan.sheet_row_number,
                "customer": plan.customer,
                "invoice_amount": plan.invoice_amount,
                "days_overdue": plan.days_overdue,
                "risk": plan.risk,
                "status": str(source_row.get(status_header, "")) if status_header else "",
                "owner": str(source_row.get(owner_header, "")) if owner_header else "",
                "baseline": {
                    "priority": plan.priority,
                    "assigned_owner": plan.assigned_owner,
                    "next_action": plan.next_action,
                    "follow_up_eta": plan.follow_up_eta,
                    "reason": plan.reason,
                    "confidence": plan.confidence,
                },
            }
        )

    payload = {
        "task": "Return row-level operational patch decisions for AR collections.",
        "operator_prompt": prompt,
        "rows": payload_rows,
        "policy_hints": policy_hints(policy),
        "workflow_context": workflow_context or {},
    }

    try:
        ai_result = call_openai_json(ROW_REASONING_SYSTEM_PROMPT, payload, temperature=0.0)
        ai_rows = ai_result.get("rows", [])
        if not isinstance(ai_rows, list):
            ai_rows = []
        refined = apply_ai_row_overrides(plans, ai_rows)
        return refined, {"source": "ai+rules", "error": None}
    except Exception as exc:  # noqa: BLE001
        if require_ai:
            raise RuntimeError(f"OpenAI row reasoning failed: {exc}") from exc
        meta["error"] = str(exc)
        return plans, meta


def build_review_intelligence(
    patches: list[Patch],
    prompt: str,
    policy: dict[str, Any],
    workflow_context: dict[str, Any] | None = None,
    require_ai: bool = False,
) -> dict[str, Any]:
    fallback = {
        "summary": "Review rows with low confidence or high projected impact first.",
        "risky_items": [
            {
                "patch_id": patch.patch_id,
                "risk": "Lower confidence recommendation",
                "tradeoff": "Could be valid, but needs human context check.",
                "review_focus": f"Verify {patch.field} change for {patch.customer}.",
            }
            for patch in sorted(patches, key=lambda item: item.confidence)[:5]
            if patch.confidence < 0.8
        ],
    }

    if not patches:
        return fallback
    if not ai_enabled():
        if require_ai:
            require_ai_configured()
        return fallback

    payload = {
        "task": "Highlight risky patches and review tradeoffs before apply.",
        "operator_prompt": prompt,
        "patches": [asdict(patch) for patch in sorted(patches, key=lambda item: item.projected_impact, reverse=True)[:30]],
        "policy_hints": policy_hints(policy),
        "workflow_context": workflow_context or {},
    }

    try:
        ai_result = call_openai_json(REVIEW_INTELLIGENCE_SYSTEM_PROMPT, payload, temperature=0.0)
        risky_items = ai_result.get("risky_items", [])
        if not isinstance(risky_items, list):
            risky_items = []
        valid_patch_ids = {patch.patch_id for patch in patches}
        cleaned_items: list[dict[str, str]] = []
        for item in risky_items:
            if not isinstance(item, dict):
                continue
            patch_id = str(item.get("patch_id", "")).strip()
            if patch_id and patch_id not in valid_patch_ids:
                continue
            cleaned_items.append(
                {
                    "patch_id": patch_id or "general",
                    "risk": str(item.get("risk", "")).strip() or "Potential ambiguity",
                    "tradeoff": str(item.get("tradeoff", "")).strip() or "Needs human confirmation.",
                    "review_focus": str(item.get("review_focus", "")).strip() or "Review before apply.",
                }
            )
            if len(cleaned_items) >= 8:
                break

        summary = str(ai_result.get("summary", "")).strip() or fallback["summary"]
        return {"summary": summary, "risky_items": cleaned_items}
    except Exception as exc:  # noqa: BLE001
        if require_ai:
            raise RuntimeError(f"OpenAI review analysis failed: {exc}") from exc
        return fallback


def classify_patch_risk(field: str, confidence: float, projected_impact: int, is_cleanup: bool) -> tuple[str, str]:
    if confidence < 0.72 or projected_impact >= 180000:
        return "high", "High business impact or lower confidence; review carefully."
    if is_cleanup and confidence >= 0.82:
        return "low", "Likely low-risk data cleanup."
    if confidence >= 0.9:
        return "low", "High-confidence recommendation."
    return "medium", "Reasonable recommendation; spot-check before apply."


def calculate_kpis(plans: list[RowPlan]) -> dict[str, int]:
    open_plans = [plan for plan in plans if plan.priority != "Done"]
    total_outstanding = int(sum(plan.invoice_amount for plan in open_plans))
    at_risk = int(sum(plan.invoice_amount for plan in open_plans if plan.days_overdue >= 30))
    projected_recovery = int(sum(plan.projected_recoverable_cash for plan in open_plans if plan.priority in {"Critical", "High", "Medium"}))
    return {
        "total_outstanding": total_outstanding,
        "at_risk": at_risk,
        "projected_recovery": projected_recovery,
    }


def build_health_meter(kpis: dict[str, int]) -> dict[str, Any]:
    total = max(kpis.get("total_outstanding", 0), 1)
    at_risk_ratio = kpis.get("at_risk", 0) / total
    recovery_ratio = kpis.get("projected_recovery", 0) / total
    score = int(round(max(0.0, min(1.0, 0.55 - at_risk_ratio + recovery_ratio)) * 100))

    if score >= 70:
        status = "green"
        label = "Healthy"
    elif score >= 45:
        status = "yellow"
        label = "Watch"
    else:
        status = "red"
        label = "At Risk"

    return {
        "score": score,
        "status": status,
        "label": label,
    }


def build_aging_buckets(plans: list[RowPlan]) -> list[dict[str, Any]]:
    buckets = {
        "0-30": 0,
        "31-60": 0,
        "61+": 0,
    }
    for plan in plans:
        if plan.priority == "Done":
            continue
        amount = int(plan.invoice_amount)
        if plan.days_overdue <= 30:
            buckets["0-30"] += amount
        elif plan.days_overdue <= 60:
            buckets["31-60"] += amount
        else:
            buckets["61+"] += amount

    return [{"bucket": key, "amount": value} for key, value in buckets.items()]


def build_anomalies(
    plans: list[RowPlan],
    prompt: str,
    policy: dict[str, Any],
    workflow_context: dict[str, Any] | None = None,
    require_ai: bool = False,
) -> list[dict[str, str]]:
    fallback: list[dict[str, str]] = []
    for plan in sorted(plans, key=lambda item: (item.days_overdue, item.invoice_amount), reverse=True):
        if plan.priority == "Done":
            continue
        if plan.days_overdue >= 45:
            fallback.append(
                {
                    "title": f"{plan.customer}: long overdue",
                    "detail": f"{plan.days_overdue} days overdue with ₹{int(plan.invoice_amount):,} open.",
                    "severity": "high",
                }
            )
        elif plan.days_overdue >= 25 and plan.invoice_amount >= 100000:
            fallback.append(
                {
                    "title": f"{plan.customer}: high-value delay",
                    "detail": f"₹{int(plan.invoice_amount):,} overdue for {plan.days_overdue} days.",
                    "severity": "medium",
                }
            )
        if len(fallback) >= 6:
            break

    if not ai_enabled():
        if require_ai:
            require_ai_configured()
        return fallback

    payload = {
        "task": "Find anomalies in receivables for executive dashboard.",
        "operator_prompt": prompt,
        "rows": [asdict(plan) for plan in plans],
        "policy_hints": policy_hints(policy),
        "workflow_context": workflow_context or {},
    }
    try:
        ai_result = call_openai_json(ANOMALY_SYSTEM_PROMPT, payload, temperature=0.0)
        anomalies = ai_result.get("anomalies", [])
        if not isinstance(anomalies, list):
            return fallback
        cleaned: list[dict[str, str]] = []
        for item in anomalies:
            if not isinstance(item, dict):
                continue
            severity = str(item.get("severity", "medium")).lower()
            if severity not in {"high", "medium", "low"}:
                severity = "medium"
            cleaned.append(
                {
                    "title": str(item.get("title", "")).strip() or "Anomaly detected",
                    "detail": str(item.get("detail", "")).strip() or "Review row-level risk before apply.",
                    "severity": severity,
                }
            )
            if len(cleaned) >= 8:
                break
        return cleaned or fallback
    except Exception as exc:  # noqa: BLE001
        if require_ai:
            raise RuntimeError(f"OpenAI anomaly analysis failed: {exc}") from exc
        return fallback


def build_row_dicts(values: list[list[Any]]) -> tuple[list[str], list[dict[str, Any]]]:
    if not values:
        raise RuntimeError("The target sheet is empty.")

    headers = [str(item).strip() for item in values[0]]
    rows: list[dict[str, Any]] = []
    for raw_row in values[1:]:
        padded = list(raw_row) + [""] * max(0, len(headers) - len(raw_row))
        rows.append({headers[idx]: padded[idx] for idx in range(len(headers))})
    return headers, rows


def build_patches_from_plans(rows: list[dict[str, Any]], mapping: dict[str, str], plans: list[RowPlan]) -> list[Patch]:
    patches: list[Patch] = []
    for plan in plans:
        row = rows[plan.row_index]

        if plan.priority == "Done":
            continue

        owner_header = mapping.get("owner")
        status_header = mapping.get("status")

        core_target_fields = {
            owner_header if owner_header else CANONICAL_COLUMNS["assigned_owner"]: plan.assigned_owner,
            status_header if status_header else "Normalized Status": plan.normalized_status,
            CANONICAL_COLUMNS["priority"]: plan.priority,
            CANONICAL_COLUMNS["assigned_owner"]: plan.assigned_owner,
            CANONICAL_COLUMNS["next_action"]: plan.next_action,
            CANONICAL_COLUMNS["follow_up_eta"]: plan.follow_up_eta,
            CANONICAL_COLUMNS["projected_recoverable_cash"]: str(plan.projected_recoverable_cash),
        }
        core_changed = any(
            str(row.get(field, "") or "").strip() != str(after_value).strip()
            for field, after_value in core_target_fields.items()
        )

        target_fields = dict(core_target_fields)
        reason_field = CANONICAL_COLUMNS["reason"]
        current_reason = str(row.get(reason_field, "") or "").strip()
        if core_changed or not current_reason:
            target_fields[reason_field] = plan.reason

        for field, after_value in target_fields.items():
            before_value = str(row.get(field, "") or "")
            after_text = str(after_value)
            if before_value.strip() == after_text.strip():
                continue

            patch_id = f"r{plan.sheet_row_number}-{normalize_header(field).replace(' ', '-') or 'field'}"
            owner_header_norm = normalize_header(owner_header or "")
            status_header_norm = normalize_header(status_header or "")
            field_norm = normalize_header(field)
            is_cleanup = field_norm in {
                owner_header_norm,
                status_header_norm,
                "assigned owner",
            }
            risk_level, review_note = classify_patch_risk(field, plan.confidence, plan.projected_recoverable_cash, is_cleanup)
            patches.append(
                Patch(
                    patch_id=patch_id,
                    row_index=plan.row_index,
                    sheet_row_number=plan.sheet_row_number,
                    customer=plan.customer,
                    field=field,
                    before=before_value,
                    after=after_text,
                    reason=plan.reason,
                    rule=plan.rule,
                    confidence=plan.confidence,
                    projected_impact=plan.projected_recoverable_cash,
                    risk_level=risk_level,
                    is_data_cleanup=is_cleanup,
                    review_note=review_note,
                )
            )

    return patches


def build_patch_set(headers: list[str], rows: list[dict[str, Any]], mapping: dict[str, str], prompt: str) -> tuple[list[Patch], list[RowPlan]]:
    plans: list[RowPlan] = []
    for row_index, row in enumerate(rows):
        plans.append(plan_row(row, mapping, row_index, prompt))
    patches = build_patches_from_plans(rows, mapping, plans)
    return patches, plans


def get_sheet_values(spreadsheet_id: str, range_name: str) -> list[list[Any]]:
    payload = run_gws(
        "sheets",
        "spreadsheets",
        "values",
        "get",
        params={
            "spreadsheetId": spreadsheet_id,
            "range": range_name,
            "valueRenderOption": "UNFORMATTED_VALUE",
        },
    )
    return payload.get("values", [])


def write_values(spreadsheet_id: str, range_name: str, values: list[list[Any]]) -> dict[str, Any]:
    return run_gws(
        "sheets",
        "spreadsheets",
        "values",
        "update",
        params={
            "spreadsheetId": spreadsheet_id,
            "range": range_name,
            "valueInputOption": "USER_ENTERED",
        },
        body={
            "majorDimension": "ROWS",
            "values": values,
        },
    )


def get_spreadsheet_metadata(spreadsheet_id: str) -> dict[str, Any]:
    return run_gws(
        "sheets",
        "spreadsheets",
        "get",
        params={
            "spreadsheetId": spreadsheet_id,
            "fields": "spreadsheetId,spreadsheetUrl,properties.title,sheets.properties",
        },
    )


def extract_sheet_titles(metadata: dict[str, Any]) -> list[str]:
    managed_tabs = {
        PROPOSED_CHANGES_SHEET_NAME,
        COLLECTIONS_QUEUE_SHEET_NAME,
        REPORT_SHEET_NAME,
    }
    titles: list[str] = []
    for sheet in metadata.get("sheets", []):
        props = sheet.get("properties", {}) if isinstance(sheet, dict) else {}
        title = str(props.get("title", "")).strip()
        if title and title not in managed_tabs:
            titles.append(title)
    return sorted(titles)


def build_source_snapshot(values: list[list[Any]], metadata: dict[str, Any]) -> dict[str, Any]:
    row_count = max(len(values) - 1, 0) if values else 0
    header_count = len(values[0]) if values else 0
    tab_titles = extract_sheet_titles(metadata)

    values_blob = json.dumps(values, ensure_ascii=True, separators=(",", ":"))
    tabs_blob = json.dumps(tab_titles, ensure_ascii=True, separators=(",", ":"))
    rows_hash = hashlib.sha1(values_blob.encode("utf-8")).hexdigest()
    tabs_hash = hashlib.sha1(tabs_blob.encode("utf-8")).hexdigest()
    signature = hashlib.sha1(f"{rows_hash}|{tabs_hash}".encode("utf-8")).hexdigest()

    return {
        "signature": signature,
        "row_count": row_count,
        "header_count": header_count,
        "tabs_hash": tabs_hash,
        "rows_hash": rows_hash,
        "tabs": tab_titles[:32],
    }


def classify_snapshot_change(previous: dict[str, Any] | None, current: dict[str, Any]) -> tuple[bool, str]:
    if not previous:
        return True, "No prior proposal snapshot found."

    prev_tabs_hash = str(previous.get("tabs_hash") or "")
    prev_row_count = int(previous.get("row_count") or 0)
    prev_signature = str(previous.get("signature") or "")

    if prev_tabs_hash != str(current.get("tabs_hash") or ""):
        return True, "Sheet tabs changed."
    if prev_row_count != int(current.get("row_count") or 0):
        return True, f"Row count changed ({prev_row_count} -> {int(current.get('row_count') or 0)})."
    if prev_signature != str(current.get("signature") or ""):
        return True, "Row values changed."
    return False, "No new rows or tab changes detected."


def batch_update(spreadsheet_id: str, requests: list[dict[str, Any]]) -> dict[str, Any]:
    return run_gws(
        "sheets",
        "spreadsheets",
        "batchUpdate",
        params={"spreadsheetId": spreadsheet_id},
        body={"requests": requests},
    )


def ensure_sheet(spreadsheet_id: str, sheet_name: str) -> None:
    metadata = get_spreadsheet_metadata(spreadsheet_id)
    sheet_names = {
        sheet["properties"]["title"]
        for sheet in metadata.get("sheets", [])
        if "properties" in sheet
    }
    if sheet_name in sheet_names:
        return

    batch_update(
        spreadsheet_id,
        [{"addSheet": {"properties": {"title": sheet_name, "gridProperties": {"rowCount": 1000, "columnCount": 26}}}}],
    )


def rename_default_sheet(spreadsheet_id: str, old_name: str, new_name: str) -> None:
    metadata = get_spreadsheet_metadata(spreadsheet_id)
    for sheet in metadata.get("sheets", []):
        props = sheet.get("properties", {})
        if props.get("title") == old_name:
            batch_update(
                spreadsheet_id,
                [
                    {
                        "updateSheetProperties": {
                            "properties": {"sheetId": props["sheetId"], "title": new_name},
                            "fields": "title",
                        }
                    }
                ],
            )
            return


def column_letter(index: int) -> str:
    result = ""
    current = index
    while current > 0:
        current, remainder = divmod(current - 1, 26)
        result = chr(65 + remainder) + result
    return result


def artifact_timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def ensure_artifacts_dir() -> None:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


def serialize_patches(patches: list[Patch]) -> list[dict[str, Any]]:
    return [asdict(patch) for patch in patches]


def serialize_plans(plans: list[RowPlan]) -> list[dict[str, Any]]:
    return [asdict(plan) for plan in plans]


def write_proposed_changes_tab(spreadsheet_id: str, patches: list[Patch]) -> None:
    ensure_sheet(spreadsheet_id, PROPOSED_CHANGES_SHEET_NAME)
    values: list[list[Any]] = [
        [
            "Patch ID",
            "Row",
            "Customer",
            "Field",
            "Before",
            "After",
            "Reason",
            "Rule",
            "Confidence",
            "Projected Impact",
            "Risk Level",
            "Data Cleanup",
            "Context Status",
            "Review Note",
        ]
    ]

    for patch in patches:
        values.append(
            [
                patch.patch_id,
                patch.sheet_row_number,
                patch.customer,
                patch.field,
                patch.before,
                patch.after,
                patch.reason,
                patch.rule,
                f"{patch.confidence:.2f}",
                patch.projected_impact,
                patch.risk_level,
                "Yes" if patch.is_data_cleanup else "No",
                patch.context_status,
                patch.review_note,
            ]
        )

    write_values(
        spreadsheet_id,
        f"{PROPOSED_CHANGES_SHEET_NAME}!A1:{column_letter(len(values[0]))}{len(values)}",
        values,
    )


def build_queue_rows(plans: list[RowPlan]) -> list[list[Any]]:
    actionable = [plan for plan in plans if plan.priority != "Done"]
    actionable.sort(
        key=lambda plan: (
            PRIORITY_ORDER.get(plan.priority, 0),
            plan.projected_recoverable_cash,
            plan.days_overdue,
        ),
        reverse=True,
    )

    values: list[list[Any]] = [
        [
            "Rank",
            "Customer",
            "Priority",
            "Assigned Owner",
            "Next Action",
            "Follow-up ETA",
            "Invoice Amount",
            "Days Overdue",
            "Payment Risk",
            "Reason",
            "Projected Recoverable Cash",
        ]
    ]

    for idx, plan in enumerate(actionable, start=1):
        values.append(
            [
                idx,
                plan.customer,
                plan.priority,
                plan.assigned_owner,
                plan.next_action,
                plan.follow_up_eta,
                int(plan.invoice_amount),
                plan.days_overdue,
                plan.risk,
                plan.reason,
                plan.projected_recoverable_cash,
            ]
        )

    return values


def build_report_values(prompt: str, applied_patches: list[dict[str, Any]], plans: list[RowPlan], rollback_path: str) -> list[list[Any]]:
    impacted_rows = {item["sheet_row_number"] for item in applied_patches}
    projected_cash = sum(plan.projected_recoverable_cash for plan in plans if plan.priority in {"Critical", "High", "Medium"})

    values: list[list[Any]] = [
        ["Prompt", prompt],
        ["Applied patch count", len(applied_patches)],
        ["Impacted accounts", len(impacted_rows)],
        ["Projected recoverable cash", projected_cash],
        ["Rollback instructions", f"Use artifact at {rollback_path} to revert before->after changes manually."],
        [],
        ["Patch ID", "Row", "Customer", "Field", "Before", "After", "Reason", "Rule", "Confidence", "Projected Impact"],
    ]

    for patch in applied_patches:
        values.append(
            [
                patch["patch_id"],
                patch["sheet_row_number"],
                patch["customer"],
                patch["field"],
                patch["before"],
                patch["after"],
                patch["reason"],
                patch["rule"],
                f"{float(patch['confidence']):.2f}",
                patch["projected_impact"],
            ]
        )

    return values


def build_row_values(headers: list[str], rows: list[dict[str, Any]]) -> list[list[Any]]:
    values = [headers]
    for row in rows:
        values.append([row.get(header, "") for header in headers])
    return values


def store_artifact(kind: str, payload: dict[str, Any]) -> Path:
    ensure_artifacts_dir()
    path = ARTIFACTS_DIR / f"{artifact_timestamp()}_{kind}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    return path


def list_proposal_artifacts() -> list[Path]:
    ensure_artifacts_dir()
    return sorted(ARTIFACTS_DIR.glob("*_proposal.json"), key=lambda item: item.stat().st_mtime, reverse=True)


def list_apply_artifacts() -> list[Path]:
    ensure_artifacts_dir()
    return sorted(ARTIFACTS_DIR.glob("*_apply.json"), key=lambda item: item.stat().st_mtime, reverse=True)


def extract_existing_proposed_patch_ids(values: list[list[Any]]) -> set[str]:
    if not values:
        return set()
    headers = [str(item).strip() for item in values[0]]
    try:
        idx = headers.index("Patch ID")
    except ValueError:
        return set()

    ids: set[str] = set()
    for row in values[1:]:
        if idx < len(row):
            value = str(row[idx]).strip()
            if value:
                ids.add(value)
    return ids


def get_context_from_previous_runs(spreadsheet_id: str, sheet_name: str) -> dict[str, Any]:
    context = {
        "existing_proposed_patch_ids": set(),
        "recently_applied_patch_ids": set(),
        "latest_apply_artifact": None,
        "latest_apply_at": None,
    }

    try:
        values = get_sheet_values(spreadsheet_id, f"{PROPOSED_CHANGES_SHEET_NAME}!A1:Z3000")
        context["existing_proposed_patch_ids"] = extract_existing_proposed_patch_ids(values)
    except Exception:
        context["existing_proposed_patch_ids"] = set()

    for path in list_apply_artifacts():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if payload.get("spreadsheet_id") != spreadsheet_id or payload.get("sheet_name") != sheet_name:
            continue
        selected_patch_ids = payload.get("selected_patch_ids", [])
        if not isinstance(selected_patch_ids, list):
            selected_patch_ids = []
        context["recently_applied_patch_ids"] = {str(item) for item in selected_patch_ids if str(item).strip()}
        context["latest_apply_artifact"] = str(path)
        context["latest_apply_at"] = payload.get("generated_at")
        break

    return context


def load_proposal_artifact(spreadsheet_id: str, sheet_name: str, proposal_id: str | None = None) -> tuple[dict[str, Any], Path]:
    proposals = list_proposal_artifacts()
    if not proposals:
        raise RuntimeError("No proposal artifacts found. Run propose first.")

    if proposal_id:
        normalized = proposal_id.strip()
        for path in proposals:
            stem = path.stem
            if normalized in {path.name, stem, stem.replace("_proposal", "")}:
                payload = json.loads(path.read_text(encoding="utf-8"))
                return payload, path
        raise RuntimeError(f"Could not find proposal artifact for id: {proposal_id}")

    for path in proposals:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("spreadsheet_id") == spreadsheet_id and payload.get("sheet_name") == sheet_name:
            return payload, path

    raise RuntimeError("No matching proposal artifact found for this spreadsheet and sheet.")


def build_preflight_decision(
    prompt: str,
    prompt_profile: dict[str, Any] | None,
    mapping_meta: dict[str, Any],
) -> dict[str, Any] | None:
    ambiguities = mapping_meta.get("ambiguities", [])
    if not isinstance(ambiguities, list):
        ambiguities = []

    confidence_raw = mapping_meta.get("confidence", 0.0)
    try:
        confidence = max(0.0, min(float(confidence_raw), 1.0))
    except Exception:  # noqa: BLE001
        confidence = 0.0

    source = str(mapping_meta.get("source") or "rules")
    if source == "ai+rules" and (ambiguities or confidence < 0.78):
        details = [f"Mapping confidence: {confidence:.2f}.", *[str(item) for item in ambiguities[:2]]]
        return {
            "reason": "mapping_ambiguity",
            "question": "Header mapping is ambiguous. Continue with best guess or refine first?",
            "details": details,
            "options": [
                {
                    "id": "proceed_best_guess",
                    "label": "Proceed with best guess",
                    "action": "proceed",
                    "recommended": True,
                },
                {
                    "id": "pause_refine",
                    "label": "Refine sheet headers first",
                    "action": "pause",
                    "recommended": False,
                },
            ],
        }

    prompt_assessment = assess_prompt_specificity(prompt, prompt_profile)
    if prompt_assessment["needs_decision"]:
        return {
            "reason": "prompt_underspecified",
            "question": "Need one decision: what should this run optimize first?",
            "details": prompt_assessment["details"],
            "options": [
                {
                    "id": "cash_recovery",
                    "label": "Cash recovery first",
                    "action": "apply_prompt_hint_and_proceed",
                    "prompt_hint": "Prioritize near-term cash recovery: escalate highest overdue and highest-value accounts first.",
                    "recommended": True,
                },
                {
                    "id": "data_hygiene",
                    "label": "Data quality first",
                    "action": "apply_prompt_hint_and_proceed",
                    "prompt_hint": "Prioritize data hygiene first: clean owner/status/follow-up fields before aggressive collections escalation.",
                    "recommended": False,
                },
            ],
        }

    return None


def preflight_sheet(
    spreadsheet_id: str,
    sheet_name: str,
    prompt: str,
    prompt_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    require_ai_configured()
    spreadsheet_id = normalize_spreadsheet_id(spreadsheet_id)
    sanitized_prompt_profile = sanitize_prompt_profile(prompt_profile)
    effective_prompt = compose_effective_prompt(prompt, sanitized_prompt_profile)
    values = get_sheet_values(spreadsheet_id, f"{sheet_name}!{WATCH_POLL_RANGE}")
    headers, row_dicts = build_row_dicts(values)
    policy = load_policy_memory()
    prior_context = get_context_from_previous_runs(spreadsheet_id, sheet_name)
    workflow_context = {
        "pending_patch_count": len(prior_context["existing_proposed_patch_ids"]),
        "recently_applied_patch_count": len(prior_context["recently_applied_patch_ids"]),
        "latest_apply_at": prior_context.get("latest_apply_at"),
        "latest_apply_artifact": prior_context.get("latest_apply_artifact"),
    }
    mapping, mapping_meta = map_headers_with_ai(
        headers,
        row_dicts,
        effective_prompt,
        policy,
        workflow_context,
        require_ai=True,
    )
    decision = build_preflight_decision(prompt, sanitized_prompt_profile, mapping_meta)

    return {
        "spreadsheet_id": spreadsheet_id,
        "sheet_name": sheet_name,
        "needs_decision": bool(decision),
        "decision": decision,
        "mapping_meta": mapping_meta,
        "mapped_fields": sorted(mapping.keys()),
        "effective_prompt_preview": effective_prompt[:1200],
    }


def watch_sheet(
    spreadsheet_id: str,
    sheet_name: str,
    prompt: str,
    prompt_profile: dict[str, Any] | None = None,
    auto_propose: bool = True,
) -> dict[str, Any]:
    spreadsheet_id = normalize_spreadsheet_id(spreadsheet_id)
    metadata = get_spreadsheet_metadata(spreadsheet_id)
    values = get_sheet_values(spreadsheet_id, f"{sheet_name}!{WATCH_POLL_RANGE}")
    current_snapshot = build_source_snapshot(values, metadata)

    previous_snapshot: dict[str, Any] | None = None
    latest_proposal_id: str | None = None
    try:
        proposal_payload, proposal_path = load_proposal_artifact(spreadsheet_id, sheet_name)
        latest_proposal_id = proposal_path.stem.replace("_proposal", "")
        candidate_snapshot = proposal_payload.get("source_snapshot")
        if isinstance(candidate_snapshot, dict):
            previous_snapshot = candidate_snapshot
    except Exception:
        previous_snapshot = None

    changed, change_reason = classify_snapshot_change(previous_snapshot, current_snapshot)
    payload: dict[str, Any] = {
        "spreadsheet_id": spreadsheet_id,
        "sheet_name": sheet_name,
        "changed": changed,
        "change_reason": change_reason,
        "current_snapshot": current_snapshot,
        "latest_proposal_id": latest_proposal_id,
    }

    if changed and auto_propose:
        proposal = propose_sheet(
            spreadsheet_id=spreadsheet_id,
            sheet_name=sheet_name,
            prompt=prompt,
            prompt_profile=prompt_profile,
        )
        payload["proposal"] = proposal
        payload["proposal_id"] = proposal.get("proposal_id")

    return payload


def update_policy_from_apply(proposal_patches: list[dict[str, Any]], selected_patch_ids: set[str]) -> dict[str, Any]:
    policy = load_policy_memory()
    policy["total_applies"] = int(policy.get("total_applies", 0)) + 1
    policy["total_proposals"] = int(policy.get("total_proposals", 0)) + len(proposal_patches)
    policy["total_selected"] = int(policy.get("total_selected", 0)) + len(selected_patch_ids)
    policy["total_rejected"] = int(policy.get("total_rejected", 0)) + max(len(proposal_patches) - len(selected_patch_ids), 0)

    field_stats = policy.setdefault("field_stats", {})
    for patch in proposal_patches:
        field = str(patch.get("field", "unknown"))
        field_entry = field_stats.setdefault(field, {"selected": 0, "rejected": 0})
        if patch.get("patch_id") in selected_patch_ids:
            field_entry["selected"] = int(field_entry.get("selected", 0)) + 1
        else:
            field_entry["rejected"] = int(field_entry.get("rejected", 0)) + 1

    policy["updated_at"] = datetime.now().isoformat()
    save_policy_memory(policy)
    return policy


def propose_sheet(
    spreadsheet_id: str,
    sheet_name: str,
    prompt: str,
    prompt_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    require_ai_configured()
    spreadsheet_id = normalize_spreadsheet_id(spreadsheet_id)
    sanitized_prompt_profile = sanitize_prompt_profile(prompt_profile)
    effective_prompt = compose_effective_prompt(prompt, sanitized_prompt_profile)
    values = get_sheet_values(spreadsheet_id, f"{sheet_name}!{WATCH_POLL_RANGE}")
    headers, row_dicts = build_row_dicts(values)
    metadata = get_spreadsheet_metadata(spreadsheet_id)
    source_snapshot = build_source_snapshot(values, metadata)
    policy = load_policy_memory()
    prior_context = get_context_from_previous_runs(spreadsheet_id, sheet_name)
    workflow_context = {
        "pending_patch_count": len(prior_context["existing_proposed_patch_ids"]),
        "recently_applied_patch_count": len(prior_context["recently_applied_patch_ids"]),
        "latest_apply_at": prior_context.get("latest_apply_at"),
        "latest_apply_artifact": prior_context.get("latest_apply_artifact"),
    }
    mapping, mapping_meta = map_headers_with_ai(
        headers,
        row_dicts,
        effective_prompt,
        policy,
        workflow_context,
        require_ai=True,
    )

    patches, plans = build_patch_set(headers, row_dicts, mapping, effective_prompt)
    plans, reasoning_meta = refine_plans_with_ai(
        plans,
        row_dicts,
        mapping,
        effective_prompt,
        policy,
        workflow_context,
        require_ai=True,
    )
    patches = build_patches_from_plans(row_dicts, mapping, plans)
    for patch in patches:
        if patch.patch_id in prior_context["recently_applied_patch_ids"]:
            patch.context_status = "reopened"
        elif patch.patch_id in prior_context["existing_proposed_patch_ids"]:
            patch.context_status = "carry_over"
        else:
            patch.context_status = "new"

    review_intelligence = build_review_intelligence(
        patches,
        effective_prompt,
        policy,
        workflow_context,
        require_ai=True,
    )
    kpis = calculate_kpis(plans)
    health_meter = build_health_meter(kpis)
    aging_buckets = build_aging_buckets(plans)
    anomalies = build_anomalies(
        plans,
        effective_prompt,
        policy,
        workflow_context,
        require_ai=True,
    )
    critical_ready = sum(1 for patch in patches if normalize_header(patch.field) == "priority" and patch.after == "Critical")
    action_alert = {
        "critical_patches_ready": critical_ready,
        "message": f"{critical_ready} critical patches ready for review." if critical_ready else "No new critical patches.",
    }
    write_proposed_changes_tab(spreadsheet_id, patches)

    proposal_payload = {
        "type": "proposal",
        "spreadsheet_id": spreadsheet_id,
        "sheet_name": sheet_name,
        "spreadsheet_url": metadata.get("spreadsheetUrl"),
        "generated_at": datetime.now().isoformat(),
        "prompt": effective_prompt,
        "operator_prompt": str(prompt or "").strip() or DEFAULT_PROMPT,
        "prompt_profile": sanitized_prompt_profile,
        "source_snapshot": source_snapshot,
        "mapping": mapping,
        "mapping_meta": mapping_meta,
        "reasoning_meta": reasoning_meta,
        "review_intelligence": review_intelligence,
        "workflow_context": workflow_context,
        "kpis": kpis,
        "health_meter": health_meter,
        "aging_buckets": aging_buckets,
        "anomalies": anomalies,
        "action_alert": action_alert,
        "source_headers": headers,
        "patches": serialize_patches(patches),
        "row_plans": serialize_plans(plans),
        "policy_hints": policy_hints(policy),
        "ai_enabled": True,
        "ai_model": openai_model(),
    }
    proposal_path = store_artifact("proposal", proposal_payload)
    changed_rows = len({patch.sheet_row_number for patch in patches})
    projected_cash = sum(
        plan.projected_recoverable_cash for plan in plans if plan.priority in {"Critical", "High", "Medium"}
    )
    execution_steps = [
        f"Read {len(row_dicts)} rows from '{sheet_name}'.",
        f"Loaded workflow context: {workflow_context['pending_patch_count']} pending patches and {workflow_context['recently_applied_patch_count']} recently applied patches.",
        f"Mapped {len(mapping)} business columns using {mapping_meta.get('source', 'rules')}: {', '.join(sorted(mapping.keys()))}.",
        f"Generated {len(patches)} proposed cell updates across {changed_rows} accounts.",
        f"KPI snapshot: outstanding ₹{kpis['total_outstanding']:,}, at-risk ₹{kpis['at_risk']:,}, projected recovery ₹{kpis['projected_recovery']:,}.",
        f"Projected recoverable cash from priority accounts: ₹{projected_cash:,}.",
        f"Detected {len(anomalies)} notable anomalies for executive review.",
        f"Generated review intelligence with {len(review_intelligence.get('risky_items', []))} risk highlights.",
        f"Wrote '{PROPOSED_CHANGES_SHEET_NAME}' tab and saved proposal artifact.",
    ]
    if any(sanitized_prompt_profile.values()):
        execution_steps.insert(1, "Loaded custom business prompt profile from UI tab.")

    return {
        "spreadsheet_id": spreadsheet_id,
        "sheet_name": sheet_name,
        "spreadsheet_url": metadata.get("spreadsheetUrl"),
        "mapping": mapping,
        "mapping_meta": mapping_meta,
        "reasoning_meta": reasoning_meta,
        "review_intelligence": review_intelligence,
        "workflow_context": workflow_context,
        "kpis": kpis,
        "health_meter": health_meter,
        "aging_buckets": aging_buckets,
        "anomalies": anomalies,
        "action_alert": action_alert,
        "patches": proposal_payload["patches"],
        "row_plans": proposal_payload["row_plans"],
        "ai_enabled": proposal_payload["ai_enabled"],
        "ai_model": proposal_payload["ai_model"],
        "proposal_artifact": str(proposal_path),
        "proposal_id": proposal_path.stem.replace("_proposal", ""),
        "operator_prompt": str(prompt or "").strip() or DEFAULT_PROMPT,
        "prompt_profile": sanitized_prompt_profile,
        "source_snapshot": source_snapshot,
        "execution_steps": execution_steps,
        "tab_status": {
            "raw": RAW_SHEET_NAME,
            "proposed_changes": PROPOSED_CHANGES_SHEET_NAME,
        },
    }


def apply_proposal(
    spreadsheet_id: str,
    sheet_name: str,
    prompt: str,
    prompt_profile: dict[str, Any] | None = None,
    selected_patch_ids: list[str] | None = None,
    apply_all: bool = False,
    proposal_id: str | None = None,
) -> dict[str, Any]:
    spreadsheet_id = normalize_spreadsheet_id(spreadsheet_id)
    sanitized_prompt_profile = sanitize_prompt_profile(prompt_profile)
    effective_prompt = compose_effective_prompt(prompt, sanitized_prompt_profile)
    proposal_payload, proposal_path = load_proposal_artifact(spreadsheet_id, sheet_name, proposal_id)
    proposal_patches = proposal_payload.get("patches", [])
    plans = proposal_payload.get("row_plans", [])

    if apply_all or not selected_patch_ids:
        selected = proposal_patches
    else:
        selected_set = set(selected_patch_ids)
        selected = [patch for patch in proposal_patches if patch["patch_id"] in selected_set]

    if not selected:
        raise RuntimeError("No patches selected to apply.")
    selected_ids = {patch["patch_id"] for patch in selected}
    policy = update_policy_from_apply(proposal_patches, selected_ids)

    current_values = get_sheet_values(spreadsheet_id, f"{sheet_name}!{WATCH_POLL_RANGE}")
    headers, row_dicts = build_row_dicts(current_values)

    needed_headers = list(headers)
    for patch in selected:
        if patch["field"] not in needed_headers:
            needed_headers.append(patch["field"])

    updated_rows = deepcopy(row_dicts)
    applied_patches: list[dict[str, Any]] = []

    for patch in selected:
        row_index = int(patch["row_index"])
        field = patch["field"]
        before_live = str(updated_rows[row_index].get(field, "") or "")
        after_value = patch["after"]
        updated_rows[row_index][field] = after_value

        applied_patch = dict(patch)
        applied_patch["before"] = before_live
        applied_patch["after"] = after_value
        applied_patches.append(applied_patch)

    raw_values = build_row_values(needed_headers, updated_rows)
    write_values(
        spreadsheet_id,
        f"{sheet_name}!A1:{column_letter(len(needed_headers))}{len(raw_values)}",
        raw_values,
    )

    queue_rows = build_queue_rows([RowPlan(**plan) for plan in plans])
    ensure_sheet(spreadsheet_id, COLLECTIONS_QUEUE_SHEET_NAME)
    write_values(
        spreadsheet_id,
        f"{COLLECTIONS_QUEUE_SHEET_NAME}!A1:{column_letter(len(queue_rows[0]))}{len(queue_rows)}",
        queue_rows,
    )

    apply_artifact_payload = {
        "type": "apply",
        "generated_at": datetime.now().isoformat(),
        "spreadsheet_id": spreadsheet_id,
        "sheet_name": sheet_name,
        "prompt": effective_prompt,
        "operator_prompt": str(prompt or "").strip() or DEFAULT_PROMPT,
        "prompt_profile": sanitized_prompt_profile,
        "proposal_artifact": str(proposal_path),
        "selected_patch_ids": sorted(selected_ids),
        "applied_patches": applied_patches,
        "policy_snapshot": policy,
    }
    apply_path = store_artifact("apply", apply_artifact_payload)

    report_values = build_report_values(effective_prompt, applied_patches, [RowPlan(**plan) for plan in plans], str(apply_path))
    report_width = max(len(row) for row in report_values)
    normalized_report = [row + [""] * (report_width - len(row)) for row in report_values]
    ensure_sheet(spreadsheet_id, REPORT_SHEET_NAME)
    write_values(
        spreadsheet_id,
        f"{REPORT_SHEET_NAME}!A1:{column_letter(report_width)}{len(normalized_report)}",
        normalized_report,
    )

    metadata = get_spreadsheet_metadata(spreadsheet_id)
    return {
        "spreadsheet_id": spreadsheet_id,
        "sheet_name": sheet_name,
        "spreadsheet_url": metadata.get("spreadsheetUrl"),
        "applied_patch_count": len(applied_patches),
        "applied_patches": applied_patches,
        "collections_queue_preview": queue_rows[: min(len(queue_rows), 12)],
        "report_preview": report_values[: min(len(report_values), 18)],
        "apply_artifact": str(apply_path),
        "policy_hints": policy_hints(policy),
        "tab_status": {
            "raw": RAW_SHEET_NAME,
            "proposed_changes": PROPOSED_CHANGES_SHEET_NAME,
            "collections_queue": COLLECTIONS_QUEUE_SHEET_NAME,
            "report": REPORT_SHEET_NAME,
        },
    }


def bootstrap_sample_sheet(title: str) -> dict[str, str]:
    created = run_gws("sheets", "spreadsheets", "create", body={"properties": {"title": title}})
    spreadsheet_id = created["spreadsheetId"]
    spreadsheet_url = created["spreadsheetUrl"]

    rename_default_sheet(spreadsheet_id, "Sheet1", RAW_SHEET_NAME)
    values = [SAMPLE_HEADERS, *build_sample_rows()]
    write_values(
        spreadsheet_id,
        f"{RAW_SHEET_NAME}!A1:{column_letter(len(SAMPLE_HEADERS))}{len(values)}",
        values,
    )

    return {
        "spreadsheet_id": spreadsheet_id,
        "spreadsheet_url": spreadsheet_url,
        "sheet_name": RAW_SHEET_NAME,
        "sector": DEMO_SECTOR_NAME,
        "row_count": len(values) - 1,
    }


def analyze_alias(spreadsheet_id: str, sheet_name: str, prompt: str) -> dict[str, Any]:
    proposal = propose_sheet(spreadsheet_id, sheet_name, prompt)
    return apply_proposal(
        spreadsheet_id=spreadsheet_id,
        sheet_name=sheet_name,
        prompt=prompt,
        apply_all=True,
        proposal_id=proposal["proposal_id"],
    )


def print_proposal_summary(payload: dict[str, Any]) -> None:
    print(f"Spreadsheet ID: {payload['spreadsheet_id']}")
    print(f"Sheet Name: {payload['sheet_name']}")
    if payload.get("spreadsheet_url"):
        print(f"Spreadsheet URL: {payload['spreadsheet_url']}")
    print(f"Mapped fields: {', '.join(sorted(payload.get('mapping', {}).keys()))}")
    print(f"Proposed patches: {len(payload.get('patches', []))}")
    print(f"Proposal artifact: {payload.get('proposal_artifact')}")


def print_apply_summary(payload: dict[str, Any]) -> None:
    print(f"Spreadsheet ID: {payload['spreadsheet_id']}")
    if payload.get("spreadsheet_url"):
        print(f"Spreadsheet URL: {payload['spreadsheet_url']}")
    print(f"Applied patches: {payload['applied_patch_count']}")
    print(f"Apply artifact: {payload.get('apply_artifact')}")


def parse_patch_ids(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    values = [item.strip() for item in raw.split(",") if item.strip()]
    return values or None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PRs for Operations demo for Google Sheets via gws.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create-demo", help="Create a sample receivables spreadsheet only.")
    create_parser.add_argument("--title", default="PRs for Operations AR Demo")

    propose_parser = subparsers.add_parser("propose", help="Propose reviewable patches and write Proposed Changes tab.")
    propose_parser.add_argument("--spreadsheet-id", required=True)
    propose_parser.add_argument("--sheet-name", default=RAW_SHEET_NAME)
    propose_parser.add_argument("--prompt", default=DEFAULT_PROMPT)

    apply_parser = subparsers.add_parser("apply", help="Apply approved patches from latest or selected proposal artifact.")
    apply_parser.add_argument("--spreadsheet-id", required=True)
    apply_parser.add_argument("--sheet-name", default=RAW_SHEET_NAME)
    apply_parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    apply_parser.add_argument("--proposal-id")
    apply_parser.add_argument("--patch-ids", help="Comma separated patch IDs")
    apply_parser.add_argument("--apply-all", action="store_true")

    analyze_parser = subparsers.add_parser("analyze", help="Backward-compatible alias: propose and apply all patches.")
    analyze_parser.add_argument("--spreadsheet-id", required=True)
    analyze_parser.add_argument("--sheet-name", default=RAW_SHEET_NAME)
    analyze_parser.add_argument("--prompt", default=DEFAULT_PROMPT)

    serve_parser = subparsers.add_parser("serve", help="Serve web UI and local API for PRs for Operations demo.")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)

    return parser.parse_args()


class DemoHTTPRequestHandler(BaseHTTPRequestHandler):
    server_version = "SheetOpsDemo/2.0"

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length > 0 else b"{}"
        return json.loads(raw.decode("utf-8") or "{}")

    def _serve_file(self, filename: str, content_type: str) -> None:
        path = Path(__file__).resolve().parent / filename
        if not path.exists():
            self.send_error(404, "Not Found")
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)

        if parsed.path in {"/", "/index.html", "/dashboard.html"}:
            self._serve_file("ui design/dashboard.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/styles.css":
            self._serve_file("ui design/styles.css", "text/css; charset=utf-8")
            return
        if parsed.path == "/app.js":
            self._serve_file("app.js", "application/javascript; charset=utf-8")
            return
        if parsed.path == "/api/health":
            self._send_json({"ok": True, "service": "prs-for-operations-demo"})
            return

        self.send_error(404, "Not Found")

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)

        try:
            data = self._read_json_body()
            if parsed.path == "/api/create-demo":
                title = str(data.get("title") or "PRs for Operations AR Demo").strip()
                payload = bootstrap_sample_sheet(title)
                self._send_json({"ok": True, **payload})
                return

            if parsed.path == "/api/propose":
                spreadsheet_id = str(data.get("spreadsheet_id") or "").strip()
                if not spreadsheet_id:
                    raise RuntimeError("spreadsheet_id is required")
                sheet_name = str(data.get("sheet_name") or RAW_SHEET_NAME).strip()
                prompt = str(data.get("prompt") or DEFAULT_PROMPT).strip()
                prompt_profile = sanitize_prompt_profile(data.get("prompt_profile"))
                payload = propose_sheet(spreadsheet_id, sheet_name, prompt, prompt_profile=prompt_profile)
                self._send_json({"ok": True, **payload})
                return

            if parsed.path == "/api/preflight":
                spreadsheet_id = str(data.get("spreadsheet_id") or "").strip()
                if not spreadsheet_id:
                    raise RuntimeError("spreadsheet_id is required")
                sheet_name = str(data.get("sheet_name") or RAW_SHEET_NAME).strip()
                prompt = str(data.get("prompt") or DEFAULT_PROMPT).strip()
                prompt_profile = sanitize_prompt_profile(data.get("prompt_profile"))
                payload = preflight_sheet(spreadsheet_id, sheet_name, prompt, prompt_profile=prompt_profile)
                self._send_json({"ok": True, **payload})
                return

            if parsed.path == "/api/apply":
                spreadsheet_id = str(data.get("spreadsheet_id") or "").strip()
                if not spreadsheet_id:
                    raise RuntimeError("spreadsheet_id is required")
                sheet_name = str(data.get("sheet_name") or RAW_SHEET_NAME).strip()
                prompt = str(data.get("prompt") or DEFAULT_PROMPT).strip()
                prompt_profile = sanitize_prompt_profile(data.get("prompt_profile"))
                selected_patch_ids = data.get("selected_patch_ids")
                if selected_patch_ids is not None and not isinstance(selected_patch_ids, list):
                    raise RuntimeError("selected_patch_ids must be an array of patch IDs")
                proposal_id = data.get("proposal_id")
                payload = apply_proposal(
                    spreadsheet_id=spreadsheet_id,
                    sheet_name=sheet_name,
                    prompt=prompt,
                    prompt_profile=prompt_profile,
                    selected_patch_ids=selected_patch_ids,
                    apply_all=bool(data.get("apply_all")),
                    proposal_id=str(proposal_id).strip() if proposal_id else None,
                )
                self._send_json({"ok": True, **payload})
                return

            if parsed.path == "/api/watch":
                spreadsheet_id = str(data.get("spreadsheet_id") or "").strip()
                if not spreadsheet_id:
                    raise RuntimeError("spreadsheet_id is required")
                sheet_name = str(data.get("sheet_name") or RAW_SHEET_NAME).strip()
                prompt = str(data.get("prompt") or DEFAULT_PROMPT).strip()
                prompt_profile = sanitize_prompt_profile(data.get("prompt_profile"))
                payload = watch_sheet(
                    spreadsheet_id=spreadsheet_id,
                    sheet_name=sheet_name,
                    prompt=prompt,
                    prompt_profile=prompt_profile,
                    auto_propose=bool(data.get("auto_propose", True)),
                )
                self._send_json({"ok": True, **payload})
                return

            self._send_json({"ok": False, "error": "Not Found"}, status=404)
        except Exception as exc:  # noqa: BLE001
            self._send_json({"ok": False, "error": str(exc)}, status=400)


def run_server(host: str, port: int) -> None:
    server = ThreadingHTTPServer((host, port), DemoHTTPRequestHandler)
    print(f"Serving PRs for Operations demo at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
    finally:
        server.server_close()


def main() -> int:
    args = parse_args()

    try:
        if args.command == "create-demo":
            payload = bootstrap_sample_sheet(args.title)
            print(f"Spreadsheet ID: {payload['spreadsheet_id']}")
            print(f"Spreadsheet URL: {payload['spreadsheet_url']}")
            print(f"Raw sheet: {payload['sheet_name']}")
            return 0

        if args.command == "propose":
            payload = propose_sheet(args.spreadsheet_id, args.sheet_name, args.prompt)
            print_proposal_summary(payload)
            return 0

        if args.command == "apply":
            payload = apply_proposal(
                spreadsheet_id=args.spreadsheet_id,
                sheet_name=args.sheet_name,
                prompt=args.prompt,
                selected_patch_ids=parse_patch_ids(args.patch_ids),
                apply_all=args.apply_all,
                proposal_id=args.proposal_id,
            )
            print_apply_summary(payload)
            return 0

        if args.command == "analyze":
            payload = analyze_alias(args.spreadsheet_id, args.sheet_name, args.prompt)
            print_apply_summary(payload)
            return 0

        if args.command == "serve":
            run_server(args.host, args.port)
            return 0

        raise RuntimeError(f"Unknown command: {args.command}")
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
