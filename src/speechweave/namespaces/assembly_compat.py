"""
AssemblyAI-shaped transcripts helpers, following the current official Python SDK:

	transcript = client.transcripts.transcribe(audio, config)        # polls to completion
	transcript = client.transcripts.submit(audio, config)            # returns a queued transcript
	transcript = client.transcripts.get_by_id(transcript_id)

`audio` is a public URL, a local file path, bytes or a binary file object. `config` is a dict.
The result is a dict that also allows attribute access (`transcript.text`, `transcript.words`).
Only the config keys listed below are honored. Anything else raises a 400 `UNSUPPORTED_OPTION`
`SpeechWeaveError` instead of being silently dropped. Word `confidence` is estimated from
segment log-probabilities and is omitted when the model reported none.

Statuses follow AssemblyAI: queued, processing, completed and error. A failed or cancelled job
comes back with status "error" and an `error` message instead of raising.

Extras on the namespace: `export_subtitles_srt` / `export_subtitles_vtt`, `list_transcripts`,
`get_sentences` and `get_paragraphs`.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, BinaryIO

from speechweave.errors import SpeechWeaveError
from speechweave.namespaces.compat_text import (
	TextRule,
	assembly_vocabulary_terms,
	build_rewrite_rules,
	build_vocabulary_prompt,
	invalid,
	parse_custom_spelling,
)
from speechweave.namespaces.compat_shapes import (
	COMPAT_TIMESTAMP_GRANULARITIES,
	assembly_status,
	assert_supported_compat_options,
	async_create_job_from_url,
	async_fetch_compat_verbose,
	async_finish_compat_job,
	async_upload_and_create_job,
	create_job_from_url,
	fetch_compat_verbose,
	finish_compat_job,
	shape_assembly_list,
	shape_assembly_response,
	shape_assembly_units,
	upload_and_create_job,
)

if TYPE_CHECKING:
	from speechweave.async_client import AsyncSpeechWeaveClient
	from speechweave.client import SpeechWeaveClient

CONFIG_OPTIONS = (
	"model",
	"language_code",
	"language",
	"file_size",
	"language_detection",
	"custom_spelling",
	"filter_profanity",
	"keyterms_prompt",
	"word_boost",
)
# `list_transcripts` paging. AssemblyAI cursors do not map to page numbers, so they are refused.
LIST_OPTIONS = ("limit", "status", "page")
CURSOR_OPTIONS = ("before_id", "after_id")
# Output is always punctuated and formatted, so asking for it changes nothing.
SATISFIED = {"punctuate": True, "format_text": True}
_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def _prepare(audio: Any, config: Mapping[str, Any] | None) -> dict[str, Any]:

	cfg = dict(config or {})
	assert_supported_compat_options(
		cfg,
		helper="AssemblyAI-style",
		supported=CONFIG_OPTIONS,
		satisfied=SATISFIED,
	)
	if audio is None or audio == "":
		raise SpeechWeaveError(
			"Provide audio (a public URL, a file path, bytes or a file object).",
			400,
			"MISSING_AUDIO",
			error_type="invalid_request_error",
			param="audio",
		)

	# AssemblyAI rejects language detection together with an explicit language, and so do we.
	if cfg.get("language_detection") and _language(cfg):
		raise invalid(
			"language_detection cannot be combined with language_code. Pass one or the other.",
			"language_detection",
		)
	# Parsed before any request so a bad rule fails without creating a job.
	_rewrite_rules(cfg)

	return cfg


def _language(cfg: Mapping[str, Any]) -> str | None:

	return cfg.get("language_code") or cfg.get("language")


def _prompt(cfg: Mapping[str, Any]) -> str | None:
	"""Vocabulary options become a short model prompt that biases the transcript toward the terms."""

	return build_vocabulary_prompt(assembly_vocabulary_terms(cfg.get("keyterms_prompt"), cfg.get("word_boost")))


def _rewrite_rules(cfg: Mapping[str, Any]) -> list[TextRule]:

	return build_rewrite_rules(parse_custom_spelling(cfg.get("custom_spelling")), cfg.get("filter_profanity"))


def _check_completed(job: Mapping[str, Any], transcript_id: str) -> None:

	if str(job.get("status")) != "completed":
		raise SpeechWeaveError(
			f"Transcript {transcript_id} is not completed (status {assembly_status(job)[0]}).",
			409,
			"TRANSCRIPT_NOT_READY",
		)


def _subtitle_format(fmt: str) -> str:

	if fmt not in ("srt", "vtt"):
		raise invalid('format must be "srt" or "vtt".', "format")

	return fmt


def _check_list_params(params: Mapping[str, Any] | None) -> dict[str, Any]:

	given = {k: v for k, v in (params or {}).items() if v is not None}
	for cursor in CURSOR_OPTIONS:
		if cursor in given:
			raise invalid(
				f"{cursor} is not supported. Page with page and limit instead.",
				cursor,
				"UNSUPPORTED_OPTION",
			)
	assert_supported_compat_options(given, helper="AssemblyAI-style list", supported=LIST_OPTIONS)
	# AssemblyAI statuses map back to job statuses: error covers failed and cancelled.
	if given.get("status") == "error":
		given["status"] = "failed"

	return given


class AssemblyTranscripts:
	def __init__(self, client: SpeechWeaveClient):
		self._client = client

	def _create(self, audio: str | bytes | BinaryIO, cfg: Mapping[str, Any]) -> dict[str, Any]:

		if isinstance(audio, str) and _URL_RE.match(audio):
			return create_job_from_url(
				self._client,
				url=audio,
				model=cfg.get("model"),
				prompt=_prompt(cfg),
				language=_language(cfg),
				timestamp_granularities=COMPAT_TIMESTAMP_GRANULARITIES,
			)
		if isinstance(audio, str):
			with open(audio, "rb") as handle:
				return upload_and_create_job(
					self._client,
					data=handle,
					filename=os.path.basename(audio),
					model=cfg.get("model"),
					prompt=_prompt(cfg),
					language=_language(cfg),
					file_size=cfg.get("file_size"),
					timestamp_granularities=COMPAT_TIMESTAMP_GRANULARITIES,
				)

		return upload_and_create_job(
			self._client,
			data=audio,
			filename="audio.bin",
			model=cfg.get("model"),
			prompt=_prompt(cfg),
			language=_language(cfg),
			file_size=cfg.get("file_size"),
			timestamp_granularities=COMPAT_TIMESTAMP_GRANULARITIES,
		)

	def _shape(self, finished: dict[str, Any], rewrites: list[TextRule] | None = None) -> Any:

		return shape_assembly_response(
			finished,
			verbose=fetch_compat_verbose(self._client, finished),
			rewrites=rewrites,
		)

	def transcribe(
		self,
		audio: str | bytes | BinaryIO,
		config: Mapping[str, Any] | None = None,
		*,
		poll_timeout: float | None = None,
		wait: bool = True,
	) -> Any:
		"""Creates a transcript and, unless `wait` is False, returns it once finished."""

		cfg = _prepare(audio, config)
		job = self._create(audio, cfg)
		finished = finish_compat_job(
			self._client,
			job,
			wait=wait,
			error_code="ASSEMBLY_PROXY",
			timeout_sec=poll_timeout,
			raise_on_failed=False,
		)
		if not wait:
			return finished

		return self._shape(finished, _rewrite_rules(cfg))

	def submit(self, audio: str | bytes | BinaryIO, config: Mapping[str, Any] | None = None) -> Any:
		"""Creates a transcript and returns immediately with a queued transcript."""

		cfg = _prepare(audio, config)
		job = self._create(audio, cfg)

		return shape_assembly_response({**job, "status": "queued"})

	def get_by_id(self, transcript_id: str) -> Any:
		"""Fetches a transcript by id."""

		return self._shape(self._client.get_job(transcript_id))

	def wait_for_completion(self, transcript_id: str, *, poll_timeout: float | None = None) -> Any:
		"""Polls a transcript until it is finished."""

		job = {"id": transcript_id}
		finished = finish_compat_job(
			self._client,
			job,
			wait=True,
			error_code="ASSEMBLY_PROXY",
			timeout_sec=poll_timeout,
			raise_on_failed=False,
		)

		return self._shape(finished)

	def export_subtitles_srt(self, transcript_id: str, chars_per_caption: int | None = None) -> str:
		"""
		SRT subtitles for a completed transcript. `chars_per_caption` is accepted and ignored for
		now: caption lines follow the transcript's own segments.
		"""

		return str(self._client.get_job_formatted(transcript_id, _subtitle_format("srt")))

	def export_subtitles_vtt(self, transcript_id: str, chars_per_caption: int | None = None) -> str:
		"""
		WebVTT subtitles for a completed transcript. `chars_per_caption` is accepted and ignored
		for now: caption lines follow the transcript's own segments.
		"""

		return str(self._client.get_job_formatted(transcript_id, _subtitle_format("vtt")))

	def list_transcripts(self, params: Mapping[str, Any] | None = None) -> Any:
		"""One page of transcripts (`limit`, `status`, `page`). `before_id` and `after_id` are not supported."""

		given = _check_list_params(params)
		listing = self._client.list_jobs(page=given.get("page"), limit=given.get("limit"), status=given.get("status"))

		return shape_assembly_list(listing, base_url=self._client.base_url, status=given.get("status"))

	def _units(self, kind: str, transcript_id: str) -> Any:

		job = self._client.get_job(transcript_id)
		_check_completed(job, transcript_id)

		return shape_assembly_units(kind, job, fetch_compat_verbose(self._client, job))

	def get_sentences(self, transcript_id: str) -> Any:
		"""Sentences of a completed transcript, split on punctuation. Times are in milliseconds."""

		return self._units("sentences", transcript_id)

	def get_paragraphs(self, transcript_id: str) -> Any:
		"""Paragraphs of a completed transcript, grouped by pauses. Times are in milliseconds."""

		return self._units("paragraphs", transcript_id)


class AsyncAssemblyTranscripts:
	def __init__(self, client: AsyncSpeechWeaveClient):
		self._client = client

	async def _create(self, audio: str | bytes | BinaryIO, cfg: Mapping[str, Any]) -> dict[str, Any]:

		if isinstance(audio, str) and _URL_RE.match(audio):
			return await async_create_job_from_url(
				self._client,
				url=audio,
				model=cfg.get("model"),
				prompt=_prompt(cfg),
				language=_language(cfg),
				timestamp_granularities=COMPAT_TIMESTAMP_GRANULARITIES,
			)
		if isinstance(audio, str):
			with open(audio, "rb") as handle:
				return await async_upload_and_create_job(
					self._client,
					data=handle,
					filename=os.path.basename(audio),
					model=cfg.get("model"),
					prompt=_prompt(cfg),
					language=_language(cfg),
					file_size=cfg.get("file_size"),
					timestamp_granularities=COMPAT_TIMESTAMP_GRANULARITIES,
				)

		return await async_upload_and_create_job(
			self._client,
			data=audio,
			filename="audio.bin",
			model=cfg.get("model"),
			prompt=_prompt(cfg),
			language=_language(cfg),
			file_size=cfg.get("file_size"),
			timestamp_granularities=COMPAT_TIMESTAMP_GRANULARITIES,
		)

	async def _shape(self, finished: dict[str, Any], rewrites: list[TextRule] | None = None) -> Any:

		return shape_assembly_response(
			finished,
			verbose=await async_fetch_compat_verbose(self._client, finished),
			rewrites=rewrites,
		)

	async def transcribe(
		self,
		audio: str | bytes | BinaryIO,
		config: Mapping[str, Any] | None = None,
		*,
		poll_timeout: float | None = None,
		wait: bool = True,
	) -> Any:
		"""Creates a transcript and, unless `wait` is False, returns it once finished."""

		cfg = _prepare(audio, config)
		job = await self._create(audio, cfg)
		finished = await async_finish_compat_job(
			self._client,
			job,
			wait=wait,
			error_code="ASSEMBLY_PROXY",
			timeout_sec=poll_timeout,
			raise_on_failed=False,
		)
		if not wait:
			return finished

		return await self._shape(finished, _rewrite_rules(cfg))

	async def submit(self, audio: str | bytes | BinaryIO, config: Mapping[str, Any] | None = None) -> Any:
		"""Creates a transcript and returns immediately with a queued transcript."""

		cfg = _prepare(audio, config)
		job = await self._create(audio, cfg)

		return shape_assembly_response({**job, "status": "queued"})

	async def get_by_id(self, transcript_id: str) -> Any:
		"""Fetches a transcript by id."""

		return await self._shape(await self._client.get_job(transcript_id))

	async def wait_for_completion(self, transcript_id: str, *, poll_timeout: float | None = None) -> Any:
		"""Polls a transcript until it is finished."""

		finished = await async_finish_compat_job(
			self._client,
			{"id": transcript_id},
			wait=True,
			error_code="ASSEMBLY_PROXY",
			timeout_sec=poll_timeout,
			raise_on_failed=False,
		)

		return await self._shape(finished)

	async def export_subtitles_srt(self, transcript_id: str, chars_per_caption: int | None = None) -> str:
		"""
		SRT subtitles for a completed transcript. `chars_per_caption` is accepted and ignored for
		now: caption lines follow the transcript's own segments.
		"""

		return str(await self._client.get_job_formatted(transcript_id, _subtitle_format("srt")))

	async def export_subtitles_vtt(self, transcript_id: str, chars_per_caption: int | None = None) -> str:
		"""
		WebVTT subtitles for a completed transcript. `chars_per_caption` is accepted and ignored
		for now: caption lines follow the transcript's own segments.
		"""

		return str(await self._client.get_job_formatted(transcript_id, _subtitle_format("vtt")))

	async def list_transcripts(self, params: Mapping[str, Any] | None = None) -> Any:
		"""One page of transcripts (`limit`, `status`, `page`). `before_id` and `after_id` are not supported."""

		given = _check_list_params(params)
		listing = await self._client.list_jobs(
			page=given.get("page"), limit=given.get("limit"), status=given.get("status")
		)

		return shape_assembly_list(listing, base_url=self._client.base_url, status=given.get("status"))

	async def _units(self, kind: str, transcript_id: str) -> Any:

		job = await self._client.get_job(transcript_id)
		_check_completed(job, transcript_id)

		return shape_assembly_units(kind, job, await async_fetch_compat_verbose(self._client, job))

	async def get_sentences(self, transcript_id: str) -> Any:
		"""Sentences of a completed transcript, split on punctuation. Times are in milliseconds."""

		return await self._units("sentences", transcript_id)

	async def get_paragraphs(self, transcript_id: str) -> Any:
		"""Paragraphs of a completed transcript, grouped by pauses. Times are in milliseconds."""

		return await self._units("paragraphs", transcript_id)
