# Changelog

## [1.1.0]

### Added
- **MIME Inference Helper:** Exported `infer_content_type(filename, fallback)` from the package root to automatically map audio and video extensions to their proper MIME types, safely defaulting to `application/octet-stream` without raising.

### Changed
- **Automatic Content-Type Resolution:** `transcribe_file` (sync and async) and all compatibility helpers (`upload_and_create_job`, `async_upload_and_create_job`) now infer `content_type` from filenames when omitted. Explicit `content_type` strings retain strict priority over filename inference.

### Fixed
- **Job Creation MIME Passthrough:** Resolved an issue where `Jobs.create()` and `AsyncJobs.create()` prematurely defaulted omitted `content_type` arguments to `application/octet-stream` before delegating to `transcribe_file`, which prevented automatic extension inference.