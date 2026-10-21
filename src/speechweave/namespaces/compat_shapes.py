from __future__ import annotations

import math
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from speechweave.client import UploadBody, _content_length
from speechweave.errors import SpeechWeaveError
from speechweave.mime import infer_content_type
from speechweave.namespaces.compat_text import (
	TextRule,
	build_paragraphs,
	build_sentences,
	count_words,
	rewrite_text,
	rewrite_words,
	search_words,
)

if TYPE_CHECKING:
	from speechweave.async_client import AsyncSpeechWeaveClient
	from speechweave.client import SpeechWeaveClient


def _job_text(job: dict[str, Any]) -> str:

	text = job.get("transcript")
	if isinstance(text, str):
		return text

	return ""


def _job_duration(job: dict[str, Any]) -> float | None:

	duration = job.get("duration")
	if duration is None:
		return None

	try:
		value = float(duration)
	except (TypeError, ValueError):
		return None

	return value if value >= 0 else None


def _job_language(job: dict[str, Any]) -> str | None:

	language = job.get("language")
	if language is None:
		return None

	text = str(language).strip().lower()
	if not text:
		return None

	return text


def shape_openai_response(job: dict[str, Any], *, task: str = "transcribe") -> dict[str, Any]:

	response: dict[str, Any] = {
		"text": _job_text(job),
		"task": task,
	}
	duration = _job_duration(job)
	if duration is not None:
		response["duration"] = duration

	language = _job_language(job)
	if language is not None:
		response["language"] = language

	return response


class CompatDict(dict):
	"""
	A dict that also allows attribute access (`result.results.channels`), the way the official
	Deepgram and AssemblyAI SDKs return objects. Plain `result["results"]` keeps working.
	"""

	def __getattr__(self, name: str) -> Any:
		try:
			return self[name]
		except KeyError:
			raise AttributeError(name) from None


def to_compat(value: Any) -> Any:
	if isinstance(value, dict):
		return CompatDict({k: to_compat(v) for k, v in value.items()})
	if isinstance(value, list):
		return [to_compat(v) for v in value]

	return value


# Both word and segment timing, so compat responses can carry real words and utterances.
COMPAT_TIMESTAMP_GRANULARITIES = ["segment", "word"]


def assert_supported_compat_options(
	options: Mapping[str, Any] | None,
	*,
	helper: str,
	supported: tuple[str, ...] | list[str],
	satisfied: Mapping[str, Any] | None = None,
) -> None:
	"""
	Rejects options a compatibility helper would otherwise drop without a word.

	The helpers read only a few options. Anything else (diarize, utterances, speaker_labels, ...)
	used to be accepted and silently ignored, so the call succeeded and the expected fields never
	appeared. `satisfied` lists options whose requested value is already how SpeechWeave behaves
	(output is always punctuated and formatted), so passing them is a no-op. Options passed as
	None are treated as not passed.
	"""

	unsupported: list[str] = []
	for key, value in (options or {}).items():
		if value is None or key in supported:
			continue
		if satisfied and key in satisfied and satisfied[key] == value:
			continue
		unsupported.append(key)
	if not unsupported:
		return

	names = ", ".join(f'"{k}"' for k in unsupported)
	noun, verb = ("Option", "is") if len(unsupported) == 1 else ("Options", "are")
	message = (
		f"{noun} {names} {verb} not supported by the {helper} helper. "
		f"Supported options: {', '.join(supported)}. Remove the option, or use the native jobs API."
	)
	raise SpeechWeaveError(
		message,
		400,
		"UNSUPPORTED_OPTION",
		body={
			"error": {
				"message": message,
				"type": "invalid_request_error",
				"param": unsupported[0],
				"code": "unsupported_option",
			},
			"unsupported": unsupported,
		},
		error_type="invalid_request_error",
		param=unsupported[0],
	)


