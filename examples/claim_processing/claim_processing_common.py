from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DOCS_DIR = DATA_DIR / "merchant_representation_docs"
CLAIMS_CSV = DATA_DIR / "claims.csv"
REPRESENTATIONS_CSV = DATA_DIR / "merchant_representations.csv"


@dataclass
class ClaimEvaluation:
    claim_id: str
    extracted_entities: Dict[str, Any]
    comparison: Dict[str, Any]
    decision: str
    rationale: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "extracted_entities": self.extracted_entities,
            "comparison": self.comparison,
            "decision": self.decision,
            "rationale": self.rationale,
        }


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _to_bool(value: str) -> bool:
    return str(value).strip().lower() in {"true", "yes", "y", "1", "matched"}


def _parse_date(value: str) -> datetime:
    return datetime.strptime(value.strip(), "%Y-%m-%d")


def _parse_amount(value: str) -> float:
    cleaned = value.replace("$", "").replace(",", "").strip()
    return float(cleaned)


def load_claims() -> Dict[str, Dict[str, str]]:
    claims: Dict[str, Dict[str, str]] = {}
    with CLAIMS_CSV.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            claims[row["claim_id"]] = row
    return claims


def load_representation_index() -> Dict[str, Dict[str, str]]:
    records: Dict[str, Dict[str, str]] = {}
    with REPRESENTATIONS_CSV.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            records[row["claim_id"]] = row
    return records


def load_representation_text(claim_id: str) -> str:
    index = load_representation_index()
    if claim_id not in index:
        raise KeyError(f"No merchant representation entry found for claim_id={claim_id}")

    document_path = BASE_DIR / index[claim_id]["document_path"]
    return document_path.read_text(encoding="utf-8")


def extract_entities_from_representation(text: str) -> Dict[str, Any]:
    patterns = {
        "claim_id": r"Claim ID:\s*(.+)",
        "merchant_name": r"Merchant Name:\s*(.+)",
        "cardholder_name": r"Cardholder Name:\s*(.+)",
        "card_last4": r"Card Last4:\s*(\d{4})",
        "transaction_date": r"Transaction Date:\s*([0-9\-]{10})",
        "transaction_amount": r"Transaction Amount:\s*([$0-9\.,]+)",
        "currency": r"Currency:\s*([A-Z]{3})",
        "avs_match": r"AVS Match:\s*(.+)",
        "cvv_match": r"CVV Match:\s*(.+)",
        "three_ds_authenticated": r"3DS Authenticated:\s*(.+)",
        "receipt_signed": r"Receipt Signed:\s*(.+)",
        "service_delivered": r"Service Delivered:\s*(.+)",
        "prior_successful_transactions": r"Prior Successful Transactions:\s*(\d+)",
        "refund_issued": r"Refund Issued:\s*(.+)",
        "duplicate_processing": r"Duplicate Processing:\s*(.+)",
    }

    extracted: Dict[str, Any] = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        extracted[key] = match.group(1).strip()

    if "transaction_amount" in extracted:
        extracted["transaction_amount"] = _parse_amount(extracted["transaction_amount"])

    if "prior_successful_transactions" in extracted:
        extracted["prior_successful_transactions"] = int(extracted["prior_successful_transactions"])

    for key in [
        "avs_match",
        "cvv_match",
        "three_ds_authenticated",
        "receipt_signed",
        "service_delivered",
        "refund_issued",
        "duplicate_processing",
    ]:
        if key in extracted:
            extracted[key] = _to_bool(extracted[key])

    return extracted


