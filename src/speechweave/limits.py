from __future__ import annotations

from typing import Any, Mapping

from speechweave.errors import SpeechWeaveError

#: How long `GET /v1/limits` is reused before refetching.
LIMITS_CACHE_SECONDS = 300.0

_DEFERRED_ALIASES = frozenset({"deferred", "async", "asynchronous", "delayed", "queue", "queued"})


def applies_sync_size_cap(service_mode: str | None) -> bool:
	"""True when the local upload gate should apply `sync_max_bytes`."""
	if service_mode is None or not str(service_mode).strip():
		return True
	return str(service_mode).strip().lower() not in _DEFERRED_ALIASES


def check_within_limits(
	size_bytes: int | None,
	limits: Mapping[str, Any] | None,
	service_mode: str | None = None,
) -> None:
	"""
	Raise before an upload is spent when a known size exceeds the account's caps.

	No-ops when the size is unmeasurable (non-seekable streams) or `limits` is
	None. In both cases the API stays the authority.

	Args:
		size_bytes: Measured body length, or None when it could not be measured.
		limits: Payload from `GET /v1/limits`, or None if the lookup failed.
		service_mode: Applies the stricter standard-mode cap when omitted, `standard`,
			or the `synchronous` alias.

	Raises:
		SpeechWeaveError: 413 with code `FILE_TOO_LARGE`.
	"""
	if size_bytes is None or limits is None:
		return

	max_input = limits.get("max_input_bytes")
	sync_max = limits.get("sync_max_bytes")

	if (
		applies_sync_size_cap(service_mode)
		and isinstance(sync_max, int)
		and isinstance(max_input, int)
		and size_bytes > sync_max
		and sync_max < max_input
	):
		raise SpeechWeaveError(
			f"File is {size_bytes} bytes, over the {sync_max} byte standard-mode limit. "
			"Use service_mode 'deferred' for files this size.",
			413,
			"FILE_TOO_LARGE",
		)

	if isinstance(max_input, int) and size_bytes > max_input:
		raise SpeechWeaveError(
			f"File is {size_bytes} bytes, over this account's {max_input} byte limit.",
			413,
			"FILE_TOO_LARGE",
		)
