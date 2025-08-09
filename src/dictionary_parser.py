# src/dictionary_parser.py (SAFE PRESERVING VERSION)
import re
from typing import List, Optional, Dict, Tuple
from .config import logger, ENTRY_PATTERN

def sort_key_ignore_punct(s: str) -> str:
    """Strips leading punctuation, returns lowercase remaining string for sorting."""
    term = s.split(' (')[0] if ' (' in s else s
    return term.lstrip(" '-\"").lower()

class DictionaryEntry:
    """Represents a single dictionary entry."""
    def __init__(self, term: str, pos: str, definition: str, etymology: Optional[str] = None, 
                 examples: Optional[List[str]] = None, raw_content: Optional[str] = None, 
                 pronunciation: Optional[str] = None, additional_info: Optional[List[str]] = None,
                 derived_terms: Optional[str] = None, preserve_original: bool = False):
        self.term = term
        self.pos = pos
        self.definition = definition
        self.etymology = etymology
        self.examples = examples or []
        self.raw_content = raw_content
        self.pronunciation = pronunciation
        self.additional_info = additional_info or []
        self.derived_terms = derived_terms
        self.preserve_original = preserve_original  # Flag to preserve original formatting

    def to_string(self) -> str:
        """Converts the entry to its string format for file output."""
        # If we're preserving original formatting, return it as-is
        if self.preserve_original and self.raw_content:
            return self.raw_content.strip()
        
        # For new entries, use consistent formatting
        result = "---------------------------------------------\n"
        
        # Add etymology if present (before main entry)
        if self.etymology:
            result += f"Etymology: {self.etymology}\n"
        
        # Build the main entry line
        main_line = f"{self.term}"
        if self.pronunciation:
            main_line += f" {self.pronunciation}"
        main_line += f" ({self.pos}) - {self.definition}"
        result += main_line
        
        # Add derived terms if present
        if self.derived_terms:
            result += f"\nDerived Terms: {self.derived_terms}"
        
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

def extract_pronunciation_from_term(text: str) -> Tuple[str, Optional[str]]:
    """Extract pronunciation from term, return cleaned text + pronunciation."""
    pronunciation = None
    
    # Pattern 1: /phonetic/ notation
    phonetic_match = re.search(r'/[^/]+/', text)
    if phonetic_match:
        pronunciation = phonetic_match.group(0)
        text = text.replace(pronunciation, '').strip()
    
    # Pattern 2: (pronounced: something)
    pron_match = re.search(r'\(pronounced:\s*([^)]+)\)', text, re.IGNORECASE)
    if pron_match:
        if not pronunciation:
            pronunciation = f"/{pron_match.group(1)}/"
        text = re.sub(r'\(pronounced:\s*[^)]+\)', '', text, flags=re.IGNORECASE).strip()
    
    # Pattern 3: [phonetic] brackets
    bracket_match = re.search(r'\[[^\]]+\]', text)
    if bracket_match and not pronunciation:
        pronunciation = bracket_match.group(0)
        text = text.replace(pronunciation, '').strip()
    
    # Clean up multiple spaces
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text, pronunciation

def parse_dictionary_entries(content: str) -> List[DictionaryEntry]:
    """Parse dictionary content preserving original formatting as much as possible."""
    entries = []

    if "-----DICTIONARY PROPER-----" not in content:
        return entries

    parts = content.split("-----DICTIONARY PROPER-----\n\n", 1)
    if len(parts) < 2:
        return entries

    body = parts[1]
    
    # Split by hyphen separators to find entry blocks
    # Use regex to split while keeping the separators
    sections = re.split(r'(\n?-{20,}\n?)', body)
    
    current_entry_content = ""
    inside_entry = False
    
    for section in sections:
        section_stripped = section.strip()
        
        # If this is a hyphen separator
        if re.match(r'^-{20,}$', section_stripped):
            if inside_entry and current_entry_content.strip():
                # We've reached the end of an entry, process it
                entry = create_entry_from_content(current_entry_content.strip())
                if entry:
                    entries.append(entry)
                current_entry_content = ""
            inside_entry = not inside_entry
        else:
            # This is content (either entry content or whitespace between entries)
            if inside_entry:
                current_entry_content += section
            else:
                # Content outside entry blocks - might be simple entries
                lines = [line.strip() for line in section.split('\n') if line.strip()]
                for line in lines:
                    if re.match(ENTRY_PATTERN, line):
                        entry = parse_simple_line_entry(line)
                        if entry:
                            entries.append(entry)
    
    # Handle any remaining entry content
    if inside_entry and current_entry_content.strip():
        entry = create_entry_from_content(current_entry_content.strip())
        if entry:
            entries.append(entry)
    
    return entries

