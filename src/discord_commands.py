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

from wordcloud import WordCloud
import matplotlib.pyplot as plt
from io import BytesIO

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
            query = query[3:]
        elif query.startswith('-a '):
            search_terms = True
            search_definitions = True
            query = query[3:]
        
        latest = self.dict_manager.find_latest_version()
        content = self.dict_manager.get_dictionary_content(latest)
        
        if not content:
            await ctx.send("No dictionary content found.")
            return
        
        if "-----DICTIONARY PROPER-----" not in content:
            await ctx.send("Dictionary format not recognized.")
            return
        
        dict_section = content.split("-----DICTIONARY PROPER-----", 1)[1]
        
        # Just search every line that looks like it has a dictionary entry
        matches = []
        lines = dict_section.split('\n')
        
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith('-----'):
                continue
                
            # Check if this line looks like a dictionary entry
            if ('(' in stripped and ')' in stripped) and (stripped.startswith('-') or ' - ' in stripped or stripped.endswith(')')):
                # Extract the term from this line
                term = self._extract_term_from_line(stripped)
                
                if search_terms and not search_definitions:
                    # Term search only
                    if term and query.lower() in term.lower():
                        matches.append(stripped)
                elif search_definitions and not search_terms:
                    # Definition search only
                    if ' - ' in stripped:
                        definition = stripped.split(' - ', 1)[1]
                        if query.lower() in definition.lower():
                            matches.append(stripped)
                else:
                    # Search both
                    if query.lower() in stripped.lower():
                        matches.append(stripped)
        
        if not matches:
            search_type = "definitions" if not search_terms else "terms" if not search_definitions else "terms and definitions"
            await ctx.send(f"🔍 No matches found for '{query}' in {search_type}.")
            return
        
        # Format results
        if len(matches) > 5:
            result_intro = f"🔍 Found {len(matches)} matches for '{query}' (showing first 5):\n\n"
            shown_matches = matches[:5]
        else:
            result_intro = f"🔍 Found {len(matches)} match{'es' if len(matches) > 1 else ''} for '{query}':\n\n"
            shown_matches = matches
        
        match_strings = [f"```{match}```" for match in shown_matches]
        result = result_intro + "\n\n".join(match_strings)
        
        if len(matches) > 5:
            result += f"\n\n...and {len(matches)-5} more"
        
        if len(result) > 2000:
            result = result[:1950] + "...\n*Message truncated*"
        
        await ctx.send(result)
    
    def _extract_term_from_line(self, line: str) -> str:
        """Extract term from a single line."""
        # Handle bullet points
        if line.strip().startswith('- '):
            line = line.strip()[2:]
        
        # Find everything before the first opening parenthesis
        if '(' in line:
            term_part = line.split('(')[0].strip()
            # Remove phonetics like /phonetic/
            term_part = re.sub(r'/[^/]+/', '', term_part)
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

    @commands.command(name='debug')
    async def debug_bot(self, ctx: commands.Context):
        """Debug command to check bot connectivity and GitHub access."""
        debug_msg = "🔧 **Bot Debug Information:**\n\n"
        
        # Test GitHub connection
        debug_msg += "**GitHub API Test:**\n"
        try:
            connection_ok = self.dict_manager.github.test_connection()
            if connection_ok:
                debug_msg += "✅ GitHub API connection successful\n"
            else:
                debug_msg += "❌ GitHub API connection failed\n"
        except Exception as e:
            debug_msg += f"❌ GitHub API connection error: {str(e)}\n"
        
        debug_msg += "\n**Repository Files:**\n"
        try:
            files = self.dict_manager.github.list_dictionary_files()
            if files:
                debug_msg += f"✅ Found {len(files)} dictionary files:\n"
                for file in files[:10]:  # Show first 10 files
                    debug_msg += f"  • {file}\n"
                if len(files) > 10:
                    debug_msg += f"  ... and {len(files) - 10} more\n"
            else:
                debug_msg += "❌ No dictionary files found\n"
        except Exception as e:
            debug_msg += f"❌ Error listing files: {str(e)}\n"
        
        debug_msg += "\n**Version Detection:**\n"
        try:
            latest_version = self.dict_manager.find_latest_version()
            debug_msg += f"✅ Latest version detected: {latest_version}\n"
            
            # Try to get content for this version
            content = self.dict_manager.get_dictionary_content(latest_version)
            if content:
                debug_msg += f"✅ Successfully loaded content ({len(content)} chars)\n"
                
                # Check corpus
                corpus = self.dict_manager.get_all_corpus(latest_version)
                debug_msg += f"✅ Corpus loaded: {len(corpus)} terms\n"
            else:
                debug_msg += "❌ Failed to load dictionary content\n"
                
        except Exception as e:
            debug_msg += f"❌ Error detecting version: {str(e)}\n"
        
        # Environment check
        debug_msg += "\n**Environment:**\n"
        import os
        github_token_set = bool(os.environ.get('YOUR_GITHUB_PAT'))
        discord_token_set = bool(os.environ.get('DISCORD_TOKEN'))
        
        debug_msg += f"{'✅' if github_token_set else '❌'} GitHub token set: {github_token_set}\n"
        debug_msg += f"{'✅' if discord_token_set else '❌'} Discord token set: {discord_token_set}\n"
        
        # If message is too long, split it
        if len(debug_msg) > 2000:
            # Send in parts
            parts = [debug_msg[i:i+1900] for i in range(0, len(debug_msg), 1900)]
            for i, part in enumerate(parts):
                if i == 0:
                    await ctx.send(part)
                else:
                    await ctx.send(f"**Debug Info (continued {i+1}):**\n{part}")
        else:
            await ctx.send(debug_msg)

    @commands.command(name='wordcloud')
    async def generate_wordcloud(self, ctx: commands.Context, num_words: int = 100):
        """Generates a word cloud from random dictionary terms.
        Usage: !wordcloud [num_words] - defaults to 100 words
        """
        await ctx.send("🎨 Generating word cloud...")
        
        try:
            latest = self.dict_manager.find_latest_version()
            corpus = self.dict_manager.get_all_corpus(latest)
            
            if not corpus:
                await ctx.send("No terms found in the dictionary corpus.")
                return
            
            # Limit num_words to reasonable range
            num_words = max(10, min(num_words, len(corpus)))
            
            # Get random sample of terms
            selected_terms = random.sample(corpus, num_words)
            
            # Convert multi-word terms to single tokens by replacing spaces with underscores
            # This keeps phrases together in the word cloud
            tokenized_terms = [term.replace(' ', '_') for term in selected_terms]
            text = ' '.join(tokenized_terms)
            
            # Generate word cloud
            wordcloud = WordCloud(
                width=1200, 
                height=600,
                background_color='white',
                colormap='viridis',
                relative_scaling=0.5,
                min_font_size=10,
                regexp=r'\S+'  # This treats underscored phrases as single words
            ).generate(text)
            
            # Replace underscores back with spaces in the final image
            # We do this by regenerating with the underscore-replaced version
            wordcloud_dict = wordcloud.words_
            cleaned_dict = {k.replace('_', ' '): v for k, v in wordcloud_dict.items()}
            
            wordcloud_final = WordCloud(
                width=1200, 
                height=600,
                background_color='white',
                colormap='viridis',
                relative_scaling=0.5,
                min_font_size=10
            ).generate_from_frequencies(cleaned_dict)
            
            # Create the plot
            plt.figure(figsize=(12, 6))
            plt.imshow(wordcloud_final, interpolation='bilinear')
            plt.axis('off')
            plt.tight_layout(pad=0)
            
            # Save to bytes buffer
            buffer = BytesIO()
            plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
            buffer.seek(0)
            plt.close()
            
            # Send to Discord
            await ctx.send(
                f"☁️ Word cloud with {num_words} random terms:",
                file=discord.File(buffer, 'wordcloud.png')
            )
            
        except Exception as e:
            logger.error(f"Error generating word cloud: {str(e)}")
            await ctx.send(f"❌ Error generating word cloud: {str(e)}")
