import discord
import re
from datetime import datetime
import os
import pytz
import asyncio
import requests
import base64
import json
from typing import Optional, List, Dict, Any

# Set up logging to stdout (visible in fly logs)
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# Configuration
BASE_VERSION = "v1.2.4"
FILE_PREFIX = "UNICYCLIST DICTIONARY"
FILE_EXTENSION = ".txt"

# GitHub configuration 
GITHUB_OWNER = "ChadDuffenshmoogle"  
GITHUB_REPO = "dictionary-bot"  
GITHUB_BRANCH = "main"
GITHUB_TOKEN = os.environ.get('DISCORD_TOKEN')  # Set this in Fly.io secrets

ENTRY_PATTERN = r'^(.+?) \((.+?)\) - (.+)$'

def sort_key_ignore_punct(s: str) -> str:
    """Strip leading punctuation, return lowercase remaining string"""
    term = s.split(' (')[0] if ' (' in s else s
    return term.lstrip(" '-\"").lower()

class GitHubAPI:
    """Handle all GitHub API interactions"""
    
    def __init__(self, token: str, owner: str, repo: str):
        self.token = token
        self.owner = owner
        self.repo = repo
        self.base_url = f"https://api.github.com/repos/{owner}/{repo}"
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }
    
    def get_file_content(self, filename: str) -> Optional[str]:
        """Get file content from GitHub"""
        try:
            url = f"{self.base_url}/contents/{filename}"
            response = requests.get(url, headers=self.headers)
            
            if response.status_code == 200:
                content = response.json()['content']
                return base64.b64decode(content).decode('utf-8')
            elif response.status_code == 404:
                logger.info(f"File {filename} not found on GitHub")
                return None
            else:
                logger.error(f"GitHub API error getting {filename}: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Error getting file from GitHub: {e}")
            return None
    
    def create_or_update_file(self, filename: str, content: str, message: str) -> bool:
        """Create or update a file on GitHub"""
        try:
            url = f"{self.base_url}/contents/{filename}"
            
            # First, try to get existing file to get its SHA (required for updates)
            existing = requests.get(url, headers=self.headers)
            
            data = {
                "message": message,
                "content": base64.b64encode(content.encode('utf-8')).decode('ascii'),
                "branch": GITHUB_BRANCH
            }
            
            if existing.status_code == 200:
                # File exists, need SHA for update
                data["sha"] = existing.json()["sha"]
            
            response = requests.put(url, headers=self.headers, json=data)
            
            if response.status_code in [200, 201]:
                logger.info(f"Successfully uploaded {filename} to GitHub")
                return True
            else:
                logger.error(f"GitHub API error uploading {filename}: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error uploading file to GitHub: {e}")
            return False
    
    def list_dictionary_files(self) -> List[str]:
        """List all dictionary files in the repo"""
        try:
            url = f"{self.base_url}/contents"
            response = requests.get(url, headers=self.headers)
            
            if response.status_code == 200:
                files = response.json()
                dict_files = [
                    f['name'] for f in files 
                    if f['type'] == 'file' and 
                    f['name'].startswith(FILE_PREFIX) and 
                    f['name'].endswith(FILE_EXTENSION)
                ]
                return dict_files
            else:
                logger.error(f"GitHub API error listing files: {response.status_code}")
                return []
        except Exception as e:
            logger.error(f"Error listing files from GitHub: {e}")
            return []

class DictionaryEntry:
    def __init__(self, term, pos, definition, etymology=None, examples=None, raw_content=None):
        self.term = term
        self.pos = pos
        self.definition = definition
        self.etymology = etymology
        self.examples = examples or []
        self.raw_content = raw_content
    
    def to_string(self):
        """Convert entry to string format for file output"""
        if self.raw_content and not self.etymology and not self.examples:
            return self.raw_content.strip()
        
        if self.etymology or self.examples:
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
            return f"{self.term} ({self.pos}) - {self.definition}"

