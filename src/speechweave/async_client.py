from __future__ import annotations

import asyncio
import os
import time
from collections.abc import AsyncIterator
from typing import Any, BinaryIO, Mapping, MutableMapping

import httpx

from speechweave.client import UploadBody, _content_length, _upload_headers
from speechweave.errors import SpeechWeaveError
from speechweave.limits import LIMITS_CACHE_SECONDS, check_within_limits
from speechweave.mime import infer_content_type
from speechweave.version import __version__

_UPLOAD_CHUNK_SIZE = 64 * 1024


def _normalize_base(url: str) -> str:

	s = (url or "").strip().rstrip("/")

	return s or "https://api.speechweave.com/v1"


async def _async_upload_content(data: UploadBody) -> bytes | AsyncIterator[bytes]:
	"""
	Normalize upload body for `httpx.AsyncClient` (rejects sync file streams).
	"""
	if isinstance(data, (bytes, bytearray, memoryview)):
		return bytes(data)

	async def _chunks() -> AsyncIterator[bytes]:
		while True:
			chunk = await asyncio.to_thread(data.read, _UPLOAD_CHUNK_SIZE)
			if not chunk:
				break
			yield chunk

	return _chunks()


class AsyncSpeechWeaveClient:
	"""
	Async SpeechWeave `/v1` client (presign, jobs, uploads).
	"""

	def __init__(
		self,
		api_key: str | None = None,
		*,
		base_url: str | None = None,
		timeout: float = 120.0,
		client: httpx.AsyncClient | None = None,
	):
		"""
		Args:
			api_key: Falls back to `SPEECHWEAVE_API_KEY`. Raises if neither is set.
			base_url: Defaults to `https://api.speechweave.com/v1`.
			timeout: httpx timeout in seconds when constructing a new client.
			client: Injected `httpx.AsyncClient`; caller owns `aclose` if provided.
		"""

		self.api_key = api_key or os.environ.get("SPEECHWEAVE_API_KEY") or ""
		self.base_url = _normalize_base(base_url or "")

		if not self.api_key:
			raise ValueError("SpeechWeave API key is required (api_key or SPEECHWEAVE_API_KEY)")

		self._owns_client = client is None
		self._client = client or httpx.AsyncClient(timeout=timeout)
		self._cached_limits: dict[str, Any] | None = None
		self._cached_limits_at = 0.0

	async def aclose(self) -> None:
		"""
		Close the owned httpx client. No-op when a client was injected.
		"""
		if self._owns_client:
			await self._client.aclose()

	async def __aenter__(self) -> AsyncSpeechWeaveClient:
		return self

	async def __aexit__(
		self,
		*args: object,
	) -> None:
		await self.aclose()

	def _auth_headers(
		self,
		json_body: bool = False,
	) -> dict[str, str]:

		h: dict[str, str] = {
			"Authorization": f"Bearer {self.api_key}",
			"Accept": "application/json",
			"User-Agent": f"speechweave-python/{__version__}",
		}

		if json_body:
			h["Content-Type"] = "application/json"

		return h

	def _url(
		self,
		path: str,
	) -> str:

		p = path if path.startswith("/") else f"/{path}"

		return f"{self.base_url}{p}"

	async def request_json(
		self,
		method: str,
		path: str,
		json: Mapping[str, Any] | None = None,
		params: Mapping[str, Any] | None = None,
	) -> Any:
		"""
		JSON request against `base_url`. Raises `SpeechWeaveError` on HTTP >= 400.

		Args:
			path: Relative to `base_url` (leading `/` optional).
		"""

		r = await self._client.request(
			method,
			self._url(path),
			headers=self._auth_headers(json_body=json is not None),
			json=json,
			params=params,
		)

		if r.status_code >= 400:
			body = None
			error_type = None
			param = None

			try:
				body = r.json()
				# `error` is an object on current servers (OpenAI-style envelope) but a plain string on
				# on servers predating that change, so support both for compatibility.
				error_val = body.get("error")
				nested_error = error_val if isinstance(error_val, dict) else None
				msg = str(
					(nested_error.get("message") if nested_error else None)
					or body.get("message")
					or error_val
					or r.text
				)
				code = (nested_error.get("code") if nested_error else None) or body.get("code")
				if nested_error:
					error_type = nested_error.get("type")
					param = nested_error.get("param")
				retry_after = body.get("retry_after")
				if retry_after is None and r.headers.get("Retry-After"):
					try:
						retry_after = int(r.headers.get("Retry-After"))
					except (TypeError, ValueError):
						retry_after = None
			except Exception:
				msg = r.text or r.reason_phrase
				code = str(r.status_code)
				retry_after = None
			raise SpeechWeaveError(
				msg,
				r.status_code,
				str(code) if code is not None else str(r.status_code),
				body=body,
				retry_after=retry_after if isinstance(retry_after, int) else None,
				error_type=error_type,
				param=param,
			)

		if r.status_code == 204 or not r.content:
			return None

		return r.json()

	async def raw_request(
		self,
		method: str,
		path: str,
		**kwargs: Any,
	) -> httpx.Response:
		"""
		Authenticated request returning the raw `httpx.Response`.

		Merges Bearer / Accept / User-Agent; caller-supplied headers win on conflict.
		"""

		headers = kwargs.pop("headers", {}) or {}
		merged = {**self._auth_headers(json_body=False), **headers}

		return await self._client.request(
			method,
			self._url(path),
			headers=merged,
			**kwargs,
		)

	async def get_limits(self) -> dict[str, Any]:
		"""
		Upload ceilings in bytes for the calling API key. Values are account-specific.

		Prefer `get_cached_limits` on hot paths. This always hits the network.
		"""

		return await self.request_json("GET", "/limits")

	async def get_cached_limits(self) -> dict[str, Any] | None:
		"""
		`get_limits` memoized for `LIMITS_CACHE_SECONDS`.

		Returns None instead of raising when the lookup fails. The local size gate
		is an optimization, so a limits outage must not block uploads the API would
		have accepted. Failures are not cached, so the next call retries.
		"""

		now = time.monotonic()
		if self._cached_limits is not None and now - self._cached_limits_at < LIMITS_CACHE_SECONDS:
			return self._cached_limits

		try:
			limits = await self.get_limits()
		except Exception:
			return None

		self._cached_limits = limits
		self._cached_limits_at = now

		return limits

	async def ensure_within_limits(
		self,
		size_bytes: int | None,
		service_mode: str | None = None,
	) -> None:
		"""
		Raise a 413 `SpeechWeaveError` when a known size exceeds the account's caps.

		No-op when the size is unmeasurable or the limits lookup failed.
		"""

		if size_bytes is None:
			return

		check_within_limits(size_bytes, await self.get_cached_limits(), service_mode)

	async def presign_upload(
		self,
		*,
		filename: str,
		content_type: str,
		content_length: int | None = None,
	) -> dict[str, Any]:
		"""
		Request a short-lived PUT URL and `object_key` for direct upload.

		Args:
			filename: Original name (used in the storage key).
			content_type: MIME type that must match the subsequent PUT.
			content_length: Declared upload size in bytes (when known).
		"""

		body: dict[str, Any] = {"filename": filename, "content_type": content_type}
		if content_length is not None:
			body["content_length"] = content_length

		return await self.request_json("POST", "/uploads", body)

	async def put_presigned_url(
		self,
		upload_url: str,
		data: UploadBody,
		content_type: str,
		*,
		file_size: int | None = None,
	) -> None:
		"""
		PUT audio bytes to a presigned `upload_url`.

		Sync file objects are read off-thread in 64 KiB chunks (`AsyncClient`
		rejects sync streams). Pass `file_size` when length cannot be measured.

		Args:
			upload_url: `upload_url` from `presign_upload`.
			file_size: Explicit byte length when length cannot be measured.
		"""

		headers = _upload_headers(content_type, data, file_size=file_size)
		content = await _async_upload_content(data)
		r = await self._client.put(
			upload_url,
			content=content,
			headers=headers,
		)

		if r.status_code >= 400:
			raise SpeechWeaveError(f"R2 upload failed: {r.text}", r.status_code, "UPLOAD_FAILED")

	async def create_job(
		self,
		body: MutableMapping[str, Any],
	) -> dict[str, Any]:
		"""
		Create a transcription job from an uploaded object or remote URL.

		Provide one of `object_key`, `input_url`, or `audio_url`. `type` defaults to
		`transcription`. Omitting `service_mode` leaves the API default (synchronous).
		Synchronous has its own size cap, at or below the account cap, see `get_limits`.

		Args:
			body: Job fields. `object_key` is from a prior presign after a PUT;
				`input_url` / `audio_url` are publicly reachable audio URLs;
				`language` is a two-letter ISO code (e.g. 'en', 'es').
		"""

		payload: dict[str, Any] = {"type": body.get("type") or "transcription"}
		for key in (
			"object_key",
			"input_url",
			"audio_url",
			"model",
			"service_mode",
			"language",
			"task",
			"prompt",
			"temperature",
			"timestamp_granularities",
			"metadata",
		):
			if key in body and body[key] is not None:
				payload[key] = body[key]

		return await self.request_json("POST", "/jobs", payload)

	async def get_job(
		self,
		job_id: str,
	) -> dict[str, Any]:
		"""
		Fetch the current job record (status, transcript when completed).

		Args:
			job_id: Id from `create_job` / `transcribe_file`.
		"""
		return await self.request_json("GET", f"/jobs/{job_id}")

	async def get_job_formatted(
		self,
		job_id: str,
		format: str,
	) -> Any:
		"""
		Fetch a completed job's transcript re-formatted server-side from its stored
		segments (`GET /v1/jobs/:id?format=`), the same formatting the sync
		OpenAI-compat proxy uses, available for jobs submitted through the native
		async flow. Raises `SpeechWeaveError` (409) if the job isn't completed yet.

		Args:
			format: 'text' | 'srt' | 'vtt' return a raw string; 'verbose_json' returns a dict.
		"""

		response = await self.raw_request("GET", f"/jobs/{job_id}", params={"format": format})

		if response.status_code >= 400:
			try:
				body = response.json()
				msg = str(body.get("error") or response.text)
			except Exception:
				msg = response.text or response.reason_phrase
			raise SpeechWeaveError(msg, response.status_code, str(response.status_code))

		content_type = response.headers.get("content-type", "")
		if "application/json" in content_type:
			return response.json()

		return response.text

	async def list_jobs(
		self,
		*,
		page: int | None = None,
		limit: int | None = None,
		status: str | None = None,
	) -> dict[str, Any]:
		"""
		List jobs for the authenticated account.

		Args:
			page: 1-based page; API default if omitted.
			limit: Page size; API default if omitted.
			status: Filter by job status (queued, processing, completed, …).
		"""
		params: dict[str, Any] = {}
		if page is not None:
			params["page"] = page
		if limit is not None:
			params["limit"] = limit
		if status is not None:
			params["status"] = status

		return await self.request_json("GET", "/jobs", params=params or None)

	async def cancel_job(
		self,
		job_id: str,
	) -> dict[str, Any]:
		"""
		Cancel a pending or processing job.

		Fails if the job is already completed, failed, or cancelled.

		Args:
			job_id: Id from `create_job` / `transcribe_file`.
		"""
		return await self.request_json("POST", f"/jobs/{job_id}/cancel", {})

	async def transcribe_file(
		self,
		file_obj: BinaryIO,
		*,
		filename: str = "audio.bin",
		content_type: str | None = None,
		model: str | None = None,
		service_mode: str | None = None,
		language: str | None = None,
		task: str | None = None,
		prompt: str | None = None,
		temperature: float | None = None,
		timestamp_granularities: list[str] | None = None,
		metadata: dict[str, Any] | None = None,
		file_size: int | None = None,
	) -> dict[str, Any]:
		"""
		Presign → PUT → create job.

		Returns the create ack (no transcript); poll `get_job` or `async_wait_for_job`.
		Sync file objects are streamed off-thread. Omitting `service_mode` leaves
		the API default (synchronous).

		Files whose size is measurable are checked against the account's limits
		(see `get_limits`) before uploading, and rejected locally with a 413
		`SpeechWeaveError` rather than spending the transfer.

		Args:
			file_obj: Open binary file or buffer to upload.
			filename: Defaults to `audio.bin`.
			content_type: Inferred from filename's extension when omitted; falls back to
				`application/octet-stream`.
			language: Two-letter ISO code (e.g. 'en', 'es'). Ignored when task is 'translate'.
			task: 'transcribe' (default) or 'translate' (translate to English).
			prompt: Custom vocabulary/style hint for the first ~30s window.
			temperature: Decoding temperature, clamped to [0, 1] server-side.
			timestamp_granularities: Include 'word' for word-level timestamps.
			file_size: `Content-Length` when the body cannot be measured.
		"""

		content_type = content_type or infer_content_type(filename)
		size_bytes = _content_length(file_obj, file_size=file_size)
		# Gate before presign so an oversized file costs neither a presign nor an upload.
		await self.ensure_within_limits(size_bytes, service_mode)
		presign = await self.presign_upload(
			filename=filename,
			content_type=content_type,
			content_length=size_bytes,
		)
		await self.put_presigned_url(
			presign["upload_url"],
			file_obj,
			content_type,
			file_size=file_size,
		)
		body: dict[str, Any] = {"object_key": presign["object_key"]}

		if model:
			body["model"] = model
		if service_mode:
			body["service_mode"] = service_mode
		if language:
			body["language"] = language
		if task:
			body["task"] = task
		if prompt:
			body["prompt"] = prompt
		if temperature is not None:
			body["temperature"] = temperature
		if timestamp_granularities:
			body["timestamp_granularities"] = timestamp_granularities
		if metadata:
			body["metadata"] = metadata

		return await self.create_job(body)
