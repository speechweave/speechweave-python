import json
import math

import httpx
import pytest

from speechweave import AsyncSpeechWeave, SpeechWeave, SpeechWeaveError
from speechweave.namespaces.compat_shapes import (
	assembly_status,
	shape_assembly_list,
	shape_assembly_response,
	shape_assembly_units,
	shape_deepgram_response,
)
from speechweave.namespaces.compat_text import (
	PARAGRAPH_GAP_SECONDS,
	PARAGRAPH_MAX_SENTENCES,
	PROFANITY_EN,
	TextRule,
	build_paragraphs,
	build_sentences,
	build_vocabulary_prompt,
	mask_word,
	parse_custom_spelling,
	parse_deepgram_replace,
	rewrite_text,
	rewrite_words,
	search_words,
)


def w(word, start, end):
	return {"word": word, "start": start, "end": end}


SPEECH = [
	w("Ask", 0, 0.3), w("not", 0.3, 0.5), w("what", 0.5, 0.7), w("your", 0.7, 0.9),
	w("country", 0.9, 1.3), w("can", 1.3, 1.5), w("do.", 1.5, 1.8),
	w("Ask", 3.0, 3.2), w("what", 3.2, 3.4), w("you", 3.4, 3.6), w("can", 3.6, 3.8), w("do?", 3.8, 4.0),
]  # fmt: skip
TEXT = "Ask not what your country can do. Ask what you can do?"


# sentences and paragraphs


def test_sentences_split_on_terminal_punctuation():
	sentences = build_sentences(SPEECH)
	assert [s["text"] for s in sentences] == ["Ask not what your country can do.", "Ask what you can do?"]
	assert sentences[0]["start"] == 0
	assert sentences[1]["end"] == 4.0


def test_sentences_ignore_initials_and_abbreviations():
	words = [w("J.", 0, 0.2), w("Smith", 0.2, 0.5), w("met", 0.5, 0.7), w("Dr.", 0.7, 0.9), w("Lee.", 0.9, 1.2)]
	assert [s["text"] for s in build_sentences(words)] == ["J. Smith met Dr. Lee."]


def test_sentences_fall_back_to_segments_without_words():
	sentences = build_sentences([], [{"start": 2, "end": 6, "text": " One. Two."}])
	assert [s["text"] for s in sentences] == ["One.", "Two."]
	assert sentences[0]["start"] == 2
	assert sentences[1]["end"] == 6


def test_empty_transcript_has_no_sentences_or_paragraphs():
	assert build_sentences([], []) == []
	assert build_paragraphs([]) == []


def test_paragraph_breaks_on_gap_and_on_max_sentences():
	assert PARAGRAPH_GAP_SECONDS == 0.8
	assert PARAGRAPH_MAX_SENTENCES == 5
	assert len(build_paragraphs(build_sentences(SPEECH))) == 2
	words = [w("Go.", i, i + 0.5) for i in range(7)]
	sizes = [len(p["sentences"]) for p in build_paragraphs(build_sentences(words))]
	assert sizes == [5, 2]


def test_deepgram_paragraphs_are_seconds_and_assembly_units_are_milliseconds():
	verbose = {"words": SPEECH, "segments": []}
	job = {"id": "job_1", "status": "completed", "transcript": TEXT}
	dg = shape_deepgram_response(job, verbose=verbose, paragraphs=True)
	paragraphs = dg["results"]["channels"][0]["alternatives"][0]["paragraphs"]["paragraphs"]
	assert paragraphs[0]["start"] == 0
	assert paragraphs[0]["num_words"] == 7
	sentences = shape_assembly_units("sentences", job, verbose)["sentences"]
	assert (sentences[1]["start"], sentences[1]["end"]) == (3000, 4000)
	assert sentences[0]["speaker"] is None
	assert len(shape_assembly_units("paragraphs", job, verbose)["paragraphs"]) == 2


# search


def test_search_matches_whole_words_with_snippet():
	[result] = search_words(SPEECH, ["COUNTRY"], lambda _w: 0.9)
	assert result["hits"] == [
		{"confidence": 0.9, "start": 0.9, "end": 1.3, "snippet": "not what your country can do. Ask"}
	]


def test_search_phrase_no_hit_and_partial_words():
	phrase, none, partial = search_words(SPEECH, ["what your", "banana", "coun"], lambda _w: None)
	assert (phrase["hits"][0]["start"], phrase["hits"][0]["end"]) == (0.5, 0.9)
	assert "confidence" not in phrase["hits"][0]
	assert none["hits"] == []
	assert partial["hits"] == []
	assert search_words([], ["x"], lambda _w: None) == [{"query": "x", "hits": []}]


