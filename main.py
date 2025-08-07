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


def sort_key_ignore_punct(s: str) -> str:
    # Strip leading punctuation, return lowercase remaining string
    # Extract just the term (before the first space and parenthesis)
    term = s.split(' (')[0] if ' (' in s else s
    return term.lstrip(" '-\"").lower()


class DictionaryEntry:
    def __init__(self, term, pos, definition, etymology=None, examples=None, raw_content=None):
        self.term = term
        self.pos = pos
        self.definition = definition
        self.etymology = etymology
        self.examples = examples or []
        self.raw_content = raw_content  # Store original formatting
    
    def to_string(self):
        """Convert entry to string format for file output"""
        if self.raw_content:
            # Use the original raw content if available (preserves exact formatting)
            return self.raw_content
        
        if self.etymology or self.examples:
            # Entry with etymology/examples needs hyphen separators
            result = "---------------------------------------------\n"
            if self.etymology:
                result += f"Etymology: {self.etymology}\n\n"
            result += f"{self.term} ({self.pos}) - {self.definition}"
            if self.examples:
                for example in self.examples:
                    result += f"\n{example}"
            result += "\n---------------------------------------------"
            return result
        else:
            # Simple entry
            return f"{self.term} ({self.pos}) - {self.definition}"


def parse_dictionary_entries(content):
    """Parse dictionary content into DictionaryEntry objects"""
    entries = []
    
    if "-----DICTIONARY PROPER-----" not in content:
        return entries
    
    body = content.split("-----DICTIONARY PROPER-----\n\n", 1)[1]
    
    # Split the content more carefully to preserve formatting
    sections = []
    current_section = []
    lines = body.split('\n')
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        if line.strip() == "---------------------------------------------":
            if current_section:
                sections.append('\n'.join(current_section).strip())
                current_section = []
            
            # Start collecting hyphen section
            hyphen_section = [line]
            i += 1
            
            while i < len(lines):
                hyphen_section.append(lines[i])
                if lines[i].strip() == "---------------------------------------------":
                    sections.append('\n'.join(hyphen_section))
                    break
                i += 1
        else:
            current_section.append(line)
        
        i += 1
    
    # Add any remaining content
    if current_section:
        remaining = '\n'.join(current_section).strip()
        if remaining:
            # Split by double newlines for simple entries
            simple_entries = [e.strip() for e in remaining.split('\n\n') if e.strip()]
            sections.extend(simple_entries)
    
    # Parse each section
    for section in sections:
        if not section.strip():
            continue
            
        if section.strip().startswith("---------------------------------------------"):
            # Complex entry with etymology/examples
            entry = parse_complex_entry(section)
            if entry:
                entries.append(entry)
        else:
            # Simple entry
            match = re.match(ENTRY_PATTERN, section.strip())
            if match:
                term, pos, definition = match.groups()
                entries.append(DictionaryEntry(term, pos, definition, raw_content=section.strip()))
    
    return entries


def parse_complex_entry(text):
    """Parse a complex entry with etymology and/or examples"""
    lines = text.split('\n')
    etymology = None
    term = pos = definition = None
    examples = []
    
    i = 0
    collecting_etymology = False
    etymology_lines = []
    
    while i < len(lines):
        line = lines[i].strip()
        
        if line.startswith("Etymology:"):
            collecting_etymology = True
            ety_text = line[10:].strip()
            etymology_lines = [ety_text] if ety_text else []
            
        elif collecting_etymology and line and not line.startswith("-----") and not re.match(ENTRY_PATTERN, line):
            etymology_lines.append(lines[i])
            
        elif re.match(ENTRY_PATTERN, line):
            # Main entry line
            if collecting_etymology and etymology_lines:
                etymology = '\n'.join(etymology_lines).strip()
                collecting_etymology = False
            
            match = re.match(ENTRY_PATTERN, line)
            term, pos, definition = match.groups()
            
        elif line.startswith("Ex") and ":" in line and term:
            # Example line
            examples.append(line)
            
        elif line and not line.startswith("-----") and term and not re.match(ENTRY_PATTERN, line):
            # Additional content (could be examples, notes, etc.)
            examples.append(line)
        
        i += 1
    
    if term and pos and definition:
        return DictionaryEntry(term, pos, definition, etymology, examples, text)
    return None


