import discord
import logging
from typing import Optional, Dict, Any
from torn_api import TornAPI

logger = logging.getLogger(__name__)


class DiscordNotifier:
    def __init__(self, bot: discord.Client, api: TornAPI):
        self.bot = bot
        self.api = api
    
    async def send_deal_notification(self, user_id: str, item_data: Dict[str, Any],
                                     listing: Dict[str, Any], max_price: int):
        try:
            user = await self.bot.fetch_user(int(user_id))
            if not user:
                logger.warning(f"Could not find Discord user with ID {user_id}")
                return False

            item_name = item_data.get("name", f"Item #{item_data.get('id', 'Unknown')}")
            item_id = item_data.get("id", "Unknown")
            item_type = item_data.get("type", "Unknown")
            listing_price = listing["price"]
            listing_amount = listing["amount"]
            average_price = item_data.get("average_price", 0)

            discount = self.api.calculate_discount(average_price, listing_price) if average_price > 0 else 0

            # Determine if this is a bazaar listing or market listing
            is_bazaar = listing.get("is_bazaar", False)
            if is_bazaar:
                # For bazaar listings, use the shop ID to create the correct URL
                shop_id = listing.get("shop_id", "unknown")
                market_url = f"https://www.torn.com/bazaar.php?userId={shop_id}#/"
                embed_title = f"DEAL ALERT: {item_name} (Bazaar - {listing.get('shop_name', 'Unknown Shop')})"
            else:
                market_url = f"https://www.torn.com/imarket.php#/p=market&step=market&type={item_id}"
                embed_title = f"DEAL ALERT: {item_name} (Market)"

            embed = discord.Embed(
                title=embed_title,
                color=discord.Color.green(),
                description=f"Listed below your threshold of ${max_price:,}!\n[🔗 View on Torn]({market_url})",
                url=market_url
            )

            embed.add_field(name="Price", value=self.api.format_price(listing_price), inline=True)
            embed.add_field(name="Amount", value=f"{listing_amount:,}", inline=True)
            embed.add_field(name="Avg Price", value=self.api.format_price(average_price), inline=True)

            if discount > 0:
                embed.add_field(
                    name="Discount",
                    value=f"{discount:.1f}% below average!",
                    inline=True
                )

            embed.add_field(name="Type", value=item_type, inline=True)
            embed.add_field(name="Action", value="Quick - grab it before it's gone!", inline=True)

            embed.set_footer(text="Torn Market Monitor | Click title to view listing")
            embed.timestamp = discord.utils.utcnow()

            await user.send(embed=embed)
            logger.info(f"Sent deal notification to {user_id} for {item_name} at {self.api.format_price(listing_price)}")
            return True

        except discord.Forbidden:
            logger.warning(f"Cannot send DM to user {user_id} (DMs disabled or bot not shared)")
            return False
        except discord.NotFound:
            logger.warning(f"User {user_id} not found")
            return False
        except Exception as e:
            logger.error(f"Error sending notification to {user_id}: {e}")
            return False
    
    async def send_confirmation_message(self, user_id: str, item_id: int, 
                                       item_name: str, max_price: int):
        try:
            user = await self.bot.fetch_user(int(user_id))
            if not user:
                return False
            
            embed = discord.Embed(
                title="Tracking Added",
                description=f"Now tracking **{item_name}** (ID: {item_id})",
                color=discord.Color.blue()
            )
            
            embed.add_field(name="Max Price", value=f"${max_price:,}", inline=True)
            embed.add_field(name="Status", value="Active", inline=True)
            embed.set_footer(text="You'll be notified when price drops below your threshold")
            
            await user.send(embed=embed)
            return True
            
        except (discord.Forbidden, discord.NotFound, Exception) as e:
            logger.warning(f"Could not send confirmation to {user_id}: {e}")
            return False
    
    async def send_error_message(self, user_id: str, error_message: str):
        try:
            user = await self.bot.fetch_user(int(user_id))
            if not user:
                return False
            
            embed = discord.Embed(
                title="Error",
                description=error_message,
                color=discord.Color.red()
            )
            
            await user.send(embed=embed)
            return True
            
        except (discord.Forbidden, discord.NotFound, Exception) as e:
            logger.warning(f"Could not send error to {user_id}: {e}")
            return False