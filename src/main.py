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
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)  # Disable default help

# Initialize GitHub API and dictionary manager globally
github_api = GitHubAPI()
dict_manager = DictionaryManager(github_api)

@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user}')

    # Check for required environment variables
    if not DISCORD_TOKEN:
        logger.error("Required environment variable DISCORD_TOKEN is missing.")
        await bot.change_presence(activity=discord.Game("❌ Missing Discord Token"))
        await bot.close()
        return

    # Test GitHub connection
    try:
        latest = dict_manager.find_latest_version()
        logger.info(f"Successfully connected to GitHub. Latest version: {latest}")
        # Set status to show latest version with a custom activity
        await bot.change_presence(activity=discord.CustomActivity(name=f"📖 Dictionary {latest}"))
    except Exception as e:
        logger.error(f"Failed to connect to GitHub during startup: {e}")
        await bot.change_presence(activity=discord.Game("❌ GitHub connection failed"))

    # Add the command cog to the bot
    try:
        cog = DictionaryCommands(bot, dict_manager)
        await bot.add_cog(cog)
        logger.info("DictionaryCommands cog loaded successfully.")
        
        # List all loaded commands for debugging
        command_names = [cmd.name for cmd in bot.commands]
        logger.info(f"Loaded commands: {command_names}")
    except Exception as e:
        logger.error(f"Failed to load DictionaryCommands cog: {e}")
        await bot.change_presence(activity=discord.Game("❌ Commands failed to load"))
        # Log the full traceback for debugging
        import traceback
        logger.error(f"Full error: {traceback.format_exc()}")

    # Find a suitable channel to send a welcome message
    welcome_sent = False
    for guild in bot.guilds:
        logger.info(f"Checking guild: {guild.name}")
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                try:
                    # message = await channel.send("📖 Dictionary Bot is online and ready!")
                    logger.info(f"Welcome message sent to {channel.name} in {guild.name}")
                    
                    # Delete the message after 2 seconds
                    # await asyncio.sleep(2)
                    # await message.delete()
                    
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
        await bot.change_presence(activity=discord.Game("⚠️ No channel access"))
# Updated @bot.event on_message function for src/main.py

@bot.event
async def on_message(message):
    # Ignore messages from the bot itself
    if message.author == bot.user:
        return

    # Log every message the bot sees (but limit length for readability)
    content_preview = message.content[:100] + "..." if len(message.content) > 100 else message.content
    logger.info(f'Message from {message.author}: {content_preview}')

    # Clean the message content
    content = message.content.strip()
    
    # Skip empty messages
    if not content:
        await bot.process_commands(message)
        return

    # Try to parse the entire message as a dictionary entry using the new parser
    from .dictionary_parser import parse_message_as_entry
    
    # First, try to detect if this looks like a dictionary entry at all
    has_definition_format = False
    
    # Look for basic patterns that suggest this is a dictionary entry
    definition_indicators = [
        r'\([^)]*\)\s*-',  # (pos) - definition pattern
        r'\w+\s*\([^)]*\)\s*-\s*.+',  # word (pos) - definition
        r'Etymology:\s*',  # Etymology section
        r'Ex:\s*',  # Examples
        r'/[^/]+/',  # Phonetic notation
        r'\(pronounced:'  # Pronunciation notes
    ]
    
    for pattern in definition_indicators:
        if re.search(pattern, content, re.IGNORECASE):
            has_definition_format = True
            break
    
    if has_definition_format:
        logger.info("Message appears to contain dictionary entry format")
        
        # Try to parse the entry
        parsed_entry = parse_message_as_entry(content)
        
        if parsed_entry:
            logger.info(f"Successfully parsed entry: {parsed_entry.term} ({parsed_entry.pos})")
            
            try:
                # Prepare data for the dictionary manager
                ety_lines = [parsed_entry.etymology] if parsed_entry.etymology else None
                examples = parsed_entry.examples if parsed_entry.examples else None
                additional = parsed_entry.additional_info if parsed_entry.additional_info else None
                
                # Handle derived terms as additional info
                if parsed_entry.derived_terms:
                    if not additional:
                        additional = []
                    additional.append(f"Derived Terms: {parsed_entry.derived_terms}")
                
                success = dict_manager.add_entry(
                    parsed_entry.term, 
                    parsed_entry.pos, 
                    parsed_entry.definition,
                    ety_lines=ety_lines,
                    example_lines=examples,
                    pronunciation=parsed_entry.pronunciation,
                    additional_info=additional
                )
                
                if success:
                    # Truncate the term for the status if it's too long
                    truncated_term = parsed_entry.term if len(parsed_entry.term) <= 50 else parsed_entry.term[:47] + '...'
                    
                    await message.add_reaction('✅')
                    logger.info(f"Successfully added entry: {parsed_entry.term}")

                    # Update the bot's status to show the latest dictionary version and the new term
                    latest_version = dict_manager.find_latest_version()
                    status_text = f"📖 {latest_version} - {truncated_term}"
                    await bot.change_presence(activity=discord.CustomActivity(name=status_text))

                    # Remove the reaction after 4 seconds
                    await asyncio.sleep(4)
                    await message.remove_reaction('✅', bot.user)
                else:
                    await message.add_reaction('❌')
                    await message.channel.send(f"❌ Could not add '{parsed_entry.term}'. It may already exist or there was an error.")
                    logger.warning(f"Failed to add entry: {parsed_entry.term}")
                    
            except Exception as e:
                logger.error(f"Error adding entry '{parsed_entry.term}': {e}")
                await message.add_reaction('❌')
                await message.channel.send(f"❌ An error occurred while adding '{parsed_entry.term}': {str(e)}")
            
            return  # Don't process commands if we've handled an entry
        
        else:
            logger.info("Message had definition indicators but couldn't be parsed as entry")
            # Maybe send a helpful message about format if it really looks like they're trying
            if re.search(r'\([^)]*\)\s*-', content):
                await message.channel.send("📝 I detected what looks like a dictionary entry, but couldn't parse it. Make sure it follows the format: `word (pos) - definition`")

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
        # Update status to show error briefly
        await bot.change_presence(activity=discord.Game("❌ Command error"))
        await asyncio.sleep(10)  # Show error for 10 seconds
        # Reset to normal status
        try:
            latest = dict_manager.find_latest_version()
            # Reset to a custom activity on command error
            await bot.change_presence(activity=discord.CustomActivity(name=f"📖 Dictionary {latest}"))
        except:
            await bot.change_presence(activity=discord.Game("📖 Dictionary Bot"))

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
