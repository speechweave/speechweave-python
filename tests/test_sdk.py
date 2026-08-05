import io
import os
import struct
from unittest.mock import AsyncMock, patch

import pytest
from speechweave import (
	AsyncSpeechWeave,
	SpeechWeave,
	SpeechWeaveError,
	async_wait_for_job,
)


@pytest.fixture(scope="session")
def api_key():

	key = os.environ.get("SPEECHWEAVE_TEST_API_KEY")
	if not key:
		pytest.skip("Skipping live tests because SPEECHWEAVE_TEST_API_KEY is not set.")
	return key


@pytest.fixture
def fake_audio():
	return io.BytesIO(b"RIFF....fake-wave-data....")


def minimal_wav_bytes() -> bytes:
	"""1s mono 16-bit PCM WAV at 8kHz (minimal probe payload)."""
	sample_rate = 8000
	num_samples = sample_rate
	data_size = num_samples * 2
	buf = bytearray(44 + data_size)
	buf[0:4] = b"RIFF"
	struct.pack_into("<I", buf, 4, 36 + data_size)
	buf[8:12] = b"WAVE"
	buf[12:16] = b"fmt "
	struct.pack_into("<I", buf, 16, 16)
	struct.pack_into("<H", buf, 20, 1)
	struct.pack_into("<H", buf, 22, 1)
	struct.pack_into("<I", buf, 24, sample_rate)
	struct.pack_into("<I", buf, 28, sample_rate * 2)
	struct.pack_into("<H", buf, 32, 2)
	struct.pack_into("<H", buf, 34, 16)
	buf[36:40] = b"data"
	struct.pack_into("<I", buf, 40, data_size)
	return bytes(buf)


@pytest.fixture
def minimal_wav_audio():
	return io.BytesIO(minimal_wav_bytes())


# =====================================================================
# 1. NATIVE METHODS (SYNC & ASYNC)
# =====================================================================


def test_native_sync_flow(
	api_key,
	fake_audio,
):

	client = SpeechWeave(api_key=api_key)

	job = client.transcribe_file(
		fake_audio,
		filename="test.wav",
		model="core",
		service_mode="deferred",
	)
	assert "id" in job

	fetched = client.get_job(job["id"])
	assert fetched["id"] == job["id"]


@pytest.mark.asyncio
async def test_native_async_flow(
	api_key,
	fake_audio,
):

	async with AsyncSpeechWeave(api_key=api_key) as client:
		job = await client.transcribe_file(
			fake_audio,
			filename="test.wav",
			model="core",
		)
		assert "id" in job


def test_native_jobs_namespace_sync(
	api_key,
	minimal_wav_audio,
):

	client = SpeechWeave(api_key=api_key)

	job = client.jobs.create(
		file=minimal_wav_audio,
		filename="jobs_test.wav",
		model="core",
		service_mode="deferred",
	)
	assert "id" in job

	fetched = client.jobs.get(job["id"])
	assert fetched["id"] == job["id"]


@pytest.mark.asyncio
async def test_native_jobs_namespace_async(
	api_key,
	minimal_wav_audio,
):

	async with AsyncSpeechWeave(api_key=api_key) as client:
		job = await client.jobs.create(
			file=minimal_wav_audio,
			filename="async_jobs_test.wav",
			model="core",
			service_mode="deferred",
		)
		assert "id" in job

		fetched = await client.jobs.get(job["id"])
		assert fetched["id"] == job["id"]


# =====================================================================
# 2. PROVIDER COMPATIBILITY SHAPES
# =====================================================================


def test_openai_compatibility_shape(
	api_key,
	minimal_wav_audio,
):

	client = SpeechWeave(api_key=api_key)

	result = client.audio.transcriptions.create(
		file=minimal_wav_audio.read(),
		filename="test.wav",
		model="core",
	)
	assert isinstance(result, dict)
	assert "text" in result
	assert result.get("task") == "transcribe"


def test_deepgram_compatibility_shape(
	api_key,
	minimal_wav_audio,
):

	client = SpeechWeave(api_key=api_key)

	response = client.listen.prerecorded.transcribe_file(
		minimal_wav_audio,
		filename="test.wav",
		model="core",
	)
	assert response is not None
	assert "results" in response
	transcript = response.get("results", {}).get("channels", [{}])[0].get("alternatives", [{}])[0].get("transcript")
	assert isinstance(transcript, str)


