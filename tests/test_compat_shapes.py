import math
from unittest.mock import AsyncMock, MagicMock

import pytest

from speechweave import AsyncSpeechWeave, SpeechWeave
from speechweave.errors import SpeechWeaveError
from speechweave.namespaces.compat_shapes import (
	assert_supported_compat_options,
	async_create_job_from_url,
	async_upload_and_create_job,
	shape_assembly_response,
	shape_deepgram_response,
	shape_openai_response,
	upload_and_create_job,
)


def test_shape_openai_response_minimal():

	job = {
		"id": "job_123",
		"status": "completed",
		"transcript": "hello world",
	}
	result = shape_openai_response(job)
	assert result == {
		"text": "hello world",
		"task": "transcribe",
	}


def test_shape_openai_response_with_metadata():

	job = {
		"id": "job_123",
		"status": "completed",
		"transcript": "hello world",
		"duration": 12.5,
		"language": "en",
	}
	result = shape_openai_response(job)
	assert result == {
		"text": "hello world",
		"task": "transcribe",
		"duration": 12.5,
		"language": "en",
	}


def test_shape_deepgram_response():

	job = {
		"id": "job_456",
		"status": "completed",
		"transcript": "deepgram text",
		"language": "en",
	}
	result = shape_deepgram_response(job, model="core")
	assert result["metadata"]["request_id"] == "job_456"
	assert result["metadata"]["model_info"]["core"]["name"] == "core"
	assert result["metadata"]["models"] == ["core"]
	assert result["results"]["channels"][0]["alternatives"][0]["transcript"] == "deepgram text"
	assert result["results"]["channels"][0]["alternatives"][0]["language"] == "en"


def test_shape_assembly_response_completed():

	job = {
		"id": "job_789",
		"status": "completed",
		"transcript": "assembly text",
		"duration": 30,
		"language": "en",
		"error": None,
	}
	result = shape_assembly_response(job)
	assert result == {
		"id": "job_789",
		"status": "completed",
		"text": "assembly text",
		"audio_duration": 30.0,
		"language_code": "en",
		"error": None,
	}


def test_shape_assembly_response_failed():

	job = {
		"id": "job_999",
		"status": "failed",
		"transcript": "",
		"error": "decode failed",
	}
	result = shape_assembly_response(job)
	assert result["status"] == "error"
	assert result["error"] == "decode failed"


@pytest.mark.asyncio
async def test_async_upload_and_create_job_passes_service_mode():

	client = AsyncMock()
	client.presign_upload = AsyncMock(
		return_value={
			"upload_url": "https://example.com/upload",
			"object_key": "obj_123",
		},
	)
	client.put_presigned_url = AsyncMock()
	client.create_job = AsyncMock(return_value={"id": "job_1"})

	await async_upload_and_create_job(
		client,
		data=b"audio",
		filename="test.wav",
		service_mode="deferred",
	)

	client.create_job.assert_awaited_once_with(
		{
			"object_key": "obj_123",
			"service_mode": "deferred",
		},
	)


@pytest.mark.asyncio
async def test_async_upload_and_create_job_streams_file_obj():

	import io

	client = AsyncMock()
	client.presign_upload = AsyncMock(
		return_value={
			"upload_url": "https://example.com/upload",
			"object_key": "obj_stream",
		},
	)
	client.put_presigned_url = AsyncMock()
	client.create_job = AsyncMock(return_value={"id": "job_stream"})
	file_obj = io.BytesIO(b"streamed-audio")

	await async_upload_and_create_job(
		client,
		data=file_obj,
		filename="stream.wav",
	)

	assert client.put_presigned_url.await_args.args[1] is file_obj
	assert not isinstance(client.put_presigned_url.await_args.args[1], (bytes, bytearray))


@pytest.mark.asyncio
async def test_async_create_job_from_url_passes_service_mode():

	client = AsyncMock()
	client.create_job = AsyncMock(return_value={"id": "job_2"})

	await async_create_job_from_url(
		client,
		url="https://example.com/audio.wav",
		service_mode="deferred",
	)

	client.create_job.assert_awaited_once_with(
		{
			"input_url": "https://example.com/audio.wav",
			"service_mode": "deferred",
		},
	)


