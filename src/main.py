# src/main.py

import os
import discord
import re
from discord.ext import commands

# Import modules from our new modular structure
from config import GITHUB_TOKEN, DISCORD_TOKEN, logger, ENTRY_PATTERN
from github_api import GitHubAPI
from dictionary_manager import DictionaryManager
from discord_commands import DictionaryCommands

# Set up the bot with a command prefix and the correct intents
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Initialize GitHub API and dictionary manager globally, so they can be accessed by on_message
github_api = GitHubAPI(token=GITHUB_TOKEN)
dict_manager = DictionaryManager(github_api)

@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user}')

    # Check for required environment variables
    if not GITHUB_TOKEN or not DISCORD_TOKEN:
        logger.error("Required environment variables (GITHUB_TOKEN or DISCORD_TOKEN) are missing.")
        # We can't proceed, so we should exit gracefully.
        await bot.close()
        return

    # Test GitHub connection
    try:
        latest = dict_manager.find_latest_version()
        logger.info(f"Successfully connected to GitHub. Latest version: {latest}")
    except Exception as e:
        logger.error(f"Failed to connect to GitHub during startup: {e}")

    # Add the command cog to the bot
    await bot.add_cog(DictionaryCommands(bot, dict_manager))
    logger.info("DictionaryCommands cog loaded.")

    # Find a suitable channel to send a welcome message.
    for guild in bot.guilds:
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                try:
                    await channel.send("Hello! I am online and ready to go.")
                    return
                except discord.errors.Forbidden:
                    continue
    logger.warning("Could not find a channel to send a welcome message to.")

# This event is crucial for the bot to see messages and process commands.
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Log every message the bot sees
    logger.info(f'Message received from {message.author}: {message.content}')

    # Check if the message matches the entry format
    lines = [line.strip() for line in message.content.splitlines() if line.strip()]
    if lines:
        entry_text = "\n".join(lines)
        # Check if the core definition line is present
        match = re.search(ENTRY_PATTERN, entry_text)

        if match:
            # This logic is moved from discord_commands.py
            term, pos, definition = match.groups()
            
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

            ety = [line for line in ety_lines if line.strip()] if ety_lines else None
            
            try:
                success = await dict_manager.add_entry(term, pos, definition, ety, example_lines)
                if success:
                    await message.add_reaction('✅')
                    await message.channel.send(f"✅ Successfully added '{term}' to the dictionary.")
                else:
                    await message.add_reaction('❌')
                    await message.channel.send(f"❌ Could not add '{term}'. It may already exist or the format is incorrect.")
            except Exception as e:
                logger.error(f"Error adding entry: {e}")
                await message.add_reaction('❌')
                await message.channel.send(f"❌ An error occurred while adding the entry.")
            return # Don't process commands if we've successfully added an entry

    # This is the single line that ensures other commands are processed if the message is not an entry
    await bot.process_commands(message)


# Start the bot
if __name__ == "__main__":
    if DISCORD_TOKEN:
        try:
            bot.run(DISCORD_TOKEN)
        except discord.errors.LoginFailure as e:
            logger.error(f"Failed to log in to Discord: {e}")
            logger.error("Please ensure your DISCORD_TOKEN environment variable is set correctly.")
    else:
        logger.error("DISCORD_TOKEN environment variable not set. Please set it in your Fly.io secrets.")

