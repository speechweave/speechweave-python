import io
from unittest.mock import AsyncMock, Mock, patch

import pytest
from speechweave import AsyncSpeechWeave, SpeechWeave, SpeechWeaveError


def _client():
	return SpeechWeave(api_key="sk_test", base_url="https://example.invalid/v1")


class _Resp:
	status_code = 200
	content = b"{}"
	headers: dict = {}

	def __init__(self, payload):
		self._payload = payload

	def json(self):
		return self._payload


@pytest.mark.parametrize("bad", ["", "has space", "a" * 256, "café", "tab\tkey"])
def test_create_job_rejects_invalid_idempotency_key_before_request(bad):
	client = _client()
	with patch.object(client._client, "request") as request_mock:
		with pytest.raises(SpeechWeaveError) as err:
			client.create_job({"input_url": "https://x/a.wav"}, idempotency_key=bad)
	assert err.value.status == 400
	assert err.value.code == "INVALID_IDEMPOTENCY_KEY"
	request_mock.assert_not_called()


def test_jobs_create_sends_idempotency_key_header():
	client = _client()
	with patch.object(client._client, "request", return_value=_Resp({"id": "job_1"})) as request_mock:
		client.jobs.create(input_url="https://x/a.wav", idempotency_key="key-123")
	assert request_mock.call_args.kwargs["headers"]["Idempotency-Key"] == "key-123"
	assert request_mock.call_args.kwargs["json"]["input_url"] == "https://x/a.wav"
	assert "idempotency_key" not in request_mock.call_args.kwargs["json"]


def test_create_job_without_key_sends_no_header():
	client = _client()
	with patch.object(client._client, "request", return_value=_Resp({"id": "job_1"})) as request_mock:
		client.create_job({"input_url": "https://x/a.wav"})
	assert "Idempotency-Key" not in request_mock.call_args.kwargs["headers"]


def test_transcribe_file_validates_key_before_presign():
	client = _client()
	with patch.object(client._client, "request") as request_mock:
		with pytest.raises(SpeechWeaveError) as err:
			client.transcribe_file(io.BytesIO(b"abc"), idempotency_key="bad key")
	assert err.value.code == "INVALID_IDEMPOTENCY_KEY"
	request_mock.assert_not_called()


def test_transcribe_file_forwards_key_to_create_job():
	client = _client()
	with (
		patch.object(client, "ensure_within_limits"),
		patch.object(client, "presign_upload", return_value={"upload_url": "u", "object_key": "k"}),
		patch.object(client, "put_presigned_url"),
		patch.object(client, "create_job", return_value={"id": "job_1"}) as create_mock,
	):
		client.transcribe_file(io.BytesIO(b"abc"), idempotency_key="key-1")
	assert create_mock.call_args.kwargs["idempotency_key"] == "key-1"


def test_transcribe_file_and_wait_uploads_then_polls():
	client = _client()
	with (
		patch.object(client, "transcribe_file", return_value={"id": "job_9"}) as tf,
		patch("speechweave.client.wait_for_job", return_value={"id": "job_9", "status": "completed"}) as wait,
	):
		job = client.transcribe_file_and_wait(
			io.BytesIO(b"abc"), idempotency_key="k1", timeout_sec=5, poll_sec=0.1, language="en"
		)
	assert job["status"] == "completed"
	assert tf.call_args.kwargs["idempotency_key"] == "k1"
	assert tf.call_args.kwargs["language"] == "en"
	assert wait.call_args.args[1] == "job_9"
	assert wait.call_args.kwargs == {"timeout_sec": 5, "poll_sec": 0.1}


@pytest.mark.asyncio
async def test_async_invalid_key_and_wait():
	client = AsyncSpeechWeave(api_key="sk_test", base_url="https://example.invalid/v1")
	with patch.object(client._client, "request", new_callable=AsyncMock) as request_mock:
		with pytest.raises(SpeechWeaveError) as err:
			await client.create_job({"input_url": "https://x/a.wav"}, idempotency_key="")
		assert err.value.code == "INVALID_IDEMPOTENCY_KEY"
		request_mock.assert_not_called()

	with (
		patch.object(client, "transcribe_file", new_callable=AsyncMock, return_value={"id": "job_2"}) as tf,
		patch(
			"speechweave.async_client.async_wait_for_job",
			new_callable=AsyncMock,
			return_value={"id": "job_2", "status": "completed"},
		) as wait,
	):
		job = await client.transcribe_file_and_wait(io.BytesIO(b"x"), idempotency_key="k2")
	assert job["id"] == "job_2"
	assert tf.call_args.kwargs["idempotency_key"] == "k2"
	assert wait.call_args.args[1] == "job_2"


def test_wait_for_job_retries_httpx_timeout():
	import httpx
	from speechweave import wait_for_job

	client = Mock()
	client.get_job.side_effect = [httpx.ReadTimeout("slow"), {"id": "j", "status": "completed"}]
	with patch("speechweave.polling.time.sleep"):
		job = wait_for_job(client, "j", poll_sec=0.01)
	assert job["status"] == "completed"
	assert client.get_job.call_count == 2