def fetch_compat_verbose(client: SpeechWeaveClient, job: dict[str, Any]) -> dict[str, Any] | None:
	"""Verbose transcript (segments and words) of a completed job, or None if unavailable."""

	job_id = str(job.get("id") or "")
	if not job_id or str(job.get("status")) != "completed":
		return None
	try:
		verbose = client.get_job_formatted(job_id, "verbose_json")
	except Exception:
		return None

	return verbose if isinstance(verbose, dict) else None


async def async_fetch_compat_verbose(
	client: AsyncSpeechWeaveClient,
	job: dict[str, Any],
) -> dict[str, Any] | None:

	job_id = str(job.get("id") or "")
	if not job_id or str(job.get("status")) != "completed":
		return None
	try:
		verbose = await client.get_job_formatted(job_id, "verbose_json")
	except Exception:
		return None

	return verbose if isinstance(verbose, dict) else None


def _num_or_nan(value: Any) -> float:

	try:
		return float(value)
	except (TypeError, ValueError):
		return float("nan")


def _round4(n: float) -> float:

	return round(n, 4)


def _segment_confidence(segment: Mapping[str, Any] | None) -> float | None:
	"""
	Confidence estimated from the model's segment log-probability (exp of avg_logprob). The model
	gives no per-word probability, so a word takes the confidence of the segment containing it.
	None when the segment carries no log-probability, rather than an invented value.
	"""

	lp = (segment or {}).get("avg_logprob")
	if lp is None:
		return None
	try:
		value = math.exp(float(lp))
	except (TypeError, ValueError, OverflowError):
		return None

	return _round4(min(1.0, max(0.0, value)))


def _overall_confidence(segments: list[dict[str, Any]]) -> float | None:

	weight = 0.0
	total = 0.0
	for seg in segments:
		c = _segment_confidence(seg)
		if c is None:
			continue
		try:
			w = max(float(seg["end"]) - float(seg["start"]), 0.001)
		except (KeyError, TypeError, ValueError):
			w = 0.001
		weight += w
		total += c * w

	return _round4(total / weight) if weight > 0 else None


def _segment_for(segments: list[dict[str, Any]], at: float) -> dict[str, Any] | None:

	for seg in segments:
		try:
			if float(seg["start"]) - 0.001 <= at <= float(seg["end"]) + 0.001:
				return seg
		except (KeyError, TypeError, ValueError):
			continue

	return None