async def get_added_term_for_version(version):
    """Get the term that was added in a specific version by comparing with previous version"""
    try:
        # Parse version number
        m = re.search(r"v\.?(\d+)\.(\d+)\.(\d+)", version, re.IGNORECASE)
        if not m:
            return None
        
        major, minor, patch = map(int, m.groups())
        if patch == 0:
            return None  # Can't get previous version
            
        # Get previous version
        prev_version = f"v{major}.{minor}.{patch-1}"
        
        current_path = get_filename(version)
        prev_path = get_filename(prev_version)
        
        if not os.path.exists(current_path) or not os.path.exists(prev_path):
            return None
        
        # Read both files and compare corpus
        with open(current_path, "r", encoding="utf-8") as f:
            current_content = f.read()
        with open(prev_path, "r", encoding="utf-8") as f:
            prev_content = f.read()
        
        # Extract corpus from both
        current_corpus = set()
        prev_corpus = set()
        
        current_match = re.search(r"Corpus:\s*(.*?)\s*\n\n", current_content, re.DOTALL | re.IGNORECASE)
        if current_match:
            current_corpus = {t.strip() for t in current_match.group(1).split(",") if t.strip()}
        
        prev_match = re.search(r"Corpus:\s*(.*?)\s*\n\n", prev_content, re.DOTALL | re.IGNORECASE)
        if prev_match:
            prev_corpus = {t.strip() for t in prev_match.group(1).split(",") if t.strip()}
        
        # Find the difference
        added_terms = current_corpus - prev_corpus
        if added_terms:
            return list(added_terms)[0]  # Return the first (should be only one)
            
    except Exception as e:
        print(f"[DEBUG] Error getting added term for {version}: {e}")
    
    return None


