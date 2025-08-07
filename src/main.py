# src/main.py
import os
import discord
from config import (
    DISCORD_TOKEN,
    GITHUB_TOKEN,
    GITHUB_OWNER,
    GITHUB_REPO,
    ENTRY_PATTERN,
    logger
)

# Set up the Discord client with the correct intents
# The 'messages' and 'guilds' intents are needed for bot functionality.
# The `message_content` intent is required to read message content.
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True # This is crucial for the bot to read your commands

# Initialize the bot client
client = discord.Client(intents=intents)

# This event is triggered when the bot successfully connects to Discord
@client.event
async def on_ready():
    logger.info(f'Logged in as {client.user}')
    # The bot is now online and listening for messages in any server it's in.
    # No initial message is sent, which means no CHANNEL_ID secret is needed.
    # The `!hello` command should now work in any channel the bot can see.

# This event is triggered when a message is sent in any channel the bot can see
@client.event
async def on_message(message):
    # Ignore messages from the bot itself
    if message.author == client.user:
        return

    # A simple example command
    if message.content.startswith('!hello'):
        await message.channel.send('Hello!')

# Start the bot
if DISCORD_TOKEN:
    try:
        client.run(DISCORD_TOKEN)
    except discord.errors.LoginFailure as e:
        logger.error(f"Failed to log in to Discord: {e}")
        logger.error("Please ensure your DISCORD_TOKEN environment variable is set correctly.")
else:
    logger.error("DISCORD_TOKEN environment variable not set. Please set it in your Fly.io secrets.")