def test_deepgram_search_and_detect_language_in_response():
	job = {"id": "j", "status": "completed", "transcript": TEXT, "language": "en"}
	out = shape_deepgram_response(job, verbose={"words": SPEECH}, search=["country"], detect_language=True)
	channel = out["results"]["channels"][0]
	assert channel["detected_language"] == "en"
	assert len(channel["search"][0]["hits"]) == 1
	plain = shape_deepgram_response(job, verbose={"words": SPEECH})
	assert "detected_language" not in plain["results"]["channels"][0]
	assert "search" not in plain["results"]["channels"][0]


# find and replace, masking


def test_replace_matches_whole_words_only():
	rules = parse_deepgram_replace("color:colour")
	assert rewrite_text("Color, colorful and COLOR.", rules) == "colour, colorful and colour."


def test_replace_allows_colons_and_lists_and_validates():
	rules = parse_deepgram_replace(["time:12:30", "foo:bar"])
	assert rewrite_text("the time foo", rules) == "the 12:30 bar"
	with pytest.raises(SpeechWeaveError, match="find:replace"):
		parse_deepgram_replace("nocolon")


def test_custom_spelling_maps_several_spellings_and_validates():
	rules = parse_custom_spelling([{"from": ["sequel", "see quill"], "to": "SQL"}])
	assert rewrite_text("use Sequel or see quill", rules) == "use SQL or SQL"
	with pytest.raises(SpeechWeaveError, match="non-empty"):
		parse_custom_spelling([{"from": [], "to": "x"}])
	with pytest.raises(SpeechWeaveError, match="5 words"):
		parse_custom_spelling([{"from": ["a b c d e f"], "to": "x"}])


def test_rewrite_words_keeps_timestamps_and_merges_multiword_matches():
	words = [w("see", 0, 0.2), w("quill.", 0.2, 0.5), w("now", 0.5, 0.8)]
	out = rewrite_words(words, parse_custom_spelling([{"from": ["see quill"], "to": "SQL"}]))
	assert out == [w("SQL.", 0, 0.5), w("now", 0.5, 0.8)]


def test_mask_keeps_length_and_applies_to_text_and_words():
	assert mask_word("damn") == "d***"
	assert "damn" in PROFANITY_EN
	rules = [TextRule(["damn"], mask_word)]
	out = shape_deepgram_response(
		{"id": "j", "status": "completed", "transcript": "well damn it"},
		verbose={"words": [w("well", 0, 0.2), w("damn", 0.2, 0.4), w("it", 0.4, 0.5)]},
		rewrites=rules,
	)
	alt = out["results"]["channels"][0]["alternatives"][0]
	assert alt["transcript"] == "well d*** it"
	assert [x["word"] for x in alt["words"]] == ["well", "d***", "it"]
	assert alt["words"][1]["start"] == 0.2


def test_assembly_rewrites_text_and_words_together():
	out = shape_assembly_response(
		{"id": "j", "status": "completed", "transcript": "hi sequel"},
		verbose={"words": [w("hi", 0, 0.1), w("sequel", 0.1, 0.4)]},
		rewrites=parse_custom_spelling([{"from": ["sequel"], "to": "SQL"}]),
	)
	assert out["text"] == "hi SQL"
	assert out["words"][1]["text"] == "SQL"
	assert out["words"][1]["end"] == 400


def test_profanity_list_is_small_and_lowercase():
	assert 10 < len(PROFANITY_EN) < 60
	assert all(word == word.lower() for word in PROFANITY_EN)


# vocabulary prompt


def test_vocabulary_prompt_exact_text_and_dedupe():
	assert build_vocabulary_prompt(["Kubernetes", "kubernetes", "Zod"]) == "Vocabulary: Kubernetes, Zod."
	assert build_vocabulary_prompt([]) is None


def test_vocabulary_prompt_keeps_caller_prompt_and_truncates_by_whole_terms():
	assert build_vocabulary_prompt(["Zod"], "Meeting notes.") == "Meeting notes. Vocabulary: Zod."
	prompt = build_vocabulary_prompt([f"term{i}" for i in range(200)])
	assert prompt is not None
	assert len(prompt) <= 600
	assert prompt.startswith("Vocabulary: term0, term1,")
	assert prompt.endswith(".")
	assert not prompt.endswith("term")


# status vocabulary


