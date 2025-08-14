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
        entries = self.dict_manager.get_all_entries(latest)
    
        matches = []
        for entry in entries:
            match_found = False
            
            if search_terms and query.lower() in entry.term.lower():
                match_found = True
            
            if search_definitions and entry.original_block and query.lower() in entry.original_block.lower():
                match_found = True
            
            if match_found:
                matches.append(entry)
    
        if not matches:
            search_type = "definitions" if not search_terms else "terms" if not search_definitions else "terms and definitions"
            await ctx.send(f"🔍 No matches found for '{query}' in {search_type}.")
            return
    
        # Rest of your existing display logic stays the same
        result_intro = ""
        shown_matches = []
        if len(matches) > 5:
            result_intro = f"🔍 Found {len(matches)} matches for '{query}' (showing first 5):\n\n"
            shown_matches = matches[:5]
        else:
            result_intro = f"🔍 Found {len(matches)} match{'es' if len(matches) > 1 else ''} for '{query}':\n\n"
            shown_matches = matches
    
        match_strings = []
        for entry in shown_matches:
            if entry.original_block and entry.definition == "":
                entry_str = f"```{entry.original_block.strip()}```"
            else:
                entry_str = f"**{entry.term}** ({entry.pos}) - {entry.definition}"
                if entry.etymology:
                    entry_str += f"\n*Etymology: {entry.etymology}*"
                if entry.examples:
                    entry_str += "\n" + "\n".join(entry.examples)
            match_strings.append(entry_str)
    
        result = result_intro + "\n\n".join(match_strings)
    
        if len(matches) > 5:
            result += f"\n\n...and {len(matches)-5} more"
    
        if len(result) > 2000:
            result = result[:1950] + "...\n*Message truncated due to Discord character limit*"
    
        await ctx.send(result)
    
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
