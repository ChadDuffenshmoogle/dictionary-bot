# src/dictionary_parser.py (COMPLETELY CONSERVATIVE VERSION)
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
                 derived_terms: Optional[str] = None, original_block: Optional[str] = None):
        self.term = term
        self.pos = pos
        self.definition = definition
        self.etymology = etymology
        self.examples = examples or []
        self.raw_content = raw_content
        self.pronunciation = pronunciation
        self.additional_info = additional_info or []
        self.derived_terms = derived_terms
        self.original_block = original_block  # Store the complete original block

    def to_string(self) -> str:
        """Converts the entry to its string format for file output."""
        # If we have the original block, use it exactly as-is
        if self.original_block:
            return self.original_block
        
        # Only new entries get standardized formatting
        result = "---------------------------------------------\n"
        
        if self.etymology:
            result += f"Etymology: {self.etymology}\n"
        
        main_line = f"{self.term}"
        if self.pronunciation:
            main_line += f" {self.pronunciation}"
        main_line += f" ({self.pos}) - {self.definition}"
        result += main_line
        
        if self.derived_terms:
            result += f"\nDerived Terms: {self.derived_terms}"
        
        if self.additional_info:
            for info in self.additional_info:
                result += f"\n{info}"
        
        if self.examples:
            for example in self.examples:
                result += f"\n{example}"
        
        result += "\n---------------------------------------------"
        return result

def extract_term_from_line(line: str) -> Optional[str]:
    """Extract just the term name for corpus/sorting purposes."""
    # Try standard pattern first
    match = re.match(ENTRY_PATTERN, line.strip())
    if match:
        raw_term = match.group(1)
        # Remove pronunciation markers to get clean term
        term = re.sub(r'/[^/]+/', '', raw_term)  # Remove /phonetic/
        term = re.sub(r'\(pronounced:\s*[^)]+\)', '', term, flags=re.IGNORECASE)  # Remove (pronounced: ...)
        term = re.sub(r'\[[^\]]+\]', '', term)  # Remove [brackets]
        return term.strip()
    
    # Try flexible pattern
    if '(' in line and ')' in line and ' - ' in line:
        parts = line.split(' - ', 1)
        if len(parts) == 2:
            left_part = parts[0].strip()
            # Find last parentheses and extract everything before it
            paren_matches = list(re.finditer(r'\(([^)]+)\)', left_part))
            if paren_matches:
                last_paren = paren_matches[-1]
                term_part = left_part[:last_paren.start()].strip()
                # Clean pronunciation markers
                term = re.sub(r'/[^/]+/', '', term_part)
                term = re.sub(r'\(pronounced:\s*[^)]+\)', '', term, flags=re.IGNORECASE)
                term = re.sub(r'\[[^\]]+\]', '', term)
                return term.strip()
    
    return None

def parse_dictionary_entries_conservative(content: str) -> List[DictionaryEntry]:
    """Parse entries while preserving ALL original formatting exactly."""
    entries = []

    if "-----DICTIONARY PROPER-----" not in content:
        return entries

    parts = content.split("-----DICTIONARY PROPER-----\n\n", 1)
    if len(parts) < 2:
        return entries

    body = parts[1]
    
    # Find all hyphen-separated blocks and preserve them exactly
    # Split by hyphen patterns but keep track of everything
    sections = re.split(r'(\n-{20,}\n)', body)
    
    i = 0
    while i < len(sections):
        section = sections[i]
        
        # If this section contains hyphens, it's a separator
        if re.match(r'^\n-{20,}\n$', section):
            # The next section should be entry content
            if i + 1 < len(sections):
                entry_content = sections[i + 1]
                # Look for the closing hyphens
                if i + 2 < len(sections) and re.match(r'^\n-{20,}\n$', sections[i + 2]):
                    # We have a complete hyphen block
                    full_block = section + entry_content + sections[i + 2]
                    
                    # Try to extract term for indexing
                    term = extract_term_from_entry_block(entry_content)
                    if term:
                        # Create entry that preserves the original block exactly
                        entry = DictionaryEntry(
                            term=term,
                            pos="n",  # Dummy values for sorting
                            definition="",
                            original_block=full_block
                        )
                        entries.append(entry)
                    else:
                        # Still preserve the block even if we can't parse it
                        entry = DictionaryEntry(
                            term="UNKNOWN",
                            pos="n", 
                            definition="",
                            original_block=full_block
                        )
                        entries.append(entry)
                    
                    i += 3  # Skip the content and closing hyphens
                    continue
        
        # Handle non-hyphen content (might be simple entries or spacing)
        lines = section.split('\n')
        for line in lines:
            line = line.strip()
            if line and re.match(ENTRY_PATTERN, line):
                term = extract_term_from_line(line)
                if term:
                    # Simple entry - preserve as original block
                    entry = DictionaryEntry(
                        term=term,
                        pos="n",
                        definition="",
                        original_block=line
                    )
                    entries.append(entry)
        
        i += 1
    
    return entries

