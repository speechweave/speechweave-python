# SpeechWeave Python SDK

[![PyPI version](https://img.shields.io/pypi/v/speechweave.svg)](https://pypi.org/project/speechweave/)
[![Python versions](https://img.shields.io/pypi/pyversions/speechweave.svg)](https://pypi.org/project/speechweave/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

The official Python SDK for SpeechWeave: transcription jobs, presigned direct uploads, webhook verification, and drop-in helpers for OpenAI, Deepgram, and AssemblyAI code. Python 3.10+.

**Docs:** [speechweave.com/docs](https://speechweave.com/docs) · [API reference](https://speechweave.com/docs/api)

## Install

```bash
pip install speechweave
```

Set your API key:

```bash
export SPEECHWEAVE_API_KEY="sk_..."
```

## Quick start

Upload a file, create the job, and wait for the transcript in one call:

```python
from speechweave import SpeechWeave

sw = SpeechWeave()

with open("podcast.mp3", "rb") as f:
	done = sw.transcribe_file_and_wait(
		f,
		filename="podcast.mp3",
		model="core",
	)
print(done["transcript"])
```

`timeout_sec` and `poll_sec` control the wait. The asyncio client has the same method (`await sw.transcribe_file_and_wait(...)`).

**Service mode vs delivery.** These are two separate choices:

| | Values | What it controls |
|---|---|---|
| Service mode (`service_mode`) | `standard`, `deferred` | Speed and price. `deferred` costs less and runs at lower priority. |
| Delivery | `sync`, `async` | How you get the result. `sync` returns the transcript in the same HTTP response (the OpenAI-compatible endpoints). `async` returns a job id, then you poll or receive a webhook (this SDK's native flow). |

`AsyncSpeechWeave` is the asyncio client. It is unrelated to async delivery: both the blocking and asyncio clients use the native async delivery flow.

## Creating jobs

`jobs.create` accepts a local path string or an open binary file and returns as soon as the job is created. Poll with `wait_for_job`, or receive the result by webhook:

```python
from speechweave import SpeechWeave, wait_for_job

sw = SpeechWeave()

job = sw.jobs.create(
	file="./podcast.mp3",
	model="core",
	service_mode="deferred",
	idempotency_key="podcast-2026-10-20",
)

done = wait_for_job(sw, job["id"])
print(done["transcript"])
```

An `idempotency_key` (1 to 255 printable ASCII characters, no spaces) makes a create call safe to repeat. Sending the same key within 24 hours returns the existing job instead of creating a duplicate. For URL input, cancel, and other job operations, see the [API reference](https://speechweave.com/docs/api).

## Files and streams

When you already have an open file handle or in-memory bytes, use `transcribe_file` directly:

```python
from speechweave import SpeechWeave, wait_for_job

sw = SpeechWeave()

with open("audio.wav", "rb") as f:
	job = sw.transcribe_file(
		f,
		filename="audio.wav",
		model="core",
		language="en",
	)

result = wait_for_job(sw, job["id"], timeout_sec=300)
print(result["transcript"])
```

## Translation and formatted transcripts

Translate audio to English text, or fetch a completed job's transcript formatted as `text`, `srt`, `vtt`, or `verbose_json` (word and segment timestamps):

```python
with open("spanish_podcast.mp3", "rb") as f:
	done = sw.transcribe_file_and_wait(
		f,
		filename="spanish_podcast.mp3",
		task="translate",
	)
print(done["transcript"])  # English text, regardless of the source language

srt = sw.get_job_formatted(done["id"], format="srt")
verbose = sw.get_job_formatted(done["id"], format="verbose_json")
```

## asyncio client

```python
import asyncio
from speechweave import AsyncSpeechWeave, async_wait_for_job

async def main():
	async with AsyncSpeechWeave() as sw:
		job = await sw.jobs.create(
			file="./podcast.mp3",
			model="core",
			service_mode="deferred",
		)

		done = await async_wait_for_job(sw, job["id"])
		print(done["transcript"])

asyncio.run(main())
```

## Webhooks

```python
from speechweave import verify_webhook

result = verify_webhook(
	secret=WEBHOOK_SECRET,
	raw_body=raw_body,
	signature_header=signature_header,
)
if not result["ok"]:
	# Reject the request. result["reason"] says why.
	...
```

Configure webhooks in the dashboard. Payloads are signed with `SpeechWeave-Signature`. See the [docs](https://speechweave.com/docs) for a full FastAPI example.

## Errors

Every API failure raises a `SpeechWeaveError` with an HTTP `status`, a machine-readable `code`, and an OpenAI-style `error_type`:

```python
from speechweave import SpeechWeaveError

try:
	sw.get_job("job_123")
except SpeechWeaveError as e:
	print(e.status, e.code, e)

	if e.status == 402:
		# Wallet balance is empty or a spend cap was reached.
		...
```

See the [API reference](https://speechweave.com/docs/api) for the full list of error codes.

## Configuration

```python
sw = SpeechWeave(
	api_key="sk_...",                           # defaults to SPEECHWEAVE_API_KEY
	base_url="https://api.speechweave.com/v1",  # default
	timeout=120.0,                              # httpx timeout in seconds (default 120)
)
```

## Compatibility and migration

For a new application, use the native SDK above. If you have an existing OpenAI, Deepgram, or AssemblyAI codebase, these helpers return the shapes you already use, so most call sites change very little. Results are dicts that also allow attribute access, and the same methods exist on the asyncio client, awaited. Uploads go straight to storage the same way `jobs.create` does, so files up to the **250 MB** self-serve limit are supported.

### OpenAI style

```python
with open("clip.mp3", "rb") as f:
	result = sw.audio.transcriptions.create(
		file=f,
		filename="clip.mp3",
		model="core",
	)

print(result["text"])
```

OpenAI model names like `whisper-1` are aliased to `core`.

You can also keep the official `openai` package and point it at SpeechWeave:

```python
from openai import OpenAI

client = OpenAI(
	api_key="sk_...",
	base_url="https://api.speechweave.com/v1",
)

with open("clip.mp3", "rb") as f:
	result = client.audio.transcriptions.create(model="core", file=f)

print(result.text)
```

`client.audio.translations.create(model="core", file=f)` works the same way for translating into English. Through the official client, uploads are capped at **90 MB** per file. For larger files, use `sw.audio.transcriptions.create` above. See the [OpenAI migration guide](https://speechweave.com/docs/migration/openai).

### Deepgram style

```python
# Keyword-only arguments, like the official Deepgram SDK
dg = sw.listen.v1.media.transcribe_url(
	url="https://example.com/a.mp3",
	paragraphs=True,
	search=["refund"],
	detect_language=True,
)
```

### AssemblyAI style

```python
# A failed job comes back with status "error" instead of raising
t = sw.transcripts.transcribe(
	"./call.mp3",
	{"custom_spelling": [{"from": ["sequel"], "to": "SQL"}], "filter_profanity": True},
)
sentences = sw.transcripts.get_sentences(t.id)
srt = sw.transcripts.export_subtitles_srt(t.id)
page = sw.transcripts.list_transcripts({"limit": 20})
```

### Supported options

| Helper | Options |
|---|---|
| Deepgram `transcribe_file` | `model`, `filename`, `language`, `file_size`, `utterances`, `paragraphs`, `search`, `detect_language`, `replace`, `profanity_filter`, `keyterm`, `keywords`, `wait` |
| Deepgram `transcribe_url` | `model`, `language`, `utterances`, `paragraphs`, `search`, `detect_language`, `replace`, `profanity_filter`, `keyterm`, `keywords`, `wait` |
| AssemblyAI config | `model`, `language_code`, `language`, `file_size`, `language_detection`, `custom_spelling`, `filter_profanity`, `keyterms_prompt`, `word_boost` |
| AssemblyAI `list_transcripts` | `limit`, `status`, `page` |

Options outside these lists raise a 400 `SpeechWeaveError` with code `UNSUPPORTED_OPTION` before any request is sent, so a call never silently drops a feature. See the [Deepgram](https://speechweave.com/docs/migration/deepgram) and [AssemblyAI](https://speechweave.com/docs/migration/assemblyai) migration guides for behavior details.