def test_upload_and_create_job_infers_content_type_from_filename():

	client = MagicMock()
	client.presign_upload.return_value = {
		"upload_url": "https://example.com/upload",
		"object_key": "obj_infer",
	}
	client.create_job.return_value = {"id": "job_infer"}

	upload_and_create_job(
		client,
		data=b"audio",
		filename="note.opus",
	)

	client.presign_upload.assert_called_once_with(
		filename="note.opus",
		content_type="audio/opus",
		content_length=5,
	)
	assert client.put_presigned_url.call_args.args[2] == "audio/opus"


def test_upload_and_create_job_explicit_content_type_wins():

	client = MagicMock()
	client.presign_upload.return_value = {
		"upload_url": "https://example.com/upload",
		"object_key": "obj_explicit",
	}
	client.create_job.return_value = {"id": "job_explicit"}

	upload_and_create_job(
		client,
		data=b"audio",
		filename="note.opus",
		content_type="audio/custom",
	)

	client.presign_upload.assert_called_once_with(
		filename="note.opus",
		content_type="audio/custom",
		content_length=5,
	)


@pytest.mark.asyncio
async def test_async_upload_and_create_job_infers_content_type_from_filename():

	client = AsyncMock()
	client.presign_upload = AsyncMock(
		return_value={
			"upload_url": "https://example.com/upload",
			"object_key": "obj_async_infer",
		},
	)
	client.put_presigned_url = AsyncMock()
	client.create_job = AsyncMock(return_value={"id": "job_async_infer"})

	await async_upload_and_create_job(
		client,
		data=b"audio",
		filename="call.flac",
	)

	client.presign_upload.assert_awaited_once_with(
		filename="call.flac",
		content_type="audio/flac",
		content_length=5,
	)


VERBOSE = {
	"task": "transcribe",
	"language": "en",
	"duration": 4,
	"text": "Hello there. Bye now.",
	"segments": [
		{"id": 0, "start": 0, "end": 2, "text": " Hello there.", "avg_logprob": math.log(0.9)},
		{"id": 1, "start": 2, "end": 4, "text": " Bye now.", "avg_logprob": math.log(0.5)},
	],
	"words": [
		{"word": " Hello", "start": 0, "end": 0.5},
		{"word": " there.", "start": 0.6, "end": 1.2},
		{"word": " Bye", "start": 2.1, "end": 2.4},
	],
}
JOB = {
	"id": "job_1",
	"status": "completed",
	"transcript": "Hello there. Bye now.",
	"language": "en",
	"duration": 4,
	"created_at": "2026-10-21T00:00:00Z",
}


def test_deepgram_response_has_real_words_and_estimated_confidence():

	out = shape_deepgram_response(JOB, model="core", verbose=VERBOSE)
	alt = out["results"]["channels"][0]["alternatives"][0]
	assert len(alt["words"]) == 3
	assert alt["words"][0]["word"] == "Hello" and alt["words"][0]["punctuated_word"] == "Hello"
	assert alt["words"][0]["confidence"] == 0.9
	assert alt["words"][2]["confidence"] == 0.5
	assert alt["confidence"] == 0.7  # duration-weighted mean of 0.9 and 0.5
	assert out["metadata"]["duration"] == 4 and out["metadata"]["created"] == "2026-10-21T00:00:00Z"
	assert "utterances" not in out["results"]


def test_deepgram_response_allows_attribute_access():

	out = shape_deepgram_response(JOB, model="core", verbose=VERBOSE)
	assert out.results.channels[0].alternatives[0].transcript == "Hello there. Bye now."
	assert out["metadata"].request_id == "job_1"


def test_deepgram_utterances_are_built_from_segments_only_when_asked():

	out = shape_deepgram_response(JOB, model="core", verbose=VERBOSE, utterances=True)
	utts = out["results"]["utterances"]
	assert [u["transcript"] for u in utts] == ["Hello there.", "Bye now."]
	assert len(utts[0]["words"]) == 2 and len(utts[1]["words"]) == 1
	assert utts[0]["confidence"] == 0.9


