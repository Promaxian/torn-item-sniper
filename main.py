"""
Main entry point for the Torn Market Monitor Discord bot.
Initializes all components and starts the bot.
"""

import asyncio
import logging
import sys
import discord
from discord.ext import commands
from config import validate_config, get_config_summary, DISCORD_BOT_TOKEN
from database import Database
from torn_api import TornAPI
from notifier import DiscordNotifier
from market_monitor import MarketMonitor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Global instances
db = None
api = None
monitor = None
notifier = None

# Set up Discord bot
intents = discord.Intents.default()
intents.messages = True
bot = commands.Bot(command_prefix='!', intents=intents)

async def setup_components():
    """Initialize all bot components."""
    global db, api, monitor
    
    # Validate configuration
    validate_config()
    logger.info("Configuration validated")
    logger.info(f"Config: {get_config_summary()}")
    
    # Initialize database
    db = Database()
    await db.connect()
    
    # Initialize Torn API
    api = TornAPI()
    
    # Initialize notifier
    global notifier
    notifier = DiscordNotifier(bot, api)
    
    # Initialize market monitor
    monitor = MarketMonitor(db, api, notifier)
    
    logger.info("All components initialized")

# Bot events
@bot.event
async def on_ready():
    """Called when the bot is ready."""
    logger.info(f'Logged in as {bot.user} (ID: {bot.user.id})')
    logger.info('------')
    
    # Start the market monitor
    if monitor:
        await monitor.start()

@bot.event
async def on_command_error(ctx, error):
    """Handle command errors."""
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("Unknown command. Use `!help` to see available commands.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Missing required argument. Usage: `{ctx.command}`")
    else:
        logger.error(f"Command error: {error}")
        await ctx.send(f"An error occurred: {error}")

# Bot commands
@bot.command(name='track')
async def track_item(ctx, item_id: int, max_price: int):
    """
    Track an item for price alerts.
    Usage: !track <item_id> <max_price>
    Example: !track 206 900000
    """
    if not db:
        await ctx.send("Bot is not ready yet. Please try again in a moment.")
        return
    
    user_id = str(ctx.author.id)
    
    try:
        # Add to database
        success = await db.add_tracked_item(user_id, item_id, max_price)
        
        if success:
            # Get item name from cache or API
            item_name = await db.get_item_name(item_id)
            
            # If not cached, fetch from API
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
            
            # Send confirmation
            await notifier.send_confirmation_message(user_id, item_id, item_name, max_price)
            await ctx.send(f"Now tracking **{item_name}** (ID: {item_id}) below ${max_price:,}")
        else:
            await ctx.send("Failed to add tracking. Please try again.")
    
    except Exception as e:
        logger.error(f"Error in track command: {e}")
        await ctx.send(f"An error occurred: {e}")

@bot.command(name='untrack')
async def untrack_item(ctx, item_id: int):
    """
    Stop tracking an item.
    Usage: !untrack <item_id>
    Example: !untrack 206
    """
    if not db:
        await ctx.send("Bot is not ready yet.")
        return
    
    user_id = str(ctx.author.id)
    
    try:
        success = await db.remove_tracked_item(user_id, item_id)
        
        if success:
            item_name = await db.get_item_name(item_id)
            await ctx.send(f"Stopped tracking **{item_name}** (ID: {item_id})")
        else:
            await ctx.send("You weren't tracking that item.")
    
    except Exception as e:
        logger.error(f"Error in untrack command: {e}")
        await ctx.send(f"An error occurred: {e}")

@bot.command(name='list')
async def list_tracked(ctx):
    """
    List all items you're currently tracking.
    Usage: !list
    """
    if not db:
        await ctx.send("Bot is not ready yet.")
        return
    
    user_id = str(ctx.author.id)
    
    try:
        tracked_items = await db.get_user_tracked_items(user_id)
        
        if not tracked_items:
            await ctx.send("You're not tracking any items. Use `!track <item_id> <max_price>` to start.")
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
        await ctx.send(embed=embed)
    
    except Exception as e:
        logger.error(f"Error in list command: {e}")
        await ctx.send(f"An error occurred: {e}")

