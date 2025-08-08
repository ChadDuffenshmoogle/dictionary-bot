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

    def add_entry(self, term: str, pos: str, definition: str, ety_lines: Optional[List[str]] = None, example_lines: Optional[List[str]] = None, pronunciation: Optional[str] = None, additional_info: Optional[List[str]] = None) -> bool:
        """Adds a new entry to the dictionary, updates version, and uploads to GitHub."""
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

        # Parse existing data
        corpus = self.get_all_corpus(latest)
        entries = self.get_all_entries(latest)

        logger.info(f"Loaded {len(corpus)} corpus terms and {len(entries)} entries for version {latest}")

        # Check if term already exists (case-insensitive)
        if any(term.lower() == e.term.lower() for e in entries):
            logger.warning(f"Term '{term}' already exists—skipping addition.")
            return False

        # Determine new version (increment patch)
        m = re.search(r"v\.?(\d+)\.(\d+)\.(\d+)", latest, re.IGNORECASE)
        if m:
            major, minor, patch = map(int, m.groups())
            new_version = f"v{major}.{minor}.{patch+1}"
        else:
            new_version = "v1.2.5" # Fallback if regex fails

        # Add to corpus and sort
        corpus.append(term)
        corpus = sorted(set(corpus), key=sort_key_ignore_punct)

        # Create new DictionaryEntry object
        etymology = "\n".join(ety_lines).strip() if ety_lines else None
        examples = example_lines if example_lines else []
        new_entry = DictionaryEntry(term, pos, definition, etymology, examples)

        # Add to entries and sort
        entries.append(new_entry)
        entries.sort(key=lambda e: sort_key_ignore_punct(e.term))

        # Build new file content
        new_header = f"{FILE_PREFIX} {new_version} - {timestamp}"
        content = f"{new_header}\n\nCorpus: " + ", ".join(corpus) + "\n\n-----DICTIONARY PROPER-----\n\n"

        entry_strings = [entry.to_string() for entry in entries]
        content += "\n\n".join(entry_strings)
        if not content.endswith('\n\n'):
            content += '\n\n'

        # Upload to GitHub
        filename = self.get_filename(new_version)
        commit_message = f"Add dictionary {new_version} with new term '{term}'"

        success = self.github.create_or_update_file(filename, content, commit_message)

        if success:
            # Clear cache to force refresh for new version
            self._cache.clear()
            logger.info(f"Successfully created {filename}")
            return True
        else:
            logger.error(f"Failed to upload {filename}")
            return False