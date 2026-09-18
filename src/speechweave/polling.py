from __future__ import annotations

import asyncio
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
		except SpeechWeaveError:
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
		except SpeechWeaveError:
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
