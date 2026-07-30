from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from typing import Any, BinaryIO, Mapping, MutableMapping

import httpx

from speechweave.client import UploadBody, _upload_headers
from speechweave.errors import SpeechWeaveError
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

	async def presign_upload(
		self,
		*,
		filename: str,
		content_type: str,
	) -> dict[str, Any]:
		"""
		Request a short-lived PUT URL and `object_key` for direct upload.

		Args:
			filename: Original name (used in the storage key).
			content_type: MIME type that must match the subsequent PUT.
		"""

		return await self.request_json(
			"POST",
			"/uploads",
			{"filename": filename, "content_type": content_type},
		)

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
		`transcription`. Omitting `service_mode` leaves the API default (deferred).
		Synchronous rejects files over the sync size cap (default 512 MiB).

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
		metadata: dict[str, Any] | None = None,
		file_size: int | None = None,
	) -> dict[str, Any]:
		"""
		Presign → PUT → create job.

		Returns the create ack (no transcript); poll `get_job` or `async_wait_for_job`.
		Sync file objects are streamed off-thread. Omitting `service_mode` leaves
		the API default (deferred). Synchronous rejects files over the sync size
		cap (default 512 MiB).

		Args:
			file_obj: Open binary file or buffer to upload.
			filename: Defaults to `audio.bin`.
			content_type: Inferred from filename's extension when omitted; falls back to
				`application/octet-stream`.
			language: Two-letter ISO code (e.g. 'en', 'es').
			file_size: `Content-Length` when the body cannot be measured.
		"""

		content_type = content_type or infer_content_type(filename)
		presign = await self.presign_upload(
			filename=filename,
			content_type=content_type,
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
		if metadata:
			body["metadata"] = metadata

		return await self.create_job(body)
