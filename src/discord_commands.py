# src/discord_commands.py

import discord
import os
import random
import re
import pytz
from datetime import datetime
from typing import TYPE_CHECKING, List
from discord.ext import commands
from .dictionary_parser import count_dictionary_entries

# To avoid circular imports for type hinting
if TYPE_CHECKING:
    from .dictionary_manager import DictionaryManager

from .config import GITHUB_OWNER, GITHUB_REPO, logger

class DictionaryCommands(commands.Cog):
    def __init__(self, bot: commands.Bot, dict_manager: "DictionaryManager"):
        self.bot = bot
        self.dict_manager = dict_manager
        logger.info("DictionaryCommands cog initialized.")

    @commands.command(name='getversion')
    async def get_version(self, ctx: commands.Context, version_arg: str = "latest"):
        """Sends a specific dictionary version file to the channel."""
        version = version_arg
        if version_arg.lower() == "latest":
            version = self.dict_manager.find_latest_version()
            await ctx.send(f"📖 Sending latest version: {version}")
        else:
            # Allow formats like "1.2.4" instead of requiring "v1.2.4"
            if not version_arg.startswith('v'):
                version = f"v{version_arg}"
            else:
                version = version_arg

        content = self.dict_manager.get_dictionary_content(version)
        if content:
            filename = self.dict_manager.get_filename(version)
            temp_filepath = f"/tmp/{filename}"
            with open(temp_filepath, "w", encoding="utf-8") as f:
                f.write(content)
            await ctx.send(file=discord.File(temp_filepath))
            os.remove(temp_filepath)
        else:
            await ctx.send(f"Version `{version_arg}` not found.")

    @commands.command(name='stats')
    async def show_stats(self, ctx: commands.Context):
        """Displays dictionary statistics."""
        latest = self.dict_manager.find_latest_version()
        content = self.dict_manager.get_dictionary_content(latest)

        if not content:
            await ctx.send("No dictionary file found to get stats from.")
            return

        corpus = self.dict_manager.get_all_corpus(latest)
        corpus_count = len(corpus)
        entry_count = count_dictionary_entries(content)
        ety_count = content.count("Etymology:")
        size_kb = round(len(content.encode('utf-8')) / 1024, 1)

        cdt = pytz.timezone('America/Chicago')
        now = datetime.now(cdt)
        formatted_datetime = now.strftime("%B %d, %Y %I:%M %p CDT")

        stats_msg = f"""📊 **Unicyclist Dictionary Statistics** as of {formatted_datetime}:

**Latest Version:** {latest}
**Corpus Terms:** {corpus_count:,}
**Dictionary Entries:** {entry_count:,}
**Entries with Etymology:** {ety_count:,}
**File Size:** {size_kb} KB
**Storage:** GitHub Repository
**GitHub Repo:** `{GITHUB_OWNER}/{GITHUB_REPO}`"""

        await ctx.send(stats_msg)

    @commands.command(name='random')
    async def show_random_entry(self, ctx: commands.Context):
        """Displays a random dictionary entry."""
        latest = self.dict_manager.find_latest_version()
        entries = self.dict_manager.get_all_entries(latest)

        if not entries:
            await ctx.send("No entries found in the dictionary.")
            return

        random_entry = random.choice(entries)
        result = random_entry.to_string()

        # Clean up display of complex entries for Discord
        if result.startswith("---------------------------------------------"):
            lines = result.split('\n')
            clean_lines = [line for line in lines if not line.strip().startswith("---------------------------------------------")]
            result = '\n'.join(clean_lines).strip()

        await ctx.send(f"{result}")

    @commands.command(name='search')
    async def search_entries(self, ctx: commands.Context, *, query: str):
        """Searches for dictionary entries by term or definition.
        Usage: 
        !search <query> - search terms only (default)
        !search -d <query> - search definitions only  
        !search -a <query> - search both terms and definitions
        """
        # Parse flags
        search_terms = True
        search_definitions = False
        
        if query.startswith('-d '):
            search_terms = False
            search_definitions = True
            query = query[3:]  # Remove the '-d ' flag
        elif query.startswith('-a '):
            search_terms = True
            search_definitions = True
            query = query[3:]  # Remove the '-a ' flag
        # Default behavior (no flag) searches terms only
        
        latest = self.dict_manager.find_latest_version()
        content = self.dict_manager.get_dictionary_content(latest)
        
        if not content:
            await ctx.send("No dictionary content found.")
            return
        
        # Extract dictionary proper section
        if "-----DICTIONARY PROPER-----" not in content:
            await ctx.send("Dictionary format not recognized.")
            return
        
        dict_section = content.split("-----DICTIONARY PROPER-----", 1)[1]
        
        # Find all matches directly in the raw content
        matches = []
        lines = dict_section.split('\n')
        current_entry = []
        
        for line in lines:
            stripped = line.strip()
            
            # If we hit hyphens, we're starting or ending an entry block
            if stripped.startswith('-----') and len(stripped) > 10:
                if current_entry:
                    # Process the accumulated entry
                    entry_text = '\n'.join(current_entry)
                    if self._matches_search_criteria(entry_text, query, search_terms, search_definitions):
                        matches.append(entry_text.strip())
                    current_entry = []
                # Start collecting the new entry (including the hyphens)
                current_entry = [line]
            elif current_entry:
                # We're inside an entry block
                current_entry.append(line)
            elif stripped and not stripped.startswith('-----'):
                # This might be a simple entry (no hyphens)
                if self._matches_search_criteria(stripped, query, search_terms, search_definitions):
                    matches.append(stripped)
        
        # Don't forget the last entry if we were building one
        if current_entry:
            entry_text = '\n'.join(current_entry)
            if self._matches_search_criteria(entry_text, query, search_terms, search_definitions):
                matches.append(entry_text.strip())
        
        if not matches:
            search_type = "definitions" if not search_terms else "terms" if not search_definitions else "terms and definitions"
            await ctx.send(f"🔍 No matches found for '{query}' in {search_type}.")
            return
        
        # Format and send results
        result_intro = ""
        shown_matches = []
        if len(matches) > 5:
            result_intro = f"🔍 Found {len(matches)} matches for '{query}' (showing first 5):\n\n"
            shown_matches = matches[:5]
        else:
            result_intro = f"🔍 Found {len(matches)} match{'es' if len(matches) > 1 else ''} for '{query}':\n\n"
            shown_matches = matches
        
        match_strings = []
        for match in shown_matches:
            # Clean up the display
            cleaned = match.replace('---------------------------------------------', '').strip()
            if cleaned:
                match_strings.append(f"```{cleaned}```")
        
        result = result_intro + "\n\n".join(match_strings)
        
        if len(matches) > 5:
            result += f"\n\n...and {len(matches)-5} more"
        
        if len(result) > 2000:
            result = result[:1950] + "...\n*Message truncated due to Discord character limit*"
        
        await ctx.send(result)
    
    def _matches_search_criteria(self, text: str, query: str, search_terms: bool, search_definitions: bool) -> bool:
        """Helper method to check if text matches search criteria."""
        text_lower = text.lower()
        query_lower = query.lower()
        
        if search_terms and not search_definitions:
            # Extract term from the text for term-only search
            term = self._extract_term_from_text(text)
            return term and query_lower in term.lower()
        elif search_definitions and not search_terms:
            # Search in definitions only - look after the " - " part
            if ' - ' in text:
                definition_part = text.split(' - ', 1)[1]
                return query_lower in definition_part.lower()
            return False
        else:
            # Search both terms and definitions
            return query_lower in text_lower
    
    def _extract_term_from_text(self, text: str) -> str:
        """Extract the main term from entry text."""
        # Look for the main entry line (not etymology, examples, etc.)
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if not line or line.startswith(('Etymology:', 'Ex:', '- ', 'Derived')):
                continue
            
            # Skip hyphen lines
            if line.startswith('-----'):
                continue
            
            # Check if this looks like a main entry line
            # Try to find the pattern: term(...) - definition OR term(...) 
            
            # First, handle entries with " - " (standard format)
            if ' - ' in line:
                left_part = line.split(' - ')[0].strip()
                # Find the actual term by taking everything before the last opening parenthesis
                # that's followed by what looks like a part of speech
                
                # Common parts of speech to look for
                pos_patterns = [r'\(n\.\)', r'\(adj\.\)', r'\(v\.\)', r'\(inter\.\)', r'\(adv\.\)', 
                               r'\(mass n\.\)', r'\(prep\.\)', r'\(conj\.\)', r'\(pron\.\)']
                
                # Work backwards to find the last POS marker
                for pos_pattern in pos_patterns:
                    if re.search(pos_pattern, left_part):
                        # Split at the last occurrence of this pattern
                        parts = re.split(pos_pattern, left_part)
                        if len(parts) >= 1:
                            term_part = parts[0].strip()
                            # Clean up term part
                            term_part = re.sub(r'/[^/]+/', '', term_part)  # Remove phonetics
                            term_part = re.sub(r'\(pronounced:\s*[^)]+\)', '', term_part, flags=re.IGNORECASE)
                            # Remove any trailing (alt. ...) parts
                            term_part = re.sub(r'\s*\(alt\..*?\)\s*$', '', term_part)
                            return term_part.strip()
                
                # Fallback: just take everything before the first parenthesis
                if '(' in left_part:
                    term_part = left_part.split('(')[0].strip()
                    term_part = re.sub(r'/[^/]+/', '', term_part)
                    term_part = re.sub(r'\(pronounced:\s*[^)]+\)', '', term_part, flags=re.IGNORECASE)
                    return term_part.strip()
            
            # Handle entries without " - " (like "seil (alt. seyl) (inter.)")
            elif '(' in line and ')' in line:
                # Look for the last parenthesis that contains a part of speech
                pos_patterns = [r'\(n\.\)', r'\(adj\.\)', r'\(v\.\)', r'\(inter\.\)', r'\(adv\.\)', 
                               r'\(mass n\.\)', r'\(prep\.\)', r'\(conj\.\)', r'\(pron\.\)']
                
                for pos_pattern in pos_patterns:
                    if re.search(pos_pattern, line):
                        # Split at this pattern and take everything before it
                        parts = re.split(pos_pattern, line)
                        if len(parts) >= 1:
                            term_part = parts[0].strip()
                            # Clean up term part
                            term_part = re.sub(r'/[^/]+/', '', term_part)  # Remove phonetics  
                            term_part = re.sub(r'\(pronounced:\s*[^)]+\)', '', term_part, flags=re.IGNORECASE)
                            # Remove any (alt. ...) parts
                            term_part = re.sub(r'\s*\(alt\..*?\)\s*$', '', term_part)
                            return term_part.strip()
                
                # Fallback for entries with parentheses but no clear POS
                term_part = line.split('(')[0].strip()
                term_part = re.sub(r'/[^/]+/', '', term_part)
                term_part = re.sub(r'\(pronounced:\s*[^)]+\)', '', term_part, flags=re.IGNORECASE)
                if term_part:
                    return term_part.strip()
        
        return ""    

    @commands.command(name='debug_search')
    async def debug_search(self, ctx: commands.Context, *, query: str):
        """Debug search to see what terms are being extracted."""
        latest = self.dict_manager.find_latest_version()
        content = self.dict_manager.get_dictionary_content(latest)
        
        if "-----DICTIONARY PROPER-----" not in content:
            await ctx.send("Dictionary format not recognized.")
            return
        
        dict_section = content.split("-----DICTIONARY PROPER-----", 1)[1]
        
        # Find entries that might contain the query and show what terms are extracted
        debug_info = []
        lines = dict_section.split('\n')
        current_entry = []
        
        for line in lines:
            stripped = line.strip()
            
            if stripped.startswith('-----') and len(stripped) > 10:
                if current_entry:
                    entry_text = '\n'.join(current_entry)
                    if query.lower() in entry_text.lower():
                        extracted_term = self._extract_term_from_text(entry_text)
                        debug_info.append(f"Entry: {entry_text[:100]}...")
                        debug_info.append(f"Extracted term: '{extracted_term}'")
                        debug_info.append("---")
                    current_entry = []
                current_entry = [line]
            elif current_entry:
                current_entry.append(line)
            elif stripped and query.lower() in stripped.lower():
                extracted_term = self._extract_term_from_text(stripped)
                debug_info.append(f"Simple entry: {stripped}")
                debug_info.append(f"Extracted term: '{extracted_term}'")
                debug_info.append("---")
        
        if current_entry:
            entry_text = '\n'.join(current_entry)
            if query.lower() in entry_text.lower():
                extracted_term = self._extract_term_from_text(entry_text)
                debug_info.append(f"Entry: {entry_text[:100]}...")
                debug_info.append(f"Extracted term: '{extracted_term}'")
        
        if debug_info:
            result = "\n".join(debug_info)
            if len(result) > 1900:
                result = result[:1900] + "..."
            await ctx.send(f"```{result}```")
        else:
            await ctx.send(f"No entries found containing '{query}'")
        
    @commands.command(name='versions')
    async def list_versions(self, ctx: commands.Context):
        """Lists all available dictionary versions."""
        files = self.dict_manager.github.list_dictionary_files()
        if not files:
            await ctx.send("No dictionary versions found on GitHub.")
            return

        versions_with_sizes = []
        for filename in files:
            m = re.search(r"v\.?(\d+)\.(\d+)\.(\d+)", filename, re.IGNORECASE)
            if m:
                version = f"v{m.group(1)}.{m.group(2)}.{m.group(3)}"
                content = self.dict_manager.get_dictionary_content(version)
                file_size = round(len(content.encode('utf-8')) / 1024, 1) if content else 0
                versions_with_sizes.append((version, file_size))

        versions_with_sizes.sort(key=lambda x: [int(i) for i in x[0][1:].split('.')])

        version_list = [f"**{v[0]}** ({v[1]} KB)" for v in versions_with_sizes]
        version_text = "\n".join(version_list)

        msg = f"""{version_text}
Use `!getversion <X.X.X>` to show any version."""

        await ctx.send(msg)

    @commands.command(name='help')
    async def send_help_message(self, ctx: commands.Context):
        """Sends the help message for the bot."""
        help_msg = f"""📖 **Dictionary Bot Commands:**

`!getversion [version]` - Download a specific version or latest (default)
`!stats` - Show dictionary statistics
`!random` - Show a random dictionary entry
`!search <query>` - Search for terms containing the query
`!search -d <query>` - Search definitions only
`!search -a <query>` - Search both terms and definitions
`!versions` - List all available versions with added terms
`!help` - Show this help message

📝 **Entry Formats for Adding New Terms:**

**Simple Entry:**
`word (n) - definition`

**With Pronunciation:**
`word /pronunciation/ (adj) - definition`

**Complex Entry with Etymology:**
```
Etymology: from Latin whatever
word (v) - definition
- Example: This is how you use it
```"""
        await ctx.send(help_msg)
