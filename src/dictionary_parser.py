# src/dictionary_parser.py (IMPROVED VERSION)
import re
from typing import List, Optional, Dict, Tuple
from .config import logger

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
        # If this is a simple entry with no additional details, keep it on one line
        if (not self.etymology and not self.examples and not self.pronunciation and 
            not self.additional_info and not self.derived_terms and self.raw_content and 
            '\n' not in self.raw_content.strip()):
            return self.raw_content.strip()

        # Check if this entry needs the hyphen format (has additional details)
        needs_hyphens = (self.etymology or self.examples or self.pronunciation or 
                        self.additional_info or self.derived_terms or 
                        (self.raw_content and '\n' in self.raw_content))

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
        else:
            # Simple one-line entry
            main_line = f"{self.term}"
            if self.pronunciation:
                main_line += f" {self.pronunciation}"
            main_line += f" ({self.pos}) - {self.definition}"
            return main_line

def extract_pronunciation(text: str) -> Tuple[str, Optional[str]]:
    """Extract pronunciation from various formats and return cleaned text + pronunciation."""
    original_text = text
    pronunciation = None
    
    # Pattern 1: /phonetic/ anywhere in the text
    phonetic_match = re.search(r'/[^/]+/', text)
    if phonetic_match:
        pronunciation = phonetic_match.group(0)
        text = text.replace(pronunciation, '').strip()
    
    # Pattern 2: (pronounced: something)
    pron_match = re.search(r'\(pronounced:\s*([^)]+)\)', text, re.IGNORECASE)
    if pron_match:
        if not pronunciation:  # Don't override if we already found phonetic
            pronunciation = f"/{pron_match.group(1)}/"
        text = re.sub(r'\(pronounced:\s*[^)]+\)', '', text, flags=re.IGNORECASE).strip()
    
    # Pattern 3: [phonetic] brackets
    bracket_match = re.search(r'\[[^\]]+\]', text)
    if bracket_match and not pronunciation:
        pronunciation = bracket_match.group(0)
        text = text.replace(pronunciation, '').strip()
    
    # Clean up any double spaces
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text, pronunciation

def parse_flexible_entry(content: str) -> Optional[DictionaryEntry]:
    """Parse a dictionary entry with flexible formatting."""
    lines = [line.strip() for line in content.split('\n') if line.strip()]
    if not lines:
        return None
    
    # Find the main definition line - look for pattern: word (pos) - definition
    main_pattern = r'^(.+?)\s*\(([^)]+)\)\s*-\s*(.+)$'
    main_line = None
    main_match = None
    term = pos = definition = None
    pronunciation = None
    etymology = None
    examples = []
    additional_info = []
    derived_terms = None
    
    # First pass: find the main entry line
    for i, line in enumerate(lines):
        # Skip lines that are clearly not main entries
        if (line.startswith('Etymology:') or line.startswith('Ex:') or 
            line.startswith('Example:') or line.startswith('Derived Terms:') or
            line.startswith('-') or line.startswith('•')):
            continue
            
        # Try to match the main pattern
        match = re.match(main_pattern, line)
        if match:
            main_line = line
            main_match = match
            raw_term, pos, definition = match.groups()
            
            # Extract pronunciation from the term
            term, pronunciation = extract_pronunciation(raw_term)
            break
    
    if not main_match:
        # If no clear main line found, try to parse the first line that looks like an entry
        for line in lines:
            # More flexible matching - look for any line with parentheses and a dash
            if '(' in line and ')' in line and ' - ' in line:
                # Try to extract components more flexibly
                parts = line.split(' - ', 1)
                if len(parts) == 2:
                    left_part = parts[0].strip()
                    definition = parts[1].strip()
                    
                    # Extract part of speech from parentheses
                    paren_match = re.search(r'\(([^)]+)\)(?!.*\([^)]*\))', left_part)
                    if paren_match:
                        pos = paren_match.group(1)
                        # Everything before the last parentheses is the term
                        term_part = left_part[:paren_match.start()].strip()
                        term, pronunciation = extract_pronunciation(term_part)
                        main_line = line
                        break
    
    if not term or not pos or not definition:
        return None
    
    # Second pass: collect additional information
    collecting_etymology = False
    etymology_lines = []
    
    for line in lines:
        if line == main_line:
            continue
            
        # Etymology
        if line.startswith('Etymology:'):
            collecting_etymology = True
            ety_content = line[10:].strip()
            if ety_content:
                etymology_lines.append(ety_content)
            continue
        
        if collecting_etymology:
            # Continue collecting etymology until we hit something else
            if (line.startswith('Ex:') or line.startswith('Example:') or 
                line.startswith('Derived Terms:') or re.match(main_pattern, line)):
                collecting_etymology = False
                etymology = ' '.join(etymology_lines) if etymology_lines else None
            else:
                etymology_lines.append(line)
                continue
        
        # Derived Terms
        if line.startswith('Derived Terms:'):
            derived_terms = line[14:].strip()
            continue
        
        # Examples
        if line.startswith('Ex:') or line.startswith('Example:'):
            examples.append(line)
            continue
        
        # Additional structured info
        if line.startswith('-') or line.startswith('•'):
            additional_info.append(line)
            continue
        
        # If we're not in etymology mode and this isn't a main line, it's additional info
        if not collecting_etymology:
            # Check if this might be a continuation of examples or additional info
            if examples and not line.startswith(('Etymology:', 'Derived Terms:')):
                # Might be example continuation
                examples.append(line)
            else:
                additional_info.append(line)
    
    # Finalize etymology if we were still collecting
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
        raw_content=content
    )

