import hashlib
import hmac
import time

from speechweave.webhooks import verify_webhook


def _sign(
	secret: str,
	timestamp: str,
	body: str,
) -> str:
	return hmac.new(
		secret.encode("utf-8"),
		f"{timestamp}.{body}".encode("utf-8"),
		hashlib.sha256,
	).hexdigest()


def test_verify_webhook_success():
	secret = "whsec_test"
	body = '{"type":"job.completed","id":"job_1"}'
	t = str(int(time.time()))
	sig = _sign(secret, t, body)

	result = verify_webhook(
		secret,
		body,
		f"t={t},v1={sig}",
	)
	assert result == {"ok": True}


def test_verify_webhook_multi_secret_rotation():
	active = "whsec_new"
	previous = "whsec_old"
	body = '{"type":"job.failed"}'
	t = str(int(time.time()))
	sig = _sign(previous, t, body)

	result = verify_webhook(
		[active, previous],
		body,
		f"t={t},v1={sig}",
	)
	assert result == {"ok": True}


def test_verify_webhook_timestamp_skew():
	secret = "whsec_test"
	body = "{}"
	t = str(int(time.time()) - 400)
	sig = _sign(secret, t, body)

	result = verify_webhook(
		secret,
		body,
		f"t={t},v1={sig}",
	)
	assert result == {"ok": False, "reason": "timestamp_skew"}


def test_verify_webhook_bad_signature():
	secret = "whsec_test"
	body = "{}"
	t = str(int(time.time()))

	result = verify_webhook(
		secret,
		body,
		f"t={t},v1={'0' * 64}",
	)
	assert result == {"ok": False, "reason": "bad_signature"}


def test_verify_webhook_mangled_header():
	result = verify_webhook(
		"whsec_test",
		"{}",
		"not-a-valid-header",
	)
	assert result == {"ok": False, "reason": "missing_t_or_v1"}


def test_verify_webhook_missing_t_or_v1():
	result = verify_webhook(
		"whsec_test",
		"{}",
		"t=12345",
	)
	assert result == {"ok": False, "reason": "missing_t_or_v1"}


def test_verify_webhook_no_secrets():
	result = verify_webhook(
		"",
		"{}",
		"t=1,v1=abc",
	)
	assert result == {"ok": False, "reason": "no_secrets"}

	result = verify_webhook(
		["", "  "],
		"{}",
		"t=1,v1=abc",
	)
	assert result == {"ok": False, "reason": "no_secrets"}


def test_verify_webhook_bad_timestamp():
	result = verify_webhook(
		"whsec_test",
		"{}",
		"t=not-a-number,v1=abc",
	)
	assert result == {"ok": False, "reason": "bad_timestamp"}