def test_deepgram_compatibility_url_shape(api_key):

	url = os.environ.get("SPEECHWEAVE_TEST_AUDIO_URL")
	if not url:
		pytest.skip("Skipping URL compat test because SPEECHWEAVE_TEST_AUDIO_URL is not set.")

	client = SpeechWeave(api_key=api_key)
	response = client.listen.prerecorded.transcribe_url(
		url,
		model="core",
	)
	assert response is not None
	assert "results" in response


def test_assemblyai_compatibility_shape(
	api_key,
	minimal_wav_audio,
):

	client = SpeechWeave(api_key=api_key)

	transcript = client.transcripts.transcribe(
		minimal_wav_audio,
		config={"model": "core"},
	)
	assert transcript is not None
	assert transcript.get("status") == "completed"
	assert isinstance(transcript.get("text"), str)


def test_async_speechweave_exposes_compat_namespaces():

	client = AsyncSpeechWeave(api_key="sk_test_key")
	assert hasattr(client, "audio")
	assert hasattr(client, "listen")
	assert hasattr(client, "transcripts")
	assert hasattr(client.audio, "transcriptions")
	assert hasattr(client.listen, "prerecorded")


@pytest.mark.asyncio
async def test_async_openai_compat_wait_false(
	api_key,
	fake_audio,
):

	async with AsyncSpeechWeave(api_key=api_key) as client:
		job = await client.audio.transcriptions.create(
			file=fake_audio.read(),
			filename="test.mp3",
			model="core",
			wait=False,
		)
		assert "id" in job
		assert job.get("status") in {"queued", "processing", "completed"}


@pytest.mark.asyncio
async def test_async_openai_compat_wait_true_mocked():

	fake_job = {
		"id": "job_mock",
		"status": "completed",
		"transcript": "mock transcript",
		"duration": 1.0,
		"language": "en",
	}
	with (
		patch(
			"speechweave.namespaces.openai_compat.async_upload_and_create_job",
			new=AsyncMock(return_value={"id": "job_mock", "status": "queued"}),
		),
		patch(
			"speechweave.namespaces.openai_compat.async_finish_compat_job",
			new=AsyncMock(return_value=fake_job),
		),
	):
		async with AsyncSpeechWeave(api_key="sk_test_key") as client:
			result = await client.audio.transcriptions.create(
				file=b"audio-bytes",
				filename="test.mp3",
				model="core",
				wait=True,
			)

	assert result == {
		"text": "mock transcript",
		"task": "transcribe",
		"duration": 1.0,
		"language": "en",
	}


def test_openai_compat_forwards_prompt_temperature_timestamp_granularities():

	fake_job = {"id": "job_mock", "status": "completed", "transcript": "hola"}
	with (
		patch(
			"speechweave.namespaces.openai_compat.upload_and_create_job",
			return_value={"id": "job_mock", "status": "queued"},
		) as mock_upload,
		patch(
			"speechweave.namespaces.openai_compat.finish_compat_job",
			return_value=fake_job,
		),
	):
		client = SpeechWeave(api_key="sk_test_key")
		client.audio.transcriptions.create(
			file=b"audio-bytes",
			filename="test.mp3",
			language="es",
			prompt="SpeechWeave, Acme Corp",
			temperature=0.2,
			timestamp_granularities=["word"],
		)

	assert mock_upload.call_args.kwargs["language"] == "es"
	assert mock_upload.call_args.kwargs["prompt"] == "SpeechWeave, Acme Corp"
	assert mock_upload.call_args.kwargs["temperature"] == 0.2
	assert mock_upload.call_args.kwargs["timestamp_granularities"] == ["word"]


def test_openai_compat_response_format_vtt_delegates_to_get_job_formatted():

	fake_job = {"id": "job_mock", "status": "completed", "transcript": "hello"}
	with (
		patch(
			"speechweave.namespaces.openai_compat.upload_and_create_job",
			return_value={"id": "job_mock", "status": "queued"},
		),
		patch(
			"speechweave.namespaces.openai_compat.finish_compat_job",
			return_value=fake_job,
		),
	):
		client = SpeechWeave(api_key="sk_test_key")
		with patch.object(
			client,
			"get_job_formatted",
			return_value="WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nhello\n",
		) as mock_formatted:
			result = client.audio.transcriptions.create(
				file=b"audio-bytes",
				filename="test.mp3",
				response_format="vtt",
			)

	mock_formatted.assert_called_once_with("job_mock", "vtt")
	assert result == "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nhello\n"


