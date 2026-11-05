"""Typed JSON boundary for lark-cli. Successful commands return a dictionary."""
import json
import shutil
import subprocess


class LarkError(RuntimeError):
    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


def decode_response(stdout, stderr, returncode):
    try:
        data = json.loads(stdout.strip() or stderr.strip())
    except ValueError as error:
        raise LarkError("lark-cli did not return a JSON response") from error
    if not isinstance(data, dict):
        raise LarkError("lark-cli response must be a JSON object")
    if data.get("ok") is not True or returncode:
        error = data.get("error") or {}
        raise LarkError(str(error.get("message") or f"lark-cli exit {returncode}"), error.get("code"))
    return data


def lark(args, timeout=120):
    executable = shutil.which("lark-cli.cmd") or shutil.which("lark-cli")
    if not executable:
        raise LarkError("lark-cli not found")
    try:
        process = subprocess.run([executable, *args], capture_output=True,
                                 encoding="utf-8", timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise LarkError(str(error)) from error
    return decode_response(process.stdout, process.stderr, process.returncode)


def upload_attachments(base, table, record, field, paths, *, identity=None, run=lark):
    args = ["base", "+record-upload-attachment", "--base-token", base,
            "--table-id", table, "--record-id", record, "--field-id", field]
    if identity:
        args.extend(["--as", identity])
    for path in paths:
        args.extend(["--file", str(path)])
    if not paths:
        raise ValueError("at least one attachment is required")
    response = run(args, timeout=300)
    if not isinstance(response, dict) or response.get("ok") is not True:
        raise LarkError("upload adapter must return a successful JSON object")
    return response
