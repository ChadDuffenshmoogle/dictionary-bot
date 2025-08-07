import re
from typing import List, Optional
from .config import ENTRY_PATTERN # Import from config

def sort_key_ignore_punct(s: str) -> str:
    """Strips leading punctuation, returns lowercase remaining string for sorting."""
    term = s.split(' (')[0] if ' (' in s else s
    return term.lstrip(" '-\"").lower()

class DictionaryEntry:
    """Represents a single dictionary entry."""
    def __init__(self, term: str, pos: str, definition: str, etymology: Optional[str] = None, examples: Optional[List[str]] = None, raw_content: Optional[str] = None):
        self.term = term
        self.pos = pos
        self.definition = definition
        self.etymology = etymology
        self.examples = examples or []
        self.raw_content = raw_content

    def to_string(self) -> str:
        """Converts the entry to its string format for file output."""
        if self.raw_content and not self.etymology and not self.examples:
            return self.raw_content.strip()

        if self.etymology or self.examples:
            result = "---------------------------------------------\n"
            if self.etymology:
                result += f"Etymology: {self.etymology}\n\n"
            result += f"{self.term} ({self.pos}) - {self.definition}"
            if self.examples:
                for example in self.examples:
                    result += f"\n{example}"
            result += "\n---------------------------------------------"
            return result
        else:
            return f"{self.term} ({self.pos}) - {self.definition}"

def parse_dictionary_entries(content: str) -> List[DictionaryEntry]:
    """Parses dictionary content into DictionaryEntry objects."""
    entries = []

    if "-----DICTIONARY PROPER-----" not in content:
        # logger.warning("No dictionary proper section found") # Logger needs to be passed or imported from config
        return entries

    parts = content.split("-----DICTIONARY PROPER-----\n\n", 1)
    if len(parts) < 2:
        return entries

    body = parts[1]
    raw_sections = body.split('\n\n')

    i = 0
    while i < len(raw_sections):
        section = raw_sections[i].strip()

        if not section:
            i += 1
            continue

        # Handle complex entries with separators
        if section.strip() == "---------------------------------------------":
            complex_entry_parts = [section]
            i += 1

            while i < len(raw_sections):
                part = raw_sections[i].strip()
                complex_entry_parts.append(part)

                if part == "---------------------------------------------":
                    break
                i += 1

            full_text = '\n\n'.join(complex_entry_parts)
            entry = parse_complex_entry(full_text)
            if entry:
                entries.append(entry)

        else:
            # Handle simple entries
            match = re.match(ENTRY_PATTERN, section)
            if match:
                term, pos, definition = match.groups()
                entries.append(DictionaryEntry(term, pos, definition, raw_content=section))
            else:
                # Multi-line simple entry
                lines = section.split('\n')
                for line in lines:
                    match = re.match(ENTRY_PATTERN, line.strip())
                    if match:
                        term, pos, definition = match.groups()
                        entries.append(DictionaryEntry(term, pos, definition, raw_content=section))
                        break

        i += 1

    # logger.info(f"Parsed {len(entries)} dictionary entries") # Logger needs to be passed or imported from config
    return entries

def parse_complex_entry(text: str) -> Optional[DictionaryEntry]:
    """Parses a complex entry with etymology and/or examples."""
    lines = text.split('\n')
    etymology = None
    term = pos = definition = None
    examples = []
    etymology_lines = []
    collecting_etymology = False

    for line in lines:
        line_stripped = line.strip()

        if line_stripped == "---------------------------------------------":
            continue

        if line_stripped.startswith("Etymology:"):
            collecting_etymology = True
            ety_text = line_stripped[10:].strip()
            etymology_lines = [ety_text] if ety_text else []
            continue

        if collecting_etymology and line_stripped and not re.match(ENTRY_PATTERN, line_stripped):
            etymology_lines.append(line.rstrip())
            continue

        match = re.match(ENTRY_PATTERN, line_stripped)
        if match:
            if collecting_etymology and etymology_lines:
                etymology = '\n'.join(etymology_lines).strip()
                collecting_etymology = False

            term, pos, definition = match.groups()
            continue

        if term and line_stripped and not line_stripped.startswith("-----"):
            examples.append(line.rstrip())

    if collecting_etymology and etymology_lines:
        etymology = '\n'.join(etymology_lines).strip()

    if term and pos and definition:
        return DictionaryEntry(term, pos, definition, etymology, examples, text)

    return None

def get_corpus_from_content(content: str) -> List[str]:
    """Extracts corpus terms from dictionary content."""
    corpus_match = re.search(r"Corpus:\s*(.*?)\s*-----DICTIONARY PROPER-----", content, re.DOTALL | re.IGNORECASE)
    if corpus_match:
        corpus_text = corpus_match.group(1).strip()
        return [t.strip() for t in corpus_text.split(",") if t.strip()]
    return []
