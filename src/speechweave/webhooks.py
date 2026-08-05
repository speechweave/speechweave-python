import hmac
import hashlib
import time
from typing import List, TypedDict, Union


class VerifyWebhookResult(TypedDict, total=False):
	ok: bool
	reason: str


def verify_webhook(
	secret: Union[str, List[str]],
	raw_body: str,
	signature_header: str,
	tolerance_sec: int = 300,
) -> VerifyWebhookResult:
	"""
	Verify `SpeechWeave-Signature` header (Stripe-style: `t=unix,v1=hex`, may include multiple `v1=` during secret rotation).

	Args:
		secret: Active webhook signing secret, or `[active, previous]` during a rotation window.
		raw_body: Exact request body string (use raw bytes as UTF-8 string).
		signature_header: Value of the `SpeechWeave-Signature` header.
		tolerance_sec: Max clock skew in seconds; defaults to 300.
	"""

	if isinstance(secret, (list, tuple)):
		secrets = [str(s).strip() for s in secret if str(s).strip()]
	else:
		secrets = [str(secret).strip()] if str(secret).strip() else []
	if not secrets:
		return {"ok": False, "reason": "no_secrets"}

	hdr = (signature_header or "").strip()
	parts = [p.strip() for p in hdr.split(",")]
	t = None
	v1_list: List[str] = []
	for part in parts:
		if part.startswith("t="):
			t = part[2:]

		if part.startswith("v1="):
			v1_list.append(part[3:])

	if not t or not v1_list:
		return {"ok": False, "reason": "missing_t_or_v1"}

	try:
		ts = int(t)
	except ValueError:
		return {"ok": False, "reason": "bad_timestamp"}

	now = int(time.time())
	if abs(now - ts) > tolerance_sec:
		return {"ok": False, "reason": "timestamp_skew"}

	for secret in secrets:
		expected = hmac.new(
			secret.encode("utf-8"),
			f"{t}.{raw_body}".encode("utf-8"),
			hashlib.sha256,
		).hexdigest()

		for v1 in v1_list:
			if hmac.compare_digest(expected, v1):
				return {"ok": True}

	return {"ok": False, "reason": "bad_signature"}
