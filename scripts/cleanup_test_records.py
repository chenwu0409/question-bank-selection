"""Preview or remove only explicitly tracked Feishu test records and verify by ID."""
import argparse
import json
import re
from pathlib import Path

from lark_client import LarkError, lark

RECORD_NOT_FOUND = 1254043
TABLES = {
    "batch": ("tblS8boB3Zm90SHg", "检索批次ID"),
    "task": ("tblFEVEPllFOztXp", "任务名称"),
    "question": ("tblFlwLDZkzQX2Wq", "题目名称"),
}
ORDER = {"batch": 0, "task": 1, "question": 2}


def direct_record(base, table, record, identity, run):
    try:
        reply = run(["api", "GET", f"/open-apis/bitable/v1/apps/{base}/tables/{table}/records/{record}",
                     "--as", identity])
    except LarkError as error:
        if error.code == RECORD_NOT_FOUND:
            return None
        raise
    result = reply.get("data", {}).get("record")
    if not isinstance(result, dict) or result.get("record_id") != record:
        raise LarkError("direct read did not confirm the requested record")
    return result


def clean(manifest, *, apply=False, run=lark):
    base, identity, marker = (manifest.get(name) for name in ("base_token", "identity", "run_marker"))
    if not isinstance(base, str) or not re.fullmatch(r"[A-Za-z0-9]+", base):
        raise ValueError("invalid Base identifier")
    if identity not in {"user", "bot"}:
        raise ValueError("explicit user or bot identity required")
    if not isinstance(marker, str) or not re.fullmatch(r"(?:KMP-TEST|TEST-KMP|TEST-K)-[A-Za-z0-9-]+", marker):
        raise ValueError("explicit KMP test run marker required")
    rows = manifest["records"]
    if not rows:
        raise ValueError("empty creation manifest")
    for row in rows:
        kind, record = row.get("kind"), row.get("record_id")
        if kind not in TABLES or not isinstance(record, str) or not re.fullmatch(r"rec[A-Za-z0-9]+", record):
            raise ValueError("unknown table role or invalid record ID")
        if row.get("table_id") != TABLES[kind][0] or row.get("ownership") not in {"created", "reused"}:
            raise ValueError("unexpected table or ownership")
    if len({(r["table_id"], r["record_id"]) for r in rows}) != len(rows):
        raise ValueError("duplicate record in manifest")

    results = []
    blocked = False
    for row in sorted(rows, key=lambda item: ORDER[item["kind"]]):
        table, field = TABLES[row["kind"]]
        record = row["record_id"]
        result = {"table_id": table, "record_id": record}
        results.append(result)
        if row["ownership"] == "reused":
            result["status"] = "retained_reused"
            continue
        if blocked:
            result["status"] = "not_attempted"
            continue
        try:
            binding = run(["base", "+table-get", "--base-token", base, "--table-id", table, "--as", identity])
            if binding.get("data", {}).get("table", {}).get("id") != table:
                raise LarkError("table binding could not be verified")
            existing = direct_record(base, table, record, identity, run)
            if existing is None:
                result["status"] = "already_absent"
                continue
            value = existing.get("fields", {}).get(field)
            if not isinstance(value, str) or value != row.get("marker_value") or not (
                value == marker or value.startswith((marker + " ", marker + "-"))
            ):
                raise ValueError(f"{field} does not match the captured test marker value")
            if row.get("external_references_checked") is not True:
                raise ValueError("verify there are no references outside the test run before deleting")
            if not apply:
                result["status"] = "would_delete"
                continue
            args = ["base", "+record-delete", "--base-token", base, "--table-id", table,
                    "--record-id", record, "--as", identity, "--yes"]
            try:
                run(args)
            except LarkError as error:
                if error.code not in {None, RECORD_NOT_FOUND}:
                    raise
                # A timeout may follow a completed delete. Verify without repeating the write.
                if direct_record(base, table, record, identity, run) is not None:
                    raise
            if direct_record(base, table, record, identity, run) is not None:
                raise LarkError("record still exists after delete")
            result["status"] = "deleted_verified"
        except (ValueError, LarkError) as error:
            result.update(status="blocked", error=str(error))
            if isinstance(error, LarkError):
                result["code"] = error.code
            # Later records may still be referenced by the blocked record.
            blocked = True
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--apply", action="store_true", help="delete and verify; default is read-only")
    args = parser.parse_args()
    try:
        results = clean(json.loads(args.manifest.read_text(encoding="utf-8")), apply=args.apply)
        print(json.dumps(results, ensure_ascii=False, indent=2))
        raise SystemExit(any(row["status"] == "blocked" for row in results))
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"{error}\n")
