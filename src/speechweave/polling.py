from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

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
) -> dict[str, Any]:
	"""
	Poll `get_job` until completed, failed, or cancelled.

	Raises `SpeechWeaveError` with code `JOB_WAIT_TIMEOUT` on deadline.

	Args:
		job_id: Id from `create_job` / `transcribe_file`.
		timeout_sec: Max wait; defaults to 3600.
		poll_sec: Interval between polls; defaults to 2.
	"""

	deadline = time.monotonic() + timeout_sec
	while time.monotonic() < deadline:
		job = client.get_job(job_id)
		if str(job.get("status", "")) in TERMINAL:
			return job

		time.sleep(poll_sec)

	from speechweave.errors import SpeechWeaveError

	raise SpeechWeaveError("Timed out waiting for job", 504, "JOB_WAIT_TIMEOUT", {"job_id": job_id})


async def async_wait_for_job(
	client: "AsyncSpeechWeaveClient",
	job_id: str,
	*,
	timeout_sec: float = 3600.0,
	poll_sec: float = 2.0,
) -> dict[str, Any]:
	"""
	Poll `get_job` until completed, failed, or cancelled.

	Raises `SpeechWeaveError` with code `JOB_WAIT_TIMEOUT` on deadline.

	Args:
		job_id: Id from `create_job` / `transcribe_file`.
		timeout_sec: Max wait; defaults to 3600.
		poll_sec: Interval between polls; defaults to 2.
	"""

	deadline = time.monotonic() + timeout_sec
	while time.monotonic() < deadline:
		job = await client.get_job(job_id)
		if str(job.get("status", "")) in TERMINAL:
			return job

		await asyncio.sleep(poll_sec)

	from speechweave.errors import SpeechWeaveError

	raise SpeechWeaveError("Timed out waiting for job", 504, "JOB_WAIT_TIMEOUT", {"job_id": job_id})
