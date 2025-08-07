import discord
import os
import re
import asyncio
from typing import Optional, List

# Import components from our new modules
from .config import DISCORD_TOKEN, YOUR_GITHUB_PAT, GITHUB_OWNER, GITHUB_REPO, ENTRY_PATTERN, logger # Use YOUR_GITHUB_PAT
from .github_api import GitHubAPI
from .dictionary_manager import DictionaryManager
from .dictionary_parser import parse_dictionary_entries # Needed for entry validation for adding
from .discord_commands import (
    send_version, show_stats, show_random_entry,
    search_entries, list_versions, send_help_message
)

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# Global dictionary manager (initialized after GitHub token is available)
dict_manager: Optional[DictionaryManager] = None

@client.event
async def on_ready():
    global dict_manager

    print(f"🤖 Logged in as {client.user}")
    logger.info(f"Bot started successfully")

    # Initialize GitHub API and dictionary manager
    if not YOUR_GITHUB_PAT: # Check for YOUR_GITHUB_PAT now
        logger.error("YOUR_GITHUB_PAT environment variable not set! Bot will not function properly for GitHub interactions.")
    else:
        github_api = GitHubAPI(YOUR_GITHUB_PAT) # Pass YOUR_GITHUB_PAT here
        dict_manager = DictionaryManager(github_api)

        # Test GitHub connection
        try:
            latest = dict_manager.find_latest_version()
            logger.info(f"Successfully connected to GitHub. Latest version: {latest}")
        except Exception as e:
            logger.error(f"Failed to connect to GitHub: {e}")
            dict_manager = None # Disable manager if GitHub fails to prevent further errors

    # Send connection message to the first available channel
    for guild in client.guilds:
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                try:
                    msg = await channel.send("📖 Dictionary bot connected! Using GitHub for storage.")
                    await msg.delete(delay=3)
                    logger.info(f"Sent connection message to #{channel.name}")
                    break # Stop after sending to one channel per guild
                except discord.errors.Forbidden:
                    logger.warning(f"No permission to send message in #{channel.name} in guild {guild.name}")
                    continue
        if dict_manager: # Only send once per guild if manager initialized
            break


@client.event
async def on_message(msg):
    # Only process messages if not from a bot and dict_manager is initialized
    if msg.author.bot or not dict_manager:
        return

    # Handle commands
    if msg.content.startswith("!"):
        command_parts = msg.content.split()
        command = command_parts[0].lower()

        if command == "!getversion":
            ver = command_parts[1] if len(command_parts) >= 2 else "latest"
            await send_version(msg.channel, dict_manager, ver)
        elif command == "!stats":
            await show_stats(msg.channel, dict_manager)
        elif command == "!random":
            await show_random_entry(msg.channel, dict_manager)
        elif command == "!search":
            if len(command_parts) < 2:
                await msg.channel.send("Usage: `!search <query>`")
                return
            query = " ".join(command_parts[1:])
            await search_entries(msg.channel, dict_manager, query)
        elif command == "!versions":
            await list_versions(msg.channel, dict_manager)
        elif command == "!help":
            await send_help_message(msg.channel)
        return # Command handled, exit

    # Handle dictionary entry additions (if not a command)
    lines = [line.strip() for line in msg.content.splitlines() if line.strip()]
    if not lines:
        return

    term_line_match = None
    for line in lines:
        m = re.match(ENTRY_PATTERN, line)
        if m:
            term_line_match = m
            break

    if not term_line_match:
        return # Not a dictionary entry

    term, pos, definition = term_line_match.groups()
    logger.info(f"Attempting to add entry: {term} ({pos}) - {definition}")

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
            if not line.startswith(("-----", "——————")): # Avoid separator lines
                ety_lines.append(line)
        elif collecting_ety and re.match(ENTRY_PATTERN, line):
            collecting_ety = False # End of etymology, found main entry line
        elif line.lower().startswith("ex:") or line.lower().startswith("example:"):
            example_lines.append(line)

    # Clean up etymology (remove empty lines, etc.)
    final_ety_lines = [line for line in ety_lines if line.strip()] if ety_lines else None
    if final_ety_lines:
        logger.info(f"Found etymology: {len(final_ety_lines)} lines")
    if example_lines:
        logger.info(f"Found examples: {len(example_lines)} lines")

    try:
        success = dict_manager.add_entry(term, pos, definition, final_ety_lines, example_lines)

        if success:
            await msg.add_reaction('✅')
            await asyncio.sleep(4)
            await msg.remove_reaction('✅', client.user)
        else:
            await msg.add_reaction('❌')
            await asyncio.sleep(4)
            await msg.remove_reaction('❌', client.user)

    except Exception as e:
        logger.error(f"Error adding entry: {e}", exc_info=True) # exc_info=True to log traceback
        await msg.add_reaction('❌')
        await asyncio.sleep(4)
        await msg.remove_reaction('❌', client.user)


if __name__ == "__main__":
    if not DISCORD_TOKEN: # Use DISCORD_TOKEN as defined in config
        logger.error("DISCORD_TOKEN environment variable not set! Bot cannot start.")
        exit(1)

    client.run(DISCORD_TOKEN) # Use DISCORD_TOKEN here
