import asyncio
import logging
import sys
import discord
from discord import app_commands
from discord.ext import commands
from config import validate_config, get_config_summary, DISCORD_BOT_TOKEN, TORN_API_KEY, get_api_key_interactive
from database import Database
from torn_api import TornAPI
from notifier import DiscordNotifier
from market_monitor import MarketMonitor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

db = None
api = None
monitor = None
notifier = None

intents = discord.Intents.default()
intents.messages = True
bot = commands.Bot(command_prefix="/", intents=intents, help_command=None)

async def setup_components():
    global db, api, monitor, notifier
    
    # api_key = get_api_key_interactive() # We'll manage API keys per-user now
    
    validate_config()
    logger.info("Configuration validated")
    logger.info(f"Config: {get_config_summary()}")
    
    db = Database()
    await db.connect()
    
    # Initialize TornAPI without a global key, will be fetched per-user
    api = TornAPI(api_key="") 
    
    notifier = DiscordNotifier(bot, api)
    
    monitor = MarketMonitor(db, api, notifier)
    
    logger.info("All components initialized")


@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user} (ID: {bot.user.id})')
    logger.info('------')

    # Sync slash commands
    await bot.tree.sync()
    logger.info("Slash commands synced")

    if monitor:
        await monitor.start()


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.CommandNotFound):
        await interaction.response.send_message("Unknown command. Use /help to see available commands.")
    elif isinstance(error, app_commands.MissingRequiredArgument):
        await interaction.response.send_message(f"Missing required argument. Usage: `{interaction.command}`")
    else:
        logger.error(f"Command error: {error}")
        await interaction.response.send_message(f"An error occurred: {error}")


@bot.tree.command(name='track', description='Start tracking an item')
@app_commands.describe(item_id="The item ID to track", max_price="Maximum price threshold")
async def track_item(interaction: discord.Interaction, item_id: int, max_price: int):
    if not db:
        await interaction.response.send_message("Bot is not ready yet. Please try again in a moment.")
        return

    user_id = str(interaction.user.id)
    user_api_key = await get_user_api_key_or_request(interaction)
    if not user_api_key:
        return # User needs to set API key first

    # Temporarily update the API key for the current operation
    original_api_key = api.api_key
    api.api_key = user_api_key

    try:
        success = await db.add_tracked_item(user_id, item_id, max_price)

        if success:
            item_name = await db.get_item_name(item_id)

            if item_name == f"Item #{item_id}":
                data = await api.get_item_market(item_id)
                if data:
                    market_data = api.extract_market_data(data)
                    if market_data and market_data["item"].get("name"):
                        item_name = market_data["item"]["name"]
                        await db.cache_item_info(
                            item_id=item_id,
                            name=market_data["item"]["name"],
                            item_type=market_data["item"].get("type", ""),
                            average_price=market_data["item"].get("average_price", 0)
                        )

            await notifier.send_confirmation_message(user_id, item_id, item_name, max_price)
            await interaction.response.send_message(f"Now tracking **{item_name}** (ID: {item_id}) below ${max_price:,}")
        else:
            await interaction.response.send_message("Failed to add tracking. Please try again.")

    except Exception as e:
        logger.error(f"Error in track command: {e}")
        await interaction.response.send_message(f"An error occurred: {e}")
    finally:
        api.api_key = original_api_key # Reset API key

def is_dm(interaction: discord.Interaction):
    return isinstance(interaction.channel, discord.DMChannel)

async def get_user_api_key_or_request(interaction: discord.Interaction):
    if not db:
        await interaction.response.send_message("Bot is not ready yet. Please try again in a moment.")
        return None

    user_id = str(interaction.user.id)
    api_key = await db.get_api_key(user_id)
    if not api_key:
        await interaction.response.send_message("Please set your Torn API key using `/setapikey <your_key>` in a direct message with me first.")
    return api_key


