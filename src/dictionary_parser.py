# src/dictionary_parser.py
import re
from typing import List, Optional, Dict
from .config import logger, ENTRY_PATTERN

DIVIDER = "-" * 45
PROPER_MARK = "-----DICTIONARY PROPER-----"

# Lines that belong to an entry but are not its "term (pos) - definition" line.
META_PREFIXES = ('etymology:', 'ex:', 'example:', 'examples:', 'derived terms:',
                 'notes:', 'pronunciation:', 'synonym:', 'synonyms:', 'antonym:',
                 'antonyms:', '- ')


def sort_key_ignore_punct(s: str) -> str:
    """Strips leading punctuation, handles articles, returns lowercase remaining string for sorting."""
    term = s.split(' (')[0] if ' (' in s else s
    term = term.lstrip(" '-\"")
    if term.lower().startswith('the '):
        term = term[4:] + ', the'
    return term.lower()


def _is_meta_line(line: str) -> bool:
    low = line.strip().lower()
    return low.startswith(META_PREFIXES) or bool(re.match(r'^\d+\.\s', low))


def _one_line(text: str) -> str:
    return re.sub(r'\s+', ' ', text or '').strip()


# ---------------------------------------------------------------------------
# On-disk format (written by the bot and by the wiki editor)
#
#   one pos, one sense, nothing extra  ->  term (n.) - definition
#   anything richer                    ->  a block between two 45-hyphen lines:
#       term (n.) - 1. first sense
#       - Example: sentence
#       2. second sense
#       term (v.) - definition of the next part of speech
#       Etymology: ...
#       Pronunciation: /.../
#
# `sections` is a list like:
#   [{"pos": "n.", "defs": [{"text": "...", "example": "..."}]}]
# ---------------------------------------------------------------------------
def format_entry(term: str, sections: List[Dict], etymology: Optional[str] = None,
                 pronunciation: Optional[str] = None) -> str:
    term = _one_line(term)
    secs = []
    for s in sections:
        defs = [{"text": _one_line(d.get("text", "")), "example": _one_line(d.get("example", ""))}
                for d in s.get("defs", []) if _one_line(d.get("text", ""))]
        if defs:
            secs.append({"pos": _one_line(s.get("pos", "")) or "n.", "defs": defs})
    etymology = _one_line(etymology or "")
    pron = _one_line(pronunciation or "")
    if pron and not (pron.startswith('/') and pron.endswith('/')):
        pron = f"/{pron.strip('/')}/"

    if (len(secs) == 1 and len(secs[0]["defs"]) == 1
            and not secs[0]["defs"][0]["example"] and not etymology and not pron):
        return f"{term} ({secs[0]['pos']}) - {secs[0]['defs'][0]['text']}"

    lines = [DIVIDER]
    for s in secs:
        numbered = len(s["defs"]) > 1
        for i, d in enumerate(s["defs"]):
            if i == 0:
                lines.append(f"{term} ({s['pos']}) - {'1. ' if numbered else ''}{d['text']}")
            else:
                lines.append(f"{i + 1}. {d['text']}")
            if d["example"]:
                lines.append(f"- Example: {d['example']}")
    if etymology:
        lines.append(f"Etymology: {etymology}")
    if pron:
        lines.append(f"Pronunciation: {pron}")
    lines.append(DIVIDER)
    return "\n".join(lines)


class DictionaryEntry:
    """Represents a single dictionary entry."""
    def __init__(self, term: str, pos: str, definition: str, etymology: Optional[str] = None,
                 examples: Optional[List[str]] = None, raw_content: Optional[str] = None,
                 pronunciation: Optional[str] = None, additional_info: Optional[List[str]] = None,
                 derived_terms: Optional[str] = None, original_block: Optional[str] = None,
                 sections: Optional[List[Dict]] = None):
        self.term = term
        self.pos = pos
        self.definition = definition
        self.etymology = etymology
        self.examples = examples or []
        self.raw_content = raw_content
        self.pronunciation = pronunciation
        self.additional_info = additional_info or []
        self.derived_terms = derived_terms
        self.original_block = original_block
        self.sections = sections or [{"pos": pos, "defs": [{"text": definition, "example": ""}]}]

    def to_string(self) -> str:
        if self.original_block:
            return self.original_block
        return format_entry(self.term, self.sections, self.etymology, self.pronunciation)


def _clean_term(raw_term: str) -> str:
    term = re.sub(r'/[^/]+/', '', raw_term)
    term = re.sub(r'\(pronounced:\s*[^)]+\)', '', term, flags=re.IGNORECASE)
    term = re.sub(r'\[[^\]]+\]', '', term)
    return term.strip()


def extract_term_from_line(line: str) -> Optional[str]:
    """Extract just the term name for sorting and duplicate checks."""
    line = line.strip()
    match = re.match(r'^([^(]+?)\s*(\([^)]*\))?\s*\(([^)]+)\)\s*-\s*(.+)$', line)
    if match:
        return _clean_term(match.group(1))
    if ' (' in line and ') - ' in line:
        parts = line.split(' (', 1)
        if len(parts) == 2:
            return _clean_term(parts[0])
    return None


def extract_term_from_entry_block(content: str) -> Optional[str]:
    """Extract the main term from an entry block for indexing."""
    for line in content.strip().split('\n'):
        line = line.strip()
        if not line or _is_meta_line(line):
            continue
        term = extract_term_from_line(line)
        if term:
            return term
    return None