def test_assembly_status_maps_failed_and_cancelled_to_error():
	assert assembly_status({"status": "failed", "error": "decode failed"}) == ("error", "decode failed")
	assert assembly_status({"status": "failed"}) == ("error", "Transcription failed")
	assert assembly_status({"status": "cancelled"}) == ("error", "Transcription was cancelled")
	assert assembly_status({"status": "completed"})[0] == "completed"
	assert assembly_status({"status": "downloading"})[0] == "processing"


def test_assembly_list_marks_pages():
	page = shape_assembly_list(
		{"data": [{"id": "z", "status": "queued"}], "pagination": {"page": 3, "limit": 2, "total": 5}},
		base_url="https://x/v1",
	)
	assert page["page_details"]["next_url"] is None
	assert "page=2" in page["page_details"]["prev_url"]
	assert math.isclose(page["page_details"]["limit"], 2)


# namespaces against a fake Brain


class FakeBrain:
	def __init__(self, job_status="completed", **extra):
		self.created = []
		self.requests = []
		self.job_status = job_status
		self.extra = extra

	def handler(self, request: httpx.Request) -> httpx.Response:
		self.requests.append(request)
		path = request.url.path
		fmt = request.url.params.get("format")
		if request.method == "POST" and path.endswith("/jobs"):
			self.created.append(json.loads(request.content))
			return httpx.Response(201, json={"id": "job_1", "status": "queued"})
		if path.endswith("/jobs/job_1") and fmt == "verbose_json":
			return httpx.Response(200, json={"words": SPEECH, "segments": [], "text": TEXT})
		if path.endswith("/jobs/job_1") and fmt == "srt":
			return httpx.Response(
				200, text="1\n00:00:00,000 --> 00:00:01,000\nhi\n", headers={"content-type": "text/plain"}
			)
		if path.endswith("/jobs/job_1"):
			return httpx.Response(
				200,
				json={
					"id": "job_1",
					"status": self.job_status,
					"transcript": TEXT,
					"duration": 4,
					"language": "en",
					**self.extra,
				},
			)
		if path.endswith("/jobs"):
			return httpx.Response(
				200,
				json={
					"data": [
						{
							"id": "a",
							"status": "completed",
							"created_at": "2026-01-01T00:00:00Z",
							"completed_at": "2026-01-01T00:01:00Z",
						},
						{"id": "b", "status": "cancelled", "created_at": "2026-01-02T00:00:00Z"},
					],
					"pagination": {"page": 1, "limit": 2, "total": 5},
				},
			)
		return httpx.Response(404, json={"error": {"message": "not found"}})

	def sync_client(self):
		client = SpeechWeave(api_key="sk_test", base_url="https://api.example.test/v1")
		client._client = httpx.Client(transport=httpx.MockTransport(self.handler))
		return client

	def async_client(self):
		client = AsyncSpeechWeave(api_key="sk_test", base_url="https://api.example.test/v1")
		client._client = httpx.AsyncClient(transport=httpx.MockTransport(self.handler))
		return client


URL = "https://example.com/a.mp3"


def test_failed_job_returns_status_error_instead_of_raising():
	brain = FakeBrain("failed", error="bad audio")
	client = brain.sync_client()
	done = client.transcripts.transcribe(URL)
	assert done["status"] == "error"
	assert done["error"] == "bad audio"
	assert client.transcripts.get_by_id("job_1")["status"] == "error"
	assert client.transcripts.wait_for_completion("job_1")["status"] == "error"


def test_cancelled_job_has_a_clear_error():
	got = FakeBrain("cancelled").sync_client().transcripts.get_by_id("job_1")
	assert got["status"] == "error"
	assert got["error"] == "Transcription was cancelled"


def test_export_subtitles_and_format_validation():
	client = FakeBrain().sync_client()
	assert "-->" in client.transcripts.export_subtitles_srt("job_1", 32)
	with pytest.raises(SpeechWeaveError):
		from speechweave.namespaces.assembly_compat import _subtitle_format

		_subtitle_format("ass")


def test_list_transcripts_shapes_a_page_and_maps_error_status():
	brain = FakeBrain()
	page = brain.sync_client().transcripts.list_transcripts({"limit": 2, "status": "error"})
	assert brain.requests[0].url.params["status"] == "failed"
	assert page["page_details"]["prev_url"] is None
	assert "page=2" in page["page_details"]["next_url"]
	assert page["transcripts"][0]["status"] == "completed"
	assert page["transcripts"][1]["status"] == "error"
	assert page["transcripts"][1]["error"] == "Transcription was cancelled"


def test_list_transcripts_refuses_cursors_before_any_request():
	brain = FakeBrain()
	with pytest.raises(SpeechWeaveError) as err:
		brain.sync_client().transcripts.list_transcripts({"after_id": "x"})
	assert err.value.code == "UNSUPPORTED_OPTION"
	assert err.value.param == "after_id"
	assert brain.requests == []