def test_confidence_is_omitted_not_invented_when_the_model_reported_none():

	bare = {
		**VERBOSE,
		"segments": [{k: v for k, v in seg.items() if k != "avg_logprob"} for seg in VERBOSE["segments"]],
	}
	alt = shape_deepgram_response(JOB, verbose=bare)["results"]["channels"][0]["alternatives"][0]
	assert "confidence" not in alt and "confidence" not in alt["words"][0]
	no_verbose = shape_deepgram_response(JOB)
	assert no_verbose["results"]["channels"][0]["alternatives"][0]["words"] == []


def test_assembly_words_are_in_milliseconds_with_official_field_names():

	out = shape_assembly_response(JOB, verbose=VERBOSE)
	assert out["words"][1] == {"text": "there.", "start": 600, "end": 1200, "confidence": 0.9}
	assert out.confidence == 0.7 and out.language_code == "en"
	assert "language" not in out


def test_assert_supported_compat_options():

	spec = {"helper": "Deepgram-style", "supported": ("model", "language"), "satisfied": {"smart_format": True}}
	assert_supported_compat_options({"model": "core", "diarize": None, "smart_format": True}, **spec)
	assert_supported_compat_options(None, **spec)

	with pytest.raises(SpeechWeaveError) as exc:
		assert_supported_compat_options({"diarize": True}, **spec)
	err = exc.value
	assert err.status == 400 and err.code == "UNSUPPORTED_OPTION" and err.param == "diarize"
	assert '"diarize"' in str(err) and "Supported options: model, language" in str(err)

	with pytest.raises(SpeechWeaveError, match='"diarize", "utterances" are not supported'):
		assert_supported_compat_options({"diarize": True, "utterances": True}, **spec)
	with pytest.raises(SpeechWeaveError, match='"smart_format" is not supported'):
		assert_supported_compat_options({"smart_format": False}, **spec)


def test_helpers_reject_unsupported_options_before_any_request():

	sw = SpeechWeave(api_key="sk_test", base_url="http://127.0.0.1:1/v1")
	with pytest.raises(SpeechWeaveError) as dg:
		sw.listen.v1.media.transcribe_url(url="https://example.com/a.mp3", topics=True)
	assert dg.value.code == "UNSUPPORTED_OPTION" and dg.value.param == "topics"
	with pytest.raises(SpeechWeaveError) as dg_file:
		sw.listen.v1.media.transcribe_file(request=b"a", diarize=True)
	assert dg_file.value.code == "UNSUPPORTED_OPTION"
	with pytest.raises(SpeechWeaveError) as aai:
		sw.transcripts.transcribe("https://example.com/a.mp3", {"speaker_labels": True})
	assert aai.value.code == "UNSUPPORTED_OPTION" and aai.value.param == "speaker_labels"
	with pytest.raises(SpeechWeaveError) as missing:
		sw.transcripts.transcribe("", {"model": "core"})
	assert missing.value.code == "MISSING_AUDIO"
	with pytest.raises(SpeechWeaveError) as no_url:
		sw.listen.v1.media.transcribe_url(url="")
	assert no_url.value.code == "MISSING_URL"


@pytest.mark.asyncio
async def test_async_helpers_reject_unsupported_options_before_any_request():

	sw = AsyncSpeechWeave(api_key="sk_test", base_url="http://127.0.0.1:1/v1")
	with pytest.raises(SpeechWeaveError) as dg:
		await sw.listen.v1.media.transcribe_url(url="https://example.com/a.mp3", summarize="v2")
	assert dg.value.code == "UNSUPPORTED_OPTION"
	with pytest.raises(SpeechWeaveError) as aai:
		await sw.transcripts.transcribe("https://example.com/a.mp3", {"sentiment_analysis": True})
	assert aai.value.code == "UNSUPPORTED_OPTION"