@bot.tree.command(name='setapikey', description='Set your Torn API key')
@app_commands.describe(api_key="Your Torn API key (16 alphanumeric characters)")
async def set_api_key_command(interaction: discord.Interaction, api_key: str):
    if not is_dm(interaction):
        # Send a DM to the user instead of responding in the channel
        try:
            user = interaction.user
            await user.send("For security reasons, please use this command in a direct message with me. 🤫")
            await interaction.response.send_message("I've sent you a direct message with instructions.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("I couldn't send you a DM. Please enable DMs from server members and try the command in a direct message with me. 🤫", ephemeral=True)
        return
    if not db:
        await interaction.response.send_message("Bot is not ready yet. Please try again in a moment.")
        return

    user_id = str(interaction.user.id)

    # Basic validation for API key length (Torn API keys are 16 characters)
    if len(api_key) != 16 or not api_key.isalnum():
        await interaction.response.send_message("That doesn\\\'t look like a valid Torn API key. It should be 16 alphanumeric characters. Double-check it! 🤔")
        return

    try:
        success = await db.set_api_key(user_id, api_key)
        if success:
            await interaction.response.send_message(f"Your Torn API key has been successfully {'updated' if success else 'set'}! ✨ I'll keep it safe.")
        else:
            await interaction.response.send_message("Hmm, I couldn't set your API key right now. Please try again later. 🚧")
    except Exception as e:
        logger.error(f"Error setting API key: {e}")
        await interaction.response.send_message(f"An error occurred while setting your API key: {e}")


@bot.tree.command(name='myapikey', description='Check your API key status')
async def my_api_key_command(interaction: discord.Interaction):
    if not is_dm(interaction):
        # Send a DM to the user instead of responding in the channel
        try:
            user = interaction.user
            await user.send("For security reasons, please use this command in a direct message with me. 🤫")
            await interaction.response.send_message("I've sent you a direct message with instructions.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("I couldn't send you a DM. Please enable DMs from server members and try the command in a direct message with me. 🤫", ephemeral=True)
        return
    if not db:
        await interaction.response.send_message("Bot is not ready yet. Please try again in a moment.")
        return

    user_id = str(interaction.user.id)

    try:
        api_key = await db.get_api_key(user_id)
        if api_key:
            last_updated_cursor = await db.db.execute("SELECT last_updated FROM api_keys WHERE discord_id = ?", (user_id,))
            last_updated_row = await last_updated_cursor.fetchone()
            last_updated_at = last_updated_row["last_updated"] if last_updated_row else "N/A"
            await interaction.response.send_message(f"You have an API key set! Last updated: {last_updated_at} 🗓️ (I won't show the key directly for security! 😉)")
        else:
            await interaction.response.send_message("You haven't set an API key yet. Use `/setapikey <your_key>` in a DM with me to add one! 🔑")
    except Exception as e:
        logger.error(f"Error getting API key status: {e}")
        await interaction.response.send_message(f"An error occurred while checking your API key status: {e}")


@bot.tree.command(name='removeapikey', description='Remove your stored API key')
async def remove_api_key_command(interaction: discord.Interaction):
    if not is_dm(interaction):
        # Send a DM to the user instead of responding in the channel
        try:
            user = interaction.user
            await user.send("For security reasons, please use this command in a direct message with me. 🤫")
            await interaction.response.send_message("I've sent you a direct message with instructions.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("I couldn't send you a DM. Please enable DMs from server members and try the command in a direct message with me. 🤫", ephemeral=True)
        return
    if not db:
        await interaction.response.send_message("Bot is not ready yet. Please try again in a moment.")
        return

    user_id = str(interaction.user.id)

    try:
        success = await db.delete_api_key(user_id)
        if success:
            await interaction.response.send_message("Your API key has been removed. You can set a new one anytime with `/setapikey <your_key>` 🗑️")
        else:
            await interaction.response.send_message("You don't have an API key set, or there was an error removing it.")
    except Exception as e:
        logger.error(f"Error removing API key: {e}")
        await interaction.response.send_message(f"An error occurred while removing your API key: {e}")


@bot.tree.command(name='list', description='Show all your tracked items')
async def list_tracked(interaction: discord.Interaction):
    if not db:
        await interaction.response.send_message("Bot is not ready yet.")
        return

    user_id = str(interaction.user.id)
    user_api_key = await get_user_api_key_or_request(interaction)
    if not user_api_key:
        return # User needs to set API key first

    # Temporarily update the API key for the current operation
    original_api_key = api.api_key
    api.api_key = user_api_key

    try:
        tracked_items = await db.get_user_tracked_items(user_id)

        if not tracked_items:
            await interaction.response.send_message("You\\'re not tracking any items. Use /track <item_id> <max_price> to start.")
            return

        embed = discord.Embed(
            title="Your Tracked Items",
            color=discord.Color.blue()
        )

        for item_id, max_price in tracked_items:
            item_name = await db.get_item_name(item_id)
            embed.add_field(
                name=f"{item_name} (ID: {item_id})",
                value=f"Max: ${max_price:,}",
                inline=False
            )

        embed.set_footer(text=f"Total: {len(tracked_items)} items")
        await interaction.response.send_message(embed=embed)

    except Exception as e:
        logger.error(f"Error in list command: {e}")
        await interaction.response.send_message(f"An error occurred: {e}")
    finally:
        api.api_key = original_api_key # Reset API key


@bot.tree.command(name='price', description='Update price threshold for a tracked item')
@app_commands.describe(item_id="The item ID to update", new_price="New maximum price threshold")
async def update_price(interaction: discord.Interaction, item_id: int, new_price: int):
    if not db:
        await interaction.response.send_message("Bot is not ready yet.")
        return

    user_id = str(interaction.user.id)
    user_api_key = await get_user_api_key_or_request(interaction)
    if not user_api_key:
        return # User needs to set API key first

    # Temporarily update the API key for the current operation
    original_api_key = api.api_key
    api.api_key = user_api_key

    try:
        tracked = await db.get_user_tracked_items(user_id)
        if not any(item[0] == item_id for item in tracked):
            await interaction.response.send_message("You\\'re not tracking that item. Use /track first.")
            return

        success = await db.add_tracked_item(user_id, item_id, new_price)

        if success:
            item_name = await db.get_item_name(item_id)
            await interaction.response.send_message(f"Updated **{item_name}** price threshold to ${new_price:,}")

    except Exception as e:
        logger.error(f"Error in price command: {e}")
        await interaction.response.send_message(f"An error occurred: {e}")
    finally:
        api.api_key = original_api_key # Reset API key


@bot.tree.command(name='iteminfo', description='Get detailed information about an item')
@app_commands.describe(item_id="The item ID to look up")
async def item_info(interaction: discord.Interaction, item_id: int):
    if not db:
        await interaction.response.send_message("Bot is not ready yet.")
        return

    try:
        cached = await db.get_cached_item_info(item_id)

        if cached:
            embed = discord.Embed(
                title=cached['name'],
                color=discord.Color.green()
            )
            embed.add_field(name="Type", value=cached['type'], inline=True)
            embed.add_field(name="Avg Price", value=f"${cached['average_price']:,}", inline=True)
            embed.set_footer(text="Data from cache")
        else:
            data = await api.get_item_market(item_id)
            if data:
                market_data = api.extract_market_data(data)
                if market_data and market_data["item"].get("name"):
                    item = market_data["item"]

                    await db.cache_item_info(
                        item_id=item_id,
                        name=item["name"],
                        item_type=item.get("type", ""),
                        average_price=item.get("average_price", 0)
                    )

                    embed = discord.Embed(
                        title=item['name'],
                        color=discord.Color.green()
                    )
                    embed.add_field(name="Type", value=item.get("type", "Unknown"), inline=True)
                    embed.add_field(name="Avg Price", value=f"${item.get('average_price', 0):,}", inline=True)

                    cheapest = api.get_cheapest_listing(market_data)
                    if cheapest:
                        embed.add_field(name="Current Cheapest", value=f"${cheapest['price']:,}", inline=True)
                        embed.add_field(name="Amount", value=f"{cheapest['amount']:,}", inline=True)

                    embed.set_footer(text="Data from Torn API")
                else:
                    await interaction.response.send_message(f"Item #{item_id} not found.")
                    return
            else:
                await interaction.response.send_message(f"Could not fetch information for item #{item_id}.")
                return

        await interaction.response.send_message(embed=embed)

    except Exception as e:
        logger.error(f"Error in iteminfo command: {e}")
        await interaction.response.send_message(f"An error occurred: {e}")


@bot.tree.command(name='status', description='Show bot status and configuration')
async def bot_status(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Torn Market Monitor Status",
        color=discord.Color.green()
    )

    config = get_config_summary()
    embed.add_field(name="Poll Interval", value=f"{config['poll_interval']} seconds", inline=True)
    embed.add_field(name="Cooldown", value=f"{config['cooldown_minutes']} minutes", inline=True)
    embed.add_field(name="Monitor Running", value="Yes" if monitor and monitor.is_running() else "No", inline=True)

    if db:
        users = await db.get_all_users()
        tracked_count = len(await db.get_all_tracked_item_ids())
        embed.add_field(name="Active Users", value=str(len(users)), inline=True)
        embed.add_field(name="Tracked Items", value=str(tracked_count), inline=True)

    embed.set_footer(text=f"Bot ID: {bot.user.id}")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name='help', description='Show help information and available commands')
async def bot_help(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Torn Market Monitor - Help",
        description="Monitor Torn item market prices and get Discord notifications!",
        color=discord.Color.blue()
    )

    embed.add_field(
        name="/track <item_id> <max_price>",
        value="Start tracking an item. Example: `/track 206 900000`",
        inline=False
    )
    embed.add_field(
        name="/untrack <item_id>",
        value="Stop tracking an item. Example: `/untrack 206`",
        inline=False
    )
    embed.add_field(
        name="/price <item_id> <new_price>",
        value="Update price threshold. Example: `/price 206 850000`",
        inline=False
    )
    embed.add_field(
        name="/list",
        value="Show all your tracked items",
        inline=False
    )
    embed.add_field(
        name="/iteminfo <item_id>",
        value="Get item information. Example: `/iteminfo 206`",
        inline=False
    )
    embed.add_field(
        name="/status",
        value="Show bot status and configuration",
        inline=False
    )

    embed.set_footer(text="Notifications are sent via DM when prices drop below your threshold")
    await interaction.response.send_message(embed=embed)


async def cleanup():
    logger.info("Cleaning up resources...")
    
    if monitor:
        await monitor.stop()
    
    if db:
        await db.close()
    
    if api:
        await api.close()
    
    logger.info("Cleanup complete")


async def main():
    try:
        await setup_components()
        
        await bot.start(DISCORD_BOT_TOKEN)
    
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        await cleanup()


if __name__ == "__main__":
    asyncio.run(main())
