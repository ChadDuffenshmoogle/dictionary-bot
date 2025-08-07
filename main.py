import discord
import re
from datetime import datetime
import os
import pytz
import asyncio

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

BASE_VERSION = "v1.2.4"
FILE_PREFIX = "UNICYCLIST DICTIONARY"
FILE_EXTENSION = ".txt"
FILE_FOLDER = "."  # change if using other directory

ENTRY_PATTERN = r'^(.+?) \((.+?)\) - (.+)$'
ETYMOLOGY_START = "Etymology:"


def get_filename(version):
    return os.path.join(FILE_FOLDER,
                        f"{FILE_PREFIX} {version}{FILE_EXTENSION}")


async def find_latest_version():
    files = [
        f for f in os.listdir(FILE_FOLDER)
        if f.startswith(FILE_PREFIX) and f.endswith(FILE_EXTENSION)
    ]
    max_version = BASE_VERSION
    max_nums = [1, 2, 4]
    for f in files:
        m = re.search(r"v\.?(\d+)\.(\d+)\.(\d+)", f, re.IGNORECASE)
        if m:
            nums = list(map(int, m.groups()))
            if nums > max_nums:
                max_nums, max_version = nums, f"v{nums[0]}.{nums[1]}.{nums[2]}"
    print(f"[DEBUG] Latest version detected: {max_version}")
    return max_version


async def delete_with_countdown(message, delay):
    """Delete a message after a countdown"""
    original_content = message.content
    for i in range(3, 0, -1):
        await asyncio.sleep(1)
        await message.edit(content=f"{original_content} ({i})")
    await asyncio.sleep(1)
    await message.delete()


def sort_key_ignore_punct(s: str) -> str:
    # Strip leading punctuation, return lowercase remaining string
    # Extract just the term (before the first space and parenthesis)
    term = s.split(' (')[0] if ' (' in s else s
    return term.lstrip(" '-").lower()


