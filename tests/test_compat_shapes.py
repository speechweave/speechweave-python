from unittest.mock import AsyncMock, MagicMock

import pytest

from speechweave.namespaces.compat_shapes import (
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
	assert result["metadata"]["model_info"]["name"] == "core"
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
		"language": "en",
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
	assert result["status"] == "failed"
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
