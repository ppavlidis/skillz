"""
Google Docs extractor for citation-validator.

Fetches a Google Doc via the Docs REST API (service account auth) and returns
the text of its reference section for parse_text().

Authentication:
  Reads service account credentials from the macOS Keychain under the entry
  name "GOOGLE_SERVICE_ACCOUNT_CREDENTIALS".  The value may be:
    - a hex-encoded JSON string  (produced by some keychain tools)
    - a raw JSON string           {"type":"service_account",...}
    - a file path                 /path/to/key.json

The service account email ("GOOGLE_SERVICE_ACCOUNT_EMAIL") is stored
separately and is looked up only for display / error messages.

Access control:
  Share the Google Doc with the service account email at Viewer level.
  No other setup required — the Docs API just needs to be enabled for the
  GCP project that owns the service account.

Dependencies:
  google-auth               (pip install google-auth)
  google-api-python-client  (pip install google-api-python-client)
"""

from __future__ import annotations

import binascii
import json
import re
import subprocess
from typing import Any

_REF_HEADINGS = {"references", "bibliography", "works cited", "literature cited"}
_GDOC_URL_RE = re.compile(r"/document/d/([A-Za-z0-9_\-]+)")


def _doc_id_from_url(url_or_id: str) -> str:
    m = _GDOC_URL_RE.search(url_or_id)
    if m:
        return m.group(1)
    # Already a bare ID
    if re.match(r"^[A-Za-z0-9_\-]{20,}$", url_or_id):
        return url_or_id
    raise ValueError(f"Cannot extract Google Doc ID from: {url_or_id!r}")


def _load_credentials() -> dict[str, Any]:
    result = subprocess.run(
        ["security", "find-generic-password",
         "-s", "GOOGLE_SERVICE_ACCOUNT_CREDENTIALS", "-w"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Service account credentials not found in Keychain.\n"
            "Add them with:\n"
            '  security add-generic-password -s "GOOGLE_SERVICE_ACCOUNT_CREDENTIALS" '
            '-a "$USER" -w "$(cat /path/to/key.json)" -U'
        )
    raw = result.stdout.strip()
    # Hex-encoded JSON (some macOS keychain tools encode binary-safe)
    if re.match(r"^[0-9a-fA-F]+$", raw) and len(raw) % 2 == 0:
        try:
            raw = binascii.unhexlify(raw).decode("utf-8")
        except Exception:
            pass
    if raw.startswith("{"):
        return json.loads(raw)
    if raw.startswith("/"):
        with open(raw) as f:
            return json.load(f)
    raise RuntimeError(
        "GOOGLE_SERVICE_ACCOUNT_CREDENTIALS keychain entry is not a JSON object "
        "or a file path.  Expected the full service account key JSON."
    )


def _para_text(para: dict) -> str:
    return "".join(
        r.get("textRun", {}).get("content", "")
        for r in para.get("elements", [])
    )


def extract_references(url_or_id: str) -> str:
    """
    Return the reference-section text of a Google Doc as a plain string
    suitable for parse_text().  Raises RuntimeError on auth/API errors.
    """
    import warnings
    warnings.filterwarnings("ignore", category=FutureWarning)

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError as e:
        raise RuntimeError(
            f"Missing dependency: {e}.  "
            "Install with: pip install google-auth google-api-python-client"
        ) from e

    doc_id = _doc_id_from_url(url_or_id)
    creds_info = _load_credentials()

    creds = service_account.Credentials.from_service_account_info(
        creds_info,
        scopes=["https://www.googleapis.com/auth/documents.readonly"],
    )
    service = build("docs", "v1", credentials=creds)

    try:
        doc = service.documents().get(documentId=doc_id).execute()
    except Exception as e:
        msg = str(e)
        if "SERVICE_DISABLED" in msg:
            raise RuntimeError(
                "Google Docs API is not enabled for this GCP project.\n"
                "Enable it at: https://console.developers.google.com/apis/api/"
                "docs.googleapis.com/overview"
            ) from e
        if "403" in msg or "PERMISSION_DENIED" in msg:
            sa_email = creds_info.get("client_email", "<service-account-email>")
            raise RuntimeError(
                f"Access denied.  Share the document with {sa_email!r} (Viewer)."
            ) from e
        raise

    body = doc.get("body", {}).get("content", [])
    ref_lines: list[str] = []
    in_refs = False

    for el in body:
        para = el.get("paragraph")
        if not para:
            continue
        text = _para_text(para).strip()
        if not text:
            continue
        if text.lower() in _REF_HEADINGS:
            in_refs = True
            continue
        if in_refs:
            ref_lines.append(text)

    if not ref_lines:
        raise RuntimeError(
            f"No reference section found in document '{doc.get('title', doc_id)}'.\n"
            f"Expected a paragraph with text 'References', 'Bibliography', etc."
        )

    # Join with blank line between each entry so parse_text() block-splits correctly
    return "\n\n".join(ref_lines)
