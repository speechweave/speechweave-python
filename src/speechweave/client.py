from __future__ import annotations

import os
from typing import Any, BinaryIO, Mapping, MutableMapping, Union

import httpx

from speechweave.errors import SpeechWeaveError
from speechweave.mime import infer_content_type
from speechweave.version import __version__

#: Bytes, buffer, or file-like object accepted by upload helpers.
UploadBody = Union[bytes, bytearray, memoryview, BinaryIO]


def _normalize_base(
	url: str,
) -> str:
	s = (url or "").strip().rstrip("/")

	return s or "https://api.speechweave.com/v1"


def _content_length(
	data: UploadBody,
	file_size: int | None = None,
) -> int | None:
	if file_size is not None:
		return int(file_size)

	if isinstance(data, (bytes, bytearray, memoryview)):
		return len(data)

	seek = getattr(data, "seek", None)
	tell = getattr(data, "tell", None)
	if not callable(seek) or not callable(tell):
		return None

	try:
		pos = tell()
		seek(0, os.SEEK_END)
		end = tell()
		seek(pos)
		return int(end - pos)
	except Exception:
		return None


def _upload_headers(
	content_type: str,
	data: UploadBody,
	file_size: int | None = None,
) -> dict[str, str]:
	headers = {"Content-Type": content_type}
	length = _content_length(data, file_size=file_size)
	if length is not None:
		headers["Content-Length"] = str(length)
	return headers


class SpeechWeaveClient:
	"""
	Synchronous SpeechWeave `/v1` client (presign, jobs, uploads).
	"""

	def __init__(
		self,
		api_key: str | None = None,
		*,
		base_url: str | None = None,
		timeout: float = 120.0,
		client: httpx.Client | None = None,
	):
		"""
		Args:
			api_key: Falls back to `SPEECHWEAVE_API_KEY`. Raises if neither is set.
			base_url: Defaults to `https://api.speechweave.com/v1`.
			timeout: httpx timeout in seconds when constructing a new client.
			client: Injected `httpx.Client`; caller owns close if provided.
		"""

		self.api_key = api_key or os.environ.get("SPEECHWEAVE_API_KEY") or ""
		self.base_url = _normalize_base(base_url or "")

		if not self.api_key:
			raise ValueError("SpeechWeave API key is required (api_key or SPEECHWEAVE_API_KEY)")

		self._owns_client = client is None
		self._client = client or httpx.Client(timeout=timeout)

	def close(self) -> None:
		"""
		Close the owned httpx client. No-op when a client was injected.
		"""
		if self._owns_client:
			self._client.close()

	def __enter__(self) -> SpeechWeaveClient:
		return self

	def __exit__(
		self,
		*args: object,
	) -> None:
		self.close()

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

		formatted_path = path if path.startswith("/") else f"/{path}"

		return f"{self.base_url}{formatted_path}"

	def request_json(
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

		response = self._client.request(
			method,
			self._url(path),
			headers=self._auth_headers(json_body=json is not None),
			json=json,
			params=params,
		)

		if response.status_code >= 400:
			body = None
			try:
				body = response.json()
				msg = str(body.get("error") or body.get("message") or response.text)
				code = body.get("code")
				retry_after = body.get("retry_after")

				if retry_after is None and response.headers.get("Retry-After"):
					try:
						retry_after = int(response.headers.get("Retry-After"))
					except (TypeError, ValueError):
						retry_after = None

			except Exception:
				msg = response.text or response.reason_phrase
				code = str(response.status_code)
				retry_after = None

			raise SpeechWeaveError(
				msg,
				response.status_code,
				str(code) if code is not None else str(response.status_code),
				body=body,
				retry_after=retry_after if isinstance(retry_after, int) else None,
			)

		if response.status_code == 204 or not response.content:
			return None

		return response.json()

	def raw_request(
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
		merged = {
			**self._auth_headers(json_body=False),
			**headers,
		}

		return self._client.request(
			method,
			self._url(path),
			headers=merged,
			**kwargs,
		)

	def presign_upload(
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

		return self.request_json(
			"POST",
			"/uploads",
			{"filename": filename, "content_type": content_type},
		)

	def put_presigned_url(
		self,
		upload_url: str,
		data: UploadBody,
		content_type: str,
		*,
		file_size: int | None = None,
	) -> None:
		"""
		PUT audio bytes to a presigned `upload_url`.

		Sets `Content-Length` when the body can be measured; pass `file_size` for
		non-seekable streams.

		Args:
			upload_url: `upload_url` from `presign_upload`.
			file_size: Explicit byte length when length cannot be measured.
		"""

		response = self._client.put(
			upload_url,
			content=data,
			headers=_upload_headers(content_type, data, file_size=file_size),
		)

		if response.status_code >= 400:
			raise SpeechWeaveError(
				f"R2 upload failed: {response.text}",
				response.status_code,
				"UPLOAD_FAILED",
			)

	def create_job(
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

		return self.request_json("POST", "/jobs", payload)

	def get_job(
		self,
		job_id: str,
	) -> dict[str, Any]:
		"""
		Fetch the current job record (status, transcript when completed).

		Args:
			job_id: Id from `create_job` / `transcribe_file`.
		"""
		return self.request_json("GET", f"/jobs/{job_id}")

	def list_jobs(
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

		return self.request_json("GET", "/jobs", params=params or None)

	def cancel_job(
		self,
		job_id: str,
	) -> dict[str, Any]:
		"""
		Cancel a pending or processing job.

		Fails if the job is already completed, failed, or cancelled.

		Args:
			job_id: Id from `create_job` / `transcribe_file`.
		"""
		return self.request_json("POST", f"/jobs/{job_id}/cancel", {})

	def transcribe_file(
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

		Returns the create ack (no transcript); poll `get_job` or `wait_for_job`.
		Omitting `service_mode` leaves the API default (deferred). Synchronous
		rejects files over the sync size cap (default 512 MiB).

		Args:
			file_obj: Open binary file or buffer to upload.
			filename: Defaults to `audio.bin`.
			content_type: Inferred from filename's extension when omitted; falls back to
				`application/octet-stream`.
			language: Two-letter ISO code (e.g. 'en', 'es').
			file_size: `Content-Length` when the body cannot be measured.
		"""

		content_type = content_type or infer_content_type(filename)
		presign = self.presign_upload(
			filename=filename,
			content_type=content_type,
		)
		self.put_presigned_url(
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

		return self.create_job(body)