async def add_entry(term, pos, definition, ety_lines=None, example_lines=None):
    # Use CDT timezone
    cdt = pytz.timezone('America/Chicago')
    now = datetime.now(cdt)
    timestamp = now.strftime("%B %d, %Y %I:%M %p CDT")
    print(f"[DEBUG] New term: '{term}' at {timestamp}")

    latest = await find_latest_version()
    old_path = get_filename(latest)
    print(f"[DEBUG] Reading from: {old_path}")

    corpus = []
    entries = []

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
            content = f.read()

        # Parse corpus
        corpus_match = re.search(r"Corpus:\s*(.*?)\s*\n\n", content,
                                 re.DOTALL | re.IGNORECASE)
        if corpus_match:
            corpus = [
                t.strip() for t in corpus_match.group(1).split(",")
                if t.strip()
            ]
        print(f"[DEBUG] Corpus loaded: {len(corpus)} terms")

        # Parse existing entries
        entries = parse_dictionary_entries(content)
        print(f"[DEBUG] Entries loaded: {len(entries)} items")
    else:
        print("[DEBUG] No existing file – starting fresh.")

    # Check if term already exists
    if any(term.lower() == e.term.lower() for e in entries):
        print(f"[DEBUG] Term '{term}' exists—skipping.")
        return

    # Add to corpus and sort
    corpus.append(term)
    corpus = sorted(set(corpus), key=sort_key_ignore_punct)
    print(f"[DEBUG] Corpus sorted: {len(corpus)} terms")

    # Create new entry
    etymology = "\n".join(ety_lines).strip() if ety_lines else None
    examples = example_lines if example_lines else []
    new_entry = DictionaryEntry(term, pos, definition, etymology, examples)
    
    # Add to entries and sort
    entries.append(new_entry)
    entries.sort(key=lambda e: sort_key_ignore_punct(e.term))
    print(f"[DEBUG] Entries sorted: {len(entries)} items")

    if etymology:
        print(f"[DEBUG] Etymology stored for '{term}'")
    if examples:
        print(f"[DEBUG] Examples stored for '{term}': {len(examples)}")

    # Build the new file content
    content = f"{FILE_PREFIX} {new_version} - {timestamp}\n\nCorpus:\n" + ", ".join(corpus) + "\n\n"
    content += "-----DICTIONARY PROPER-----\n\n"
    
    # Add all entries in order
    entry_strings = []
    for entry in entries:
        entry_strings.append(entry.to_string())
    
    content += "\n\n".join(entry_strings) + "\n\n"

    new_path = get_filename(new_version)
    with open(new_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[DEBUG] Wrote new file: {new_path}")
    print(f"[DEBUG] File exists check: {os.path.exists(new_path)}")


@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    print(f"[DEBUG] Current working directory: {os.getcwd()}")
    print(f"[DEBUG] Files in current directory: {os.listdir('.')}")

    # Send connection message to the first available channel
    for guild in client.guilds:
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                try:
                    msg = await channel.send("Dictionary bot connected and ready.")
                    await msg.delete(delay=2)  # Auto-delete after 2 seconds
                    print(f"[DEBUG] Sent connection message to #{channel.name}")
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
            # Default to latest if no version specified
            ver = command_parts[1] if len(command_parts) >= 2 else "latest"
            await send_version(msg.channel, ver)
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

        elif command == "!versions":
            await list_versions(msg.channel)
            return

        elif command == "!help":
            help_msg = """Dictionary Bot Commands:

`!getversion [version]` - Download a specific version or latest (default)
`!stats` - Show dictionary statistics
`!random` - Show a random dictionary entry
`!search <query>` - Search for terms containing the query (includes etymology)
`!versions` - List all available versions with added terms
`!help` - Show this help message

**Adding Entries:**
```
(Optional) Etymology: origin information
Term (noun) - the definition
(Optional) Ex: example usage
```"""
            await msg.channel.send(help_msg)
            return

        # If it's a command we don't recognize, just return silently
        return

    # Handle dictionary entry additions (non-command messages)
    lines = [line.strip() for line in msg.content.splitlines() if line.strip()]
    if not lines:
        return

    # Look for dictionary entry pattern in any line
    term, pos, definition, ety, examples = None, None, None, None, []

    for i, line in enumerate(lines):
        m = re.match(ENTRY_PATTERN, line)
        if m:
            term, pos, definition = m.groups()
            print(f"[DEBUG] Found entry: {term} ({pos}) - {definition}")
            break

    if not term:
        return  # No dictionary entry found

    # Look for etymology and examples in the message
    ety_lines = []
    example_lines = []
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
            collecting_ety = False
        elif line.startswith("Ex") and ":" in line:
            # Example line
            example_lines.append(line)

    # Clean up lines
    if ety_lines:
        ety = [line for line in ety_lines if line.strip()]
        print(f"[DEBUG] Found etymology: {len(ety)} lines")
    
    if example_lines:
        print(f"[DEBUG] Found examples: {len(example_lines)} lines")

    await add_entry(term, pos, definition, ety, example_lines)
    # React to the user's message 
    await msg.add_reaction('✅')
    await asyncio.sleep(4)
    await msg.remove_reaction('✅', client.user)


async def send_version(channel, version):
    if version.lower() == "latest":
        version = await find_latest_version()
        await channel.send(f"📖 Sending latest version: {version}")

    path = get_filename(version)
    if os.path.exists(path):
        await channel.send(file=discord.File(path))
    else:
        await channel.send(f"Version `{version}` not found.")


async def show_stats(channel):
    latest = await find_latest_version()
    path = get_filename(latest)

    if not os.path.exists(path):
        await channel.send("No dictionary file found.")
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
File Size: {size_kb} KB""" 

    await channel.send(stats_msg) 


async def show_random_entry(channel):
    latest = await find_latest_version()
    path = get_filename(latest)

    if not os.path.exists(path):
        await channel.send("No dictionary file found.")
        return

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    entries = parse_dictionary_entries(content)

    if not entries:
        await channel.send("No entries found.")  
        return

    import random
    random_entry = random.choice(entries)

    result = random_entry.to_string()
    
    # Clean up the result for display (remove separating hyphens)
    if result.startswith("---------------------------------------------"):
        lines = result.split('\n')
        clean_lines = []
        for line in lines:
            if not line.strip().startswith("---------------------------------------------"):
                clean_lines.append(line)
        result = '\n'.join(clean_lines).strip()

    await channel.send(result)


async def search_entries(channel, query):
    latest = await find_latest_version()
    path = get_filename(latest)

    if not os.path.exists(path):
        await channel.send("No dictionary file found.") 
        return

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    entries = parse_dictionary_entries(content)

    # Search only in terms and definitions (NOT etymology)
    matches = []
    for entry in entries:
        # Search in term
        if query.lower() in entry.term.lower():
            matches.append(entry)
        # Search in definition  
        elif query.lower() in entry.definition.lower():
            matches.append(entry)

    if not matches:
        await channel.send(f"No matches found for '{query}'.")
        return

    if len(matches) > 5:
        result = f"Found {len(matches)} matches for '{query}' (showing first 5):\n\n"
        shown_matches = matches[:5]
        result += f"\n\n...and {len(matches)-5} more"
    else:
        result = f"Found {len(matches)} match{'es' if len(matches) > 1 else ''} for '{query}':\n\n"
        shown_matches = matches

    # Format matches for display
    match_strings = []
    for entry in shown_matches:
        entry_str = f"{entry.term} ({entry.pos}) - {entry.definition}"
        if entry.etymology:
            entry_str += f"\nEtymology: {entry.etymology}"
        if entry.examples:
            entry_str += "\n" + "\n".join(entry.examples)
        match_strings.append(entry_str)

    result += "\n\n".join(match_strings)

    if len(result) > 2000:  # Discord message limit
        result = result[:1950] + "...\nMessage truncated"

    await channel.send(result)


async def list_versions(channel):
    files = [
        f for f in os.listdir(FILE_FOLDER)
        if f.startswith(FILE_PREFIX) and f.endswith(FILE_EXTENSION)
    ]

    if not files:
        await channel.send("No dictionary versions found.")
        return

    versions = []
    for f in files:
        m = re.search(r"v\.?(\d+)\.(\d+)\.(\d+)", f, re.IGNORECASE)
        if m:
            version = f"v{m.group(1)}.{m.group(2)}.{m.group(3)}"
            file_size = round(
                os.path.getsize(os.path.join(FILE_FOLDER, f)) / 1024, 1)
            
            # Get the added term for this version
            added_term = await get_added_term_for_version(version)
            versions.append((version, file_size, added_term))

    # Sort versions
    versions.sort(key=lambda x: [int(i) for i in x[0][1:].split('.')])

    version_list = []
    for v in versions:
        line = f"{v[0]} ({v[1]} KB)"
        if v[2]:  # If we found an added term
            line += f" - added '{v[2]}'"
        version_list.append(line)
    
    version_text = "\n".join(version_list)
    latest = versions[-1][0] if versions else "Unknown"

    msg = f"""Available Dictionary Versions:

{version_text}

Latest: {latest}
Use `!getversion <vX.X.X>` to download any version."""

    await channel.send(msg)


client.run(os.environ['DISCORD_TOKEN'])
