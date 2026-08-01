# Changelog

## [1.3.0]

### Added
- **Upload Limit Gate:** `transcribe_file` (on both `SpeechWeaveClient` and `AsyncSpeechWeaveClient`) and `upload_and_create_job`/`async_upload_and_create_job` now check the file size against the account's upload limits (`GET /v1/limits`, cached 5 minutes) before presigning, raising a 413 `SpeechWeaveError` with code `FILE_TOO_LARGE` locally rather than spending a presign/upload on a file the API would reject. Also adds `get_limits`/`get_cached_limits` on both clients. Falls back to letting the API decide when the limits lookup fails or the body size can't be measured (non-seekable streams).

## [1.2.0]

### Changed
- **OpenAI-style error envelope:** the server now nests wallet/billing `402` errors (`PLATFORM_SPEND_CAP_REACHED`, `USER_SPEND_CAP_REACHED`, `INSUFFICIENT_BALANCE`, `CHECKOUT_REQUIRED`, `CHECKOUT_UNAVAILABLE`, `WALLET_EMPTY`) as `{"error": {"message", "type", "param", "code"}}`, matching the OpenAI SDK's own error-body convention. `SpeechWeaveError` gained `error_type` and `param`, populated from the new envelope. This SDK version parses both the new nested shape and the previous flat-string shape, so it's safe to upgrade independent of which server version you're calling.

## [1.1.1]

### Fixed
- **Linter Dependency Pinning:** Pinned `ruff` in `dev` dependencies (`0.15.21`) to match pre-commit configurations and prevent upstream version drift from breaking release builds. *(Note: Replaces `1.1.0`, which was not published to PyPI due to an automated CI workflow error; includes all `1.1.0` changes.)*

## [1.1.0]

### Added
- **MIME Inference Helper:** Exported `infer_content_type(filename, fallback)` from the package root to automatically map audio and video extensions to their proper MIME types, safely defaulting to `application/octet-stream` without raising.

### Changed
- **Automatic Content-Type Resolution:** `transcribe_file` (sync and async) and all compatibility helpers (`upload_and_create_job`, `async_upload_and_create_job`) now infer `content_type` from filenames when omitted. Explicit `content_type` strings retain strict priority over filename inference.

### Fixed
- **Job Creation MIME Passthrough:** Resolved an issue where `Jobs.create()` and `AsyncJobs.create()` prematurely defaulted omitted `content_type` arguments to `application/octet-stream` before delegating to `transcribe_file`, which prevented automatic extension inference.