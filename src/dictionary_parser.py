# src/dictionary_parser.py (CORRECTED VERSION)
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
                 derived_terms: Optional[str] = None):
        self.term = term
        self.pos = pos
        self.definition = definition
        self.etymology = etymology
        self.examples = examples or []
        self.raw_content = raw_content
        self.pronunciation = pronunciation
        self.additional_info = additional_info or []
        self.derived_terms = derived_terms

    def to_string(self) -> str:
        """Converts the entry to its string format for file output."""
        # Every entry gets wrapped in hyphens, following your format
        result = "---------------------------------------------\n"
        
        # Add etymology if present (before main entry)
        if self.etymology:
            result += f"Etymology: {self.etymology}\n\n"
        
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

def extract_pronunciation_and_alts(text: str) -> Tuple[str, Optional[str]]:
    """Extract pronunciation and alternative forms, return cleaned text + pronunciation."""
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

def parse_single_entry_line(line: str) -> Optional[DictionaryEntry]:
    """Parse a single line that should contain one dictionary entry."""
    line = line.strip()
    if not line:
        return None
    
    # Try the main pattern first
    match = re.match(ENTRY_PATTERN, line)
    if match:
        raw_term, pos, definition = match.groups()
        term, pronunciation = extract_pronunciation_and_alts(raw_term)
        return DictionaryEntry(term, pos, definition, pronunciation=pronunciation, raw_content=line)
    
    # Try more flexible matching for entries with complex term formats
    # Look for: anything (pos) - definition
    flexible_pattern = r'^(.+?)\s*\(([^)]+)\)\s*-\s*(.+)$'
    match = re.match(flexible_pattern, line)
    if match:
        raw_term, pos, definition = match.groups()
        term, pronunciation = extract_pronunciation_and_alts(raw_term)
        return DictionaryEntry(term, pos, definition, pronunciation=pronunciation, raw_content=line)
    
    return None

def parse_complex_entry(text: str) -> Optional[DictionaryEntry]:
    """Parse a complex entry that might span multiple lines."""
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    if not lines:
        return None
    
    # Remove hyphen separators
    lines = [line for line in lines if not re.match(r'^-+$', line)]
    
    etymology = None
    term = pos = definition = pronunciation = None
    examples = []
    additional_info = []
    derived_terms = None
    main_entry_found = False
    
    # Process lines to extract information
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Etymology (comes first)
        if line.startswith('Etymology:') and not main_entry_found:
            etymology_parts = [line[10:].strip()]
            i += 1
            # Continue collecting etymology lines
            while i < len(lines) and not re.match(ENTRY_PATTERN, lines[i]) and not lines[i].startswith(('Ex:', 'Derived Terms:')):
                etymology_parts.append(lines[i])
                i += 1
            etymology = ' '.join(etymology_parts).strip()
            continue
        
        # Try to find main entry line
        entry = parse_single_entry_line(line)
        if entry and not main_entry_found:
            term = entry.term
            pos = entry.pos
            definition = entry.definition
            pronunciation = entry.pronunciation
            main_entry_found = True
            i += 1
            continue
        
        # Derived Terms
        if line.startswith('Derived Terms:'):
            derived_terms = line[14:].strip()
            i += 1
            continue
        
        # Examples
        if line.startswith(('Ex:', 'Ex.', 'Example:')):
            examples.append(line)
            i += 1
            continue
        
        # Additional info
        if main_entry_found:
            additional_info.append(line)
        
        i += 1
    
    if term and pos and definition:
        return DictionaryEntry(
            term=term,
            pos=pos,
            definition=definition,
            etymology=etymology,
            examples=examples,
            pronunciation=pronunciation,
            additional_info=additional_info,
            derived_terms=derived_terms,
            raw_content=text
        )
    
    return None

def parse_dictionary_entries(content: str) -> List[DictionaryEntry]:
    """Parse dictionary content into DictionaryEntry objects."""
    entries = []

    if "-----DICTIONARY PROPER-----" not in content:
        return entries

    parts = content.split("-----DICTIONARY PROPER-----\n\n", 1)
    if len(parts) < 2:
        return entries

    body = parts[1]
    
    # Split into sections by double newlines
    raw_sections = body.split('\n\n')
    
    i = 0
    while i < len(raw_sections):
        section = raw_sections[i].strip()
        
        if not section:
            i += 1
            continue
        
        # Check if this section starts with hyphens (complex entry)
        if section.strip().startswith('-----'):
            # Collect the entire hyphen-wrapped entry
            entry_parts = [section]
            i += 1
            
            # Continue collecting until we find the closing hyphens or end
            while i < len(raw_sections):
                part = raw_sections[i].strip()
                entry_parts.append(part)
                
                if part.endswith('-----'):
                    break
                i += 1
            
            # Parse this complex entry
            full_entry_text = '\n\n'.join(entry_parts)
            entry = parse_complex_entry(full_entry_text)
            if entry:
                entries.append(entry)
        
        else:
            # This might be a simple entry or multiple simple entries
            lines = [line.strip() for line in section.split('\n') if line.strip()]
            
            for line in lines:
                entry = parse_single_entry_line(line)
                if entry:
                    entries.append(entry)
        
        i += 1
    
    return entries

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
    return len(entries)

# Function to handle new entries from Discord messages
def parse_message_as_entry(content: str) -> Optional[DictionaryEntry]:
    """Parse a Discord message that might contain a dictionary entry."""
    content = content.strip()
    
    # First try as a simple single-line entry
    entry = parse_single_entry_line(content)
    if entry:
        return entry
    
    # Try as a complex multi-line entry
    return parse_complex_entry(content)