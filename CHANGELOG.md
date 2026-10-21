# Changelog


## [2.0.0]

### Breaking changes

- **The Deepgram-style helper moved to `listen.v1.media.*` with keyword-only arguments**, like the current official Python SDK. `listen.prerecorded.*` is removed.

  ```python
  # before (1.x)
  result = sw.listen.prerecorded.transcribe_url("https://example.com/a.mp3", model="core")

  # after (2.0)
  result = sw.listen.v1.media.transcribe_url(url="https://example.com/a.mp3", model="core")
  result = sw.listen.v1.media.transcribe_file(request=open("a.mp3", "rb"), filename="a.mp3", model="core")
  ```

- **The AssemblyAI-style result key `language` is now `language_code`**, the name AssemblyAI uses. The `transcripts.transcribe(audio, config)` signature is unchanged, and `config` accepts `language_code` (and still `language`).

  ```python
  # before (1.x)
  transcript = sw.transcripts.transcribe("call.mp3")
  transcript["language"]

  # after (2.0)
  transcript["language_code"]
  ```

- **Unsupported options raise `UNSUPPORTED_OPTION` instead of being ignored.** The helpers raise a 400 `SpeechWeaveError` (before any request is sent) for options they do not read, such as `diarize`, `summarize` or `speaker_labels`. The option name is in `param` and the supported list is in the message.

  ```python
  # before (1.x): the option was silently dropped and the call succeeded
  sw.listen.prerecorded.transcribe_url("https://example.com/a.mp3", diarize=True)

  # after (2.0): raises SpeechWeaveError (status 400, code "UNSUPPORTED_OPTION", param "diarize")
  sw.listen.v1.media.transcribe_url(url="https://example.com/a.mp3")
  ```

- **`confidence` is estimated or left out.** Word and overall `confidence` is derived from the model's segment log-probabilities and is omitted when the model reported none. It used to be a constant `1`.

  ```python
  # before (1.x)
  word["confidence"]  # always 1

  # after (2.0)
  word.get("confidence")  # a number between 0 and 1, or None
  ```

- **AssemblyAI-style statuses use AssemblyAI's vocabulary.** A failed or cancelled job now reports `status` `"error"` (it was `failed` or `cancelled`), with `error` set to `"Transcription was cancelled"` for a cancelled job. `transcribe`, `get_by_id` and `wait_for_completion` return the transcript with that status instead of raising when a job fails, as the AssemblyAI SDK does.

  ```python
  # before (1.x)
  try:
  	transcript = sw.transcripts.transcribe("call.mp3")
  except SpeechWeaveError:
  	...  # job failed

  # after (2.0)
  transcript = sw.transcripts.transcribe("call.mp3")
  if transcript["status"] == "error":
  	print(transcript["error"])
  ```

- **Renamed limits field; the old name is removed.** The local upload gate reads `standard_max_bytes` from `GET /v1/limits` only (`sync_max_bytes` is no longer read), and `service_mode` is `standard` or `deferred` only (the `synchronous` and `asynchronous` spellings are no longer treated as service modes by the SDK).

### Added

- **Safe request retries (`idempotency_key`):** `create_job`, `transcribe_file`, `transcribe_file_and_wait` and `jobs.create` (sync and asyncio clients) accept an optional `idempotency_key`. Re-sending the same key within 24 hours returns the existing job instead of creating a duplicate. It must be 1 to 255 printable ASCII characters (no spaces), and an invalid key raises a 400 `INVALID_IDEMPOTENCY_KEY` error before any request.
- **`transcribe_file_and_wait`** (sync and asyncio): uploads, creates the job and polls until it finishes. It takes the same options as `transcribe_file`, plus `timeout_sec` and `poll_sec`.
- **Deepgram-style options** on `listen.v1.media.transcribe_file` and `transcribe_url`:
  - `paragraphs` adds `alternatives[0].paragraphs`, grouped from sentence punctuation and pauses (a gap over 0.8 s, or 5 sentences, starts a new paragraph).
  - `search` (a string or a list) adds `channels[0].search` with whole-word, case-insensitive hits and a snippet.
  - `detect_language` sets `channels[0].detected_language` to the language the model reported.
  - `replace` (`"find:replace"` or a list) rewrites whole words, case-insensitively, in the transcript, words and utterances.
  - `profanity_filter` masks common English profanity as first letter plus asterisks. English only.
  - `keyterm` and `keywords` bias the transcript toward your vocabulary through the model prompt. This is a bias, not a guarantee, and it is weaker than a dedicated keyword boost.