def parse_dictionary_entries(content: str) -> List[DictionaryEntry]:
    """Parse dictionary content with flexible entry detection."""
    entries = []
    
    if "-----DICTIONARY PROPER-----" not in content:
        return entries

    parts = content.split("-----DICTIONARY PROPER-----\n\n", 1)
    if len(parts) < 2:
        return entries

    body = parts[1]
    
    # Split content into potential entry blocks
    # First, handle hyphen-separated complex entries
    sections = re.split(r'\n\n(?=---------------------------------------------)', body)
    remaining_content = []
    
    for section in sections:
        if '---------------------------------------------' in section:
            # This is a complex entry
            entry = parse_complex_entry_flexible(section)
            if entry:
                entries.append(entry)
        else:
            remaining_content.append(section)
    
    # Now handle the remaining content as simple entries
    remaining_text = '\n\n'.join(remaining_content)
    simple_sections = [s.strip() for s in remaining_text.split('\n\n') if s.strip()]
    
    for section in simple_sections:
        # Try to parse as a single entry or multiple single-line entries
        lines = [line.strip() for line in section.split('\n') if line.strip()]
        
        # Check if this whole section is one entry
        entry = parse_flexible_entry(section)
        if entry:
            entries.append(entry)
        else:
            # Try parsing individual lines
            for line in lines:
                if line.strip():
                    line_entry = parse_flexible_entry(line)
                    if line_entry:
                        entries.append(line_entry)
    
    return entries

def parse_complex_entry_flexible(text: str) -> Optional[DictionaryEntry]:
    """Parse complex entries with hyphen separators more flexibly."""
    # Remove the hyphen separators for easier parsing
    clean_text = re.sub(r'^-+\n?', '', text, flags=re.MULTILINE)
    clean_text = re.sub(r'\n?-+$', '', clean_text, flags=re.MULTILINE)
    clean_text = clean_text.strip()
    
    return parse_flexible_entry(clean_text)

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

# Test function to validate parsing
def test_parsing_examples():
    """Test the parser with your examples."""
    test_cases = [
        'testword (n.) - A word or phrase used as a deliberate, complex example to verify the functionality of an automated system.',
        'testword (n.) - /ˈtɛstˌwɜːrd/ A word or phrase used as a deliberate, complex example',
        'aaa (pronounced: ayy) (n.) - aaa',
        'aaa (n.) (pronounced: ayy) - aaa',
        'aaa (n.) - (pronounced: ayy) aaa',
        'aaa (n.) - /ayy/ aaa',
        '''testword (n.) - A word or phrase used as a deliberate, complex example to verify the functionality of an automated system. 
Etymology: A neologism created for the purpose of demonstrating advanced bot parsing
Ex: "The developer used 'testword' to ensure the dictionary bot could handle multi-line entries"'''
    ]
    
    for i, test_case in enumerate(test_cases):
        print(f"\nTest case {i+1}:")
        print(f"Input: {repr(test_case)}")
        entry = parse_flexible_entry(test_case)
        if entry:
            print(f"Parsed: term='{entry.term}', pos='{entry.pos}', def='{entry.definition[:50]}...'")
            if entry.pronunciation:
                print(f"Pronunciation: {entry.pronunciation}")
            if entry.etymology:
                print(f"Etymology: {entry.etymology}")
        else:
            print("Failed to parse")

if __name__ == "__main__":
    test_parsing_examples()