def compare_extracted_to_claim(
    claim: Dict[str, str],
    extracted: Dict[str, Any],
    amount_tolerance: float = 1.00,
    date_tolerance_days: int = 2,
) -> Dict[str, Any]:
    claim_amount = _parse_amount(claim["transaction_amount"])
    extracted_amount = float(extracted.get("transaction_amount", -1))

    claim_date = _parse_date(claim["transaction_date"])
    extracted_date_raw = extracted.get("transaction_date")
    extracted_date = _parse_date(extracted_date_raw) if extracted_date_raw else None

    amount_difference = abs(claim_amount - extracted_amount) if extracted_amount >= 0 else None
    date_difference_days = abs((claim_date - extracted_date).days) if extracted_date else None

    comparison = {
        "customer_name_match": _normalize_text(claim["customer_name"]) == _normalize_text(str(extracted.get("cardholder_name", ""))),
        "card_last4_match": claim["card_last4"] == str(extracted.get("card_last4", "")),
        "merchant_name_match": _normalize_text(claim["merchant_name"]) == _normalize_text(str(extracted.get("merchant_name", ""))),
        "amount_difference": amount_difference,
        "amount_match": amount_difference is not None and amount_difference <= amount_tolerance,
        "date_difference_days": date_difference_days,
        "date_match": date_difference_days is not None and date_difference_days <= date_tolerance_days,
        "currency_match": claim["currency"].upper() == str(extracted.get("currency", "")).upper(),
        "avs_match": bool(extracted.get("avs_match", False)),
        "cvv_match": bool(extracted.get("cvv_match", False)),
        "three_ds_authenticated": bool(extracted.get("three_ds_authenticated", False)),
        "receipt_signed": bool(extracted.get("receipt_signed", False)),
        "service_delivered": bool(extracted.get("service_delivered", False)),
        "prior_successful_transactions": int(extracted.get("prior_successful_transactions", 0) or 0),
        "refund_issued": bool(extracted.get("refund_issued", False)),
        "duplicate_processing": bool(extracted.get("duplicate_processing", False)),
    }
    comparison["all_core_fields_match"] = all(
        [
            comparison["customer_name_match"],
            comparison["card_last4_match"],
            comparison["merchant_name_match"],
            comparison["amount_match"],
            comparison["date_match"],
            comparison["currency_match"],
        ]
    )
    return comparison


def decide_claim(comparison: Dict[str, Any], reason_code: str) -> Tuple[str, List[str]]:
    rationale: List[str] = []

    hard_mismatch_checks = {
        "customer name mismatch": not comparison["customer_name_match"],
        "card number mismatch": not comparison["card_last4_match"],
        "merchant name mismatch": not comparison["merchant_name_match"],
        "amount mismatch": not comparison["amount_match"],
        "date mismatch": not comparison["date_match"],
        "currency mismatch": not comparison["currency_match"],
    }

    for label, failed in hard_mismatch_checks.items():
        if failed:
            rationale.append(f"Hard mismatch detected: {label}.")

    if rationale:
        rationale.append("Rule: any hard mismatch approves customer claim.")
        return "approved", rationale

    if comparison["refund_issued"] or comparison["duplicate_processing"]:
        rationale.append("Merchant indicates refund or duplicate processing.")
        rationale.append("Rule: admitted billing error approves customer claim.")
        return "approved", rationale

    evidence_score = 0
    if comparison["avs_match"]:
        evidence_score += 1
    if comparison["cvv_match"]:
        evidence_score += 1
    if comparison["three_ds_authenticated"]:
        evidence_score += 1
    if comparison["receipt_signed"] or comparison["service_delivered"]:
        evidence_score += 1
    if comparison["prior_successful_transactions"] >= 2:
        evidence_score += 1

    rationale.append(f"Merchant evidence score={evidence_score}/5.")

    if comparison["all_core_fields_match"] and evidence_score >= 4:
        rationale.append("Rule: strong merchant evidence with core match denies customer claim.")
        return "denied", rationale

    if reason_code.lower() in {"fraud_card_not_present", "unauthorized"} and evidence_score <= 1:
        rationale.append("Rule: weak merchant evidence on fraud-like reason approves claim.")
        return "approved", rationale

    rationale.append("Rule: partial evidence or uncertainty continues arbitration.")
    return "continue_arbitration", rationale


def evaluate_claim(claim_id: str) -> ClaimEvaluation:
    claims = load_claims()
    if claim_id not in claims:
        raise KeyError(f"Claim id not found: {claim_id}")

    claim = claims[claim_id]
    representation_text = load_representation_text(claim_id)
    extracted = extract_entities_from_representation(representation_text)
    comparison = compare_extracted_to_claim(claim, extracted)
    decision, rationale = decide_claim(comparison, claim["reason_code"])
    return ClaimEvaluation(
        claim_id=claim_id,
        extracted_entities=extracted,
        comparison=comparison,
        decision=decision,
        rationale=rationale,
    )


def evaluate_all_claims() -> List[ClaimEvaluation]:
    claims = load_claims()
    return [evaluate_claim(claim_id) for claim_id in claims.keys()]


def to_pretty_json(data: Dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=True)
