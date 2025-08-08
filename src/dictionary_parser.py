# src/dictionary_parser.py
import re
from typing import List, Optional
from .config import ENTRY_PATTERN # Import from config with relative import

def sort_key_ignore_punct(s: str) -> str:
    """Strips leading punctuation, returns lowercase remaining string for sorting."""
    term = s.split(' (')[0] if ' (' in s else s
    return term.lstrip(" '-\"").lower()

class DictionaryEntry:
    """Represents a single dictionary entry."""
    def __init__(self, term: str, pos: str, definition: str, etymology: Optional[str] = None, examples: Optional[List[str]] = None, raw_content: Optional[str] = None, pronunciation: Optional[str] = None, additional_info: Optional[List[str]] = None):
        self.term = term
        self.pos = pos
        self.definition = definition
        self.etymology = etymology
        self.examples = examples or []
        self.raw_content = raw_content
        self.pronunciation = pronunciation
        self.additional_info = additional_info or []

    def to_string(self) -> str:
        """Converts the entry to its string format for file output using consistent formatting."""
        # If this is a simple entry with no additional details, keep it on one line
        if (not self.etymology and not self.examples and not self.pronunciation and 
            not self.additional_info and self.raw_content and 
            '\n' not in self.raw_content.strip()):
            return self.raw_content.strip()

        # Check if this entry needs the hyphen format (has additional details)
        needs_hyphens = (self.etymology or self.examples or self.pronunciation or 
                        self.additional_info or (self.raw_content and '\n' in self.raw_content))

        if needs_hyphens:
            result = "---------------------------------------------\n"
            
            # Add etymology if present
            if self.etymology:
                result += f"Etymology: {self.etymology}\n\n"
            
            # Main entry line with pronunciation if present
            main_line = f"{self.term}"
            if self.pronunciation:
                main_line += f" {self.pronunciation}"
            main_line += f" ({self.pos}) - {self.definition}"
            result += main_line
            
            # Add additional info if present
            if self.additional_info:
                for info in self.additional_info:
                    result += f"\n{info}"
            
            # Add examples if present
            if self.examples:
                for example in self.examples:
                    result += f"\n{example}"
            
            result += "\n---------------------------------------------"
            return result
        else:
            # Simple one-line entry
            main_line = f"{self.term}"
            if self.pronunciation:
                main_line += f" {self.pronunciation}"
            main_line += f" ({self.pos}) - {self.definition}"
            return main_line

def parse_dictionary_entries(content: str) -> List[DictionaryEntry]:
    """Parses dictionary content into DictionaryEntry objects using consistent formatting."""
    entries = []

    if "-----DICTIONARY PROPER-----" not in content:
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

        # Handle complex entries with separators (consistent hyphen format)
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
                # Check for pronunciation in the term part
                pronunciation = None
                if ' /' in term and '/ ' in term:
                    term_parts = term.split(' /')
                    if len(term_parts) == 2:
                        actual_term = term_parts[0].strip()
                        pron_part = '/' + term_parts[1]
                        if pron_part.endswith('/'):
                            pronunciation = pron_part
                            term = actual_term
                
                entries.append(DictionaryEntry(term, pos, definition, raw_content=section, pronunciation=pronunciation))
            else:
                # Multi-line simple entry
                lines = section.split('\n')
                for line in lines:
                    match = re.match(ENTRY_PATTERN, line.strip())
                    if match:
                        term, pos, definition = match.groups()
                        # Check for pronunciation
                        pronunciation = None
                        if ' /' in term and '/ ' in term:
                            term_parts = term.split(' /')
                            if len(term_parts) == 2:
                                actual_term = term_parts[0].strip()
                                pron_part = '/' + term_parts[1]
                                if pron_part.endswith('/'):
                                    pronunciation = pron_part
                                    term = actual_term
                        
                        entries.append(DictionaryEntry(term, pos, definition, raw_content=section, pronunciation=pronunciation))
                        break

        i += 1

    return entries

def parse_complex_entry(text: str) -> Optional[DictionaryEntry]:
    """Parses a complex entry with etymology and/or examples using consistent formatting."""
    lines = text.split('\n')
    etymology = None
    term = pos = definition = None
    pronunciation = None
    examples = []
    additional_info = []
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

        # Check for main entry pattern
        match = re.match(ENTRY_PATTERN, line_stripped)
        if match:
            if collecting_etymology and etymology_lines:
                etymology = '\n'.join(etymology_lines).strip()
                collecting_etymology = False

            term, pos, definition = match.groups()
            
            # Extract pronunciation if present
            if ' /' in term and '/' in term:
                # Look for pronunciation pattern
                pron_match = re.search(r'(.+?)\s+(/[^/]+/)', term)
                if pron_match:
                    term = pron_match.group(1).strip()
                    pronunciation = pron_match.group(2)
            
            continue

        # Collect examples and additional info after main entry
        if term and line_stripped and not line_stripped.startswith("-----"):
            if line_stripped.startswith("Ex:") or line_stripped.startswith("Ex.") or line_stripped.startswith("Example:"):
                examples.append(line.rstrip())
            elif line_stripped.startswith("-") or line_stripped.startswith("•"):
                additional_info.append(line.rstrip())
            else:
                # Other additional information
                additional_info.append(line.rstrip())

    if collecting_etymology and etymology_lines:
        etymology = '\n'.join(etymology_lines).strip()

    if term and pos and definition:
        return DictionaryEntry(term, pos, definition, etymology, examples, text, pronunciation, additional_info)

    return None

def get_corpus_from_content(content: str) -> List[str]:
    """Extracts corpus terms from dictionary content."""
    corpus_match = re.search(r"Corpus:\s*(.*?)\s*-----DICTIONARY PROPER-----", content, re.DOTALL | re.IGNORECASE)
    if corpus_match:
        corpus_text = corpus_match.group(1).strip()
        return [t.strip() for t in corpus_text.split(",") if t.strip()]
    return []

def count_dictionary_entries(content: str) -> int:
    """Count actual dictionary entries in the proper format."""
    if "-----DICTIONARY PROPER-----" not in content:
        return 0
    
    parts = content.split("-----DICTIONARY PROPER-----\n\n", 1)
    if len(parts) < 2:
        return 0
    
    body = parts[1]
    entry_count = 0
    
    # Count lines that match the dictionary entry pattern
    lines = body.split('\n')
    for line in lines:
        line = line.strip()
        if re.match(ENTRY_PATTERN, line):
            entry_count += 1
    
    return entry_count