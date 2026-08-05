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
		prompt: str | None = None,
		temperature: float | None = None,
		response_format: str | None = None,
		timestamp_granularities: list[str] | None = None,
		file_size: int | None = None,
	) -> Any:
		"""
		OpenAI-shaped transcription create, drop-in compatibility wrapper.

		`response_format` 'json' (default) and 'verbose_json' return a dict;
		'text' / 'srt' / 'vtt' return a raw string.
		"""

		job = upload_and_create_job(
			self._client,
			data=file,
			filename=filename,
			model=model,
			language=language,
			prompt=prompt,
			temperature=temperature,
			timestamp_granularities=timestamp_granularities,
			file_size=file_size,
		)
		finished = finish_compat_job(
			self._client,
			job,
			wait=True,
			error_code="OPENAI_PROXY",
		)
		if response_format and response_format != "json":
			return self._client.get_job_formatted(str(finished.get("id") or ""), response_format)

		return shape_openai_response(finished, task="transcribe")


class _Translations:
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
		prompt: str | None = None,
		temperature: float | None = None,
		response_format: str | None = None,
		file_size: int | None = None,
	) -> Any:
		"""
		OpenAI-shaped translation create (audio in any supported language -> English text).

		Note: unlike transcriptions, OpenAI's translations endpoint (and SpeechWeave's)
		has no `language` parameter, the source language is auto-detected, and the
		target is always English.
		"""

		job = upload_and_create_job(
			self._client,
			data=file,
			filename=filename,
			model=model,
			task="translate",
			prompt=prompt,
			temperature=temperature,
			file_size=file_size,
		)
		finished = finish_compat_job(
			self._client,
			job,
			wait=True,
			error_code="OPENAI_TRANSLATE_PROXY",
		)
		if response_format and response_format != "json":
			return self._client.get_job_formatted(str(finished.get("id") or ""), response_format)

		return shape_openai_response(finished, task="translate")


class OpenAiAudio:
	def __init__(
		self,
		client: SpeechWeaveClient,
	):
		self.transcriptions = _Transcriptions(client)
		self.translations = _Translations(client)


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
		prompt: str | None = None,
		temperature: float | None = None,
		response_format: str | None = None,
		timestamp_granularities: list[str] | None = None,
		file_size: int | None = None,
		wait: bool = True,
	) -> Any:
		"""
		OpenAI-shaped transcription create, drop-in compatibility wrapper.
		"""

		job = await async_upload_and_create_job(
			self._client,
			data=file,
			filename=filename,
			model=model,
			language=language,
			prompt=prompt,
			temperature=temperature,
			timestamp_granularities=timestamp_granularities,
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

		if response_format and response_format != "json":
			return await self._client.get_job_formatted(str(finished.get("id") or ""), response_format)

		return shape_openai_response(finished, task="transcribe")


class _AsyncTranslations:
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
		prompt: str | None = None,
		temperature: float | None = None,
		response_format: str | None = None,
		file_size: int | None = None,
		wait: bool = True,
	) -> Any:
		"""
		OpenAI-shaped translation create (audio in any supported language -> English text).
		"""

		job = await async_upload_and_create_job(
			self._client,
			data=file,
			filename=filename,
			model=model,
			task="translate",
			prompt=prompt,
			temperature=temperature,
			file_size=file_size,
		)
		finished = await async_finish_compat_job(
			self._client,
			job,
			wait=wait,
			error_code="OPENAI_TRANSLATE_PROXY",
		)
		if not wait:
			return finished

		if response_format and response_format != "json":
			return await self._client.get_job_formatted(str(finished.get("id") or ""), response_format)

		return shape_openai_response(finished, task="translate")


class AsyncOpenAiAudio:
	def __init__(
		self,
		client: AsyncSpeechWeaveClient,
	):
		self.transcriptions = _AsyncTranscriptions(client)
		self.translations = _AsyncTranslations(client)