def test_openai_compat_translations_forces_task_translate_and_omits_language():

	fake_job = {"id": "job_mock", "status": "completed", "transcript": "hello world"}
	with (
		patch(
			"speechweave.namespaces.openai_compat.upload_and_create_job",
			return_value={"id": "job_mock", "status": "queued"},
		) as mock_upload,
		patch(
			"speechweave.namespaces.openai_compat.finish_compat_job",
			return_value=fake_job,
		),
	):
		client = SpeechWeave(api_key="sk_test_key")
		result = client.audio.translations.create(
			file=b"audio-bytes",
			filename="test.mp3",
		)

	assert mock_upload.call_args.kwargs["task"] == "translate"
	assert "language" not in mock_upload.call_args.kwargs
	assert result == {"text": "hello world", "task": "translate"}


@pytest.mark.asyncio
async def test_async_openai_compat_translations_wait_true_mocked():

	fake_job = {
		"id": "job_mock",
		"status": "completed",
		"transcript": "hello world",
		"language": "en",
	}
	with (
		patch(
			"speechweave.namespaces.openai_compat.async_upload_and_create_job",
			new=AsyncMock(return_value={"id": "job_mock", "status": "queued"}),
		) as mock_upload,
		patch(
			"speechweave.namespaces.openai_compat.async_finish_compat_job",
			new=AsyncMock(return_value=fake_job),
		),
	):
		async with AsyncSpeechWeave(api_key="sk_test_key") as client:
			result = await client.audio.translations.create(
				file=b"audio-bytes",
				filename="test.mp3",
				wait=True,
			)

	assert mock_upload.await_args.kwargs["task"] == "translate"
	assert result == {"text": "hello world", "task": "translate", "language": "en"}


# =====================================================================
# 3. ERROR HANDLING SECURITY
# =====================================================================


def test_error_handling_payload():

	invalid_client = SpeechWeave(api_key="bad_token_format")
	with patch.object(
		invalid_client,
		"request_json",
		side_effect=SpeechWeaveError("Unauthorized", 401, "UNAUTHORIZED"),
	):
		with pytest.raises(SpeechWeaveError) as exc_info:
			invalid_client.get_job("any_id")

	assert exc_info.value.status == 401
	assert exc_info.value.code == "UNAUTHORIZED"


def test_maps_402_payment_required_to_speechweave_error():
	client = SpeechWeave(api_key="sk_test_key")

	class FakeResponse:
		status_code = 402
		text = '{"error":"Insufficient wallet balance","code":"INSUFFICIENT_BALANCE"}'
		reason_phrase = "Payment Required"
		content = text.encode()
		headers = {}

		def json(self):
			return {
				"error": "Insufficient wallet balance",
				"message": "Insufficient wallet balance",
				"code": "INSUFFICIENT_BALANCE",
				"balanceCents": 0,
				"requiredCents": 100,
			}

	with patch.object(client._client, "request", return_value=FakeResponse()):
		with pytest.raises(SpeechWeaveError) as exc_info:
			client.request_json("GET", "/jobs/any_id")

	assert exc_info.value.status == 402
	assert exc_info.value.code == "INSUFFICIENT_BALANCE"
	assert "Insufficient wallet balance" in str(exc_info.value)


def test_maps_openai_style_nested_error_envelope_to_speechweave_error():
	client = SpeechWeave(api_key="sk_test_key")

	class FakeResponse:
		status_code = 402
		text = '{"error":{"message":"Platform monthly spend cap reached for this account tier.","type":"insufficient_quota","param":null,"code":"PLATFORM_SPEND_CAP_REACHED"},"code":"PLATFORM_SPEND_CAP_REACHED"}'
		reason_phrase = "Payment Required"
		content = text.encode()
		headers = {}

		def json(self):
			return {
				"error": {
					"message": "Platform monthly spend cap reached for this account tier.",
					"type": "insufficient_quota",
					"param": None,
					"code": "PLATFORM_SPEND_CAP_REACHED",
				},
				"code": "PLATFORM_SPEND_CAP_REACHED",
				"message": "Platform monthly spend cap reached for this account tier.",
				"limit": {"period": "month", "tier": 2, "limitCents": 50000},
			}

	with patch.object(client._client, "request", return_value=FakeResponse()):
		with pytest.raises(SpeechWeaveError) as exc_info:
			client.request_json("GET", "/jobs/any_id")

	assert exc_info.value.status == 402
	assert exc_info.value.code == "PLATFORM_SPEND_CAP_REACHED"
	assert exc_info.value.error_type == "insufficient_quota"
	assert exc_info.value.param is None
	assert "Platform monthly spend cap reached for this account tier." in str(exc_info.value)