def create_entry_from_content(content: str) -> Optional[DictionaryEntry]:
    """Create a DictionaryEntry from content, preserving original formatting."""
    lines = [line.rstrip() for line in content.split('\n')]  # Preserve internal structure but remove trailing spaces
    
    # Find the main entry line
    main_entry_line = None
    main_entry_match = None
    term = pos = definition = None
    
    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue
            
        # Skip obvious non-entry lines
        if line_stripped.startswith(('Etymology:', 'Ex:', 'Example:', 'Derived Terms:')):
            continue
            
        # Try to match entry pattern
        match = re.match(ENTRY_PATTERN, line_stripped)
        if match:
            main_entry_line = line_stripped
            main_entry_match = match
            raw_term, pos, definition = match.groups()
            term, pronunciation = extract_pronunciation_from_term(raw_term)
            break
    
    if not main_entry_match:
        # Try more flexible pattern matching
        for line in lines:
            line_stripped = line.strip()
            if '(' in line_stripped and ')' in line_stripped and ' - ' in line_stripped:
                # Try to extract components more flexibly
                parts = line_stripped.split(' - ', 1)
                if len(parts) == 2:
                    left_part = parts[0].strip()
                    definition = parts[1].strip()
                    
                    # Find the last parentheses (should be part of speech)
                    paren_matches = list(re.finditer(r'\(([^)]+)\)', left_part))
                    if paren_matches:
                        last_paren = paren_matches[-1]
                        pos = last_paren.group(1)
                        term_part = left_part[:last_paren.start()].strip()
                        term, pronunciation = extract_pronunciation_from_term(term_part)
                        main_entry_line = line_stripped
                        break
    
    if not term or not pos or not definition:
        # If we can't parse it, still preserve it as raw content
        if content.strip():
            logger.warning(f"Could not parse entry content, preserving as-is: {content[:50]}...")
            # Create a dummy entry that preserves the original formatting
            return DictionaryEntry("UNPARSED", "n", "UNPARSED", raw_content=content, preserve_original=True)
        return None
    
    # Extract additional information while preserving original formatting
    etymology = None
    examples = []
    additional_info = []
    derived_terms = None
    
    collecting_etymology = False
    etymology_lines = []
    
    for line in lines:
        line_stripped = line.strip()
        
        if line_stripped == main_entry_line:
            continue
            
        if line_stripped.startswith('Etymology:'):
            collecting_etymology = True
            ety_content = line_stripped[10:].strip()
            if ety_content:
                etymology_lines.append(ety_content)
            continue
        
        if collecting_etymology:
            if line_stripped.startswith(('Ex:', 'Example:', 'Derived Terms:')) or re.match(ENTRY_PATTERN, line_stripped):
                collecting_etymology = False
                etymology = ' '.join(etymology_lines) if etymology_lines else None
            else:
                etymology_lines.append(line_stripped)
                continue
        
        if line_stripped.startswith('Derived Terms:'):
            derived_terms = line_stripped[14:].strip()
            continue
        
        if line_stripped.startswith(('Ex:', 'Example:')):
            examples.append(line.rstrip())  # Preserve original line formatting
            continue
        
        # Everything else is additional info
        if line_stripped and not collecting_etymology:
            additional_info.append(line.rstrip())  # Preserve original line formatting
    
    # Finalize etymology if still collecting
    if collecting_etymology and etymology_lines:
        etymology = ' '.join(etymology_lines)
    
    return DictionaryEntry(
        term=term.strip(),
        pos=pos.strip(),
        definition=definition.strip(),
        etymology=etymology,
        examples=examples,
        pronunciation=pronunciation,
        additional_info=additional_info,
        derived_terms=derived_terms,
        raw_content=content,
        preserve_original=True  # Preserve original formatting for existing entries
    )

def parse_simple_line_entry(line: str) -> Optional[DictionaryEntry]:
    """Parse a single-line entry."""
    match = re.match(ENTRY_PATTERN, line.strip())
    if match:
        raw_term, pos, definition = match.groups()
        term, pronunciation = extract_pronunciation_from_term(raw_term)
        return DictionaryEntry(term, pos, definition, pronunciation=pronunciation, raw_content=line)
    return None

def get_corpus_from_content(content: str) -> List[str]:
    """Extract corpus terms from dictionary content."""
    corpus_match = re.search(r"Corpus:\s*(.*?)\s*-----DICTIONARY PROPER-----", content, re.DOTALL | re.IGNORECASE)
    if corpus_match:
        corpus_text = corpus_match.group(1).strip()
        return [t.strip() for t in corpus_text.split(",") if t.strip()]
    return []

def count_dictionary_entries(content: str) -> int:
    """Count actual dictionary entries."""
    entries = parse_dictionary_entries(content)
    # Only count entries that aren't just preserved unparsed content
    return len([e for e in entries if not (e.term == "UNPARSED" and e.preserve_original)])

def parse_message_as_entry(content: str) -> Optional[DictionaryEntry]:
    """Parse a Discord message that might contain a dictionary entry."""
    content = content.strip()
    
    # Try simple single-line parsing first
    entry = parse_simple_line_entry(content)
    if entry:
        entry.preserve_original = False  # New entries use standard formatting
        return entry
    
    # Try complex multi-line parsing
    entry = create_entry_from_content(content)
    if entry and entry.term != "UNPARSED":
        entry.preserve_original = False  # New entries use standard formatting
        return entry
    
    return None