async def add_entry(term, pos, definition, ety_lines=None):
    # Use CDT timezone
    cdt = pytz.timezone('America/Chicago')
    now = datetime.now(cdt)
    timestamp = now.strftime("%B %d, %Y %I:%M %p CDT")
    print(f"[DEBUG] New term: '{term}' at {timestamp}")

    latest = await find_latest_version()
    old_path = get_filename(latest)
    print(f"[DEBUG] Reading from: {old_path}")

    # Use dictionaries to store entries and etymologies keyed by lowercased term for uniqueness
    parsed_entries_map = {}  # {lower_term: original_full_entry_string}
    ety_map = {}  # {lower_term: etymology_text}
    corpus_terms = set()  # Use a set for unique corpus terms

    # Determine the new version by incrementing the latest version
    m = re.search(r"v\.?(\d+)\.(\d+)\.(\d+)", latest, re.IGNORECASE)
    if m:
        major, minor, patch = map(int, m.groups())
        new_version = f"v{major}.{minor}.{patch+1}"
        print(f"[DEBUG] New version will be: {new_version}")
    else:
        new_version = "v1.2.5"  # Default increment from BASE_VERSION
        print(f"[DEBUG] Using default new version: {new_version}")

    if os.path.exists(old_path):
        with open(old_path, "r", encoding="utf-8") as f:
            c = f.read()

        # --- PARSING EXISTING FILE CONTENT ---

        # 1. Parse Corpus
        corpus_match = re.search(r"Corpus:\s*(.*?)\s*\n\n", c,
                                 re.DOTALL | re.IGNORECASE)
        if corpus_match:
            corpus_terms.update(t.strip() for t in corpus_match.group(1).split(",") if t.strip())
        print(f"[DEBUG] Corpus loaded: {len(corpus_terms)} terms")

        # 2. Parse Entries and Etymologies from the Dictionary Proper section
        # Find the start of the dictionary proper section
        dict_proper_start_idx = c.find("-----DICTIONARY PROPER-----")
        if dict_proper_start_idx != -1:
            dict_content = c[dict_proper_start_idx + len("-----DICTIONARY PROPER-----"):].strip()

            # Split the content by the etymology separator to get blocks
            blocks = re.split(r'^-+$', dict_content, flags=re.MULTILINE) # Split by lines of only hyphens

            current_term_for_ety = None
            current_ety_text = []

            for block in blocks:
                lines = [line.strip() for line in block.split('\n') if line.strip()]
                if not lines:
                    continue

                is_etymology_block = False
                temp_entry_line = None

                for line in lines:
                    if line.startswith("Etymology:"):
                        is_etymology_block = True
                        current_ety_text.append(line[10:].strip()) # Collect etymology text
                    elif re.match(ENTRY_PATTERN, line):
                        match = re.match(ENTRY_PATTERN, line)
                        if match:
                            term_from_entry = match.group(1)
                            parsed_entries_map[term_from_entry.lower()] = line
                            corpus_terms.add(term_from_entry) # Add to corpus from parsed entry

                            if is_etymology_block and current_ety_text:
                                ety_map[term_from_entry.lower()] = "\n".join(current_ety_text).strip()
                                current_ety_text = [] # Reset for next etymology
                            is_etymology_block = False # Reset flag after processing entry
                    elif is_etymology_block:
                        current_ety_text.append(line) # Continue collecting etymology lines

            print(f"[DEBUG] Entries loaded: {len(parsed_entries_map)} items")
            print(f"[DEBUG] Etymologies parsed: {len(ety_map)} terms")
    else:
        print("[DEBUG] No existing file – starting fresh.")

    # --- ADD/UPDATE NEW ENTRY ---
    new_entry_string = f"{term} ({pos}) - {definition}"

    # Add or update the new entry in the map
    if term.lower() in parsed_entries_map:
        print(f"[DEBUG] Term '{term}' exists in parsed map—updating definition.")
        parsed_entries_map[term.lower()] = new_entry_string # Overwrite if exists
    else:
        print(f"[DEBUG] Adding new term '{term}' to parsed map.")
        parsed_entries_map[term.lower()] = new_entry_string
        corpus_terms.add(term) # Add to corpus only if it's a genuinely new term

    # Add or update etymology for the new term
    if ety_lines:
        ety_map[term.lower()] = "\n".join(ety_lines).strip()
        print(f"[DEBUG] Etymology stored/updated for '{term}'")

    # --- PREPARE FOR WRITING ---
    # Sort the unique terms for consistent dictionary order
    # Use the original casing from the stored entry for sorting, otherwise just the term
    sorted_unique_terms_keys = sorted(parsed_entries_map.keys(), key=lambda k: sort_key_ignore_punct(parsed_entries_map.get(k, k)))

    # Reconstruct the entries list from the map, in sorted order, using original casing
    final_sorted_entries = [parsed_entries_map[key] for key in sorted_unique_terms_keys]
    final_corpus = sorted(list(corpus_terms), key=sort_key_ignore_punct) # Ensure corpus is sorted and from set

    # --- BUILD THE NEW FILE CONTENT ---
    content = f"{FILE_PREFIX} {new_version} - {timestamp}\n\nCorpus:\n" + ", ".join(
        final_corpus) + "\n\n"

    content += "-----DICTIONARY PROPER-----\n\n"

    dictionary_proper_content_parts = []
    for entry_string in final_sorted_entries:
        match = re.match(ENTRY_PATTERN, entry_string)
        if match:
            current_term = match.group(1) # Get the term using its original casing from the entry string
            if current_term.lower() in ety_map: # Check if this term has an etymology
                dictionary_proper_content_parts.append("---------------------------------------------")
                dictionary_proper_content_parts.append(f"Etymology: {ety_map[current_term.lower()]}")
                dictionary_proper_content_parts.append(entry_string)
                dictionary_proper_content_parts.append("---------------------------------------------")
            else:
                dictionary_proper_content_parts.append(entry_string)

    content += "\n\n".join(dictionary_proper_content_parts) + "\n\n" # Join all parts with double newlines

    new_path = get_filename(new_version)
    with open(new_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[DEBUG] Wrote new file: {new_path}")


@client.event
async def on_ready():
    print(f"Logged in as {client.user}")

    # Send connection message to the first available channel
    for guild in client.guilds:
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                try:
                    msg = await channel.send(
                        "Dictionary bot connected and ready.") # Removed fluff
                    # await msg.delete(delay=2) # Removed auto-deletion
                    print(
                        f"[DEBUG] Sent connection message to #{channel.name}")
                    return  # Only send to one channel
                except discord.errors.Forbidden:
                    continue


@client.event
async def on_message(msg):
    if msg.author.bot: 
        return

    # Handle all bot commands first
    if msg.content.startswith("!"):
        command_parts = msg.content.split()
        command = command_parts[0].lower()

        if command == "!getversion":
            ver = command_parts[1] if len(command_parts) == 2 else None
            # send_version is not defined in the original code,
            # assuming it was intended to send the file directly.
            # For this request, we'll just acknowledge if it were defined.
            await msg.channel.send("Command '!getversion' functionality (sending file) is not implemented in this snippet.") # Removed delete_after
            return

        elif command == "!stats":
            await show_stats(msg.channel)
            return

        elif command == "!random":
            await show_random_entry(msg.channel)
            return

        elif command == "!search":
            if len(command_parts) < 2:
                await msg.channel.send("Usage: `!search <query>`")
                return
            query = " ".join(command_parts[1:])
            await search_entries(msg.channel, query)
            return

        elif command == "!define":
            if len(command_parts) < 2:
                await msg.channel.send("Usage: `!define <term>`")
                return
            query = " ".join(command_parts[1:])
            await define_term(msg.channel, query)
            return

        elif command == "!versions":
            await list_versions(msg.channel)
            return

        elif command == "!help":
            help_msg = """Dictionary Bot Commands:

`!getversion <version>` - Download a specific version (or `latest`)
`!stats` - Show dictionary statistics
`!random` - Show a random dictionary entry
`!search <query>` - Search for terms containing the query
`!define <term>` - Look up a specific term
`!versions` - List all available versions
`!help` - Show this help message

Adding Entries:
Type: `Term (part of speech) - definition`""" # Removed optional etymology section
            await msg.channel.send(help_msg) # Removed delete_after
            return

        # If it's a command we don't recognize, just return silently
        return

    # Handle dictionary entry additions (non-command messages)
    lines = [line.strip() for line in msg.content.splitlines() if line.strip()]
    if not lines:
        return

    # Look for dictionary entry pattern in any line
    term, pos, definition, ety = None, None, None, None

    for i, line in enumerate(lines):
        m = re.match(ENTRY_PATTERN, line)
        if m:
            term, pos, definition = m.groups()
            print(f"[DEBUG] Found entry: {term} ({pos}) - {definition}")
            break

    if not term:
        return  # No dictionary entry found

    # Look for etymology in the message
    ety_lines = []
    collecting_ety = False

    for line in lines:
        if line.startswith("Etymology:"):
            collecting_ety = True
            ety_text = line[10:].strip()  # Remove "Etymology: "
            if ety_text:
                ety_lines.append(ety_text)
        elif collecting_ety and line and not re.match(ENTRY_PATTERN, line):
            # Continue collecting etymology until we hit another entry or end
            if not line.startswith(("-----", "——————")):
                ety_lines.append(line)
        elif collecting_ety and re.match(ENTRY_PATTERN, line):
            # Hit another entry, stop collecting etymology
            break

    # Clean up etymology lines
    if ety_lines:
        ety = [line for line in ety_lines if line.strip()]
        print(f"[DEBUG] Found etymology: {len(ety)} lines")

    await add_entry(term, pos, definition, ety)
    # React to the user's message instead of sending a new one
    await msg.add_reaction('✅') # Use the unicode emoji for :white_check_mark:
    await asyncio.sleep(4) # Wait for 4 seconds
    try:
        await msg.remove_reaction('✅', client.user) # Remove the bot's reaction
    except discord.errors.Forbidden:
        print(f"[DEBUG] Could not remove reaction from message {msg.id}. Bot lacks permissions.")


async def show_stats(channel):
    latest = await find_latest_version()
    path = get_filename(latest)

    if not os.path.exists(path):
        await channel.send("No dictionary file found.") # Removed fluff
        return

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Count corpus terms (this will be the 'Entries' count)
    corpus_match = re.search(r"Corpus:\s*(.*?)\s*\n\n", content,
                             re.DOTALL | re.IGNORECASE)
    corpus_count = 0
    if corpus_match:
        corpus = [
            t.strip() for t in corpus_match.group(1).split(",") if t.strip()
        ]
        corpus_count = len(corpus)

    # Count etymologies
    ety_count = content.count("Etymology:")

    # File size
    file_size = os.path.getsize(path)
    size_kb = round(file_size / 1024, 1)

    # Get current date and time in CDT
    cdt = pytz.timezone('America/Chicago')
    now = datetime.now(cdt)
    formatted_datetime = now.strftime("%B %d, %Y %I:%M %p CDT")

    stats_msg = f"""Unicyclist Dictionary Statistics as of {formatted_datetime}:

Latest Version: {latest}
Entries: {corpus_count}
Entries with Etymology: {ety_count}
File Size: {size_kb} KB

Use `!getversion latest` to download the current version.""" # Removed fluff, adjusted wording

    await channel.send(stats_msg) # Removed delete_after


async def show_random_entry(channel):
    latest = await find_latest_version()
    path = get_filename(latest)

    if not os.path.exists(path):
        await channel.send("No dictionary file found.") # Removed fluff
        return

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    entries = []
    if "-----DICTIONARY PROPER-----" in content:
        dict_proper_start_idx = content.find("-----DICTIONARY PROPER-----")
        if dict_proper_start_idx != -1:
            dict_content = content[dict_proper_start_idx + len("-----DICTIONARY PROPER-----"):].strip()

            # Extract individual entries, skipping etymology and separator lines
            lines = [line.strip() for line in dict_content.split('\n') if line.strip()]
            for line in lines:
                if re.match(ENTRY_PATTERN, line):
                    entries.append(line)

    if not entries:
        await channel.send("No entries found.") # Removed fluff
        return

    import random
    random_entry = random.choice(entries)

    await channel.send(f"Random Entry:\n{random_entry}") # Removed fluff, removed delete_after


async def search_entries(channel, query):
    latest = await find_latest_version()
    path = get_filename(latest)

    if not os.path.exists(path):
        await channel.send("No dictionary file found.") # Removed fluff
        return

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    entries = []
    if "-----DICTIONARY PROPER-----" in content:
        dict_proper_start_idx = content.find("-----DICTIONARY PROPER-----")
        if dict_proper_start_idx != -1:
            dict_content = content[dict_proper_start_idx + len("-----DICTIONARY PROPER-----"):].strip()

            lines = [line.strip() for line in dict_content.split('\n') if line.strip()]
            for line in lines:
                if re.match(ENTRY_PATTERN, line):
                    entries.append(line)

    # Search only for terms
    matches = []
    for entry in entries:
        match = re.match(ENTRY_PATTERN, entry)
        if match:
            term = match.group(1) # Get just the term
            if query.lower() in term.lower():
                matches.append(entry)

    if not matches:
        await channel.send(f"No terms found containing '{query}'.") # Removed fluff
        return

    if len(matches) > 5:
        result = f"Found {len(matches)} matches for '{query}' (showing first 5):\n\n" # Removed fluff
        result += "\n\n".join(matches[:5])
        result += f"\n\n...and {len(matches)-5} more"
    else:
        result = f"Found {len(matches)} match{'es' if len(matches) > 1 else ''} for '{query}':\n\n" # Removed fluff
        result += "\n\n".join(matches)

    if len(result) > 2000:  # Discord message limit
        result = result[:1950] + "...\nMessage truncated" # Removed fluff

    await channel.send(result) # Removed delete_after


async def define_term(channel, query):
    latest = await find_latest_version()
    path = get_filename(latest)

    if not os.path.exists(path):
        await channel.send("No dictionary file found.") # Removed fluff
        return

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    entries_map_for_define = {} # {lower_term: full_entry_string}
    etymologies_for_define = {} # {lower_term: etymology_text}

    if "-----DICTIONARY PROPER-----" in content:
        dict_proper_start_idx = content.find("-----DICTIONARY PROPER-----")
        if dict_proper_start_idx != -1:
            dict_content = content[dict_proper_start_idx + len("-----DICTIONARY PROPER-----"):].strip()

            blocks = re.split(r'^-+$', dict_content, flags=re.MULTILINE)

            current_term_for_ety = None
            current_ety_text = []
            is_etymology_block = False

            for block in blocks:
                lines = [line.strip() for line in block.split('\n') if line.strip()]
                if not lines:
                    continue

                for line in lines:
                    if line.startswith("Etymology:"):
                        is_etymology_block = True
                        current_ety_text.append(line[10:].strip())
                    elif re.match(ENTRY_PATTERN, line):
                        match = re.match(ENTRY_PATTERN, line)
                        if match:
                            term_from_entry = match.group(1)
                            entries_map_for_define[term_from_entry.lower()] = line

                            if is_etymology_block and current_ety_text:
                                etymologies_for_define[term_from_entry.lower()] = "\n".join(current_ety_text).strip()
                                current_ety_text = []
                            is_etymology_block = False
                    elif is_etymology_block:
                        current_ety_text.append(line)

    # Search for exact or partial matches
    exact_matches = []
    partial_matches = []

    for term_lower, full_entry_string in entries_map_for_define.items():
        match = re.match(ENTRY_PATTERN, full_entry_string)
        if match:
            term_original_case, pos, definition = match.groups()
            if term_lower == query.lower():
                exact_matches.append((term_original_case, pos, definition, full_entry_string))
            elif query.lower() in term_lower:
                partial_matches.append((term_original_case, pos, definition, full_entry_string))

    if not exact_matches and not partial_matches:
        await channel.send(f"No definition found for '{query}'.") # Removed fluff
        return

    result = ""

    if exact_matches:
        result += f"Definition for '{query}':\n\n" # Removed fluff
        for term, pos, definition, full_entry in exact_matches:
            if term.lower() in etymologies_for_define:
                result += f"Etymology: {etymologies_for_define[term.lower()]}\n"
            result += f"{term} ({pos}) - {definition}\n\n" # Added extra line break

    if partial_matches and not exact_matches:
        result += f"Similar terms to '{query}':\n\n" # Removed fluff
        for term, pos, definition, full_entry in partial_matches[:
                                                                 3]:  # Limit to 3
            if term.lower() in etymologies_for_define:
                result += f"Etymology: {etymologies_for_define[term.lower()]}\n"
            result += f"{term} ({pos}) - {definition}\n\n" # Added extra line break

        if len(partial_matches) > 3:
            result += f"...and {len(partial_matches)-3} more similar terms\n" # Removed fluff

    if len(result) > 2000:
        result = result[:1950] + "...\nMessage truncated" # Removed fluff

    await channel.send(result) # Removed delete_after


async def list_versions(channel):
    files = [
        f for f in os.listdir(FILE_FOLDER)
        if f.startswith(FILE_PREFIX) and f.endswith(FILE_EXTENSION)
    ]

    if not files:
        await channel.send("No dictionary versions found.") # Removed fluff
        return

    versions = []
    for f in files:
        m = re.search(r"v\.?(\d+)\.(\d+)\.(\d+)", f, re.IGNORECASE)
        if m:
            version = f"v{m.group(1)}.{m.group(2)}.{m.group(3)}"
            file_size = round(
                os.path.getsize(os.path.join(FILE_FOLDER, f)) / 1024, 1)
            versions.append((version, file_size))

    # Sort versions
    versions.sort(key=lambda x: [int(i) for i in x[0][1:].split('.')])

    version_list = "\n".join([f"{v[0]} ({v[1]} KB)" for v in versions]) # Simplified list format
    latest = versions[-1][0] if versions else "Unknown"

    msg = f"""Available Dictionary Versions:

{version_list}

Latest: {latest}
Use `!getversion <version>` to download any version.""" # Removed fluff

    await channel.send(msg) # Removed delete_after


client.run(os.environ['DISCORD_TOKEN'])