@bot.command(name='price')
async def update_price(ctx, item_id: int, new_price: int):
    """
    Update the price threshold for a tracked item.
    Usage: !price <item_id> <new_price>
    Example: !price 206 850000
    """
    if not db:
        await ctx.send("Bot is not ready yet.")
        return
    
    user_id = str(ctx.author.id)
    
    try:
        # Check if user is tracking this item
        tracked = await db.get_user_tracked_items(user_id)
        if not any(item[0] == item_id for item in tracked):
            await ctx.send("You're not tracking that item. Use `!track` first.")
            return
        
        # Update the price
        success = await db.add_tracked_item(user_id, item_id, new_price)
        
        if success:
            item_name = await db.get_item_name(item_id)
            await ctx.send(f"Updated **{item_name}** price threshold to ${new_price:,}")
    
    except Exception as e:
        logger.error(f"Error in price command: {e}")
        await ctx.send(f"An error occurred: {e}")

@bot.command(name='iteminfo')
async def item_info(ctx, item_id: int):
    """
    Get information about an item.
    Usage: !iteminfo <item_id>
    Example: !iteminfo 206
    """
    if not db:
        await ctx.send("Bot is not ready yet.")
        return
    
    try:
        # Check cache first
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
            # Fetch from API
            data = await api.get_item_market(item_id)
            if data:
                market_data = api.extract_market_data(data)
                if market_data and market_data["item"].get("name"):
                    item = market_data["item"]
                    
                    # Cache the info
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
                    
                    # Show current cheapest if available
                    cheapest = api.get_cheapest_listing(market_data)
                    if cheapest:
                        embed.add_field(name="Current Cheapest", value=f"${cheapest['price']:,}", inline=True)
                        embed.add_field(name="Amount", value=f"{cheapest['amount']:,}", inline=True)
                    
                    embed.set_footer(text="Data from Torn API")
                else:
                    await ctx.send(f"Item #{item_id} not found.")
                    return
            else:
                await ctx.send(f"Could not fetch information for item #{item_id}.")
                return
        
        await ctx.send(embed=embed)
    
    except Exception as e:
        logger.error(f"Error in iteminfo command: {e}")
        await ctx.send(f"An error occurred: {e}")

@bot.command(name='status')
async def bot_status(ctx):
    """
    Show bot status and configuration.
    Usage: !status
    """
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
    await ctx.send(embed=embed)

@bot.command(name='help')
async def bot_help(ctx):
    """
    Show help information.
    Usage: !help
    """
    embed = discord.Embed(
        title="Torn Market Monitor - Help",
        description="Monitor Torn item market prices and get Discord notifications!",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="!track <item_id> <max_price>",
        value="Start tracking an item. Example: `!track 206 900000`",
        inline=False
    )
    embed.add_field(
        name="!untrack <item_id>",
        value="Stop tracking an item. Example: `!untrack 206`",
        inline=False
    )
    embed.add_field(
        name="!price <item_id> <new_price>",
        value="Update price threshold. Example: `!price 206 850000`",
        inline=False
    )
    embed.add_field(
        name="!list",
        value="Show all your tracked items",
        inline=False
    )
    embed.add_field(
        name="!iteminfo <item_id>",
        value="Get item information. Example: `!iteminfo 206`",
        inline=False
    )
    embed.add_field(
        name="!status",
        value="Show bot status and configuration",
        inline=False
    )
    
    embed.set_footer(text="Notifications are sent via DM when prices drop below your threshold")
    await ctx.send(embed=embed)

async def cleanup():
    """Clean up resources on shutdown."""
    global db, api, monitor
    
    logger.info("Cleaning up resources...")
    
    if monitor:
        await monitor.stop()
    
    if db:
        await db.close()
    
    if api:
        await api.close()
    
    logger.info("Cleanup complete")

async def main():
    """Main entry point."""
    try:
        # Setup components
        await setup_components()
        
        # Start the bot
        await bot.start(DISCORD_BOT_TOKEN)
    
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        await cleanup()

if __name__ == "__main__":
    asyncio.run(main())