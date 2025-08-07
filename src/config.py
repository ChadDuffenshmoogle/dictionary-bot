import os
import logging

# Set up logging (moved here for global configuration)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Discord Configuration
DISCORD_TOKEN = os.environ.get('DISCORD_TOKEN') # Ensure this is the correct env var for Discord

# GitHub Configuration
GITHUB_OWNER = "ChadDuffenshmoogle"
GITHUB_REPO = "dictionary-bot"
GITHUB_BRANCH = "main"
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN') # It's better to use a dedicated GITHUB_TOKEN env var, not DISCORD_TOKEN

# Dictionary File Configuration
BASE_VERSION = "v1.2.4"
FILE_PREFIX = "UNICYCLIST DICTIONARY"
FILE_EXTENSION = ".txt"

# Regex Pattern
ENTRY_PATTERN = r'^(.+?) \((.+?)\) - (.+)$'
