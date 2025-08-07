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
    # This code finds a suitable channel to send a welcome message.
    # It will find the first text channel in the first server the bot is in.
    # This avoids needing a hardcoded CHANNEL_ID secret.
    for guild in client.guilds:
        # Check all channels in the guild
        for channel in guild.channels:
            if isinstance(channel, discord.TextChannel):
                try:
                    await channel.send("Hello! I am online and ready to go.")
                    # We send a message and then break out of the loops to avoid spamming
                    return
                except discord.errors.Forbidden:
                    # If we don't have permission to send a message here, we just ignore it
                    continue
    # If the bot is in a server with no available text channels, log an error
    logger.error("Could not find a channel to send a welcome message to.")

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