def parse_dictionary_entries_conservative(content: str) -> List[DictionaryEntry]:
    """Read the dictionary line by line: one entry per distinct word, so a word
    with several parts of speech (several 'term (pos) - ...' lines) counts once."""
    entries: List[DictionaryEntry] = []
    if PROPER_MARK not in content:
        return entries
    body = content.split(PROPER_MARK, 1)[1]

    in_block = False
    block: List[str] = []

    def flush(block_lines):
        seen = set()
        for bl in block_lines:
            if not bl or _is_meta_line(bl) or not re.match(ENTRY_PATTERN, bl):
                continue
            term = extract_term_from_line(bl)
            if term and term.lower() not in seen:
                seen.add(term.lower())
                entries.append(DictionaryEntry(term=term, pos="n", definition="",
                                               original_block="\n".join(block_lines)))
        if not seen:
            entries.append(DictionaryEntry(term="UNKNOWN", pos="n", definition="",
                                           original_block="\n".join(block_lines)))

    for raw in body.split('\n'):
        line = raw.strip()
        if re.match(r'^-{20,}$', line):
            if in_block:
                flush(block)
                block, in_block = [], False
            else:
                in_block, block = True, []
            continue
        if in_block:
            block.append(line)
        elif line and not _is_meta_line(line) and re.match(ENTRY_PATTERN, line):
            term = extract_term_from_line(line)
            if term:
                entries.append(DictionaryEntry(term=term, pos="n", definition="", original_block=line))
    if in_block and block:
        flush(block)
    return entries


def get_corpus_from_content(content: str) -> List[str]:
    """Extract corpus terms from dictionary content (older files only)."""
    corpus_match = re.search(r"Corpus:\s*(.*?)\s*-----DICTIONARY PROPER-----", content, re.DOTALL | re.IGNORECASE)
    if corpus_match:
        corpus_text = corpus_match.group(1).strip()
        return [t.strip() for t in corpus_text.split(",") if t.strip()]
    return []


def count_dictionary_entries(content: str) -> int:
    return len(parse_dictionary_entries_conservative(content))


# ---------------------------------------------------------------------------
# Discord message syntax
#
#   word /ipa/ (n.) - first meaning          <- first line (pronunciation optional)
#   + another meaning of the same part of speech      (or "2. another meaning")
#   Ex: an example sentence for the meaning just above it
#   (v.) - a meaning as a different part of speech    (starts a new section)
#   Etymology: where the word came from
#   Pron: /ipa/
#
# Plain "word (pos) - definition" still works exactly as before.
# ---------------------------------------------------------------------------
def parse_message_as_entry(content: str) -> Optional[DictionaryEntry]:
    lines = [l.strip() for l in content.replace('\r', '').split('\n') if l.strip()]
    term = None
    pronunciation = None
    etymology: List[str] = []
    sections: List[Dict] = []
    cur = None
    sense = None
    last = None

    for line in lines:
        m = re.match(r'^etymology:\s*(.*)$', line, re.IGNORECASE)
        if m:
            etymology.append(m.group(1).strip()); last = 'ety'; continue
        m = re.match(r'^(?:pronunciation|pron):\s*(.*)$', line, re.IGNORECASE)
        if m:
            pronunciation = m.group(1).strip(); last = 'pron'; continue
        m = re.match(r'^(?:-\s*)?(?:examples?|ex):\s*(.*)$', line, re.IGNORECASE)
        if m:
            if sense is not None:
                sense["example"] = (sense["example"] + "; " if sense["example"] else "") + m.group(1).strip()
                last = 'ex'
            continue

        if term is None:
            m = re.match(ENTRY_PATTERN, line)
            if not m:
                continue
            raw_term, pos, definition = m.groups()
            phon = re.search(r'/[^/]+/', raw_term)
            if phon:
                pronunciation = pronunciation or phon.group(0)
            pm = re.search(r'\(pronounced:\s*([^)]+)\)', raw_term, re.IGNORECASE)
            if pm and not pronunciation:
                pronunciation = f"/{pm.group(1)}/"
            term = _clean_term(raw_term)
            cur = {"pos": pos.strip(), "defs": []}
            sense = {"text": definition.strip(), "example": ""}
            cur["defs"].append(sense); sections.append(cur); last = 'def'
            continue

        m = re.match(r'^\(([^()]+)\)\s*-\s*(.+)$', line)
        if m:
            cur = {"pos": m.group(1).strip(), "defs": []}
            sense = {"text": m.group(2).strip(), "example": ""}
            cur["defs"].append(sense); sections.append(cur); last = 'def'
            continue
        m = re.match(ENTRY_PATTERN, line)
        if m and _clean_term(m.group(1)).lower() == term.lower():
            cur = {"pos": m.group(2).strip(), "defs": []}
            sense = {"text": m.group(3).strip(), "example": ""}
            cur["defs"].append(sense); sections.append(cur); last = 'def'
            continue
        m = re.match(r'^(?:\+|\d+[.)])\s+(.+)$', line)
        if m and cur is not None:
            sense = {"text": m.group(1).strip(), "example": ""}
            cur["defs"].append(sense); last = 'def'
            continue

        # Anything else continues whatever came just before it.
        if last == 'ety' and etymology:
            etymology[-1] += " " + line
        elif last == 'ex' and sense is not None:
            sense["example"] += " " + line
        elif sense is not None:
            sense["text"] += " " + line

    if term is None or not sections:
        return None

    first = sections[0]["defs"][0]
    return DictionaryEntry(
        term=term, pos=sections[0]["pos"], definition=first["text"],
        etymology=_one_line(" ".join(etymology)) or None,
        pronunciation=pronunciation or None,
        sections=sections,
    )


# Keep the old function names for compatibility
def parse_dictionary_entries(content: str) -> List[DictionaryEntry]:
    return parse_dictionary_entries_conservative(content)
