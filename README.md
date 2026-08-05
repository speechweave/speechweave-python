# SpeechWeave Python SDK

[![PyPI version](https://img.shields.io/pypi/v/speechweave.svg)](https://pypi.org/project/speechweave/)
[![Python versions](https://img.shields.io/pypi/pyversions/speechweave.svg)](https://pypi.org/project/speechweave/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

The native Python SDK for SpeechWeave: background job polling, presigned uploads, and webhook verification. Python 3.10+.

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

```python
from speechweave import SpeechWeave, wait_for_job

sw = SpeechWeave()

job = sw.jobs.create(
	file="./podcast.mp3",
	model="core",
	service_mode="deferred",
)

done = wait_for_job(sw, job["id"])
print(done["transcript"])
```

`jobs.create` accepts a local path string or an open binary file. For URL input, cancel, and other job operations, see the [API reference](https://speechweave.com/docs/api).

## Translation & formatted transcripts

Translate audio to English text, or fetch a completed job's transcript formatted as `text`, `srt`, `vtt`, or `verbose_json` (word/segment timestamps):

```python
from speechweave import SpeechWeave, wait_for_job

sw = SpeechWeave()

job = sw.jobs.create(file="./spanish_podcast.mp3", task="translate")
done = wait_for_job(sw, job["id"])
print(done["transcript"])  # English text, regardless of the source language

# Once a job has completed, fetch its transcript in another format
srt = sw.get_job_formatted(job["id"], format="srt")
```

## Handling buffers & streams

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

## Async

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
```

See the [docs](https://speechweave.com/docs) for a full FastAPI example.

## Errors

```python
from speechweave import SpeechWeave, SpeechWeaveError

try:
	client = SpeechWeave(api_key="bad_key")
	client.get_job("job_123")
except SpeechWeaveError as e:
	print(e.status)
	print(e.code)
	print(e.error_type)  # OpenAI-style category, e.g. "insufficient_quota"
	# Prepaid wallet / spend caps: HTTP 402 with codes like INSUFFICIENT_BALANCE,
	# WALLET_EMPTY, USER_SPEND_CAP_REACHED, CHECKOUT_REQUIRED, PLATFORM_SPEND_CAP_REACHED.
	if e.status == 402 and e.code == "PLATFORM_SPEND_CAP_REACHED":
		print("Monthly account limit reached; do not retry until next month.")
	elif e.status == 402:
		print("Top up the wallet or raise spend caps, then retry.")
	# HTTP 403 with code EMAIL_UNVERIFIED: the account owning this API key hasn't
	# verified its email yet. Verify it, then retry -- the key itself is still valid.
	elif e.status == 403 and e.code == "EMAIL_UNVERIFIED":
		print("Verify the account email before uploading or creating jobs.")
```

## Configuration

- `api_key`, or set `SPEECHWEAVE_API_KEY`
- `base_url`, defaults to `https://api.speechweave.com/v1`
- `timeout`, httpx timeout in seconds (default `120`)

## Compatibility & Migration

If you are building a new application, use the native SDK above for full feature support. If you have an existing OpenAI, Deepgram, or AssemblyAI codebase, use the options below to switch with minimal changes.

### Drop-in usage

Convenience helpers if you want OpenAI/Deepgram/AssemblyAI response shapes without adding another package. They use presigned uploads like the native API.

```python
from speechweave import SpeechWeave

client = SpeechWeave()

with open("clip.mp3", "rb") as f:
	result = client.audio.transcriptions.create(
		file=f,
		filename="clip.mp3",
		model="core",
	)

print(result["text"])
```

Uploads go straight to storage the same way `jobs.create` does, so this supports files up to the same **250 MB** self-serve limit.

More examples: [OpenAI](https://speechweave.com/docs/migration/openai) · [Deepgram](https://speechweave.com/docs/migration/deepgram) · [AssemblyAI](https://speechweave.com/docs/migration/assemblyai)

### Migrating from OpenAI

You don't need this SDK for a quick swap, use the official `openai` package and point it at SpeechWeave:

```python
from openai import OpenAI

client = OpenAI(
    api_key="sk_live_...",
    base_url="https://api.speechweave.com/v1",
)

with open("clip.mp3", "rb") as f:
    result = client.audio.transcriptions.create(model="core", file=f)

print(result.text)
```

`client.audio.translations.create(model="core", file=f)` works the same way for translating audio into English text; OpenAI's translations endpoint has no `language` parameter, the source language is always auto-detected.

> **Upload size:** this path posts through the same wire format as the official OpenAI client, so it's capped at **90 MB** per file to stay under standard upload limits. For anything larger, switch to `client.audio.transcriptions.create(...)` from this SDK's drop-in helpers above: same call shape, and it unlocks the full 250 MB limit because uploads go straight to storage instead.

OpenAI model names like `whisper-1` are aliased to `core` on our backend. See the [OpenAI migration guide](https://speechweave.com/docs/migration/openai).
