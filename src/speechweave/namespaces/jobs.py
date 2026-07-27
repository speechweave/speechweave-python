from __future__ import annotations

from typing import TYPE_CHECKING, Any, BinaryIO

if TYPE_CHECKING:
	from speechweave.async_client import AsyncSpeechWeaveClient
	from speechweave.client import SpeechWeaveClient


class Jobs:
	"""
	Native jobs API: create / get / list / cancel.
	"""

	def __init__(
		self,
		client: SpeechWeaveClient,
	):
		self._client = client

	def create(
		self,
		*,
		file: str | BinaryIO | None = None,
		filename: str | None = None,
		content_type: str | None = None,
		object_key: str | None = None,
		input_url: str | None = None,
		audio_url: str | None = None,
		model: str | None = None,
		service_mode: str | None = None,
		language: str | None = None,
		type: str | None = None,
		metadata: dict[str, Any] | None = None,
		file_size: int | None = None,
	) -> dict[str, Any]:
		"""
		Create a job from a local file or a remote URL / object_key.

		Pass `file` (path or binary) to presign-upload then create. Otherwise
		pass one of `object_key`, `input_url`, or `audio_url` (no upload).
		Omitting `service_mode` leaves the API default (deferred).

		Args:
			file: Local path or open binary file. Mutually exclusive with URL keys.
			input_url: Publicly reachable audio URL (`audio_url` is an alias).
			object_key: From a prior presign + PUT.
			language: Two-letter ISO code (e.g. 'en', 'es').
			file_size: Content-Length when a stream body cannot be measured.
		"""

		if file is not None:
			if isinstance(file, str):
				with open(file, "rb") as f:
					return self._client.transcribe_file(
						f,
						filename=filename or file.split("/")[-1] or "audio.bin",
						content_type=content_type,
						model=model,
						service_mode=service_mode,
						language=language,
						metadata=metadata,
						file_size=file_size,
					)

			return self._client.transcribe_file(
				file,
				filename=filename or "audio.bin",
				content_type=content_type,
				model=model,
				service_mode=service_mode,
				language=language,
				metadata=metadata,
				file_size=file_size,
			)

		body: dict[str, Any] = {}
		if object_key is not None:
			body["object_key"] = object_key
		if input_url is not None:
			body["input_url"] = input_url
		if audio_url is not None:
			body["audio_url"] = audio_url
		if model is not None:
			body["model"] = model
		if service_mode is not None:
			body["service_mode"] = service_mode
		if language is not None:
			body["language"] = language
		if type is not None:
			body["type"] = type
		if metadata is not None:
			body["metadata"] = metadata

		return self._client.create_job(body)

	def get(
		self,
		job_id: str,
	) -> dict[str, Any]:
		"""
		Fetch the current job record.

		Args:
			job_id: Id from create / `transcribe_file`.
		"""
		return self._client.get_job(job_id)

	def list(
		self,
		*,
		page: int | None = None,
		limit: int | None = None,
		status: str | None = None,
	) -> dict[str, Any]:
		"""
		List jobs for the authenticated account.

		Args:
			status: Filter by job status (queued, processing, completed, …).
		"""
		return self._client.list_jobs(page=page, limit=limit, status=status)

	def cancel(
		self,
		job_id: str,
	) -> dict[str, Any]:
		"""
		Cancel a pending or processing job.

		Fails if the job is already completed, failed, or cancelled.

		Args:
			job_id: Id from create / `transcribe_file`.
		"""
		return self._client.cancel_job(job_id)


class AsyncJobs:
	"""
	Async native jobs API: create / get / list / cancel.
	"""

	def __init__(
		self,
		client: AsyncSpeechWeaveClient,
	):
		self._client = client

	async def create(
		self,
		*,
		file: str | BinaryIO | None = None,
		filename: str | None = None,
		content_type: str | None = None,
		object_key: str | None = None,
		input_url: str | None = None,
		audio_url: str | None = None,
		model: str | None = None,
		service_mode: str | None = None,
		language: str | None = None,
		type: str | None = None,
		metadata: dict[str, Any] | None = None,
		file_size: int | None = None,
	) -> dict[str, Any]:
		"""
		Create a job from a local file or a remote URL / object_key.

		Pass `file` (path or binary) to presign-upload then create. Otherwise
		pass one of `object_key`, `input_url`, or `audio_url` (no upload).
		Omitting `service_mode` leaves the API default (deferred).

		Args:
			file: Local path or open binary file. Mutually exclusive with URL keys.
			input_url: Publicly reachable audio URL (`audio_url` is an alias).
			object_key: From a prior presign + PUT.
			language: Two-letter ISO code (e.g. 'en', 'es').
			file_size: Content-Length when a stream body cannot be measured.
		"""

		if file is not None:
			if isinstance(file, str):
				with open(file, "rb") as f:
					return await self._client.transcribe_file(
						f,
						filename=filename or file.split("/")[-1] or "audio.bin",
						content_type=content_type,
						model=model,
						service_mode=service_mode,
						language=language,
						metadata=metadata,
						file_size=file_size,
					)

			return await self._client.transcribe_file(
				file,
				filename=filename or "audio.bin",
				content_type=content_type,
				model=model,
				service_mode=service_mode,
				language=language,
				metadata=metadata,
				file_size=file_size,
			)

		body: dict[str, Any] = {}
		if object_key is not None:
			body["object_key"] = object_key
		if input_url is not None:
			body["input_url"] = input_url
		if audio_url is not None:
			body["audio_url"] = audio_url
		if model is not None:
			body["model"] = model
		if service_mode is not None:
			body["service_mode"] = service_mode
		if language is not None:
			body["language"] = language
		if type is not None:
			body["type"] = type
		if metadata is not None:
			body["metadata"] = metadata

		return await self._client.create_job(body)

	async def get(
		self,
		job_id: str,
	) -> dict[str, Any]:
		"""
		Fetch the current job record.

		Args:
			job_id: Id from create / `transcribe_file`.
		"""
		return await self._client.get_job(job_id)

	async def list(
		self,
		*,
		page: int | None = None,
		limit: int | None = None,
		status: str | None = None,
	) -> dict[str, Any]:
		"""
		List jobs for the authenticated account.

		Args:
			status: Filter by job status (queued, processing, completed, …).
		"""
		return await self._client.list_jobs(page=page, limit=limit, status=status)

	async def cancel(
		self,
		job_id: str,
	) -> dict[str, Any]:
		"""
		Cancel a pending or processing job.

		Fails if the job is already completed, failed, or cancelled.

		Args:
			job_id: Id from create / `transcribe_file`.
		"""
		return await self._client.cancel_job(job_id)
