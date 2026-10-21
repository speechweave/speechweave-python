"""
Pure text helpers for the Deepgram-style and AssemblyAI-style helpers: sentence and paragraph
building, keyword search, find and replace, profanity masking, and vocabulary prompts.
Nothing here touches the network. Times are seconds. Vendor layers convert as needed.

Words are dicts with `word`, `start` and `end`, as in the verbose transcript.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from importlib import resources
from typing import Any

from speechweave.errors import SpeechWeaveError

# A new paragraph starts when the silence between two sentences is longer than this.
PARAGRAPH_GAP_SECONDS = 0.8
# A paragraph holds at most this many sentences.
PARAGRAPH_MAX_SENTENCES = 5
# Upper bound for the vocabulary list in the prompt (the model reads roughly 224 tokens of prompt).
VOCABULARY_PROMPT_MAX_CHARS = 600
# Words on each side of a search hit that go into its snippet.
SEARCH_SNIPPET_CONTEXT_WORDS = 3

_ABBREVIATIONS = frozenset(
	["mr.", "mrs.", "ms.", "dr.", "prof.", "sr.", "jr.", "st.", "vs.", "inc.", "ltd.", "co.", "mt."]
)
_CLOSERS = re.compile(r"[\"'”’)\]]+$")
_OPENERS = re.compile(r"^[\"'“‘(\[]+")
_ENDS_WITH_STOP = re.compile(r"[.?!][\"'”’)\]]*$")
_EDGE = re.compile(r"^(\W*)(.*?)(\W*)$", re.S)


def _load_profanity() -> list[str]:

	raw = resources.files("speechweave").joinpath("data/profanity_en.json").read_text(encoding="utf-8")

	return [str(w) for w in json.loads(raw)]


PROFANITY_EN = _load_profanity()


def invalid(message: str, param: str, code: str = "INVALID_OPTION") -> SpeechWeaveError:

	return SpeechWeaveError(message, 400, code, error_type="invalid_request_error", param=param)


# ---------------------------------------------------------------------------------------------
# Sentences and paragraphs
# ---------------------------------------------------------------------------------------------


def _unquote(token: str) -> str:

	return _OPENERS.sub("", _CLOSERS.sub("", token.strip()))


def _ends_sentence(token: str) -> bool:
	"""True when the token closes a sentence: it ends in . ? or !, and is not a likely abbreviation."""

	t = token.strip()
	if not _ENDS_WITH_STOP.search(t):
		return False
	bare = _unquote(t)
	if bare.endswith(("?", "!")):
		return True
	# A single capital letter and a period is an initial ("J."), not the end of a sentence.
	if re.fullmatch(r"[A-Z]\.", bare) or bare.lower() in _ABBREVIATIONS:
		return False

	return True


def _num(value: Any) -> float:

	try:
		return float(value)
	except (TypeError, ValueError):
		return 0.0


def build_sentences(
	words: Sequence[Mapping[str, Any]] | None = None,
	segments: Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
	"""
	Splits a transcript into sentences. With word timing, a word that ends in . ? or ! closes a
	sentence. Without words, each segment's text is split the same way, the first sentence starts at
	the segment start and the last ends at the segment end, and interior boundaries are ESTIMATED in
	proportion to character count. With neither words nor segments there is no timing, so the
	result is empty.
	"""

	words = words or []
	segments = segments or []
	out: list[dict[str, Any]] = []

	if words:
		current: list[dict[str, Any]] = []

		def flush() -> None:
			nonlocal current
			if not current:
				return
			out.append(
				{
					"text": " ".join(w["word"] for w in current),
					"start": current[0]["start"],
					"end": current[-1]["end"],
					"words": current,
				}
			)
			current = []

		for w in words:
			token = str(w.get("word") or "").strip()
			if not token:
				continue
			current.append({"word": token, "start": _num(w.get("start")), "end": _num(w.get("end"))})
			if _ends_sentence(token):
				flush()
		flush()

		return out

	for seg in segments:
		tokens = str(seg.get("text") or "").strip().split()
		groups: list[list[str]] = []
		group: list[str] = []
		for token in tokens:
			group.append(token)
			if _ends_sentence(token):
				groups.append(group)
				group = []
		if group:
			groups.append(group)
		start = _num(seg.get("start"))
		end = _num(seg.get("end"))
		total = sum(len(" ".join(g)) for g in groups) or 1
		cursor = start
		used = 0
		for i, g in enumerate(groups):
			used += len(" ".join(g))
			nxt = end if i == len(groups) - 1 else start + ((end - start) * used) / total
			out.append({"text": " ".join(g), "start": cursor, "end": nxt, "words": []})
			cursor = nxt

	return out


def build_paragraphs(sentences: list[dict[str, Any]]) -> list[dict[str, Any]]:
	"""Groups sentences into paragraphs on a long gap or after PARAGRAPH_MAX_SENTENCES sentences."""

	out: list[dict[str, Any]] = []
	current: list[dict[str, Any]] = []

	def flush() -> None:
		nonlocal current
		if not current:
			return
		out.append({"sentences": current, "start": current[0]["start"], "end": current[-1]["end"]})
		current = []

	for s in sentences:
		if current:
			prev = current[-1]
			if s["start"] - prev["end"] > PARAGRAPH_GAP_SECONDS or len(current) >= PARAGRAPH_MAX_SENTENCES:
				flush()
		current.append(s)
	flush()

	return out


def count_words(text: str) -> int:

	return len(text.split())


# ---------------------------------------------------------------------------------------------
# Find and replace, profanity masking
# ---------------------------------------------------------------------------------------------


@dataclass
class TextRule:
	# Phrases to find (case-insensitive, whole words).
	from_: list[str]
	# Replacement text, or a function of the matched text.
	to: str | Callable[[str], str]


def _phrase_regex(phrases: list[str]) -> re.Pattern[str] | None:

	parts = [r"\s+".join(re.escape(t) for t in p.split()) for p in phrases if p.strip()]
	parts.sort(key=len, reverse=True)
	if not parts:
		return None

	return re.compile(rf"(?<!\w)(?:{'|'.join(parts)})(?!\w)", re.IGNORECASE)


def _replacer(rule: TextRule) -> Callable[[str], str]:

	to = rule.to

	return to if callable(to) else (lambda _matched: to)


def rewrite_text(text: str, rules: list[TextRule]) -> str:
	"""Applies each rule in order to a string."""

	out = text
	for rule in rules:
		pattern = _phrase_regex(rule.from_)
		if pattern is not None:
			fn = _replacer(rule)
			out = pattern.sub(lambda m: fn(m.group(0)), out)

	return out


def _edges(token: str) -> tuple[str, str, str]:

	m = _EDGE.match(token)

	return (m.group(1), m.group(2), m.group(3)) if m else ("", token, "")


def rewrite_words(words: list[dict[str, Any]], rules: list[TextRule]) -> list[dict[str, Any]]:
	"""
	Applies rules to timed words without touching timestamps. A single-word phrase rewrites the
	word in place. A multi-word phrase becomes one word spanning the first start to the last end.
	"""

	out = words
	for rule in rules:
		single = [p for p in rule.from_ if len(p.split()) == 1]
		multi = sorted((p.split() for p in rule.from_ if len(p.split()) > 1), key=len, reverse=True)
		pattern = _phrase_regex(single)
		fn = _replacer(rule)
		nxt: list[dict[str, Any]] = []
		i = 0
		while i < len(out):
			consumed = 0
			for phrase in multi:
				if i + len(phrase) > len(out):
					continue
				if all(_edges(out[i + k]["word"])[1].lower() == p.lower() for k, p in enumerate(phrase)):
					first = _edges(out[i]["word"])
					last = _edges(out[i + len(phrase) - 1]["word"])
					matched = " ".join(_edges(out[i + k]["word"])[1] for k in range(len(phrase)))
					nxt.append(
						{
							**out[i],
							"word": first[0] + fn(matched) + last[2],
							"start": out[i]["start"],
							"end": out[i + len(phrase) - 1]["end"],
						}
					)
					consumed = len(phrase)
					break
			if consumed:
				i += consumed
				continue
			word = out[i]
			if pattern is not None:
				word = {**word, "word": pattern.sub(lambda m: fn(m.group(0)), word["word"])}
			nxt.append(word)
			i += 1
		out = nxt

	return out


def mask_word(word: str) -> str:
	"""First letter plus asterisks, so the length is kept ("shit" becomes "s***")."""

	return word if len(word) <= 1 else word[0] + "*" * (len(word) - 1)


def profanity_rule() -> TextRule:
	"""English only: the list is not translated, so other languages are not masked."""

	return TextRule(list(PROFANITY_EN), mask_word)


def parse_deepgram_replace(value: Any) -> list[TextRule]:
	"""Parses Deepgram `replace` values ("find:replace", one or a list). The first colon splits."""

	items = [] if value is None else value if isinstance(value, (list, tuple)) else [value]
	rules: list[TextRule] = []
	for item in items:
		s = str(item)
		at = s.find(":")
		if at <= 0:
			raise invalid(f'replace entries must look like "find:replace", got "{s}"', "replace")
		rules.append(TextRule([s[:at]], s[at + 1 :]))

	return rules


def parse_custom_spelling(value: Any) -> list[TextRule]:
	"""Parses AssemblyAI `custom_spelling`: [{"from": ["x", "y"], "to": "z"}]."""

	if value is None:
		return []
	if not isinstance(value, (list, tuple)):
		raise invalid('custom_spelling must be a list of {"from": [...], "to": "..."}', "custom_spelling")
	rules: list[TextRule] = []
	for entry in value:
		from_ = entry.get("from") if isinstance(entry, Mapping) else None
		to = entry.get("to") if isinstance(entry, Mapping) else None
		if (
			not isinstance(from_, (list, tuple))
			or not from_
			or not isinstance(to, str)
			or any(not isinstance(f, str) or not f.strip() for f in from_)
		):
			raise invalid(
				'Each custom_spelling entry needs a non-empty "from" list of strings and a string "to"',
				"custom_spelling",
			)
		if any(len(f.split()) > 5 for f in from_):
			raise invalid('custom_spelling "from" entries can have at most 5 words', "custom_spelling")
		rules.append(TextRule(list(from_), to))

	return rules


def build_rewrite_rules(custom: list[TextRule], filter_profanity: Any) -> list[TextRule]:
	"""Custom rules first, then profanity masking."""

	return [*custom, profanity_rule()] if filter_profanity else custom


# ---------------------------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------------------------


def _normalize_token(token: str) -> str:

	return _edges(str(token))[1].lower()


def search_words(
	words: Sequence[Mapping[str, Any]],
	queries: list[str],
	confidence_for: Callable[[Mapping[str, Any]], float | None],
) -> list[dict[str, Any]]:
	"""
	Whole-word, case-insensitive search over timed words, ignoring punctuation. A multi-word query
	matches consecutive words. A query with no hits still appears with an empty list.
	`confidence_for` returns the estimated confidence of a word or None, in which case it is left out.
	"""

	norm = [_normalize_token(w.get("word", "")) for w in words]
	results: list[dict[str, Any]] = []
	for query in queries:
		q = [t for t in (_normalize_token(p) for p in query.split()) if t]
		hits: list[dict[str, Any]] = []
		i = 0
		while q and i + len(q) <= len(words):
			if any(norm[i + k] != t for k, t in enumerate(q)):
				i += 1
				continue
			matched = words[i : i + len(q)]
			lo = max(0, i - SEARCH_SNIPPET_CONTEXT_WORDS)
			hi = min(len(words), i + len(q) + SEARCH_SNIPPET_CONTEXT_WORDS)
			hit: dict[str, Any] = {
				"start": matched[0].get("start"),
				"end": matched[-1].get("end"),
				"snippet": " ".join(str(w.get("word", "")).strip() for w in words[lo:hi]),
			}
			scores = [c for c in (confidence_for(w) for w in matched) if c is not None]
			if scores:
				hit["confidence"] = round(sum(scores) / len(scores), 4)
			hits.append(hit)
			i += len(q)
		results.append({"query": query, "hits": hits})

	return results


# ---------------------------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------------------------


def _to_list(value: Any) -> list[str]:

	if value is None:
		return []
	items = value if isinstance(value, (list, tuple)) else [value]

	return [s for s in (str(v).strip() for v in items) if s]


def deepgram_vocabulary_terms(keyterm: Any, keywords: Any) -> list[str]:
	"""Deepgram `keyterm` plus `keywords` (entries are "word" or "word:boost", and the boost is dropped)."""

	boosted = [re.sub(r":-?\d+(\.\d+)?$", "", k).strip() for k in _to_list(keywords)]

	return [t for t in [*_to_list(keyterm), *boosted] if t]


def assembly_vocabulary_terms(keyterms_prompt: Any, word_boost: Any) -> list[str]:
	"""AssemblyAI `keyterms_prompt` plus `word_boost`."""

	return [*_to_list(keyterms_prompt), *_to_list(word_boost)]


def build_vocabulary_prompt(terms: list[str], base_prompt: str | None = None) -> str | None:
	"""
	Builds the model prompt for a vocabulary list: "Vocabulary: a, b, c." The prompt BIASES the
	transcript toward these terms. It does not guarantee them and is weaker than a vendor's
	keyword boosting. Terms are kept whole and in order (earlier terms win), duplicates dropped,
	and the list stops before VOCABULARY_PROMPT_MAX_CHARS. A caller prompt, if any, comes first.
	"""

	seen: set[str] = set()
	kept: list[str] = []
	prefix = "Vocabulary: "
	length = len(prefix) + 1
	for term in terms:
		key = term.lower()
		if key in seen:
			continue
		added = len(term) + (2 if kept else 0)
		if length + added > VOCABULARY_PROMPT_MAX_CHARS:
			break
		seen.add(key)
		kept.append(term)
		length += added
	vocabulary = f"{prefix}{', '.join(kept)}." if kept else None
	base = (base_prompt or "").strip()
	if not vocabulary:
		return base or None

	return f"{base} {vocabulary}" if base else vocabulary
