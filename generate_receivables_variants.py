#!/usr/bin/env python3

import argparse
import csv
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path


COLLECTORS = ["Riya", "Arjun", "Megha", "Karan", "Sana", "Vikram", "", ""]


@dataclass(frozen=True)
class BusinessProfile:
    slug: str
    invoice_prefix: str
    headers: list[str]
    region_cities: dict[str, list[str]]
    account_bases: list[str]
    payer_types: list[str]
    mixes: list[str]
    amount_base: int
    amount_step: int
    amount_secondary_step: int
    disputed_note: str
    promise_note: str
    partial_note: str
    overdue_notes: list[str]
    paid_note: str
    source_urls: list[str]


SAMOSA_PARTY = BusinessProfile(
    slug="samosa_party",
    invoice_prefix="SP-AR",
    headers=[
        "Invoice Ref",
        "Account Name",
        "Inv Amt (INR)",
        "Due Dt",
        "Days Late",
        "Last Touch",
        "Collector",
        "Payment Risk",
        "A/R State",
        "Region",
        "City Cluster",
        "Channel Type",
        "Order Mix",
        "Escalation Note",
        "Promised Dt",
        "Source URL",
    ],
    region_cities={
        "south": ["Bengaluru", "Hyderabad", "Chennai"],
        "north": ["Delhi", "Noida", "Gurugram", "Ghaziabad", "Faridabad"],
    },
    account_bases=[
        "Swiggy Settlement",
        "Zomato Settlement",
        "Corporate Catering - Infosys",
        "Corporate Catering - Wipro",
        "Corporate Catering - Microsoft",
        "Phoenix Mall Food Court Events",
        "Airport Kiosk Bulk Order Desk",
        "Direct App Enterprise Orders",
        "Tech Park Pantry Program",
        "Festival Bulk Orders Desk",
        "Metro Hub Breakfast Program",
        "Retail Franchise Supplies",
    ],
    payer_types=[
        "Food Aggregator",
        "Corporate Catering",
        "Mall/Transit Venue",
        "Franchise Partner",
        "Direct App Enterprise",
    ],
    mixes=[
        "Marketplace Delivery",
        "Corporate Snack Boxes",
        "Breakfast Combos",
        "Festival Catering",
        "Chai Flask Bulk Orders",
        "Airport Grab & Go",
    ],
    amount_base=18000,
    amount_step=9200,
    amount_secondary_step=4700,
    disputed_note="Settlement dispute: commission or outlet-level payout mismatch under review",
    promise_note="Finance contact committed payout release after outlet-level reconciliation",
    partial_note="Short remittance received; balance pending against catering or marketplace cycle",
    overdue_notes=[
        "No remittance confirmation from aggregator settlement team",
        "GST invoice uploaded but payout still pending",
        "Bulk event order signoff pending from client admin",
        "Store-wise reconciliation pending with channel partner",
    ],
    paid_note="Closed after settlement remittance confirmation",
    source_urls=[
        "https://samosaparty.in/",
        "https://samosaparty.in/about",
        "https://samosaparty.in/store-locator",
        "https://samosaparty.in/contact-us",
    ],
)


MISSION_CONTROL = BusinessProfile(
    slug="mission_control",
    invoice_prefix="MC-AR",
    headers=[
        "Invoice Ref",
        "Account Name",
        "Inv Amt (INR)",
        "Due Dt",
        "Days Late",
        "Last Touch",
        "Collector",
        "Payment Risk",
        "A/R State",
        "Region",
        "HQ Cluster",
        "Account Segment",
        "Plan Type",
        "Escalation Note",
        "Promised Dt",
        "Source URL",
    ],
    region_cities={
        "west": ["San Francisco", "Los Angeles", "Seattle"],
        "north": ["New York", "Toronto", "London"],
        "south": ["Austin", "Miami", "Singapore"],
        "east": ["Berlin", "Amsterdam", "Sydney"],
    },
    account_bases=[
        "Altura Growth Studio",
        "Northstar RevOps",
        "Cascade Capital",
        "PixelForge Agency",
        "Vector Labs",
        "Apex GTM Systems",
        "Orbit Product Ops",
        "Beacon Portfolio Services",
        "Summit AI Studio",
        "Driftline Ventures",
        "Catalyst Automation",
        "SignalStack Cloud",
    ],
    payer_types=[
        "Startup",
        "Mid-Market SaaS",
        "Agency",
        "VC Platform",
        "Enterprise Innovation",
    ],
    mixes=[
        "Starter Plan",
        "Growth Plan",
        "Annual Enterprise",
        "Agent Overage",
        "Onboarding Fee",
        "Pilot Program",
    ],
    amount_base=78000,
    amount_step=28500,
    amount_secondary_step=11600,
    disputed_note="Usage overage or contract scope disputed while finance reviews agent-run logs",
    promise_note="Champion confirmed payment after PO or vendor onboarding completion",
    partial_note="Base subscription paid; onboarding fee or overage balance remains open",
    overdue_notes=[
        "Awaiting purchase order approval from finance ops",
        "Vendor onboarding blocked on tax or banking documents",
        "Card failure reported on renewal invoice; retry pending",
        "Customer requested revised invoice split across entities",
    ],
    paid_note="Closed after subscription remittance confirmation",
    source_urls=[
        "https://missioncontrolhq.ai/",
        "https://www.scamadviser.com/check-website/missioncontrolhq.ai",
        "https://openclawmap.com/tools/mission-control-hq",
    ],
)


