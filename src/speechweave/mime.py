from __future__ import annotations

_EXTENSION_TO_MIME: dict[str, str] = {
	".mp3": "audio/mpeg",
	".wav": "audio/wav",
	".flac": "audio/flac",
	".m4a": "audio/mp4",
	".mp4": "video/mp4",
	".mov": "video/quicktime",
	".m4v": "video/x-m4v",
	".webm": "audio/webm",
	".ogg": "audio/ogg",
	".opus": "audio/opus",
	".aac": "audio/aac",
}


def infer_content_type(
	filename: str | None,
	fallback: str = "application/octet-stream",
) -> str:
	"""
	Infer a MIME type from a filename's extension. Falls back to `application/octet-stream`
	(never raises) so callers can use it unconditionally on optional filenames.
	"""

	if not filename:
		return fallback

	last_dot = filename.rfind(".")
	if last_dot == -1:
		return fallback

	ext = filename[last_dot:].lower()

	return _EXTENSION_TO_MIME.get(ext, fallback)