def test_put_presigned_url_streams_file_with_content_length():

	client = SpeechWeave(api_key="sk_test_key")
	payload = b"RIFF....audio-bytes...."
	file_obj = io.BytesIO(payload)
	mock_response = type("R", (), {"status_code": 200, "text": ""})()

	with patch.object(client._client, "put", return_value=mock_response) as put_mock:
		client.put_presigned_url(
			"https://upload.example/presigned",
			file_obj,
			"audio/wav",
		)

	assert put_mock.call_count == 1
	kwargs = put_mock.call_args.kwargs
	assert kwargs["content"] is file_obj
	assert not isinstance(kwargs["content"], (bytes, bytearray))
	assert kwargs["headers"]["Content-Type"] == "audio/wav"
	assert kwargs["headers"]["Content-Length"] == str(len(payload))
	assert file_obj.tell() == 0
	assert file_obj.read() == payload


@pytest.mark.asyncio
async def test_async_put_presigned_url_accepts_file_obj():

	client = AsyncSpeechWeave(api_key="sk_test_key")
	payload = b"RIFF....audio-bytes...."
	file_obj = io.BytesIO(payload)
	mock_response = type("R", (), {"status_code": 200, "text": ""})()

	with patch.object(client._client, "put", new_callable=AsyncMock, return_value=mock_response) as put_mock:
		await client.put_presigned_url(
			"https://upload.example/presigned",
			file_obj,
			"audio/wav",
		)

	assert put_mock.await_count == 1
	kwargs = put_mock.await_args.kwargs
	assert kwargs["headers"]["Content-Type"] == "audio/wav"
	assert kwargs["headers"]["Content-Length"] == str(len(payload))
	content = kwargs["content"]
	assert not isinstance(content, (bytes, bytearray, memoryview, io.BytesIO))
	chunks = [chunk async for chunk in content]
	assert b"".join(chunks) == payload


def test_auth_headers_include_user_agent():

	from speechweave.version import __version__

	client = SpeechWeave(api_key="sk_test_key")
	headers = client._auth_headers()
	assert headers["User-Agent"] == f"speechweave-python/{__version__}"


def test_put_presigned_url_file_size_override_for_nonseekable():

	class NonSeekable:
		def read(self, size: int = -1) -> bytes:
			return b""

	client = SpeechWeave(api_key="sk_test_key")
	mock_response = type("R", (), {"status_code": 200, "text": ""})()

	with patch.object(client._client, "put", return_value=mock_response) as put_mock:
		client.put_presigned_url(
			"https://upload.example/presigned",
			NonSeekable(),  # type: ignore[arg-type]
			"audio/wav",
			file_size=42,
		)

	kwargs = put_mock.call_args.kwargs
	assert kwargs["headers"]["Content-Length"] == "42"
	assert kwargs["headers"]["Content-Type"] == "audio/wav"


def _call_for(request_mock, fragment: str):
	"""
	Locate a mocked request by URL fragment rather than call index. The SDK
	makes a limits lookup before uploading, so positional order is not stable.
	"""
	for call in request_mock.call_args_list:
		if fragment in str(call.args[1]):
			return call

	raise AssertionError(f"no request matching {fragment!r}")


class _FakePresignResponse:
	status_code = 200
	text = ""
	content = b"{}"

	def json(self):
		return {
			"upload_url": "https://upload.example/presigned",
			"object_key": "obj_1",
			"id": "job_1",
			"status": "queued",
		}


def test_transcribe_file_infers_content_type_from_filename():

	client = SpeechWeave(api_key="sk_test_key")
	put_response = type("R", (), {"status_code": 200, "text": ""})()

	with patch.object(client._client, "request", return_value=_FakePresignResponse()) as request_mock:
		with patch.object(client._client, "put", return_value=put_response):
			client.transcribe_file(io.BytesIO(b"fake-flac-bytes"), filename="call.flac")

	presign_call = _call_for(request_mock, "/uploads")
	assert presign_call.kwargs["json"]["content_type"] == "audio/flac"


def test_transcribe_file_explicit_content_type_wins():

	client = SpeechWeave(api_key="sk_test_key")
	put_response = type("R", (), {"status_code": 200, "text": ""})()

	with patch.object(client._client, "request", return_value=_FakePresignResponse()) as request_mock:
		with patch.object(client._client, "put", return_value=put_response):
			client.transcribe_file(
				io.BytesIO(b"fake-flac-bytes"),
				filename="call.flac",
				content_type="audio/custom",
			)

	presign_call = _call_for(request_mock, "/uploads")
	assert presign_call.kwargs["json"]["content_type"] == "audio/custom"