def _verbose_parts(verbose: Mapping[str, Any] | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:

	segments = (verbose or {}).get("segments")
	words = (verbose or {}).get("words")

	return (
		[s for s in segments if isinstance(s, dict)] if isinstance(segments, list) else [],
		[w for w in words if isinstance(w, dict)] if isinstance(words, list) else [],
	)


def _rewritten_view(
	text: str,
	verbose: Mapping[str, Any] | None,
	rules: list[TextRule] | None,
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
	"""
	Applies find and replace and profanity rules to the transcript text, segment text and words.
	Run after word timing exists: only the strings change, never a timestamp. Everything the shapers
	derive afterwards (utterances, paragraphs, search) reads this rewritten view.
	"""

	segments, raw_words = _verbose_parts(verbose)
	if not rules:
		return text, segments, raw_words
	# The model's tokens carry a leading space, so trim before matching and keep timing as is.
	timed = [{**w, "word": str(w.get("word") or "").strip()} for w in raw_words]

	return (
		rewrite_text(text, rules),
		[{**seg, "text": rewrite_text(str(seg.get("text") or ""), rules)} for seg in segments],
		rewrite_words(timed, rules),
	)


def _sentence_word_count(sentence: Mapping[str, Any]) -> int:

	return len(sentence["words"]) or count_words(sentence["text"])


def _deepgram_paragraphs(paragraphs: list[dict[str, Any]]) -> dict[str, Any]:

	return {
		"transcript": "\n\n".join(" ".join(s["text"] for s in p["sentences"]) for p in paragraphs),
		"paragraphs": [
			{
				"sentences": [{"text": s["text"], "start": s["start"], "end": s["end"]} for s in p["sentences"]],
				"num_words": sum(_sentence_word_count(s) for s in p["sentences"]),
				"start": p["start"],
				"end": p["end"],
			}
			for p in paragraphs
		],
	}


def shape_deepgram_response(
	job: dict[str, Any],
	*,
	model: str | None = None,
	verbose: Mapping[str, Any] | None = None,
	utterances: bool = False,
	paragraphs: bool = False,
	search: str | list[str] | None = None,
	detect_language: bool = False,
	rewrites: list[TextRule] | None = None,
) -> CompatDict:
	"""
	`paragraphs` adds alternatives[0].paragraphs, `search` adds channels[0].search, and
	`detect_language` sets channels[0].detected_language to the language the model reported.
	`rewrites` (replace, profanity_filter) are applied after word timing is built.
	"""

	job_id = str(job.get("id") or "")
	model_name = model or str(job.get("model") or "core")
	language = _job_language(job)
	duration = _job_duration(job)
	text, segments, raw_words = _rewritten_view(_job_text(job), verbose, rewrites)

	words: list[dict[str, Any]] = []
	for w in raw_words:
		# The model's tokens carry a leading space, while the vendors' words do not.
		token = str(w.get("word") or "").strip()
		word: dict[str, Any] = {
			"word": token,
			"start": w.get("start"),
			"end": w.get("end"),
			"punctuated_word": token,
		}
		try:
			conf = _segment_confidence(_segment_for(segments, float(w["start"])))
		except (KeyError, TypeError, ValueError):
			conf = None
		if conf is not None:
			word["confidence"] = conf
		words.append(word)

	alternative: dict[str, Any] = {"transcript": text, "words": words}
	confidence = _overall_confidence(segments)
	if confidence is not None:
		alternative["confidence"] = confidence
	if language is not None:
		alternative["language"] = language

	metadata: dict[str, Any] = {
		"request_id": job_id,
		"channels": 1,
		"models": [model_name],
		"model_info": {model_name: {"name": model_name, "version": "1", "arch": "speechweave"}},
	}
	if isinstance(job.get("created_at"), str):
		metadata["created"] = job["created_at"]
	if duration is not None:
		metadata["duration"] = duration

	if paragraphs:
		alternative["paragraphs"] = _deepgram_paragraphs(build_paragraphs(build_sentences(raw_words, segments)))
	channel: dict[str, Any] = {"alternatives": [alternative]}
	if detect_language and language is not None:
		channel["detected_language"] = language
	if search is not None:
		queries = [str(q) for q in (search if isinstance(search, (list, tuple)) else [search])]
		channel["search"] = search_words(
			raw_words,
			queries,
			lambda w: _segment_confidence(_segment_for(segments, _num_or_nan(w.get("start")))),
		)
	results: dict[str, Any] = {"channels": [channel]}
	if utterances:
		built = []
		for i, seg in enumerate(segments):
			start = float(seg.get("start") or 0)
			end = float(seg.get("end") or 0)
			utterance: dict[str, Any] = {
				"start": start,
				"end": end,
				"channel": 0,
				"transcript": str(seg.get("text") or "").strip(),
				"words": [
					w for w in words if w["start"] is not None and start - 0.001 <= float(w["start"]) <= end + 0.001
				],
				"id": str(i),
			}
			c = _segment_confidence(seg)
			if c is not None:
				utterance["confidence"] = c
			built.append(utterance)
		results["utterances"] = built

	return to_compat({"metadata": metadata, "results": results})


def assembly_status(job: Mapping[str, Any]) -> tuple[str, str | None]:
	"""
	AssemblyAI statuses are queued, processing, completed and error. Failed and cancelled jobs both
	report as error, with a message. Any other in-flight state reports as processing.
	"""

	status = str(job.get("status") or "unknown")
	if status in ("completed", "queued"):
		return status, None
	if status == "error":
		return "error", str(job["error"]) if job.get("error") is not None else None
	if status == "failed":
		return "error", str(job.get("error") or "") or "Transcription failed"
	if status == "cancelled":
		return "error", "Transcription was cancelled"

	return "processing", None


def shape_assembly_response(
	job: dict[str, Any],
	*,
	verbose: Mapping[str, Any] | None = None,
	rewrites: list[TextRule] | None = None,
) -> CompatDict:
	"""`rewrites` (custom_spelling, filter_profanity) are applied after word timing is built."""

	pub_status, error = assembly_status(job)
	duration = _job_duration(job)
	language = _job_language(job)
	text, segments, raw_words = _rewritten_view(_job_text(job), verbose, rewrites)

	response: dict[str, Any] = {
		"id": str(job.get("id") or ""),
		"status": pub_status,
		"text": text,
	}
	if verbose is not None and isinstance(verbose.get("words"), list):
		# AssemblyAI reports word timing in milliseconds.
		words = []
		for w in raw_words:
			word: dict[str, Any] = {
				"text": str(w.get("word") or "").strip(),
				"start": round(float(w.get("start") or 0) * 1000),
				"end": round(float(w.get("end") or 0) * 1000),
			}
			try:
				conf = _segment_confidence(_segment_for(segments, float(w["start"])))
			except (KeyError, TypeError, ValueError):
				conf = None
			if conf is not None:
				word["confidence"] = conf
			words.append(word)
		response["words"] = words
	confidence = _overall_confidence(segments)
	if confidence is not None:
		response["confidence"] = confidence
	if duration is not None:
		response["audio_duration"] = duration
	if language is not None:
		response["language_code"] = language
	response["error"] = error

	return to_compat(response)


def _assembly_unit_words(sentence: Mapping[str, Any], segments: list[dict[str, Any]]) -> list[dict[str, Any]]:

	out: list[dict[str, Any]] = []
	for w in sentence["words"]:
		word: dict[str, Any] = {
			"text": w["word"],
			"start": round(w["start"] * 1000),
			"end": round(w["end"] * 1000),
			"speaker": None,
		}
		conf = _segment_confidence(_segment_for(segments, w["start"]))
		if conf is not None:
			word["confidence"] = conf
		out.append(word)

	return out


def shape_assembly_units(
	kind: str,
	job: Mapping[str, Any],
	verbose: Mapping[str, Any] | None,
) -> CompatDict:
	"""
	AssemblyAI `sentences` and `paragraphs` views of a completed transcript (times in milliseconds).
	Sentences are derived from punctuation, paragraphs from pauses. See compat_text.py.
	`kind` is "sentences" or "paragraphs".
	"""

	segments, raw_words = _verbose_parts(verbose)
	sentences = build_sentences(raw_words, segments)

	def to_unit(text: str, group: list[dict[str, Any]]) -> dict[str, Any]:
		words = [w for s in group for w in _assembly_unit_words(s, segments)]
		unit: dict[str, Any] = {
			"text": text,
			"start": round(group[0]["start"] * 1000),
			"end": round(group[-1]["end"] * 1000),
			"words": words,
			"speaker": None,
		}
		scores = [w["confidence"] for w in words if isinstance(w.get("confidence"), float)]
		conf = (
			_round4(sum(scores) / len(scores))
			if scores
			else _segment_confidence(_segment_for(segments, group[0]["start"]))
		)
		if conf is not None:
			unit["confidence"] = conf

		return unit

	if kind == "sentences":
		units = [to_unit(s["text"], [s]) for s in sentences]
	else:
		units = [
			to_unit(" ".join(s["text"] for s in p["sentences"]), p["sentences"]) for p in build_paragraphs(sentences)
		]
	response: dict[str, Any] = {"id": str(job.get("id") or "")}
	overall = _overall_confidence(segments)
	if overall is not None:
		response["confidence"] = overall
	duration = _job_duration(dict(job))
	if duration is not None:
		response["audio_duration"] = duration
	response[kind] = units

	return to_compat(response)


def shape_assembly_list(
	listing: Mapping[str, Any],
	*,
	base_url: str,
	status: str | None = None,
) -> CompatDict:
	"""
	AssemblyAI `transcripts.list` page from a jobs list. Page links are the SpeechWeave jobs list
	URLs for the neighbouring pages. `audio_url` is left out because a job does not record one.
	"""

	jobs = [j for j in (listing.get("data") or []) if isinstance(j, dict)]
	pagination = listing.get("pagination") or {}
	page = int(pagination.get("page") or 1)
	limit = int(pagination.get("limit") or len(jobs))
	total = pagination.get("total")

	def link(n: int) -> str:
		query = f"page={n}&limit={limit}"
		if status:
			query += f"&status={status}"

		return f"{base_url}/jobs?{query}"

	has_next = page * limit < total if isinstance(total, int) else (limit > 0 and len(jobs) >= limit)
	transcripts = []
	for job in jobs:
		pub_status, error = assembly_status(job)
		transcripts.append(
			{
				"id": str(job.get("id") or ""),
				"status": pub_status,
				"created": job.get("created_at"),
				"completed": job.get("completed_at"),
				"error": error,
			}
		)

	return to_compat(
		{
			"page_details": {
				"limit": limit,
				"result_count": len(jobs),
				"current_url": link(page),
				"prev_url": link(page - 1) if page > 1 else None,
				"next_url": link(page + 1) if has_next else None,
			},
			"transcripts": transcripts,
		}
	)


def upload_and_create_job(
	client: SpeechWeaveClient,
	*,
	data: UploadBody,
	filename: str,
	content_type: str | None = None,
	model: str | None = None,
	language: str | None = None,
	task: str | None = None,
	prompt: str | None = None,
	temperature: float | None = None,
	timestamp_granularities: list[str] | None = None,
	service_mode: str = "standard",
	metadata: dict[str, Any] | None = None,
	file_size: int | None = None,
) -> dict[str, Any]:

	content_type = content_type or infer_content_type(filename)
	size_bytes = _content_length(data, file_size=file_size)
	# Gate before presign so an oversized file costs neither a presign nor an upload.
	client.ensure_within_limits(size_bytes, service_mode)
	presign = client.presign_upload(
		filename=filename,
		content_type=content_type,
		content_length=size_bytes,
	)
	client.put_presigned_url(
		presign["upload_url"],
		data,
		content_type,
		file_size=file_size,
	)

	body: dict[str, Any] = {
		"object_key": presign["object_key"],
		"service_mode": service_mode,
	}
	if model is not None:
		body["model"] = model
	if language is not None:
		body["language"] = language
	if task is not None:
		body["task"] = task
	if prompt is not None:
		body["prompt"] = prompt
	if temperature is not None:
		body["temperature"] = temperature
	if timestamp_granularities is not None:
		body["timestamp_granularities"] = timestamp_granularities
	if metadata is not None:
		body["metadata"] = metadata

	return client.create_job(body)


def create_job_from_url(
	client: SpeechWeaveClient,
	*,
	url: str,
	model: str | None = None,
	prompt: str | None = None,
	language: str | None = None,
	timestamp_granularities: list[str] | None = None,
	service_mode: str = "standard",
	metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:

	body: dict[str, Any] = {
		"input_url": url,
		"service_mode": service_mode,
	}
	if model is not None:
		body["model"] = model
	if prompt is not None:
		body["prompt"] = prompt
	if language is not None:
		body["language"] = language
	if timestamp_granularities is not None:
		body["timestamp_granularities"] = timestamp_granularities
	if metadata is not None:
		body["metadata"] = metadata

	return client.create_job(body)


def finish_compat_job(
	client: SpeechWeaveClient,
	job: dict[str, Any],
	*,
	wait: bool,
	error_code: str,
	timeout_sec: float | None = None,
	poll_sec: float | None = None,
	# When False, a failed job is returned instead of raised (AssemblyAI reports it as status error).
	raise_on_failed: bool = True,
) -> dict[str, Any]:

	if not wait:
		return job

	from speechweave.polling import wait_for_job

	wait_kwargs: dict[str, Any] = {}
	if timeout_sec is not None:
		wait_kwargs["timeout_sec"] = timeout_sec
	if poll_sec is not None:
		wait_kwargs["poll_sec"] = poll_sec
	finished = wait_for_job(
		client,
		str(job.get("id") or ""),
		**wait_kwargs,
	)
	status = str(finished.get("status", ""))
	if status == "failed" and raise_on_failed:
		from speechweave.errors import SpeechWeaveError

		raise SpeechWeaveError(
			str(finished.get("error") or "Transcription failed"),
			500,
			error_code,
			body=finished,
		)

	return finished


async def async_upload_and_create_job(
	client: AsyncSpeechWeaveClient,
	*,
	data: UploadBody,
	filename: str,
	content_type: str | None = None,
	model: str | None = None,
	language: str | None = None,
	task: str | None = None,
	prompt: str | None = None,
	temperature: float | None = None,
	timestamp_granularities: list[str] | None = None,
	service_mode: str = "standard",
	metadata: dict[str, Any] | None = None,
	file_size: int | None = None,
) -> dict[str, Any]:

	content_type = content_type or infer_content_type(filename)
	size_bytes = _content_length(data, file_size=file_size)
	# Gate before presign so an oversized file costs neither a presign nor an upload.
	await client.ensure_within_limits(size_bytes, service_mode)
	presign = await client.presign_upload(
		filename=filename,
		content_type=content_type,
		content_length=size_bytes,
	)
	await client.put_presigned_url(
		presign["upload_url"],
		data,
		content_type,
		file_size=file_size,
	)

	body: dict[str, Any] = {
		"object_key": presign["object_key"],
		"service_mode": service_mode,
	}
	if model is not None:
		body["model"] = model
	if language is not None:
		body["language"] = language
	if task is not None:
		body["task"] = task
	if prompt is not None:
		body["prompt"] = prompt
	if temperature is not None:
		body["temperature"] = temperature
	if timestamp_granularities is not None:
		body["timestamp_granularities"] = timestamp_granularities
	if metadata is not None:
		body["metadata"] = metadata

	return await client.create_job(body)


async def async_create_job_from_url(
	client: AsyncSpeechWeaveClient,
	*,
	url: str,
	model: str | None = None,
	prompt: str | None = None,
	language: str | None = None,
	timestamp_granularities: list[str] | None = None,
	service_mode: str = "standard",
	metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:

	body: dict[str, Any] = {
		"input_url": url,
		"service_mode": service_mode,
	}
	if model is not None:
		body["model"] = model
	if prompt is not None:
		body["prompt"] = prompt
	if language is not None:
		body["language"] = language
	if timestamp_granularities is not None:
		body["timestamp_granularities"] = timestamp_granularities
	if metadata is not None:
		body["metadata"] = metadata

	return await client.create_job(body)


async def async_finish_compat_job(
	client: AsyncSpeechWeaveClient,
	job: dict[str, Any],
	*,
	wait: bool,
	error_code: str,
	timeout_sec: float | None = None,
	poll_sec: float | None = None,
	# When False, a failed job is returned instead of raised (AssemblyAI reports it as status error).
	raise_on_failed: bool = True,
) -> dict[str, Any]:

	if not wait:
		return job

	from speechweave.polling import async_wait_for_job

	wait_kwargs: dict[str, Any] = {}
	if timeout_sec is not None:
		wait_kwargs["timeout_sec"] = timeout_sec
	if poll_sec is not None:
		wait_kwargs["poll_sec"] = poll_sec
	finished = await async_wait_for_job(
		client,
		str(job.get("id") or ""),
		**wait_kwargs,
	)
	status = str(finished.get("status", ""))
	if status == "failed" and raise_on_failed:
		from speechweave.errors import SpeechWeaveError

		raise SpeechWeaveError(
			str(finished.get("error") or "Transcription failed"),
			500,
			error_code,
			body=finished,
		)

	return finished