PROFILES = {
    SAMOSA_PARTY.slug: SAMOSA_PARTY,
    MISSION_CONTROL.slug: MISSION_CONTROL,
}


def build_sample_rows(profile: BusinessProfile, row_count: int, anchor: date) -> list[list[str | int]]:
    regions = list(profile.region_cities.keys())
    rows: list[list[str | int]] = []

    for idx in range(row_count):
        region = regions[idx % len(regions)]
        city = profile.region_cities[region][(idx // len(regions)) % len(profile.region_cities[region])]
        account_base = profile.account_bases[idx % len(profile.account_bases)]
        account_name = f"{account_base} {city}"
        payer_type = profile.payer_types[idx % len(profile.payer_types)]
        mix = profile.mixes[(idx * 2) % len(profile.mixes)]
        source_url = profile.source_urls[idx % len(profile.source_urls)]
        invoice_ref = f"{profile.invoice_prefix}-{anchor.year % 100:02d}-{1001 + idx}"

        amount = (
            profile.amount_base
            + (idx % 9) * profile.amount_step
            + (idx % 5) * profile.amount_secondary_step
            + (idx // 6) * (profile.amount_secondary_step // 2)
        )
        collector = COLLECTORS[idx % len(COLLECTORS)]

        if idx % 19 == 0:
            status = "Paid"
            risk = "Low"
            days_late = 0
            last_touch_gap = 1
            escalation_note = profile.paid_note
            promised_date = ""
            if not collector:
                collector = "Riya"
        elif idx % 17 == 0:
            status = "Disputed"
            risk = "High"
            days_late = 34 + (idx % 21)
            last_touch_gap = 11 + (idx % 5)
            escalation_note = profile.disputed_note
            promised_date = ""
        elif idx % 11 == 0:
            status = "Promise to Pay"
            risk = "Medium"
            days_late = 14 + (idx % 13)
            last_touch_gap = 3 + (idx % 4)
            escalation_note = profile.promise_note
            promised_date = (anchor + timedelta(days=(idx % 4) + 1)).isoformat()
        elif idx % 7 == 0:
            status = "Partial Payment"
            risk = "Medium"
            days_late = 18 + (idx % 11)
            last_touch_gap = 5 + (idx % 6)
            escalation_note = profile.partial_note
            promised_date = (anchor + timedelta(days=(idx % 6) + 2)).isoformat()
        else:
            status = "Overdue"
            risk = "High" if idx % 5 == 0 else "Medium" if idx % 3 == 0 else "Low"
            days_late = 6 + ((idx * 3) % 41)
            last_touch_gap = 2 + (idx % 9)
            escalation_note = profile.overdue_notes[idx % len(profile.overdue_notes)]
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
                account_name,
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
                mix,
                escalation_note,
                promised_date,
                source_url,
            ]
        )

    return rows


def write_csv(path: Path, headers: list[str], rows: list[list[str | int]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate business-specific AR demo CSVs.")
    parser.add_argument(
        "--output-dir",
        default="output/spreadsheet",
        help="Directory where CSV files should be written.",
    )
    parser.add_argument(
        "--anchor",
        default=None,
        help="Anchor date in YYYY-MM-DD. Defaults to today's date.",
    )
    parser.add_argument(
        "--rows",
        type=int,
        default=180,
        help="Number of rows to generate per business.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    anchor = date.fromisoformat(args.anchor) if args.anchor else date.today()
    output_dir = Path(args.output_dir)

    for profile in PROFILES.values():
        rows = build_sample_rows(profile, row_count=args.rows, anchor=anchor)
        write_csv(output_dir / f"{profile.slug}_receivables_raw.csv", profile.headers, rows)


if __name__ == "__main__":
    main()