def test_jobs_namespace_create_infers_content_type_from_filename():
	"""
	Regression test: Jobs.create() used to collapse an omitted content_type to the literal
	"application/octet-stream" before calling transcribe_file, defeating inference entirely.
	"""

	client = SpeechWeave(api_key="sk_test_key")
	put_response = type("R", (), {"status_code": 200, "text": ""})()

	with patch.object(client._client, "request", return_value=_FakePresignResponse()) as request_mock:
		with patch.object(client._client, "put", return_value=put_response):
			client.jobs.create(file=io.BytesIO(b"fake-ogg-bytes"), filename="voice.ogg")

	presign_call = _call_for(request_mock, "/uploads")
	assert presign_call.kwargs["json"]["content_type"] == "audio/ogg"


@pytest.mark.asyncio
async def test_async_upload_uses_to_thread_for_reads():

	client = AsyncSpeechWeave(api_key="sk_test_key")
	payload = b"threaded-bytes"
	file_obj = io.BytesIO(payload)
	mock_response = type("R", (), {"status_code": 200, "text": ""})()
	original_to_thread = __import__("asyncio").to_thread
	calls: list[tuple] = []

	async def tracking_to_thread(func, *args, **kwargs):
		calls.append((func, args, kwargs))
		return await original_to_thread(func, *args, **kwargs)

	with (
		patch.object(client._client, "put", new_callable=AsyncMock, return_value=mock_response) as put_mock,
		patch("speechweave.async_client.asyncio.to_thread", side_effect=tracking_to_thread),
	):
		await client.put_presigned_url(
			"https://upload.example/presigned",
			file_obj,
			"audio/wav",
		)
		kwargs = put_mock.await_args.kwargs
		chunks = [chunk async for chunk in kwargs["content"]]

	assert b"".join(chunks) == payload
	assert len(calls) >= 1
	assert calls[0][0] == file_obj.read


def test_list_jobs_passes_query_params():

	client = SpeechWeave(api_key="sk_test_key")
	expected = {"data": [{"id": "job_1"}], "pagination": {"page": 2}}

	with patch.object(client, "request_json", return_value=expected) as request_mock:
		result = client.jobs.list(page=2, limit=10, status="completed")

	request_mock.assert_called_once_with(
		"GET",
		"/jobs",
		params={"page": 2, "limit": 10, "status": "completed"},
	)
	assert result == expected


def test_get_job_formatted_returns_raw_text_for_text_plain():

	client = SpeechWeave(api_key="sk_test_key")

	class FakeResponse:
		status_code = 200
		text = "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nhello\n"
		headers = {"content-type": "text/plain; charset=utf-8"}

	with patch.object(client._client, "request", return_value=FakeResponse()) as request_mock:
		result = client.get_job_formatted("job_1", "vtt")

	assert result == "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nhello\n"
	call = request_mock.call_args
	assert call.kwargs.get("params") == {"format": "vtt"}


def test_get_job_formatted_returns_parsed_dict_for_verbose_json():

	client = SpeechWeave(api_key="sk_test_key")
	verbose = {"task": "transcribe", "text": "hello world", "segments": []}

	class FakeResponse:
		status_code = 200
		headers = {"content-type": "application/json"}

		def json(self):
			return verbose

	with patch.object(client._client, "request", return_value=FakeResponse()):
		result = client.get_job_formatted("job_1", "verbose_json")

	assert result == verbose


def test_get_job_formatted_raises_on_409_not_completed():

	client = SpeechWeave(api_key="sk_test_key")

	class FakeResponse:
		status_code = 409
		text = '{"error":"Job is not completed yet (status: processing)"}'
		reason_phrase = "Conflict"
		headers = {}

		def json(self):
			return {"error": "Job is not completed yet (status: processing)"}

	with patch.object(client._client, "request", return_value=FakeResponse()):
		with pytest.raises(SpeechWeaveError) as exc_info:
			client.get_job_formatted("job_1", "srt")

	assert exc_info.value.status == 409


