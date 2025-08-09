# src/dictionary_manager.py
import re
import pytz
from datetime import datetime
from typing import Optional, List
from .github_api import GitHubAPI # Import GitHubAPI with relative import
from .dictionary_parser import DictionaryEntry, parse_dictionary_entries, get_corpus_from_content, sort_key_ignore_punct # Import parsing functions and class
from .config import BASE_VERSION, FILE_PREFIX, FILE_EXTENSION, logger # Import from config with relative import

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

    # Updated add_entry method for src/dictionary_manager.py

def add_entry(self, term: str, pos: str, definition: str, ety_lines: Optional[List[str]] = None, 
              example_lines: Optional[List[str]] = None, pronunciation: Optional[str] = None, 
              additional_info: Optional[List[str]] = None) -> bool:
    """Adds a new entry by ONLY appending to existing content, preserving all original formatting."""
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

    # Add to corpus and sort (this is the only thing we modify)
    new_corpus = corpus + [term]
    new_corpus = sorted(set(new_corpus), key=sort_key_ignore_punct)

    # Create new entry with standard formatting
    etymology = "\n".join(ety_lines).strip() if ety_lines else None
    examples = example_lines if example_lines else []
    new_entry = DictionaryEntry(term, pos, definition, etymology, examples, pronunciation=pronunciation, additional_info=additional_info)

    # Find where to insert the new entry alphabetically in the original content
    # We'll do this by finding the right insertion point and adding it there
    
    # Split the original content into parts
    if "-----DICTIONARY PROPER-----\n\n" in latest_content:
        header_part, body_part = latest_content.split("-----DICTIONARY PROPER-----\n\n", 1)
        
        # Update header with new version and timestamp
        new_header_line = f"{FILE_PREFIX} {new_version} - {timestamp}"
        # Replace the first line of header_part with new header
        header_lines = header_part.split('\n')
        header_lines[0] = new_header_line
        
        # Update corpus in header
        corpus_line_index = None
        for i, line in enumerate(header_lines):
            if line.strip().startswith("Corpus:"):
                corpus_line_index = i
                break
        
        if corpus_line_index is not None:
            header_lines[corpus_line_index] = "Corpus: " + ", ".join(new_corpus)
        
        new_header = '\n'.join(header_lines)
        
        # Find insertion point for new entry in body
        # We need to find where this entry should go alphabetically
        insertion_point = find_insertion_point_in_body(body_part, term)
        
        if insertion_point is not None:
            # Insert at the specific location
            body_before = body_part[:insertion_point]
            body_after = body_part[insertion_point:]
            
            # Add the new entry
            new_entry_text = new_entry.to_string()
            if not body_before.endswith('\n\n'):
                body_before += '\n\n'
            if not body_after.startswith('\n\n'):
                new_entry_text += '\n\n'
            
            new_body = body_before + new_entry_text + body_after
        else:
            # Append at the end
            new_entry_text = new_entry.to_string()
            if not body_part.endswith('\n\n'):
                body_part += '\n\n'
            new_body = body_part + new_entry_text + '\n\n'
        
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

    def find_insertion_point_in_body(body: str, new_term: str) -> Optional[int]:
        """Find where to insert a new entry alphabetically in the existing body."""
        
        # Get the sort key for the new term
        new_sort_key = sort_key_ignore_punct(new_term)
        
        # Find all entry positions and their sort keys
        entry_positions = []
        
        # Look for hyphen-separated entries
        for match in re.finditer(r'-{20,}', body):
            start_pos = match.start()
            # Find the next hyphen block
            next_match = re.search(r'-{20,}', body[match.end():])
            if next_match:
                end_pos = match.end() + next_match.end()
                entry_block = body[start_pos:end_pos]
                
                # Try to extract the term from this block
                term = extract_main_term_from_block(entry_block)
                if term:
                    sort_key = sort_key_ignore_punct(term)
                    entry_positions.append((start_pos, sort_key, term))
        
        # Also look for simple entries (lines matching the pattern)
        for match in re.finditer(ENTRY_PATTERN, body, re.MULTILINE):
            line_start = body.rfind('\n', 0, match.start()) + 1
            line_end = body.find('\n', match.end())
            if line_end == -1:
                line_end = len(body)
            
            raw_term = match.group(1)
            term = re.sub(r'/[^/]+/', '', raw_term).strip()  # Remove pronunciation
            sort_key = sort_key_ignore_punct(term)
            entry_positions.append((line_start, sort_key, term))
        
        # Sort by position to maintain order
        entry_positions.sort(key=lambda x: x[0])
        
        # Find insertion point
        for pos, sort_key, term in entry_positions:
            if new_sort_key < sort_key:
                return pos
        
        # If we get here, insert at the end
        return None

    def extract_main_term_from_block(block: str) -> Optional[str]:
        """Extract the main term from an entry block."""
        lines = block.split('\n')
        for line in lines:
            line = line.strip()
            if not line or line.startswith('-'):
                continue
            if line.startswith(('Etymology:', 'Ex:', 'Example:', 'Derived Terms:')):
                continue
            
            # Try to extract term
            match = re.match(ENTRY_PATTERN, line)
            if match:
                raw_term = match.group(1)
                term = re.sub(r'/[^/]+/', '', raw_term).strip()
                return term
        return None