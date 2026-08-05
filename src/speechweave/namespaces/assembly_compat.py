from __future__ import annotations

from typing import TYPE_CHECKING, Any, BinaryIO

from speechweave.namespaces.compat_shapes import (
	async_create_job_from_url,
	async_finish_compat_job,
	async_upload_and_create_job,
	create_job_from_url,
	finish_compat_job,
	shape_assembly_response,
	upload_and_create_job,
)

if TYPE_CHECKING:
	from speechweave.async_client import AsyncSpeechWeaveClient
	from speechweave.client import SpeechWeaveClient


class AssemblyTranscripts:
	def __init__(
		self,
		client: SpeechWeaveClient,
	):
		self._client = client

	def transcribe(
		self,
		audio: str | bytes | BinaryIO,
		config: dict[str, Any] | None = None,
	) -> Any:
		"""
		AssemblyAI-shaped transcription, drop-in compatibility wrapper.

		Pass a URL string or binary/file body. Polls to completion.
		"""

		cfg = config or {}
		model = cfg.get("model")
		language = cfg.get("language")
		file_size = cfg.get("file_size")

		if isinstance(audio, str):
			job = create_job_from_url(
				self._client,
				url=audio,
				model=model,
				language=language,
			)
		else:
			job = upload_and_create_job(
				self._client,
				data=audio,
				filename="audio.bin",
				model=model,
				language=language,
				file_size=file_size,
			)

		finished = finish_compat_job(
			self._client,
			job,
			wait=True,
			error_code="ASSEMBLY_PROXY",
		)
		return shape_assembly_response(finished)


class AsyncAssemblyTranscripts:
	def __init__(
		self,
		client: AsyncSpeechWeaveClient,
	):
		self._client = client

	async def transcribe(
		self,
		audio: str | bytes | BinaryIO,
		config: dict[str, Any] | None = None,
		*,
		wait: bool = True,
	) -> Any:
		"""
		AssemblyAI-shaped transcription, drop-in compatibility wrapper.

		Pass a URL string or binary/file body.
		"""

		cfg = config or {}
		model = cfg.get("model")
		language = cfg.get("language")
		file_size = cfg.get("file_size")

		if isinstance(audio, str):
			job = await async_create_job_from_url(
				self._client,
				url=audio,
				model=model,
				language=language,
			)
		else:
			job = await async_upload_and_create_job(
				self._client,
				data=audio,
				filename="audio.bin",
				model=model,
				language=language,
				file_size=file_size,
			)

		finished = await async_finish_compat_job(
			self._client,
			job,
			wait=wait,
			error_code="ASSEMBLY_PROXY",
		)
		if not wait:
			return finished

		return shape_assembly_response(finished)
