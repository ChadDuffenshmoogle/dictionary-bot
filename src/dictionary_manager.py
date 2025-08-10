# src/dictionary_manager.py
import re
import pytz
from datetime import datetime
from typing import Optional, List
from .github_api import GitHubAPI
from .dictionary_parser import DictionaryEntry, parse_dictionary_entries, get_corpus_from_content, sort_key_ignore_punct
from .config import BASE_VERSION, FILE_PREFIX, FILE_EXTENSION, logger, ENTRY_PATTERN

class DictionaryManager:
    """Manages dictionary operations with GitHub integration."""

    def __init__(self, github_api: GitHubAPI):
        self.github = github_api
        self._cache = {}  # Cache file contents to avoid repeated API calls

    def find_latest_version(self) -> str:
        """Finds the latest dictionary version from GitHub."""
        files = self.github.list_dictionary_files()

        max_version = BASE_VERSION
        max_nums = [int(i) for i in BASE_VERSION[1:].split('.')]

        for filename in files:
            m = re.search(r"v\.?(\d+)\.(\d+)\.(\d+)", filename, re.IGNORECASE)
            if m:
                nums = list(map(int, m.groups()))
                if nums > max_nums:
                    max_nums, max_version = nums, f"v{nums[0]}.{nums[1]}.{nums[2]}"

        logger.info(f"Latest version detected: {max_version}")
        return max_version

    def get_filename(self, version: str) -> str:
        """Constructs the filename for a given dictionary version."""
        return f"{FILE_PREFIX} {version}{FILE_EXTENSION}"

    def get_dictionary_content(self, version: str) -> Optional[str]:
        """Gets dictionary content from GitHub (with caching)."""
        filename = self.get_filename(version)

        if filename in self._cache:
            return self._cache[filename]

        content = self.github.get_file_content(filename)
        if content:
            self._cache[filename] = content

        return content

    def get_all_entries(self, version: str) -> List[DictionaryEntry]:
        """Gets and parses all dictionary entries for a given version."""
        content = self.get_dictionary_content(version)
        if content:
            return parse_dictionary_entries(content)
        return []

    def get_all_corpus(self, version: str) -> List[str]:
        """Gets all corpus terms for a given version."""
        content = self.get_dictionary_content(version)
        if content:
            return get_corpus_from_content(content)
        return []

    def add_entry(self, term: str, pos: str, definition: str, ety_lines: Optional[List[str]] = None, 
                  example_lines: Optional[List[str]] = None, pronunciation: Optional[str] = None, 
                  additional_info: Optional[List[str]] = None) -> bool:
        """Adds a new entry by preserving all original formatting and adding entry in alphabetical order."""
        cdt = pytz.timezone('America/Chicago')
        now = datetime.now(cdt)
        timestamp = now.strftime("%B %d, %Y %I:%M %p CDT")
        logger.info(f"Adding new term: '{term}' at {timestamp}")

        # Find latest version
        latest = self.find_latest_version()
        latest_content = self.get_dictionary_content(latest)

        if not latest_content:
            logger.error(f"Could not get content for version {latest}. Cannot add entry.")
            return False

        # Extract corpus for checking duplicates and updating
        corpus = self.get_all_corpus(latest)
        logger.info(f"Loaded {len(corpus)} corpus terms for version {latest}")

        # Check if term already exists (case-insensitive)
        if any(term.lower() == existing_term.lower() for existing_term in corpus):
            logger.warning(f"Term '{term}' already exists—skipping addition.")
            return False

        # Determine new version (increment patch)
        m = re.search(r"v\.?(\d+)\.(\d+)\.(\d+)", latest, re.IGNORECASE)
        if m:
            major, minor, patch = map(int, m.groups())
            new_version = f"v{major}.{minor}.{patch+1}"
        else:
            new_version = "v1.2.5"  # Fallback

        # Add to corpus and sort
        new_corpus = corpus + [term]
        new_corpus = sorted(set(new_corpus), key=sort_key_ignore_punct)
        
        logger.info(f"Original corpus count: {len(corpus)}")
        logger.info(f"New corpus count: {len(new_corpus)}")
        logger.info(f"Added term '{term}' to corpus")
        
        # Debug: show where the term should be in the sorted list
        term_position = None
        for i, corpus_term in enumerate(new_corpus):
            if corpus_term.lower() == term.lower():
                term_position = i
                break
        
        if term_position is not None:
            logger.info(f"Term '{term}' is at position {term_position} in sorted corpus")
            # Show surrounding terms for context
            start = max(0, term_position - 3)
            end = min(len(new_corpus), term_position + 4)
            context = new_corpus[start:end]
            logger.info(f"Context: {context}")
        else:
            logger.warning(f"Term '{term}' not found in new corpus!")

        # Create new entry with appropriate formatting
        new_entry_text = self._format_new_entry(term, pos, definition, pronunciation, ety_lines, example_lines, additional_info)

        # Split content into header and body
        if "-----DICTIONARY PROPER-----\n\n" in latest_content:
            header_part, body_part = latest_content.split("-----DICTIONARY PROPER-----\n\n", 1)
            
            # Update header with new version and timestamp
            new_header = self._update_header(header_part, new_version, timestamp, new_corpus)
            
            # Find insertion point and insert new entry
            new_body = self._insert_entry_in_body(body_part, term, new_entry_text)
            
            # Reconstruct the file
            new_content = new_header + "\n\n-----DICTIONARY PROPER-----\n\n" + new_body
        else:
            logger.error("Could not find dictionary proper section")
            return False

        # Upload to GitHub
        filename = self.get_filename(new_version)
        commit_message = f"Add dictionary {new_version} with new term '{term}'"

        success = self.github.create_or_update_file(filename, new_content, commit_message)

        if success:
            # Clear cache to force refresh for new version
            self._cache.clear()
            logger.info(f"Successfully created {filename}")
            return True
        else:
            logger.error(f"Failed to upload {filename}")
            return False

    def _format_new_entry(self, term: str, pos: str, definition: str, pronunciation: Optional[str] = None,
                         ety_lines: Optional[List[str]] = None, example_lines: Optional[List[str]] = None,
                         additional_info: Optional[List[str]] = None) -> str:
        """Format a new entry based on the dictionary style."""
        
        # Check if this should be a complex entry (has etymology, examples, or additional info)
        needs_complex_format = (ety_lines and any(ety_lines)) or (example_lines and any(example_lines)) or (additional_info and any(additional_info))
        
        if needs_complex_format:
            # Use hyphen-separated format for complex entries
            result = "---------------------------------------------\n"
            
            # Add etymology first if present
            if ety_lines:
                for ety_line in ety_lines:
                    if ety_line.strip():
                        if not ety_line.strip().startswith('Etymology:'):
                            result += f"Etymology: {ety_line.strip()}\n"
                        else:
                            result += f"{ety_line.strip()}\n"
                result += "\n"
            
            # Main entry line
            main_line = term
            if pronunciation:
                main_line += f" {pronunciation}"
            main_line += f" ({pos}) - {definition}"
            result += main_line
            
            # Add additional info
            if additional_info:
                for info in additional_info:
                    if info.strip():
                        result += f"\n{info.strip()}"
            
            # Add examples
            if example_lines:
                for example in example_lines:
                    if example.strip():
                        if not example.strip().startswith(('Ex:', 'Example:')):
                            result += f"\nEx: {example.strip()}"
                        else:
                            result += f"\n{example.strip()}"
            
            result += "\n---------------------------------------------"
            
        else:
            # Simple inline format
            result = term
            if pronunciation:
                result += f" {pronunciation}"
            result += f" ({pos}) - {definition}"
        
        return result

    def _update_header(self, header_part: str, new_version: str, timestamp: str, new_corpus: List[str]) -> str:
        """Update the header with new version, timestamp, and corpus."""
        header_lines = header_part.split('\n')
        
        # Replace the first line with new version and timestamp
        header_lines[0] = f"{FILE_PREFIX} {new_version} - {timestamp}"
        
        # Find the corpus section and update it
        corpus_start = None
        corpus_end = None
        
        for i, line in enumerate(header_lines):
            if line.strip().startswith("Corpus:"):
                corpus_start = i
                break
        
        if corpus_start is not None:
            # Find the end of the corpus section (look for empty line or start of next section)
            corpus_end = corpus_start + 1
            while corpus_end < len(header_lines):
                line = header_lines[corpus_end].strip()
                if line == "" or line.startswith("-----"):
                    break
                # Check if this looks like the start of a new section
                if line and not any(char in line for char in [',', ':', 'T:', 'S:', 'P:', 'C:']):
                    break
                corpus_end += 1
            
            # Format the new corpus
            formatted_corpus = self._format_corpus_with_grouping(new_corpus)
            logger.info(f"Formatted corpus preview: {formatted_corpus[:200]}...")
            
            # Replace the corpus section
            new_corpus_text = f"Corpus: {formatted_corpus.strip()}"
            
            # Split into lines if it's very long
            corpus_lines = [new_corpus_text]
            
            # Replace the old corpus section with the new one
            header_lines = header_lines[:corpus_start] + corpus_lines + header_lines[corpus_end:]
        else:
            logger.warning("Could not find corpus section in header")
        
        return '\n'.join(header_lines)

    def _format_corpus_with_grouping(self, corpus: List[str]) -> str:
        """Format corpus with each letter getting its own line."""
        if not corpus:
            return ""
        
        # Group by first letter
        grouped = {}
        for term in corpus:
            first_letter = term[0].upper()
            if first_letter not in grouped:
                grouped[first_letter] = []
            grouped[first_letter].append(term)
        
        # Sort terms within each group
        for letter in grouped:
            grouped[letter] = sorted(grouped[letter], key=sort_key_ignore_punct)
        
        result_parts = []
        letters = sorted(grouped.keys())
        
        for i, letter in enumerate(letters):
            terms = grouped[letter]
            
            # Each letter gets its own line with letter prefix
            if i == 0:
                # First letter doesn't need extra newlines at start
                result_parts.append(f"{letter}: {', '.join(terms)}")
            else:
                # All other letters get double newline before them
                result_parts.append(f"\n\n{letter}: {', '.join(terms)}")
        
        return ''.join(result_parts)

    def _insert_entry_in_body(self, body_part: str, new_term: str, new_entry_text: str) -> str:
        """Insert the new entry in alphabetical order in the body."""
        new_sort_key = sort_key_ignore_punct(new_term)
        logger.info(f"Inserting '{new_term}' with sort key: '{new_sort_key}'")
        
        # Split body into lines and find insertion point
        lines = body_part.split('\n')
        insertion_line = len(lines)  # Default to end
        
        i = 0
        in_complex_entry = False
        
        while i < len(lines):
            line = lines[i].strip()
            
            # Track if we're inside a complex entry block
            if line.startswith('-----'):
                in_complex_entry = not in_complex_entry
                i += 1
                continue
            
            # Skip empty lines
            if not line:
                i += 1
                continue
            
            # Skip etymology and other metadata lines within complex entries
            if in_complex_entry and (line.startswith('Etymology:') or line.startswith('Ex:') or 
                                   line.startswith('Example:') or line.startswith('Derived Terms:')):
                i += 1
                continue
            
            # Try to extract term from this line
            term = self._extract_term_from_line(line)
            if term:
                term_sort_key = sort_key_ignore_punct(term)
                logger.info(f"Comparing '{new_term}' ({new_sort_key}) with '{term}' ({term_sort_key})")
                
                if new_sort_key < term_sort_key:
                    # Insert before this entry
                    insertion_line = i
                    
                    # If this is part of a complex entry, go back to the start of it
                    if in_complex_entry:
                        # Find the previous separator line
                        j = i - 1
                        while j >= 0 and not lines[j].strip().startswith('-----'):
                            j -= 1
                        if j >= 0:
                            insertion_line = j
                    
                    logger.info(f"Found insertion point at line {insertion_line}")
                    break
            
            i += 1
        
        # Insert the new entry
        if insertion_line < len(lines):
            # Add spacing before if needed
            if insertion_line > 0 and lines[insertion_line - 1].strip() != "":
                lines.insert(insertion_line, "")
                insertion_line += 1
            
            # Insert the new entry
            entry_lines = new_entry_text.split('\n')
            for j, entry_line in enumerate(entry_lines):
                lines.insert(insertion_line + j, entry_line)
            
            # Add spacing after if needed
            next_line_index = insertion_line + len(entry_lines)
            if next_line_index < len(lines) and lines[next_line_index].strip() != "":
                lines.insert(next_line_index, "")
        else:
            # Add at the end
            if lines and lines[-1].strip() != "":
                lines.append("")
            entry_lines = new_entry_text.split('\n')
            lines.extend(entry_lines)
            lines.append("")
        
        return '\n'.join(lines)

    def _extract_term_from_line(self, line: str) -> Optional[str]:
        """Extract the main term from a line for sorting purposes."""
        # Handle complex entries that might start with just the term
        line = line.strip()
        
        # Try standard pattern first: term (pos) - definition
        match = re.match(ENTRY_PATTERN, line)
        if match:
            raw_term = match.group(1)
            # Remove pronunciation markers to get clean term
            term = re.sub(r'/[^/]+/', '', raw_term)  # Remove /phonetic/
            term = re.sub(r'\(pronounced:\s*[^)]+\)', '', term, flags=re.IGNORECASE)
            term = re.sub(r'\[[^\]]+\]', '', term)
            return term.strip()
        
        # Try to handle lines that just have the term followed by (pos) - definition
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
        
        # Try to extract term from lines that might not follow exact pattern
        # Look for pattern: word (anything) - anything
        simple_match = re.match(r'^([^(]+?)\s*\([^)]+\)\s*-', line)
        if simple_match:
            term = simple_match.group(1).strip()
            # Clean pronunciation markers
            term = re.sub(r'/[^/]+/', '', term)
            term = re.sub(r'\(pronounced:\s*[^)]+\)', '', term, flags=re.IGNORECASE)
            term = re.sub(r'\[[^\]]+\]', '', term)
            return term.strip()
        
        return None