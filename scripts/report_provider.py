"""Route broker report extraction through the private subscription worker."""
import json
import os
import subprocess



class NoReportCapacity(RuntimeError):
    """Neither provider accepted the request."""


def plan_request(payload):
    target = os.environ.get("REPORT_PLAN_SSH_TARGET")
    if not target:
        raise RuntimeError("Missing private report worker")
    proc = subprocess.run(
        ["ssh", "-T", "-oBatchMode=yes", "-oStrictHostKeyChecking=yes",
         "-oConnectTimeout=15", "-oIdentitiesOnly=yes", "-i",
         os.path.expanduser("~/.ssh/report_worker"), "--", target],
        input=json.dumps(payload), text=True, capture_output=True, timeout=660,
    )
    if proc.returncode:
        # Never treat a connection failure as permission to spend API credits.
        diagnostics = (
            ("bad permissions", "SSH_PRIVATE_KEY_PERMISSIONS"),
            ("error in libcrypto", "SSH_PRIVATE_KEY_FORMAT"),
            ("invalid format", "SSH_KEY_FORMAT"),
            ("host key verification failed", "SSH_HOST_KEY_CHECK"),
            ("permission denied (", "SSH_LOGIN_DENIED"),
            ("could not resolve hostname", "SSH_TARGET_NAME"),
            ("connection timed out", "SSH_TIMEOUT"),
            ("connection refused", "SSH_CONNECTION_REFUSED"),
            ("no route to host", "SSH_NO_ROUTE"),
            ("connection reset", "SSH_CONNECTION_RESET"),
            ("connection closed", "SSH_CONNECTION_CLOSED"),
        )
        stderr = proc.stderr.lower()
        reason = next((label for marker, label in diagnostics if marker in stderr),
                      "SSH_UNCLASSIFIED" if proc.returncode == 255 else "WORKER_FAILED")
        raise RuntimeError(f"Private report worker failed (exit {proc.returncode}, {reason})")
    return json.loads(proc.stdout)


def complete_report(payload):
    if os.environ.get("REPORT_AI_ROUTE") == "plan-first":
        result = plan_request(payload)
        if result.get("status") == "ok" and isinstance(result.get("text"), str) and result["text"].strip():
            print("Broker report provider: ChatGPT plan")
            return result["text"]
        if result.get("status") != "plan_limit":
            raise RuntimeError("Private report worker did not complete the request")
        print("Broker report provider: plan limit reached, using API")
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise NoReportCapacity("API fallback has no API key")
    import requests

    response = requests.post("https://api.openai.com/v1/responses",
                             headers={"Authorization": f"Bearer {key}"},
                             json=payload, timeout=180)
    if response.status_code >= 400:
        try:
            code = response.json()["error"]["code"]
        except (ValueError, KeyError, TypeError):
            code = None
        if code in {"insufficient_quota", "credit_balance_exhausted"}:
            raise NoReportCapacity(str(code))
        raise RuntimeError(f"Report API returned HTTP {response.status_code}: {code}")
    return "\n".join(part["text"] for item in response.json()["output"]
                     for part in item.get("content", []) if part.get("type") == "output_text").strip()

