from __future__ import annotations

from typing import Any, Mapping

from speechweave.errors import SpeechWeaveError

#: How long `GET /v1/limits` is reused before refetching.
LIMITS_CACHE_SECONDS = 300.0


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
		service_mode: Applies the stricter synchronous cap when 'synchronous'.

	Raises:
		SpeechWeaveError: 413 with code `FILE_TOO_LARGE`.
	"""
	if size_bytes is None or limits is None:
		return

	max_input = limits.get("max_input_bytes")
	sync_max = limits.get("sync_max_bytes")

	if (
		service_mode == "synchronous"
		and isinstance(sync_max, int)
		and isinstance(max_input, int)
		and size_bytes > sync_max
		and sync_max < max_input
	):
		raise SpeechWeaveError(
			f"File is {size_bytes} bytes, over the {sync_max} byte synchronous limit. "
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
