from __future__ import annotations

import asyncio
import random
import time
from typing import TYPE_CHECKING, Any

from speechweave.errors import SpeechWeaveError

if TYPE_CHECKING:
	from speechweave.async_client import AsyncSpeechWeaveClient
	from speechweave.client import SpeechWeaveClient

TERMINAL = frozenset({"completed", "failed", "cancelled"})


def wait_for_job(
	client: "SpeechWeaveClient",
	job_id: str,
	*,
	timeout_sec: float = 3600.0,
	poll_sec: float = 2.0,
	max_consecutive_network_errors: int = 5,
) -> dict[str, Any]:
	"""
	Poll `get_job` until completed, failed, or cancelled.

	A transient network error is retried at the normal poll interval instead
	of failing the wait outright, up to `max_consecutive_network_errors` in a row.
	A 429 (rate limited) response is always retried -- using the server's
	`retry_after` when present, else the normal poll interval -- since it reflects
	polling pressure, not the job's own outcome, and doesn't count against
	`max_consecutive_network_errors`. The wait is jittered (50-100% of the reported
	value) and never exceeds what's left of timeout_sec, since retry_after reflects
	the server's full rate-limit window rather than time remaining in it. Any other
	API error (4xx/5xx) is raised immediately.

	Raises `SpeechWeaveError` with code `JOB_WAIT_TIMEOUT` on deadline.

	Args:
		job_id: Id from `create_job` / `transcribe_file`.
		timeout_sec: Max wait (defaults to 3600).
		poll_sec: Interval between polls (defaults to 2).
		max_consecutive_network_errors: Consecutive transient network errors
			tolerated before giving up (defaults to 5).
	"""

	deadline = time.monotonic() + timeout_sec
	consecutive_errors = 0

	while time.monotonic() < deadline:
		try:
			job = client.get_job(job_id)
		except SpeechWeaveError as error:
			if error.status == 429:
				# retry_after is the server's full rate-limit window, not time remaining in it,
				# so it can exceed our own deadline. Clamp to what's left and jitter to 50-100%
				# of that so concurrent callers sharing one account's limit don't retry in lockstep.
				raw_wait_sec = error.retry_after if error.retry_after and error.retry_after > 0 else poll_sec
				remaining_sec = deadline - time.monotonic()
				wait_sec = max(0.0, min(raw_wait_sec * random.uniform(0.5, 1.0), remaining_sec))
				time.sleep(wait_sec)
				continue
			raise
		except Exception:
			consecutive_errors += 1
			if consecutive_errors > max_consecutive_network_errors:
				raise
			time.sleep(poll_sec)
			continue

		consecutive_errors = 0
		if str(job.get("status", "")) in TERMINAL:
			return job

		time.sleep(poll_sec)

	raise SpeechWeaveError("Timed out waiting for job", 504, "JOB_WAIT_TIMEOUT", {"job_id": job_id})


async def async_wait_for_job(
	client: "AsyncSpeechWeaveClient",
	job_id: str,
	*,
	timeout_sec: float = 3600.0,
	poll_sec: float = 2.0,
	max_consecutive_network_errors: int = 5,
) -> dict[str, Any]:
	"""
	Poll `get_job` until completed, failed, or cancelled.

	A transient network erroris retried at the normal poll interval instead
	 of failing the wait outright, up to `max_consecutive_network_errors` in a row.
	A 429 (rate limited) response is always retried -- using the server's
	`retry_after` when present, else the normal poll interval -- since it reflects
	polling pressure, not the job's own outcome, and doesn't count against
	`max_consecutive_network_errors`. The wait is jittered (50-100% of the reported
	value) and never exceeds what's left of timeout_sec, since retry_after reflects
	the server's full rate-limit window rather than time remaining in it. Any other
	API error (4xx/5xx) is raised immediately.

	Raises `SpeechWeaveError` with code `JOB_WAIT_TIMEOUT` on deadline.

	Args:
		job_id: Id from `create_job` / `transcribe_file`.
		timeout_sec: Max wait (defaults to 3600).
		poll_sec: Interval between polls (defaults to 2).
		max_consecutive_network_errors: Consecutive transient network errors
			tolerated before giving up (defaults to 5).
	"""

	deadline = time.monotonic() + timeout_sec
	consecutive_errors = 0

	while time.monotonic() < deadline:
		try:
			job = await client.get_job(job_id)
		except SpeechWeaveError as error:
			if error.status == 429:
				raw_wait_sec = error.retry_after if error.retry_after and error.retry_after > 0 else poll_sec
				remaining_sec = deadline - time.monotonic()
				wait_sec = max(0.0, min(raw_wait_sec * random.uniform(0.5, 1.0), remaining_sec))
				await asyncio.sleep(wait_sec)
				continue
			raise
		except Exception:
			consecutive_errors += 1
			if consecutive_errors > max_consecutive_network_errors:
				raise
			await asyncio.sleep(poll_sec)
			continue

		consecutive_errors = 0
		if str(job.get("status", "")) in TERMINAL:
			return job

		await asyncio.sleep(poll_sec)

	raise SpeechWeaveError("Timed out waiting for job", 504, "JOB_WAIT_TIMEOUT", {"job_id": job_id})
