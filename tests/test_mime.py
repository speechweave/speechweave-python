from speechweave.mime import infer_content_type


def test_infer_content_type_maps_known_extensions():

	assert infer_content_type("recording.mp3") == "audio/mpeg"
	assert infer_content_type("recording.WAV") == "audio/wav"
	assert infer_content_type("recording.flac") == "audio/flac"
	assert infer_content_type("recording.m4a") == "audio/mp4"
	assert infer_content_type("recording.mov") == "video/quicktime"
	assert infer_content_type("recording.m4v") == "video/x-m4v"
	assert infer_content_type("recording.webm") == "audio/webm"
	assert infer_content_type("recording.ogg") == "audio/ogg"
	assert infer_content_type("recording.opus") == "audio/opus"
	assert infer_content_type("recording.aac") == "audio/aac"


def test_infer_content_type_falls_back_to_octet_stream():

	assert infer_content_type("recording.xyz") == "application/octet-stream"
	assert infer_content_type("recording") == "application/octet-stream"
	assert infer_content_type(None) == "application/octet-stream"
	assert infer_content_type("") == "application/octet-stream"


def test_infer_content_type_never_raises_on_unusual_input():

	assert infer_content_type(".") == "application/octet-stream"
	assert infer_content_type("no-dot-at-all") == "application/octet-stream"
