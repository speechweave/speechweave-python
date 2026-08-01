from __future__ import annotations

from typing import TYPE_CHECKING, Any

from speechweave.client import UploadBody, _content_length
from speechweave.mime import infer_content_type

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


def shape_openai_response(job: dict[str, Any]) -> dict[str, Any]:

	response: dict[str, Any] = {
		"text": _job_text(job),
		"task": "transcribe",
	}
	duration = _job_duration(job)
	if duration is not None:
		response["duration"] = duration

	language = _job_language(job)
	if language is not None:
		response["language"] = language

	return response


def shape_deepgram_response(
	job: dict[str, Any],
	*,
	model: str | None = None,
) -> dict[str, Any]:

	job_id = str(job.get("id") or "")
	model_name = model or str(job.get("model") or "core")
	text = _job_text(job)
	language = _job_language(job)

	alternative: dict[str, Any] = {
		"transcript": text,
		"confidence": 1,
		"words": [],
	}
	if language is not None:
		alternative["language"] = language

	return {
		"metadata": {
			"request_id": job_id,
			"model_info": {
				"name": model_name,
				"version": "1",
				"arch": "speechweave",
			},
		},
		"results": {
			"channels": [
				{
					"alternatives": [alternative],
				},
			],
		},
	}


def shape_assembly_response(job: dict[str, Any]) -> dict[str, Any]:

	status = str(job.get("status") or "unknown")
	pub_status = "completed" if status == "completed" else status
	duration = _job_duration(job)
	language = _job_language(job)
	error = job.get("error")

	response: dict[str, Any] = {
		"id": str(job.get("id") or ""),
		"status": pub_status,
		"text": _job_text(job),
	}
	if duration is not None:
		response["audio_duration"] = duration
	if language is not None:
		response["language"] = language
	if error is not None and pub_status == "failed":
		response["error"] = str(error)
	else:
		response["error"] = None

	return response


def upload_and_create_job(
	client: SpeechWeaveClient,
	*,
	data: UploadBody,
	filename: str,
	content_type: str | None = None,
	model: str | None = None,
	language: str | None = None,
	service_mode: str = "synchronous",
	metadata: dict[str, Any] | None = None,
	file_size: int | None = None,
) -> dict[str, Any]:

	content_type = content_type or infer_content_type(filename)
	# Gate before presign so an oversized file costs neither a presign nor an upload.
	client.ensure_within_limits(
		_content_length(data, file_size=file_size),
		service_mode,
	)
	presign = client.presign_upload(
		filename=filename,
		content_type=content_type,
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
	if metadata is not None:
		body["metadata"] = metadata

	return client.create_job(body)


def create_job_from_url(
	client: SpeechWeaveClient,
	*,
	url: str,
	model: str | None = None,
	language: str | None = None,
	service_mode: str = "synchronous",
	metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:

	body: dict[str, Any] = {
		"input_url": url,
		"service_mode": service_mode,
	}
	if model is not None:
		body["model"] = model
	if language is not None:
		body["language"] = language
	if metadata is not None:
		body["metadata"] = metadata

	return client.create_job(body)


def finish_compat_job(
	client: SpeechWeaveClient,
	job: dict[str, Any],
	*,
	wait: bool,
	error_code: str,
) -> dict[str, Any]:

	if not wait:
		return job

	from speechweave.polling import wait_for_job

	finished = wait_for_job(client, str(job.get("id") or ""))
	status = str(finished.get("status", ""))
	if status == "failed":
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
	service_mode: str = "synchronous",
	metadata: dict[str, Any] | None = None,
	file_size: int | None = None,
) -> dict[str, Any]:

	content_type = content_type or infer_content_type(filename)
	# Gate before presign so an oversized file costs neither a presign nor an upload.
	await client.ensure_within_limits(
		_content_length(data, file_size=file_size),
		service_mode,
	)
	presign = await client.presign_upload(
		filename=filename,
		content_type=content_type,
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
	if metadata is not None:
		body["metadata"] = metadata

	return await client.create_job(body)


async def async_create_job_from_url(
	client: AsyncSpeechWeaveClient,
	*,
	url: str,
	model: str | None = None,
	language: str | None = None,
	service_mode: str = "synchronous",
	metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:

	body: dict[str, Any] = {
		"input_url": url,
		"service_mode": service_mode,
	}
	if model is not None:
		body["model"] = model
	if language is not None:
		body["language"] = language
	if metadata is not None:
		body["metadata"] = metadata

	return await client.create_job(body)


async def async_finish_compat_job(
	client: AsyncSpeechWeaveClient,
	job: dict[str, Any],
	*,
	wait: bool,
	error_code: str,
) -> dict[str, Any]:

	if not wait:
		return job

	from speechweave.polling import async_wait_for_job

	finished = await async_wait_for_job(client, str(job.get("id") or ""))
	status = str(finished.get("status", ""))
	if status == "failed":
		from speechweave.errors import SpeechWeaveError

		raise SpeechWeaveError(
			str(finished.get("error") or "Transcription failed"),
			500,
			error_code,
			body=finished,
		)

	return finished