class DictionaryManager:
    """Manage dictionary operations with GitHub integration"""
    
    def __init__(self, github_api: GitHubAPI):
        self.github = github_api
        self._cache = {}  # Cache file contents to avoid repeated API calls
    
    def find_latest_version(self) -> str:
        """Find the latest version from GitHub"""
        files = self.github.list_dictionary_files()
        
        max_version = BASE_VERSION
        max_nums = [1, 2, 4]
        
        for filename in files:
            m = re.search(r"v\.?(\d+)\.(\d+)\.(\d+)", filename, re.IGNORECASE)
            if m:
                nums = list(map(int, m.groups()))
                if nums > max_nums:
                    max_nums, max_version = nums, f"v{nums[0]}.{nums[1]}.{nums[2]}"
        
        logger.info(f"Latest version detected: {max_version}")
        return max_version
    
    def get_filename(self, version: str) -> str:
        return f"{FILE_PREFIX} {version}{FILE_EXTENSION}"
    
    def get_dictionary_content(self, version: str) -> Optional[str]:
        """Get dictionary content from GitHub (with caching)"""
        filename = self.get_filename(version)
        
        if filename in self._cache:
            return self._cache[filename]
        
        content = self.github.get_file_content(filename)
        if content:
            self._cache[filename] = content
        
        return content
    
    def parse_dictionary_entries(self, content: str) -> List[DictionaryEntry]:
        """Parse dictionary content into DictionaryEntry objects"""
        entries = []
        
        if "-----DICTIONARY PROPER-----" not in content:
            logger.warning("No dictionary proper section found")
            return entries
        
        parts = content.split("-----DICTIONARY PROPER-----\n\n", 1)
        if len(parts) < 2:
            return entries
        
        body = parts[1]
        raw_sections = body.split('\n\n')
        
        i = 0
        while i < len(raw_sections):
            section = raw_sections[i].strip()
            
            if not section:
                i += 1
                continue
            
            # Handle complex entries with separators
            if section.strip() == "---------------------------------------------":
                complex_entry_parts = [section]
                i += 1
                
                while i < len(raw_sections):
                    part = raw_sections[i].strip()
                    complex_entry_parts.append(part)
                    
                    if part == "---------------------------------------------":
                        break
                    i += 1
                
                full_text = '\n\n'.join(complex_entry_parts)
                entry = self.parse_complex_entry(full_text)
                if entry:
                    entries.append(entry)
            
            else:
                # Handle simple entries
                match = re.match(ENTRY_PATTERN, section)
                if match:
                    term, pos, definition = match.groups()
                    entries.append(DictionaryEntry(term, pos, definition, raw_content=section))
                else:
                    # Multi-line simple entry
                    lines = section.split('\n')
                    for line in lines:
                        match = re.match(ENTRY_PATTERN, line.strip())
                        if match:
                            term, pos, definition = match.groups()
                            entries.append(DictionaryEntry(term, pos, definition, raw_content=section))
                            break
            
            i += 1
        
        logger.info(f"Parsed {len(entries)} dictionary entries")
        return entries
    
    def parse_complex_entry(self, text: str) -> Optional[DictionaryEntry]:
        """Parse a complex entry with etymology and/or examples"""
        lines = text.split('\n')
        etymology = None
        term = pos = definition = None
        examples = []
        etymology_lines = []
        collecting_etymology = False
        
        for line in lines:
            line_stripped = line.strip()
            
            if line_stripped == "---------------------------------------------":
                continue
            
            if line_stripped.startswith("Etymology:"):
                collecting_etymology = True
                ety_text = line_stripped[10:].strip()
                etymology_lines = [ety_text] if ety_text else []
                continue
            
            if collecting_etymology and line_stripped and not re.match(ENTRY_PATTERN, line_stripped):
                etymology_lines.append(line.rstrip())
                continue
            
            match = re.match(ENTRY_PATTERN, line_stripped)
            if match:
                if collecting_etymology and etymology_lines:
                    etymology = '\n'.join(etymology_lines).strip()
                    collecting_etymology = False
                
                term, pos, definition = match.groups()
                continue
            
            if term and line_stripped and not line_stripped.startswith("-----"):
                examples.append(line.rstrip())
        
        if collecting_etymology and etymology_lines:
            etymology = '\n'.join(etymology_lines).strip()
        
        if term and pos and definition:
            return DictionaryEntry(term, pos, definition, etymology, examples, text)
        
        return None
    
    def get_corpus_from_content(self, content: str) -> List[str]:
        """Extract corpus from dictionary content"""
        corpus_match = re.search(r"Corpus:\s*(.*?)\s*-----DICTIONARY PROPER-----", content, re.DOTALL | re.IGNORECASE)
        if corpus_match:
            corpus_text = corpus_match.group(1).strip()
            return [t.strip() for t in corpus_text.split(",") if t.strip()]
        return []
    
    def add_entry(self, term: str, pos: str, definition: str, ety_lines: Optional[List[str]] = None, example_lines: Optional[List[str]] = None) -> bool:
        """Add a new entry to the dictionary"""
        cdt = pytz.timezone('America/Chicago')
        now = datetime.now(cdt)
        timestamp = now.strftime("%B %d, %Y %I:%M %p CDT")
        logger.info(f"Adding new term: '{term}' at {timestamp}")

        # Find latest version
        latest = self.find_latest_version()
        latest_content = self.get_dictionary_content(latest)
        
        if not latest_content:
            logger.error(f"Could not get content for version {latest}")
            return False

        # Parse existing data
        corpus = self.get_corpus_from_content(latest_content)
        entries = self.parse_dictionary_entries(latest_content)
        
        logger.info(f"Loaded {len(corpus)} corpus terms and {len(entries)} entries")

        # Check if term already exists
        if any(term.lower() == e.term.lower() for e in entries):
            logger.warning(f"Term '{term}' already exists—skipping.")
            return False

        # Determine new version
        m = re.search(r"v\.?(\d+)\.(\d+)\.(\d+)", latest, re.IGNORECASE)
        if m:
            major, minor, patch = map(int, m.groups())
            new_version = f"v{major}.{minor}.{patch+1}"
        else:
            new_version = "v1.2.5"

        # Add to corpus and sort
        corpus.append(term)
        corpus = sorted(set(corpus), key=sort_key_ignore_punct)

        # Create new entry
        etymology = "\n".join(ety_lines).strip() if ety_lines else None
        examples = example_lines if example_lines else []
        new_entry = DictionaryEntry(term, pos, definition, etymology, examples)
        
        # Add to entries and sort
        entries.append(new_entry)
        entries.sort(key=lambda e: sort_key_ignore_punct(e.term))

        # Build new file content
        new_header = f"{FILE_PREFIX} {new_version} - {timestamp}"
        content = f"{new_header}\n\nCorpus: " + ", ".join(corpus) + "\n\n-----DICTIONARY PROPER-----\n\n"
        
        entry_strings = []
        for entry in entries:
            entry_strings.append(entry.to_string())
        
        content += "\n\n".join(entry_strings)
        if not content.endswith('\n\n'):
            content += '\n\n'

        # Upload to GitHub
        filename = self.get_filename(new_version)
        commit_message = f"Add dictionary {new_version} with new term '{term}'"
        
        success = self.github.create_or_update_file(filename, content, commit_message)
        
        if success:
            # Clear cache to force refresh
            self._cache.clear()
            logger.info(f"Successfully created {new_version}")
            return True
        else:
            logger.error(f"Failed to upload {new_version}")
            return False