- **AssemblyAI-style config keys** on `transcripts.transcribe` and `submit`: `language_detection` (cannot be combined with `language_code`, as in AssemblyAI), `custom_spelling`, `filter_profanity` (English only), `keyterms_prompt` and `word_boost` (a bias, not a guarantee). Text rewrites apply to the transcript the call returns. A later `get_by_id` of the same id returns the original text.
- **AssemblyAI-style methods:** `export_subtitles_srt( id, chars_per_caption=None )` and `export_subtitles_vtt( id, chars_per_caption=None )` (`chars_per_caption` is accepted and ignored for now), `list_transcripts( params=None )` (`limit`, `status`, `page`, while `before_id` and `after_id` raise `UNSUPPORTED_OPTION`), `get_sentences( id )` and `get_paragraphs( id )` (times in milliseconds). All are also on the asyncio client.

### Changed

- **Deepgram-style helper follows the current official Python SDK:** `listen.v1.media.transcribe_url(url=..., model=...)` and `transcribe_file(request=<bytes or file>, ...)` are keyword-only like the official methods (async client too). `wait=False` still returns the created job.
- **AssemblyAI-style helper follows the official `Transcriber` shape:** `transcripts.transcribe(audio, config=None, *, poll_timeout=None)` where `audio` is a public URL, a local file path, bytes or a file object, with new `submit`, `get_by_id` and `wait_for_completion`.
- **Compat responses carry real word data and allow attribute access:** both helpers request word and segment timing, so Deepgram `words` (with `start`, `end`, `punctuated_word`) and AssemblyAI `words` (milliseconds) are populated instead of empty, and Deepgram metadata includes `duration`, `channels`, `created` and `models`. The Deepgram `utterances` option builds `results.utterances` from the transcript segments. Results are dicts that also allow attribute access (`resp.results.channels[0]...`, `transcript.text`).
- **Service mode and delivery use separate vocabulary.** `service_mode` is `standard` or `deferred` only, and `sync` / `async` describe delivery (transcript in the same HTTP response, or a job id then poll or webhook). `AsyncSpeechWeave` is the asyncio client and is unrelated to delivery.
- **`standard_max_bytes`:** the local upload gate reads the `standard_max_bytes` field from `GET /v1/limits`. The size error now says "standard service mode limit".

### Fixed

- A timed-out or dropped status check inside `wait_for_job` and `async_wait_for_job` is retried at the normal poll interval (up to `max_consecutive_network_errors`), including `httpx` timeouts and transport errors.


## [1.7.2]

### Fixed

- `wait_for_job` and `async_wait_for_job` now retry HTTP 429 rate limits instead of failing permanently or counting against network error limits.
- 429 retry waits are now jittered (50–100%) and clamped to the remaining `timeout_sec` to prevent synchronized polling bursts and false timeout errors.


## [1.7.1]

### Fixed

