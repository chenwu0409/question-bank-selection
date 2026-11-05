import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from action_overlap import compare
from cleanup_test_records import clean, TABLES
from lark_client import decode_response, LarkError, upload_attachments


class ToolsTest(unittest.TestCase):
    def setUp(self):
        self.marker = "KMP-TEST-036-OFFLINE"
        self.table = TABLES["task"][0]
        self.row = dict(kind="task", table_id=self.table, record_id="recFixture01", ownership="created",
                        marker_value=self.marker + " test", external_references_checked=True)
        self.manifest = dict(run_marker=self.marker, base_token="FixtureBase", identity="user",
                             records=[self.row, dict(self.row, record_id="recExisting02", ownership="reused")])
        self.calls = []
        self.exists = True

    def fake(self, args):
        self.calls.append(args)
        if args[1] == "+table-get":
            return {"data": {"table": {"id": self.table}}}
        if args[1] == "+record-delete":
            self.exists = False
            return {"ok": True}
        if not self.exists:
            raise LarkError("RecordIdNotFound", 1254043)
        return {"data": {"record": {"record_id": self.row["record_id"],
                                    "fields": {"任务名称": self.row["marker_value"]}}}}

    def test_preview_cleanup_retry_and_reuse(self):
        self.assertEqual([r["status"] for r in clean(self.manifest, run=self.fake)],
                         ["would_delete", "retained_reused"])
        self.assertTrue(self.exists)
        self.assertEqual([r["status"] for r in clean(self.manifest, apply=True, run=self.fake)],
                         ["deleted_verified", "retained_reused"])
        self.assertEqual(clean(self.manifest, apply=True, run=self.fake)[0]["status"], "already_absent")
        self.assertEqual(sum("+record-delete" in args for args in self.calls), 1)
        self.assertFalse(any("recExisting02" in str(args) for args in self.calls))

    def test_wrong_base_and_uncertain_marker_block(self):
        def wrong_base(args):
            raise LarkError("BaseTokenNotFound", 1254040)
        result = clean(self.manifest, apply=True, run=wrong_base)
        self.assertEqual((result[0]["status"], result[0]["code"]), ("blocked", 1254040))
        self.row["external_references_checked"] = False
        self.assertEqual(clean(self.manifest, apply=True, run=self.fake)[0]["status"], "blocked")
        self.assertTrue(self.exists)

    def test_upload_has_one_structured_return(self):
        payload = {"ok": True, "data": {"attachments": [{"file_token": "fixture"}]}}
        result = upload_attachments("base", "tbl", "rec", "图", ["a.png"],
                                    run=lambda args, timeout: decode_response(json.dumps(payload), "progress", 0))
        self.assertEqual(result, payload)
        with self.assertRaises(LarkError):
            upload_attachments("base", "tbl", "rec", "图", ["a.png"],
                               run=lambda args, timeout: ("stdout", "stderr", 0))
        with self.assertRaises(LarkError) as error:
            decode_response("", json.dumps({"ok": False, "error": {"code": 1254040}}), 1)
        self.assertEqual(error.exception.code, 1254040)

    def test_action_overlap_flags_only_discretionary_actions(self):
        self.assertEqual(compare(["pivot", "arm"], ["pivot", "arm"], ["pivot", "arm"]),
                         {"similarity": None, "suspected_duplicate": False})
        self.assertTrue(compare(["pivot", "rotate"], ["pivot", "rotate"], ["pivot"])["suspected_duplicate"])
        self.assertFalse(compare(["pivot", "rotate"], ["pivot", "classify"], ["pivot"])["suspected_duplicate"])
