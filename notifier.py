"""
Discord notification handler for the Torn Market Monitor bot.
Handles sending formatted notifications to Discord users.
"""

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
        """
        Send a Discord DM notification about a deal.
        
        Args:
            user_id: Discord user ID to notify
            item_data: Item information from API (name, type, average_price)
            listing: Listing data (price, amount)
            max_price: User's maximum price threshold
        """
        try:
            user = await self.bot.fetch_user(int(user_id))
            if not user:
                logger.warning(f"Could not find Discord user with ID {user_id}")
                return False
            
            # Build the embed
            item_name = item_data.get("name", f"Item #{item_data.get('id', 'Unknown')}")
            item_type = item_data.get("type", "Unknown")
            listing_price = listing["price"]
            listing_amount = listing["amount"]
            average_price = item_data.get("average_price", 0)
            
            # Calculate discount
            discount = self.api.calculate_discount(average_price, listing_price) if average_price > 0 else 0
            
            # Create embed
            embed = discord.Embed(
                title=f"DEAL ALERT: {item_name}",
                color=discord.Color.green(),
                description=f"Listed below your threshold of ${max_price:,}!"
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
            
            embed.set_footer(text="Torn Market Monitor | Click item name to view in-game")
            embed.timestamp = discord.utils.utcnow()
            
            # Add link to item (if we had a way to link, for now just mention it)
            # In a real implementation, you might add a link to the item in Torn
            
            # Send the DM
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
        """Send a confirmation message when a user adds tracking."""
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
        """Send an error message to a user."""
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