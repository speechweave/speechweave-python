import pytest
from speechweave import SpeechWeaveError
from speechweave.limits import check_within_limits

_LIMITS = {
	"max_input_bytes": 1000,
	"sync_max_bytes": 500,
	"proxy_max_bytes": 500,
}


def test_passes_when_within_limits():
	assert check_within_limits(400, _LIMITS) is None


def test_raises_over_account_cap():
	with pytest.raises(SpeechWeaveError) as exc_info:
		check_within_limits(1001, _LIMITS)

	assert exc_info.value.status == 413
	assert exc_info.value.code == "FILE_TOO_LARGE"


def test_points_at_deferred_when_only_the_sync_cap_is_exceeded():
	with pytest.raises(SpeechWeaveError) as exc_info:
		check_within_limits(600, _LIMITS, "synchronous")

	assert "deferred" in str(exc_info.value)


def test_does_not_suggest_deferred_when_the_account_cap_is_the_binding_one():
	"""The 500-vs-512 bug: advising deferred for a size deferred also rejects."""
	limits = {"max_input_bytes": 500, "sync_max_bytes": 500, "proxy_max_bytes": 500}
	with pytest.raises(SpeechWeaveError) as exc_info:
		check_within_limits(600, limits, "synchronous")

	assert "deferred" not in str(exc_info.value)


def test_no_ops_when_size_unknown():
	assert check_within_limits(None, _LIMITS) is None


def test_no_ops_when_limits_unavailable():
	assert check_within_limits(10**12, None) is None
