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
