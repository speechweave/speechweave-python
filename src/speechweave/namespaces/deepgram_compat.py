"""
Deepgram-shaped listen helpers, following the current official Python SDK:

	client.listen.v1.media.transcribe_url(url=..., model=...)
	client.listen.v1.media.transcribe_file(request=<bytes or file>, model=...)

Responses are dicts that also allow attribute access (`resp.results.channels[0]...`).
Only the options listed below are honored. Anything else raises a 400 `UNSUPPORTED_OPTION`
`SpeechWeaveError` instead of being silently dropped. Word `confidence` is estimated from
segment log-probabilities and is omitted when the model reported none.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, BinaryIO

from speechweave.errors import SpeechWeaveError
from speechweave.namespaces.compat_text import (
	TextRule,
	build_rewrite_rules,
	build_vocabulary_prompt,
	deepgram_vocabulary_terms,
	parse_deepgram_replace,
)
from speechweave.namespaces.compat_shapes import (
	COMPAT_TIMESTAMP_GRANULARITIES,
	assert_supported_compat_options,
	async_create_job_from_url,
	async_fetch_compat_verbose,
	async_finish_compat_job,
	async_upload_and_create_job,
	create_job_from_url,
	fetch_compat_verbose,
	finish_compat_job,
	shape_deepgram_response,
	upload_and_create_job,
)

if TYPE_CHECKING:
	from speechweave.async_client import AsyncSpeechWeaveClient
	from speechweave.client import SpeechWeaveClient

_FEATURE_OPTIONS = (
	"utterances",
	"paragraphs",
	"search",
	"detect_language",
	"replace",
	"profanity_filter",
	"keyterm",
	"keywords",
)
FILE_OPTIONS = ("model", "filename", "language", "file_size", *_FEATURE_OPTIONS, "wait")
URL_OPTIONS = ("model", "language", *_FEATURE_OPTIONS, "wait")
# Output is always punctuated and formatted, so asking for it changes nothing.
SATISFIED = {"punctuate": True, "smart_format": True}


def _check(options: dict[str, Any], supported: tuple[str, ...]) -> None:

	assert_supported_compat_options(
		options,
		helper="Deepgram-style",
		supported=supported,
		satisfied=SATISFIED,
	)


def _vocabulary_prompt(keyterm: Any, keywords: Any) -> str | None:
	"""Vocabulary options become a short model prompt that biases the transcript toward the terms."""

	return build_vocabulary_prompt(deepgram_vocabulary_terms(keyterm, keywords))


def _rewrite_rules(replace: Any, profanity_filter: Any) -> list[TextRule]:
	# Parsed before any request so a bad rule fails without creating a job.

	return build_rewrite_rules(parse_deepgram_replace(replace), profanity_filter)


def _require_url(url: Any) -> str:

	if not isinstance(url, str) or not url.strip():
		raise SpeechWeaveError(
			"A url is required.",
			400,
			"MISSING_URL",
			error_type="invalid_request_error",
			param="url",
		)

	return url


class _Media:
	def __init__(self, client: SpeechWeaveClient):
		self._client = client

	def transcribe_file(
		self,
		*,
		request: bytes | BinaryIO,
		filename: str = "audio.bin",
		model: str | None = None,
		language: str | None = None,
		file_size: int | None = None,
		utterances: bool | None = None,
		paragraphs: bool | None = None,
		search: str | list[str] | None = None,
		detect_language: bool | None = None,
		replace: str | list[str] | None = None,
		profanity_filter: bool | None = None,
		keyterm: str | list[str] | None = None,
		keywords: str | list[str] | None = None,
		wait: bool = True,
		**options: Any,
	) -> Any:
		"""Deepgram-shaped pre-recorded file transcription (official `transcribe_file`)."""

		_check(options, FILE_OPTIONS)
		rewrites = _rewrite_rules(replace, profanity_filter)
		job = upload_and_create_job(
			self._client,
			data=request,
			filename=filename,
			model=model,
			language=language,
			file_size=file_size,
			prompt=_vocabulary_prompt(keyterm, keywords),
			timestamp_granularities=COMPAT_TIMESTAMP_GRANULARITIES,
		)
		finished = finish_compat_job(self._client, job, wait=wait, error_code="DEEPGRAM_PROXY")
		if not wait:
			return finished

		return shape_deepgram_response(
			finished,
			model=model,
			verbose=fetch_compat_verbose(self._client, finished),
			utterances=bool(utterances),
			paragraphs=bool(paragraphs),
			search=search,
			detect_language=bool(detect_language),
			rewrites=rewrites,
		)

	def transcribe_url(
		self,
		*,
		url: str,
		model: str | None = None,
		language: str | None = None,
		utterances: bool | None = None,
		paragraphs: bool | None = None,
		search: str | list[str] | None = None,
		detect_language: bool | None = None,
		replace: str | list[str] | None = None,
		profanity_filter: bool | None = None,
		keyterm: str | list[str] | None = None,
		keywords: str | list[str] | None = None,
		wait: bool = True,
		**options: Any,
	) -> Any:
		"""Deepgram-shaped pre-recorded URL transcription (official `transcribe_url`)."""

		_check(options, URL_OPTIONS)
		rewrites = _rewrite_rules(replace, profanity_filter)
		job = create_job_from_url(
			self._client,
			url=_require_url(url),
			model=model,
			language=language,
			prompt=_vocabulary_prompt(keyterm, keywords),
			timestamp_granularities=COMPAT_TIMESTAMP_GRANULARITIES,
		)
		finished = finish_compat_job(self._client, job, wait=wait, error_code="DEEPGRAM_PROXY")
		if not wait:
			return finished

		return shape_deepgram_response(
			finished,
			model=model,
			verbose=fetch_compat_verbose(self._client, finished),
			utterances=bool(utterances),
			paragraphs=bool(paragraphs),
			search=search,
			detect_language=bool(detect_language),
			rewrites=rewrites,
		)


class _V1:
	def __init__(self, client: SpeechWeaveClient):
		self.media = _Media(client)


class DeepgramListen:
	def __init__(self, client: SpeechWeaveClient):
		self.v1 = _V1(client)


class _AsyncMedia:
	def __init__(self, client: AsyncSpeechWeaveClient):
		self._client = client

	async def transcribe_file(
		self,
		*,
		request: bytes | BinaryIO,
		filename: str = "audio.bin",
		model: str | None = None,
		language: str | None = None,
		file_size: int | None = None,
		utterances: bool | None = None,
		paragraphs: bool | None = None,
		search: str | list[str] | None = None,
		detect_language: bool | None = None,
		replace: str | list[str] | None = None,
		profanity_filter: bool | None = None,
		keyterm: str | list[str] | None = None,
		keywords: str | list[str] | None = None,
		wait: bool = True,
		**options: Any,
	) -> Any:
		"""Deepgram-shaped pre-recorded file transcription (official `transcribe_file`)."""

		_check(options, FILE_OPTIONS)
		rewrites = _rewrite_rules(replace, profanity_filter)
		job = await async_upload_and_create_job(
			self._client,
			data=request,
			filename=filename,
			model=model,
			language=language,
			file_size=file_size,
			prompt=_vocabulary_prompt(keyterm, keywords),
			timestamp_granularities=COMPAT_TIMESTAMP_GRANULARITIES,
		)
		finished = await async_finish_compat_job(self._client, job, wait=wait, error_code="DEEPGRAM_PROXY")
		if not wait:
			return finished

		return shape_deepgram_response(
			finished,
			model=model,
			verbose=await async_fetch_compat_verbose(self._client, finished),
			utterances=bool(utterances),
			paragraphs=bool(paragraphs),
			search=search,
			detect_language=bool(detect_language),
			rewrites=rewrites,
		)

	async def transcribe_url(
		self,
		*,
		url: str,
		model: str | None = None,
		language: str | None = None,
		utterances: bool | None = None,
		paragraphs: bool | None = None,
		search: str | list[str] | None = None,
		detect_language: bool | None = None,
		replace: str | list[str] | None = None,
		profanity_filter: bool | None = None,
		keyterm: str | list[str] | None = None,
		keywords: str | list[str] | None = None,
		wait: bool = True,
		**options: Any,
	) -> Any:
		"""Deepgram-shaped pre-recorded URL transcription (official `transcribe_url`)."""

		_check(options, URL_OPTIONS)
		rewrites = _rewrite_rules(replace, profanity_filter)
		job = await async_create_job_from_url(
			self._client,
			url=_require_url(url),
			model=model,
			language=language,
			prompt=_vocabulary_prompt(keyterm, keywords),
			timestamp_granularities=COMPAT_TIMESTAMP_GRANULARITIES,
		)
		finished = await async_finish_compat_job(self._client, job, wait=wait, error_code="DEEPGRAM_PROXY")
		if not wait:
			return finished

		return shape_deepgram_response(
			finished,
			model=model,
			verbose=await async_fetch_compat_verbose(self._client, finished),
			utterances=bool(utterances),
			paragraphs=bool(paragraphs),
			search=search,
			detect_language=bool(detect_language),
			rewrites=rewrites,
		)


class _AsyncV1:
	def __init__(self, client: AsyncSpeechWeaveClient):
		self.media = _AsyncMedia(client)


class AsyncDeepgramListen:
	def __init__(self, client: AsyncSpeechWeaveClient):
		self.v1 = _AsyncV1(client)
