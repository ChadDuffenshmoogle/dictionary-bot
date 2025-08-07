# src/main.py

import os
import discord
import re
import asyncio
from discord.ext import commands

# Import modules from our new modular structure
from .config import DISCORD_TOKEN, logger, ENTRY_PATTERN
from .github_api import GitHubAPI
from .dictionary_manager import DictionaryManager
from .discord_commands import DictionaryCommands

# Set up the bot with a command prefix and the correct intents
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Initialize GitHub API and dictionary manager globally
github_api = GitHubAPI()
dict_manager = DictionaryManager(github_api)

@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user}')

    # Check for required environment variables
    if not DISCORD_TOKEN:
        logger.error("Required environment variable DISCORD_TOKEN is missing.")
        await bot.close()
        return

    # Test GitHub connection
    try:
        latest = dict_manager.find_latest_version()
        logger.info(f"Successfully connected to GitHub. Latest version: {latest}")
    except Exception as e:
        logger.error(f"Failed to connect to GitHub during startup: {e}")

    # Add the command cog to the bot
    try:
        await bot.add_cog(DictionaryCommands(bot, dict_manager))
        logger.info("DictionaryCommands cog loaded.")
    except Exception as e:
        logger.error(f"Failed to load DictionaryCommands cog: {e}")

    # Find a suitable channel to send a welcome message
    welcome_sent = False
    for guild in bot.guilds:
        logger.info(f"Checking guild: {guild.name}")
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                try:
                    await channel.send("📖 Dictionary Bot is online and ready!")
                    logger.info(f"Welcome message sent to {channel.name} in {guild.name}")
                    welcome_sent = True
                    break
                except discord.errors.Forbidden:
                    logger.warning(f"Forbidden to send message in {channel.name}")
                    continue
                except Exception as e:
                    logger.error(f"Error sending welcome message to {channel.name}: {e}")
                    continue
        if welcome_sent:
            break
    
    if not welcome_sent:
        logger.warning("Could not find a channel to send a welcome message to.")

@bot.event
async def on_message(message):
    # Ignore messages from the bot itself
    if message.author == bot.user:
        return

    # Log every message the bot sees (but limit length for readability)
    content_preview = message.content[:100] + "..." if len(message.content) > 100 else message.content
    logger.info(f'Message from {message.author}: {content_preview}')

    # Check if the message matches the entry format
    lines = [line.strip() for line in message.content.splitlines() if line.strip()]
    if lines:
        entry_text = "\n".join(lines)
        # Check if the core definition line is present
        match = re.search(ENTRY_PATTERN, entry_text)

        if match:
            logger.info(f"Detected dictionary entry format: {match.groups()}")
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

            ety = ety_lines if ety_lines else None
            
            try:
                success = dict_manager.add_entry(term, pos, definition, ety, example_lines)
                if success:
                    await message.add_reaction('✅')
                    await message.channel.send(f"✅ Successfully added '{term}' to the dictionary.")
                    logger.info(f"Successfully added entry: {term}")
                else:
                    await message.add_reaction('❌')
                    await message.channel.send(f"❌ Could not add '{term}'. It may already exist or there was an error.")
                    logger.warning(f"Failed to add entry: {term}")
            except Exception as e:
                logger.error(f"Error adding entry '{term}': {e}")
                await message.add_reaction('❌')
                await message.channel.send(f"❌ An error occurred while adding '{term}': {str(e)}")
            return # Don't process commands if we've handled an entry

    # Process commands if the message is not an entry
    await bot.process_commands(message)

@bot.event
async def on_command_error(ctx, error):
    """Handle command errors."""
    if isinstance(error, commands.CommandNotFound):
        await ctx.send(f"❓ Unknown command. Use `!help` to see available commands.")
    else:
        logger.error(f"Command error in {ctx.command}: {error}")
        await ctx.send(f"❌ An error occurred: {str(error)}")

# Start the bot
if __name__ == "__main__":
    if DISCORD_TOKEN:
        try:
            logger.info("Starting Discord bot...")
            bot.run(DISCORD_TOKEN)
        except discord.errors.LoginFailure as e:
            logger.error(f"Failed to log in to Discord: {e}")
            logger.error("Please ensure your DISCORD_TOKEN environment variable is set correctly.")
        except Exception as e:
            logger.error(f"Unexpected error starting bot: {e}")
    else:
        logger.error("DISCORD_TOKEN environment variable not set. Please set it in your Fly.io secrets.")