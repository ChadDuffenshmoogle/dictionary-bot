# src/config.py
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
GITHUB_REPO = "dictionary-versions"  # ← Changed from "dictionary-bot"  
GITHUB_BRANCH = "main"

# IMPORTANT: Fix the environment variable name
# The bot code expects YOUR_GITHUB_PAT, so we'll rename this variable.
GITHUB_TOKEN = os.environ.get('YOUR_GITHUB_PAT')
YOUR_GITHUB_PAT = os.environ.get('YOUR_GITHUB_PAT') # We'll keep this variable name in this file for clarity and for the bot to be able to use it

# Dictionary File Configuration
BASE_VERSION = "v1.2.4"
FILE_PREFIX = "UNICYCLIST DICTIONARY"
FILE_EXTENSION = ".txt"

# Regex Pattern
ENTRY_PATTERN = r'^(.+?) \((.+?)\) - (.+)$'