# Global dictionary manager (initialized after GitHub token is available)
dict_manager: Optional[DictionaryManager] = None

@client.event
async def on_ready():
    global dict_manager
    
    print(f"🤖 Logged in as {client.user}")
    logger.info(f"Bot started successfully")
    
    # Initialize GitHub API and dictionary manager
    if not GITHUB_TOKEN:
        logger.error("GITHUB_TOKEN not set! Bot will not function properly.")
        return
    
    github_api = GitHubAPI(GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO)
    dict_manager = DictionaryManager(github_api)
    
    # Test GitHub connection
    try:
        latest = dict_manager.find_latest_version()
        logger.info(f"Successfully connected to GitHub. Latest version: {latest}")
    except Exception as e:
        logger.error(f"Failed to connect to GitHub: {e}")

    # Send connection message
    for guild in client.guilds:
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                try:
                    msg = await channel.send("📖 Dictionary bot connected! Using GitHub for storage.")
                    await msg.delete(delay=3)
                    logger.info(f"Sent connection message to #{channel.name}")
                    return
                except discord.errors.Forbidden:
                    continue

@client.event
async def on_message(msg):
    if msg.author.bot or not dict_manager:
        return

    # Handle commands
    if msg.content.startswith("!"):
        command_parts = msg.content.split()
        command = command_parts[0].lower()

        if command == "!getversion":
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
            help_msg = """📖 **Dictionary Bot Commands:**

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
            return

        return

    # Handle dictionary entry additions
    lines = [line.strip() for line in msg.content.splitlines() if line.strip()]
    if not lines:
        return

    # Look for dictionary entry pattern
    term = pos = definition = None
    for line in lines:
        m = re.match(ENTRY_PATTERN, line)
        if m:
            term, pos, definition = m.groups()
            logger.info(f"Found entry: {term} ({pos}) - {definition}")
            break

    if not term:
        return

    # Parse etymology and examples
    ety_lines = []
    example_lines = []
    collecting_ety = False

    for line in lines:
        if line.startswith("Etymology:"):
            collecting_ety = True
            ety_text = line[10:].strip()
            if ety_text:
                ety_lines.append(ety_text)
        elif collecting_ety and line and not re.match(ENTRY_PATTERN, line):
            if not line.startswith(("-----", "——————")):
                ety_lines.append(line)
        elif collecting_ety and re.match(ENTRY_PATTERN, line):
            collecting_ety = False
        elif line.startswith("Ex") and ":" in line:
            example_lines.append(line)

    # Clean up etymology
    if ety_lines:
        ety = [line for line in ety_lines if line.strip()]
        logger.info(f"Found etymology: {len(ety)} lines")
    else:
        ety = None

    if example_lines:
        logger.info(f"Found examples: {len(example_lines)} lines")

    # Add the entry
    try:
        success = dict_manager.add_entry(term, pos, definition, ety, example_lines)
        
        if success:
            await msg.add_reaction('✅')
            await asyncio.sleep(4)
            await msg.remove_reaction('✅', client.user)
        else:
            await msg.add_reaction('❌')
            await asyncio.sleep(4)
            await msg.remove_reaction('❌', client.user)
    
    except Exception as e:
        logger.error(f"Error adding entry: {e}")
        await msg.add_reaction('❌')
        await asyncio.sleep(4)
        await msg.remove_reaction('❌', client.user)

# Command implementations
async def send_version(channel, version):
    if version.lower() == "latest":
        version = dict_manager.find_latest_version()
        await channel.send(f"📖 Sending latest version: {version}")

    content = dict_manager.get_dictionary_content(version)
    if content:
        # Send as file
        filename = dict_manager.get_filename(version)
        with open(f"/tmp/{filename}", "w", encoding="utf-8") as f:
            f.write(content)
        await channel.send(file=discord.File(f"/tmp/{filename}"))
        os.remove(f"/tmp/{filename}")
    else:
        await channel.send(f"Version `{version}` not found.")

async def show_stats(channel):
    latest = dict_manager.find_latest_version()
    content = dict_manager.get_dictionary_content(latest)

    if not content:
        await channel.send("No dictionary file found.")
        return

    # Count corpus terms
    corpus = dict_manager.get_corpus_from_content(content)
    corpus_count = len(corpus)

    # Count etymologies
    ety_count = content.count("Etymology:")

    # File size (approximate)
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

async def show_random_entry(channel):
    latest = dict_manager.find_latest_version()
    content = dict_manager.get_dictionary_content(latest)

    if not content:
        await channel.send("No dictionary file found.")
        return

    entries = dict_manager.parse_dictionary_entries(content)
    if not entries:
        await channel.send("No entries found.")  
        return

    import random
    random_entry = random.choice(entries)
    result = random_entry.to_string()
    
    # Clean up display
    if result.startswith("---------------------------------------------"):
        lines = result.split('\n')
        clean_lines = [line for line in lines if not line.strip().startswith("---------------------------------------------")]
        result = '\n'.join(clean_lines).strip()

    await channel.send(f"🎲 **Random Entry:**\n{result}")

async def search_entries(channel, query):
    latest = dict_manager.find_latest_version()
    content = dict_manager.get_dictionary_content(latest)

    if not content:
        await channel.send("No dictionary file found.") 
        return

    entries = dict_manager.parse_dictionary_entries(content)
    matches = [
        entry for entry in entries 
        if query.lower() in entry.term.lower() or query.lower() in entry.definition.lower()
    ]

    if not matches:
        await channel.send(f"🔍 No matches found for '{query}'.")
        return

    if len(matches) > 5:
        result = f"🔍 Found {len(matches)} matches for '{query}' (showing first 5):\n\n"
        shown_matches = matches[:5]
        result += f"\n\n...and {len(matches)-5} more"
    else:
        result = f"🔍 Found {len(matches)} match{'es' if len(matches) > 1 else ''} for '{query}':\n\n"
        shown_matches = matches

    match_strings = []
    for entry in shown_matches:
        entry_str = f"**{entry.term}** ({entry.pos}) - {entry.definition}"
        if entry.etymology:
            entry_str += f"\n*Etymology: {entry.etymology}*"
        if entry.examples:
            entry_str += "\n" + "\n".join(entry.examples)
        match_strings.append(entry_str)

    result += "\n\n".join(match_strings)

    if len(result) > 2000:
        result = result[:1950] + "...\n*Message truncated*"

    await channel.send(result)

async def list_versions(channel):
    files = dict_manager.github.list_dictionary_files()
    if not files:
        await channel.send("No dictionary versions found.")
        return

    versions = []
    for filename in files:
        m = re.search(r"v\.?(\d+)\.(\d+)\.(\d+)", filename, re.IGNORECASE)
        if m:
            version = f"v{m.group(1)}.{m.group(2)}.{m.group(3)}"
            # Get approximate file size from GitHub API if needed
            content = dict_manager.get_dictionary_content(version)
            file_size = round(len(content.encode('utf-8')) / 1024, 1) if content else 0
            versions.append((version, file_size))

    versions.sort(key=lambda x: [int(i) for i in x[0][1:].split('.')])

    version_list = [f"**{v[0]}** ({v[1]} KB)" for v in versions]
    version_text = "\n".join(version_list)
    latest = versions[-1][0] if versions else "Unknown"

    msg = f"""📚 **Available Dictionary Versions:**

{version_text}

**Latest:** {latest}
Use `!getversion <vX.X.X>` to download any version.
🐙 **GitHub:** `{GITHUB_OWNER}/{GITHUB_REPO}`"""

    await channel.send(msg)

if __name__ == "__main__":
    if not GITHUB_TOKEN:
        logger.error("GITHUB_TOKEN environment variable not set!")
        exit(1)
    
    client.run(os.environ['DISCORD_TOKEN'])