- `wait_for_job` **/** `async_wait_for_job` **no longer fail permanently on a single transient network error.** A dropped connection or timeout during a status poll is now retried (using the same poll interval) up to `max_consecutive_network_errors` (default 5) times before giving up, instead of immediately raising even though the job was still running normally. A real API error response is still raised immediately, unretried.


## [1.7.0]

### Changed

- **Public** `service_mode` **is now** `standard`**.** Omitting it on job create uses the higher-priority queue. `synchronous` remains an accepted alias. Pass `service_mode="deferred"` for the cheaper background queue. The local upload size gate applies to omitted / `standard` / `synchronous`, not only the old name.


## [1.6.0]

### Changed

- **API default** `service_mode` **is now** `synchronous`**.** Omitting `service_mode` on job create uses the standard queue. Pass `service_mode="deferred"` explicitly for the background queue.


## [1.5.0]

### Added

- `content_length` **on presign:** `presign_upload` (sync and async) accepts an optional `content_length` (bytes), and `transcribe_file`/`upload_and_create_job` pass it automatically when the body size is known locally.


## [1.4.0]

### Added

- **Translation task:** Added `task="translate"` to `transcribe_file`, `create_job`, and `upload_and_create_job` to translate audio to English text.
- **OpenAI-compat translations:** Added `client.audio.translations.create(...)` to mirror the OpenAI SDK's transcription translation flow.
- **Transcript formatting options:** Added support for `prompt`, `temperature`, and `timestamp_granularities` when creating jobs.
- **Formatted fetches:** Added `client.get_job_formatted(job_id, format)` to fetch a completed transcript as `text`, `srt`, `vtt`, or `verbose_json`. This also powers `response_format` resolution in the OpenAI-compat helper.
- **New types:** Exported `TranscriptionTask`, `TranscriptionResponseFormat`, `TimestampGranularity`, `TranscriptSegment`, `TranscriptWord`, and `VerboseTranscript`.


## [1.3.0]

### Added

- **Upload Limit Gate:** `transcribe_file` (on both `SpeechWeaveClient` and `AsyncSpeechWeaveClient`) and `upload_and_create_job`/`async_upload_and_create_job` now check the file size against the account's upload limits (`GET /v1/limits`, cached 5 minutes) before presigning, raising a 413 `SpeechWeaveError` with code `FILE_TOO_LARGE` locally rather than spending a presign/upload on a file the API would reject. Also adds `get_limits`/`get_cached_limits` on both clients. Falls back to letting the API decide when the limits lookup fails or the body size can't be measured (non-seekable streams).


## [1.2.0]

### Changed

- **OpenAI-style error envelope:** the server now nests wallet/billing `402` errors (`PLATFORM_SPEND_CAP_REACHED`, `USER_SPEND_CAP_REACHED`, `INSUFFICIENT_BALANCE`, `CHECKOUT_REQUIRED`, `CHECKOUT_UNAVAILABLE`, `WALLET_EMPTY`) as `{"error": {"message", "type", "param", "code"}}`, matching the OpenAI SDK's own error-body convention. `SpeechWeaveError` gained `error_type` and `param`, populated from the new envelope. This SDK version parses both the new nested shape and the previous flat-string shape, so it's safe to upgrade independent of which server version you're calling.


## [1.1.1]

### Fixed

- **Linter Dependency Pinning:** Pinned `ruff` in `dev` dependencies (`0.15.21`) to match pre-commit configurations and prevent upstream version drift from breaking release builds. *(Note: Replaces* `1.1.0`*, which was not published to PyPI due to an automated CI workflow error, and includes all* `1.1.0` *changes.)*


## [1.1.0]

### Added

- **MIME Inference Helper:** Exported `infer_content_type(filename, fallback)` from the package root to automatically map audio and video extensions to their proper MIME types, safely defaulting to `application/octet-stream` without raising.

### Changed

- **Automatic Content-Type Resolution:** `transcribe_file` (sync and async) and all compatibility helpers (`upload_and_create_job`, `async_upload_and_create_job`) now infer `content_type` from filenames when omitted. Explicit `content_type` strings retain strict priority over filename inference.

### Fixed

- **Job Creation MIME Passthrough:** Resolved an issue where `Jobs.create()` and `AsyncJobs.create()` prematurely defaulted omitted `content_type` arguments to `application/octet-stream` before delegating to `transcribe_file`, which prevented automatic extension inference.