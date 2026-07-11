from __future__ import annotations

from typing import TYPE_CHECKING, Any

from speechweave.client import UploadBody
from speechweave.namespaces.compat_shapes import (
	async_finish_compat_job,
	async_upload_and_create_job,
	finish_compat_job,
	shape_openai_response,
	upload_and_create_job,
)

if TYPE_CHECKING:
	from speechweave.async_client import AsyncSpeechWeaveClient
	from speechweave.client import SpeechWeaveClient


class _Transcriptions:
	def __init__(
		self,
		client: SpeechWeaveClient,
	):
		self._client = client

	def create(
		self,
		*,
		file: UploadBody,
		filename: str = "audio.bin",
		model: str | None = None,
		language: str | None = None,
		file_size: int | None = None,
	) -> dict[str, Any]:
		"""
		OpenAI-shaped transcription create — drop-in compatibility wrapper.
		"""

		job = upload_and_create_job(
			self._client,
			data=file,
			filename=filename,
			model=model,
			language=language,
			file_size=file_size,
		)
		finished = finish_compat_job(
			self._client,
			job,
			wait=True,
			error_code="OPENAI_PROXY",
		)
		return shape_openai_response(finished)


class OpenAiAudio:
	def __init__(
		self,
		client: SpeechWeaveClient,
	):
		self.transcriptions = _Transcriptions(client)


class _AsyncTranscriptions:
	def __init__(
		self,
		client: AsyncSpeechWeaveClient,
	):
		self._client = client

	async def create(
		self,
		*,
		file: UploadBody,
		filename: str = "audio.bin",
		model: str | None = None,
		language: str | None = None,
		file_size: int | None = None,
		wait: bool = True,
	) -> dict[str, Any]:
		"""
		OpenAI-shaped transcription create — drop-in compatibility wrapper.
		"""

		job = await async_upload_and_create_job(
			self._client,
			data=file,
			filename=filename,
			model=model,
			language=language,
			file_size=file_size,
		)
		finished = await async_finish_compat_job(
			self._client,
			job,
			wait=wait,
			error_code="OPENAI_PROXY",
		)
		if not wait:
			return finished

		return shape_openai_response(finished)


class AsyncOpenAiAudio:
	def __init__(
		self,
		client: AsyncSpeechWeaveClient,
	):
		self.transcriptions = _AsyncTranscriptions(client)