@pytest.mark.asyncio
async def test_async_get_job_formatted_returns_raw_text():

	async with AsyncSpeechWeave(api_key="sk_test_key") as client:

		class FakeResponse:
			status_code = 200
			text = "1\n00:00:00,000 --> 00:00:01,000\nhello\n"
			headers = {"content-type": "text/plain; charset=utf-8"}

		with patch.object(client._client, "request", new=AsyncMock(return_value=FakeResponse())):
			result = await client.get_job_formatted("job_1", "srt")

		assert result == "1\n00:00:00,000 --> 00:00:01,000\nhello\n"


@pytest.mark.asyncio
async def test_async_wait_for_job_mocked():

	client = AsyncMock()
	client.get_job = AsyncMock(
		side_effect=[
			{"id": "job_1", "status": "queued"},
			{"id": "job_1", "status": "completed", "transcript": "done"},
		]
	)

	with patch("speechweave.polling.asyncio.sleep", new=AsyncMock()):
		result = await async_wait_for_job(client, "job_1", poll_sec=0.01)

	assert result["status"] == "completed"
	assert result["transcript"] == "done"


# =====================================================================
# 5. UPLOAD SIZE GATE
# =====================================================================


def _limits_response(max_bytes: int):
	return type(
		"R",
		(),
		{
			"status_code": 200,
			"text": "",
			"content": b"{}",
			"json": lambda self: {
				"max_input_bytes": max_bytes,
				"sync_max_bytes": max_bytes,
				"proxy_max_bytes": max_bytes,
			},
		},
	)()


def test_transcribe_file_rejects_oversized_input_before_presign():

	client = SpeechWeave(api_key="sk_test_key")

	with patch.object(client._client, "request", return_value=_limits_response(4)) as request_mock:
		with patch.object(client._client, "put") as put_mock:
			with pytest.raises(SpeechWeaveError) as exc_info:
				client.transcribe_file(io.BytesIO(b"way-too-many-bytes"), filename="big.wav")

	assert exc_info.value.status == 413
	assert exc_info.value.code == "FILE_TOO_LARGE"
	# Only the limits lookup happened, no presign, no upload.
	assert len(request_mock.call_args_list) == 1
	assert "/limits" in str(request_mock.call_args_list[0].args[1])
	put_mock.assert_not_called()


def test_transcribe_file_uploads_when_limits_lookup_fails():
	"""The gate is an optimization; a limits outage must not block a valid upload."""

	client = SpeechWeave(api_key="sk_test_key")
	put_response = type("R", (), {"status_code": 200, "text": ""})()

	def _request(method, url, **kwargs):
		if "/limits" in str(url):
			raise RuntimeError("limits unavailable")
		return _FakePresignResponse()

	with patch.object(client._client, "request", side_effect=_request):
		with patch.object(client._client, "put", return_value=put_response):
			job = client.transcribe_file(io.BytesIO(b"audio"), filename="call.wav")

	assert job["id"] == "job_1"


def test_transcribe_file_caches_limits_across_uploads():

	client = SpeechWeave(api_key="sk_test_key")
	put_response = type("R", (), {"status_code": 200, "text": ""})()

	def _request(method, url, **kwargs):
		if "/limits" in str(url):
			return _limits_response(500 * 1024 * 1024)
		return _FakePresignResponse()

	with patch.object(client._client, "request", side_effect=_request) as request_mock:
		with patch.object(client._client, "put", return_value=put_response):
			client.transcribe_file(io.BytesIO(b"one"), filename="one.wav")
			client.transcribe_file(io.BytesIO(b"two"), filename="two.wav")

	limits_calls = [c for c in request_mock.call_args_list if "/limits" in str(c.args[1])]
	assert len(limits_calls) == 1


def test_ensure_within_limits_skips_unmeasurable_body():

	client = SpeechWeave(api_key="sk_test_key")

	with patch.object(client, "get_cached_limits") as limits_mock:
		client.ensure_within_limits(None)

	limits_mock.assert_not_called()


@pytest.mark.asyncio
async def test_async_transcribe_file_rejects_oversized_input_before_presign():

	client = AsyncSpeechWeave(api_key="sk_test_key")

	with patch.object(
		client,
		"get_cached_limits",
		new=AsyncMock(
			return_value={
				"max_input_bytes": 4,
				"sync_max_bytes": 4,
				"proxy_max_bytes": 4,
			}
		),
	):
		with patch.object(client, "presign_upload", new=AsyncMock()) as presign_mock:
			with pytest.raises(SpeechWeaveError) as exc_info:
				await client.transcribe_file(io.BytesIO(b"way-too-many-bytes"), filename="big.wav")

	assert exc_info.value.status == 413
	presign_mock.assert_not_called()
	await client.aclose()