def test_get_sentences_and_paragraphs_in_milliseconds():
	client = FakeBrain().sync_client()
	sentences = client.transcripts.get_sentences("job_1")
	assert sentences["id"] == "job_1"
	assert sentences["audio_duration"] == 4
	assert [s["start"] for s in sentences["sentences"]] == [0, 3000]
	assert len(client.transcripts.get_paragraphs("job_1")["paragraphs"]) == 2


def test_get_sentences_on_unfinished_transcript_is_409():
	with pytest.raises(SpeechWeaveError) as err:
		FakeBrain("processing").sync_client().transcripts.get_sentences("job_1")
	assert err.value.status == 409


def test_language_detection_with_language_code_is_400_before_any_request():
	brain = FakeBrain()
	with pytest.raises(SpeechWeaveError) as err:
		brain.sync_client().transcripts.transcribe(URL, {"language_detection": True, "language_code": "en"})
	assert err.value.status == 400
	assert err.value.param == "language_detection"
	assert brain.requests == []


def test_language_detection_alone_reports_language_code():
	out = FakeBrain().sync_client().transcripts.transcribe(URL, {"language_detection": True})
	assert out["language_code"] == "en"


def test_assembly_sends_exact_vocabulary_prompt_and_applies_custom_spelling():
	brain = FakeBrain()
	out = brain.sync_client().transcripts.transcribe(
		URL,
		{
			"keyterms_prompt": ["Kubernetes"],
			"word_boost": ["Zod"],
			"custom_spelling": [{"from": ["country"], "to": "nation"}],
		},
	)
	assert brain.created[0]["prompt"] == "Vocabulary: Kubernetes, Zod."
	assert "your nation can do" in out["text"]


def test_bad_custom_spelling_fails_before_any_request():
	brain = FakeBrain()
	with pytest.raises(SpeechWeaveError) as err:
		brain.sync_client().transcripts.transcribe(URL, {"custom_spelling": [{"from": "x", "to": "y"}]})
	assert err.value.param == "custom_spelling"
	assert brain.requests == []


def test_deepgram_options_end_to_end():
	brain = FakeBrain()
	out = brain.sync_client().listen.v1.media.transcribe_url(
		url=URL,
		keyterm=["Kubernetes"],
		keywords=["Zod:2"],
		detect_language=True,
		search=["country"],
		profanity_filter=True,
		paragraphs=True,
	)
	assert brain.created[0]["prompt"] == "Vocabulary: Kubernetes, Zod."
	channel = out["results"]["channels"][0]
	assert channel["detected_language"] == "en"
	assert len(channel["search"][0]["hits"]) == 1
	assert len(channel["alternatives"][0]["paragraphs"]["paragraphs"]) == 2


def test_deepgram_bad_replace_fails_before_any_request():
	brain = FakeBrain()
	with pytest.raises(SpeechWeaveError, match="find:replace"):
		brain.sync_client().listen.v1.media.transcribe_url(url=URL, replace="nocolon")
	assert brain.requests == []


def test_deepgram_unknown_option_still_unsupported():
	with pytest.raises(SpeechWeaveError) as err:
		FakeBrain().sync_client().listen.v1.media.transcribe_url(url=URL, diarize=True)
	assert err.value.code == "UNSUPPORTED_OPTION"


@pytest.mark.asyncio
async def test_async_namespace_matches_sync_behaviour():
	brain = FakeBrain("failed", error="bad audio")
	async with brain.async_client() as client:
		done = await client.transcripts.transcribe(URL, {"keyterms_prompt": ["Zod"]})
		assert done["status"] == "error"
		assert brain.created[0]["prompt"] == "Vocabulary: Zod."
	ok = FakeBrain()
	async with ok.async_client() as client:
		assert "-->" in await client.transcripts.export_subtitles_srt("job_1")
		assert "-->" in await client.transcripts.export_subtitles_srt("job_1", 10)
		page = await client.transcripts.list_transcripts({"limit": 2})
		assert page["transcripts"][1]["status"] == "error"
		sentences = await client.transcripts.get_sentences("job_1")
		assert [s["start"] for s in sentences["sentences"]] == [0, 3000]
		with pytest.raises(SpeechWeaveError):
			await client.transcripts.list_transcripts({"before_id": "x"})
		out = await client.listen.v1.media.transcribe_url(url=URL, search="country", detect_language=True)
		assert out["results"]["channels"][0]["detected_language"] == "en"
