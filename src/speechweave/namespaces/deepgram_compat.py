from __future__ import annotations

from typing import TYPE_CHECKING, Any, BinaryIO

from speechweave.namespaces.compat_shapes import (
	async_create_job_from_url,
	async_finish_compat_job,
	async_upload_and_create_job,
	create_job_from_url,
	finish_compat_job,
	shape_deepgram_response,
	upload_and_create_job,
)

if TYPE_CHECKING:
	from speechweave.async_client import AsyncSpeechWeaveClient
	from speechweave.client import SpeechWeaveClient


class _Prerecorded:
	def __init__(
		self,
		client: SpeechWeaveClient,
	):
		self._client = client

	def transcribe_file(
		self,
		file_obj: BinaryIO,
		*,
		filename: str = "audio.bin",
		model: str | None = None,
		language: str | None = None,
		file_size: int | None = None,
	) -> Any:
		"""
		Deepgram-shaped prerecorded file transcription — drop-in compatibility wrapper.
		"""

		job = upload_and_create_job(
			self._client,
			data=file_obj,
			filename=filename,
			model=model,
			language=language,
			file_size=file_size,
		)
		finished = finish_compat_job(
			self._client,
			job,
			wait=True,
			error_code="DEEPGRAM_PROXY",
		)
		return shape_deepgram_response(
			finished,
			model=model,
		)

	def transcribe_url(
		self,
		url: str,
		*,
		model: str | None = None,
		language: str | None = None,
	) -> Any:
		"""
		Deepgram-shaped prerecorded URL transcription — drop-in compatibility wrapper.
		"""

		job = create_job_from_url(
			self._client,
			url=url,
			model=model,
			language=language,
		)
		finished = finish_compat_job(
			self._client,
			job,
			wait=True,
			error_code="DEEPGRAM_PROXY",
		)
		return shape_deepgram_response(
			finished,
			model=model,
		)


class DeepgramListen:
	def __init__(
		self,
		client: SpeechWeaveClient,
	):
		self.prerecorded = _Prerecorded(client)


class _AsyncPrerecorded:
	def __init__(
		self,
		client: AsyncSpeechWeaveClient,
	):
		self._client = client

	async def transcribe_file(
		self,
		file_obj: BinaryIO,
		*,
		filename: str = "audio.bin",
		model: str | None = None,
		language: str | None = None,
		file_size: int | None = None,
		wait: bool = True,
	) -> Any:
		"""
		Deepgram-shaped prerecorded file transcription — drop-in compatibility wrapper.
		"""

		job = await async_upload_and_create_job(
			self._client,
			data=file_obj,
			filename=filename,
			model=model,
			language=language,
			file_size=file_size,
		)
		finished = await async_finish_compat_job(
			self._client,
			job,
			wait=wait,
			error_code="DEEPGRAM_PROXY",
		)
		if not wait:
			return finished

		return shape_deepgram_response(
			finished,
			model=model,
		)

	async def transcribe_url(
		self,
		url: str,
		*,
		model: str | None = None,
		language: str | None = None,
		wait: bool = True,
	) -> Any:
		"""
		Deepgram-shaped prerecorded URL transcription — drop-in compatibility wrapper.
		"""

		job = await async_create_job_from_url(
			self._client,
			url=url,
			model=model,
			language=language,
		)
		finished = await async_finish_compat_job(
			self._client,
			job,
			wait=wait,
			error_code="DEEPGRAM_PROXY",
		)
		if not wait:
			return finished

		return shape_deepgram_response(
			finished,
			model=model,
		)


class AsyncDeepgramListen:
	def __init__(
		self,
		client: AsyncSpeechWeaveClient,
	):
		self.prerecorded = _AsyncPrerecorded(client)