def extract_term_from_entry_block(content: str) -> Optional[str]:
    """Extract the main term from an entry block for indexing."""
    lines = content.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Skip metadata lines
        if line.startswith(('Etymology:', 'Ex:', 'Example:', 'Derived Terms:')):
            continue
        
        # Try to find a line that looks like a main entry
        term = extract_term_from_line(line)
        if term:
            return term
    
    return None

def get_corpus_from_content(content: str) -> List[str]:
    """Extract corpus terms from dictionary content."""
    corpus_match = re.search(r"Corpus:\s*(.*?)\s*-----DICTIONARY PROPER-----", content, re.DOTALL | re.IGNORECASE)
    if corpus_match:
        corpus_text = corpus_match.group(1).strip()
        return [t.strip() for t in corpus_text.split(",") if t.strip()]
    return []

def count_dictionary_entries(content: str) -> int:
    """Count entries by counting hyphen blocks and simple entries."""
    if "-----DICTIONARY PROPER-----" not in content:
        return 0
    
    body = content.split("-----DICTIONARY PROPER-----\n\n", 1)[1]
    
    # Count hyphen blocks
    hyphen_blocks = len(re.findall(r'-{20,}.*?-{20,}', body, re.DOTALL))
    
    # Count simple entries (lines matching pattern outside hyphen blocks)
    # Remove all hyphen blocks first
    without_blocks = re.sub(r'-{20,}.*?-{20,}', '', body, flags=re.DOTALL)
    simple_entries = len(re.findall(ENTRY_PATTERN, without_blocks, re.MULTILINE))
    
    return hyphen_blocks + simple_entries

def parse_message_as_entry(content: str) -> Optional[DictionaryEntry]:
    """Parse a Discord message - this creates NEW entries with standard formatting."""
    content = content.strip()
    
    # Try to match the basic pattern
    match = re.match(ENTRY_PATTERN, content)
    if match:
        raw_term, pos, definition = match.groups()
        
        # Extract pronunciation
        pronunciation = None
        term = raw_term
        
        phonetic_match = re.search(r'/[^/]+/', term)
        if phonetic_match:
            pronunciation = phonetic_match.group(0)
            term = term.replace(pronunciation, '').strip()
        
        pron_match = re.search(r'\(pronounced:\s*([^)]+)\)', term, re.IGNORECASE)
        if pron_match:
            if not pronunciation:
                pronunciation = f"/{pron_match.group(1)}/"
            term = re.sub(r'\(pronounced:\s*[^)]+\)', '', term, flags=re.IGNORECASE).strip()
        
        return DictionaryEntry(
            term=term,
            pos=pos,
            definition=definition,
            pronunciation=pronunciation,
            original_block=None  # New entries don't have original blocks
        )
    
    # Try to handle multi-line entries
    lines = [line.strip() for line in content.split('\n') if line.strip()]
    main_entry = None
    etymology = None
    examples = []
    additional_info = []
    
    for line in lines:
        if line.startswith('Etymology:'):
            etymology = line[10:].strip()
        elif line.startswith(('Ex:', 'Example:')):
            examples.append(line)
        elif not main_entry and re.match(ENTRY_PATTERN, line):
            match = re.match(ENTRY_PATTERN, line)
            if match:
                raw_term, pos, definition = match.groups()
                term = re.sub(r'/[^/]+/', '', raw_term).strip()
                main_entry = DictionaryEntry(term, pos, definition)
        else:
            additional_info.append(line)
    
    if main_entry:
        main_entry.etymology = etymology
        main_entry.examples = examples
        main_entry.additional_info = additional_info
        main_entry.original_block = None  # New entry
        return main_entry
    
    return None

# Keep the old function names for compatibility
def parse_dictionary_entries(content: str) -> List[DictionaryEntry]:
    """Main parsing function - preserves all original formatting."""
    return parse_dictionary_entries_conservative(content)