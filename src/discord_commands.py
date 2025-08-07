import discord
import os
import random
import pytz
from datetime import datetime
from typing import TYPE_CHECKING, List

# To avoid circular imports for type hinting
if TYPE_CHECKING:
    from .dictionary_manager import DictionaryManager

from .config import GITHUB_OWNER, GITHUB_REPO, logger # Import from config

async def send_version(channel: discord.TextChannel, dict_manager: "DictionaryManager", version_arg: str):
    """Sends a specific dictionary version file to the channel."""
    version = version_arg
    if version_arg.lower() == "latest":
        version = dict_manager.find_latest_version()
        await channel.send(f"📖 Sending latest version: {version}")

    content = dict_manager.get_dictionary_content(version)
    if content:
        filename = dict_manager.get_filename(version)
        # Use /tmp for writing files in ephemeral environments like Fly.io
        temp_filepath = f"/tmp/{filename}"
        with open(temp_filepath, "w", encoding="utf-8") as f:
            f.write(content)
        await channel.send(file=discord.File(temp_filepath))
        os.remove(temp_filepath) # Clean up the temporary file
    else:
        await channel.send(f"Version `{version_arg}` not found.")

async def show_stats(channel: discord.TextChannel, dict_manager: "DictionaryManager"):
    """Displays dictionary statistics."""
    latest = dict_manager.find_latest_version()
    content = dict_manager.get_dictionary_content(latest)

    if not content:
        await channel.send("No dictionary file found to get stats from.")
        return

    corpus = dict_manager.get_all_corpus(latest)
    corpus_count = len(corpus)
    ety_count = content.count("Etymology:") # Assuming "Etymology:" prefix indicates an etymology

    size_kb = round(len(content.encode('utf-8')) / 1024, 1)

    cdt = pytz.timezone('America/Chicago')
    now = datetime.now(cdt)
    formatted_datetime = now.strftime("%B %d, %Y %I:%M %p CDT")

    stats_msg = f"""📊 **Unicyclist Dictionary Statistics** as of {formatted_datetime}:

**Latest Version:** {latest}
**Entries:** {corpus_count:,}
**Entries with Etymology:** {ety_count:,}
**File Size:** {size_kb} KB
**Storage:** GitHub Repository
**GitHub Repo:** `{GITHUB_OWNER}/{GITHUB_REPO}`"""

    await channel.send(stats_msg)

async def show_random_entry(channel: discord.TextChannel, dict_manager: "DictionaryManager"):
    """Displays a random dictionary entry."""
    latest = dict_manager.find_latest_version()
    entries = dict_manager.get_all_entries(latest)

    if not entries:
        await channel.send("No entries found in the dictionary.")
        return

    random_entry = random.choice(entries)
    result = random_entry.to_string()

    # Clean up display of complex entries for Discord
    if result.startswith("---------------------------------------------"):
        lines = result.split('\n')
        clean_lines = [line for line in lines if not line.strip().startswith("---------------------------------------------")]
        result = '\n'.join(clean_lines).strip()

    await channel.send(f"🎲 **Random Entry:**\n{result}")

async def search_entries(channel: discord.TextChannel, dict_manager: "DictionaryManager", query: str):
    """Searches for dictionary entries by term or definition."""
    latest = dict_manager.find_latest_version()
    entries = dict_manager.get_all_entries(latest)

    matches = [
        entry for entry in entries
        if query.lower() in entry.term.lower() or query.lower() in entry.definition.lower()
    ]

    if not matches:
        await channel.send(f"🔍 No matches found for '{query}'.")
        return

    result_intro = ""
    shown_matches: List[dict] = []
    if len(matches) > 5:
        result_intro = f"🔍 Found {len(matches)} matches for '{query}' (showing first 5):\n\n"
        shown_matches = matches[:5]
    else:
        result_intro = f"🔍 Found {len(matches)} match{'es' if len(matches) > 1 else ''} for '{query}':\n\n"
        shown_matches = matches

    match_strings = []
    for entry in shown_matches:
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

    await channel.send(result)

async def list_versions(channel: discord.TextChannel, dict_manager: "DictionaryManager"):
    """Lists all available dictionary versions."""
    files = dict_manager.github.list_dictionary_files()
    if not files:
        await channel.send("No dictionary versions found on GitHub.")
        return

    versions_with_sizes = []
    for filename in files:
        m = re.search(r"v\.?(\d+)\.(\d+)\.(\d+)", filename, re.IGNORECASE)
        if m:
            version = f"v{m.group(1)}.{m.group(2)}.{m.group(3)}"
            # Fetch content to get size - this can be slow if many versions
            content = dict_manager.get_dictionary_content(version)
            file_size = round(len(content.encode('utf-8')) / 1024, 1) if content else 0
            versions_with_sizes.append((version, file_size))

    versions_with_sizes.sort(key=lambda x: [int(i) for i in x[0][1:].split('.')])

    version_list = [f"**{v[0]}** ({v[1]} KB)" for v in versions_with_sizes]
    version_text = "\n".join(version_list)
    latest = versions_with_sizes[-1][0] if versions_with_sizes else "Unknown"

    msg = f"""📚 **Available Dictionary Versions:**

{version_text}

**Latest:** {latest}
Use `!getversion <vX.X.X>` to download any version.
🐙 **GitHub:** `{GITHUB_OWNER}/{GITHUB_REPO}`"""

    await channel.send(msg)

async def send_help_message(channel: discord.TextChannel):
    """Sends the help message for the bot."""
    help_msg = f"""📖 **Dictionary Bot Commands:**

`!getversion [version]` - Download a specific version or latest (default)
`!stats` - Show dictionary statistics
`!random` - Show a random dictionary entry
`!search <query>` - Search for terms containing the query
`!versions` - List all available versions with added terms
`!help` - Show this help message

**Adding Entries:**
```
(Optional) Etymology: origin information
Term (noun) - the definition
(Optional) Ex: example usage
```

**🐙 GitHub Integration:** All versions stored at `{GITHUB_OWNER}/{GITHUB_REPO}`
**📊 Logging:** Use `fly logs` to view bot activity"""
            await msg.channel.send(help_msg)
