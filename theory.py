"""Presentation data for theory statements and saved validation receipts."""

import json


def build_theory_view(theory, run_path):
    """Keep proof validation distinct from empirical verdicts and premise links.

    Only attach receipt status to declarations explicitly named by that receipt.
    Paths in artifacts remain display text; they are not executed or fetched.
    """
    receipts = []
    for name in ("attachments/formalization/validation.json", "attachments/validation.json"):
        path = run_path / name
        if path.is_file():
            try:
                data = json.loads(path.read_text())
                if not isinstance(data, dict):
                    continue
                receipts.append({"path": name, "data": data,
                                 "text": json.dumps(data, indent=2, ensure_ascii=False)})
            except (ValueError, OSError):
                receipts.append({"path": name, "data": {}, "text": "Unable to read validation receipt."})

    theory = theory if isinstance(theory, dict) else {}
    statement_links = theory.get("statement_links") or theory.get("links") or []
    entries = list(theory.get("entries") or [])
    known = {e["id"] for e in entries}
    for link in statement_links:
        if link.get("ref") and link["ref"] not in known:
            entries.append({"id": link["ref"], "kind": "reference"})
            known.add(link["ref"])
    coverage = {c["ref"]: c for c in theory.get("premise_coverage", [])}
    statements = []
    for entry in entries:
        ref = entry["id"]
        formal = entry.get("formalization") or {}
        declaration = entry.get("declaration", "")
        matches = []
        for receipt in receipts:
            data = receipt["data"]
            named = set(data.get("declarations") or {}) | set(data.get("axioms") or {})
            named.update(data.get("validated_declarations") or [])
            if data.get("featured_declaration"):
                named.add(data["featured_declaration"])
            if declaration and declaration in named:
                matches.append(receipt)
        draft = "sorryAx" in entry.get("statement", "") or entry.get("kind") == "conjecture"
        status = "Not formalized" if not formal else "Formalization referenced"
        if matches:
            statuses = {r["data"].get("status") for r in matches}
            status = "Partial validation" if "partially_validated" in statuses else (
                "Validated (saved receipt)" if statuses == {"validated"} else "See validation receipt")
        if draft:
            status = "Draft / sorryAx" if "sorryAx" in entry.get("statement", "") else "Conjecture"

        summary = coverage.get(ref, {})
        premises = {p["id"]: dict(p) for p in entry.get("premises", [])}
        for p in summary.get("premises", []):
            premises.setdefault(p["id"], dict(p))
        for premise_id in summary.get("unaccounted", []):
            premises.setdefault(premise_id, {"id": premise_id})
        rows = []
        for premise_id, premise in premises.items():
            links = [link for link in theory.get("premise_links", [])
                     if link.get("ref") == f"{ref}::{premise_id}"]
            for link in premise.get("links", []):
                if link not in links:
                    links.append(link)
            rows.append({
                "id": premise_id, "statement": premise.get("statement", ""),
                "type": premise.get("type", ""),
                "accounting": "Linked" if links else (
                    "Reported accounted; no link" if premise.get("accounted") else "Unaccounted"),
                "links": [_link_view(link) for link in links],
            })
        statements.append({
            "id": ref, "kind": entry.get("kind", "statement"),
            "statement": entry.get("statement", "Statement not bundled; see the links below."),
            "status": status, "declaration": declaration,
            "metadata": [{"name": label, "value": value} for label, value in [
                ("System", formal.get("system")), ("Repository", formal.get("repository")),
                ("Revision", formal.get("revision")), ("Source", entry.get("source_path")),
            ] if value],
            "premises": rows, "linked_count": sum(bool(row["links"]) for row in rows),
            "links": [_link_view(link) for link in statement_links if link.get("ref") == ref],
            "receipts": [r["path"] for r in matches],
        })
    return {
        "available": bool(theory or receipts), "statements": statements,
        "receipts": [{
            "path": r["path"], "text": r["text"],
            "fields": [{"name": label, "value": str(r["data"][key])}
                       for key, label in [
                           ("status", "Saved validation status"), ("checked_at", "Checked at"),
                           ("scope", "Scope"), ("review_scope", "Review scope"),
                           ("build", "Build"), ("axiom_audit", "Axiom audit"),
                           ("mode", "Validation mode"), ("validation_mode", "Validation mode"),
                           ("full_package_rebuilt", "Full package rebuilt"),
                           ("lean_toolchain", "Lean toolchain"), ("mathlib_revision", "Mathlib revision"),
                           ("source_revision", "Source revision"),
                           ("submission_revision", "Submission revision"),
                           ("formalization_revision", "Formalization revision"),
                           ("experiment_binding", "Experiment binding"),
                           ("empirical_limit", "Empirical limit"), ("limitation", "Limitation"),
                           ("assessment_timing", "Assessment timing"),
                       ] if key in r["data"]],
        } for r in receipts],
        "raw": json.dumps(theory, indent=2, ensure_ascii=False),
    }


def _link_view(link):
    source = link.get("file", "")
    if source and link.get("line") is not None:
        source += f":{link['line']}"
    if link.get("qualname"):
        source += f" ({link['qualname']})"
    return {"relation": link.get("relation", "unspecified"),
            "note": link.get("note", ""), "source": source}
