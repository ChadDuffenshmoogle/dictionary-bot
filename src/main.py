# src/main.py
import os
import discord
from discord.ext import commands # Import the commands module
from config import (
    DISCORD_TOKEN,
    GITHUB_TOKEN,
    GITHUB_OWNER,
    GITHUB_REPO,
    ENTRY_PATTERN,
    logger
)

# Set up the bot with a command prefix and the correct intents
# The `commands.Bot` class is an extension of `discord.Client`
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True # This is crucial for the bot to read your commands

# Use a command prefix (e.g., '!')
# A command prefix tells the bot what to listen for at the beginning of a message
bot = commands.Bot(command_prefix='!', intents=intents)

# This event is triggered when the bot successfully connects to Discord
@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user}')
    # This code finds a suitable channel to send a welcome message.
    # It will find the first text channel in the first server the bot is in.
    # This avoids needing a hardcoded CHANNEL_ID secret.
    for guild in bot.guilds:
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

# This is a new command handler using the recommended `commands.Bot` approach
# The bot will automatically respond to messages that start with `!hello`
@bot.command(name='hello')
async def hello_command(ctx):
    await ctx.send('Hello!')

# To debug, let's add an `on_message` event listener to see every message the bot processes
@bot.event
async def on_message(message):
    # Ignore messages from the bot itself
    if message.author == bot.user:
        return
    
    # Log every message the bot sees, which is useful for debugging
    logger.info(f'Message received from {message.author}: {message.content}')

    # This line is crucial for the bot to process commands. Without it, the @bot.command decorator won't work.
    await bot.process_commands(message)

# Start the bot
if DISCORD_TOKEN:
    try:
        bot.run(DISCORD_TOKEN)
    except discord.errors.LoginFailure as e:
        logger.error(f"Failed to log in to Discord: {e}")
        logger.error("Please ensure your DISCORD_TOKEN environment variable is set correctly.")
else:
    logger.error("DISCORD_TOKEN environment variable not set. Please set it in your Fly.io secrets.")
