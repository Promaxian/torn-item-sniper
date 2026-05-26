"""
Market monitoring logic for the Torn Market Monitor bot.
Handles polling the Torn API, deduplicating requests, and checking prices.
"""

import asyncio
import logging
from typing import Dict, List, Tuple, Any
from database import Database
from torn_api import TornAPI
from notifier import DiscordNotifier
from config import POLL_INTERVAL

logger = logging.getLogger(__name__)

class MarketMonitor:
    def __init__(self, db: Database, api: TornAPI, notifier: DiscordNotifier):
        self.db = db
        self.api = api
        self.notifier = notifier
        self.running = False
        self.task = None
    
    async def start(self):
        """Start the market monitoring loop."""
        self.running = True
        self.task = asyncio.create_task(self._monitor_loop())
        logger.info("Market monitor started")
    
    async def stop(self):
        """Stop the market monitoring loop."""
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("Market monitor stopped")
    
    async def _monitor_loop(self):
        """Main monitoring loop that runs continuously."""
        logger.info(f"Starting market monitor loop (poll interval: {POLL_INTERVAL}s)")
        
        while self.running:
            try:
                await self._check_market()
                await asyncio.sleep(POLL_INTERVAL)
            except asyncio.CancelledError:
                logger.info("Market monitor loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}")
                # Wait before retrying on error
                await asyncio.sleep(POLL_INTERVAL)
    
    async def _check_market(self):
        """
        Main market checking logic.
        1. Get all tracked items with their users
        2. Fetch market data for each unique item ID (deduplication)
        3. Check prices against user thresholds
        4. Send notifications for qualifying deals
        """
        # Get all tracked items grouped by item_id
        tracked_items = await self.db.get_all_tracked_items_with_users()
        
        if not tracked_items:
            logger.debug("No items being tracked, skipping market check")
            return
        
        logger.info(f"Checking market for {len(tracked_items)} unique items")
        
        # Process each unique item
        for item_id, user_list in tracked_items.items():
            try:
                # Fetch market data (only once per item per cycle - deduplication!)
                raw_data = await self.api.get_item_market(item_id)
                
                if not raw_data:
                    logger.warning(f"Failed to fetch market data for item {item_id}")
                    continue
                
                # Extract relevant data
                market_data = self.api.extract_market_data(raw_data)
                if not market_data:
                    continue
                
                # Cache item information
                item_info = market_data["item"]
                if item_info.get("name"):
                    await self.db.cache_item_info(
                        item_id=item_id,
                        name=item_info.get("name", ""),
                        item_type=item_info.get("type", ""),
                        average_price=item_info.get("average_price", 0)
                    )
                
                # Get the cheapest listing
                cheapest = self.api.get_cheapest_listing(market_data)
                if not cheapest:
                    logger.debug(f"No listings available for item {item_id}")
                    continue
                
                listing_price = cheapest["price"]
                listing_amount = cheapest["amount"]
                
                logger.debug(f"Item {item_id}: cheapest price = {self.api.format_price(listing_price)}")
                
                # Check each user's threshold
                for user_id, max_price in user_list:
                    if listing_price < max_price:
                        await self._process_deal(
                            user_id=user_id,
                            item_id=item_id,
                            item_info=item_info,
                            listing=cheapest,
                            max_price=max_price
                        )
                
            except Exception as e:
                logger.error(f"Error processing item {item_id}: {e}")
                continue
        
        logger.info(f"Market check completed for {len(tracked_items)} items")
    
    async def _process_deal(self, user_id: str, item_id: int, item_info: Dict, 
                           listing: Dict, max_price: int):
        """
        Process a potential deal for a user.
        Checks cooldown and sends notification if appropriate.
        """
        # Check if we should notify (cooldown check)
        should_notify = await self.db.should_notify(user_id, item_id)
        
        if not should_notify:
            logger.debug(f"Cooldown active for user {user_id}, item {item_id}")
            return
        
        # Send notification
        success = await self.notifier.send_deal_notification(
            user_id=user_id,
            item_data=item_info,
            listing=listing,
            max_price=max_price
        )
        
        if success:
            # Record notification for cooldown tracking
            await self.db.record_notification(
                user_id=user_id,
                item_id=item_id,
                listing_price=listing["price"]
            )
            logger.info(
                f"Notified {user_id} about {item_info.get('name', f'Item #{item_id}')} "
                f"at {self.api.format_price(listing['price'])}"
            )
        else:
            logger.warning(f"Failed to notify {user_id} about deal for item {item_id}")
    
    async def run_single_check(self):
        """Run a single market check (useful for testing or manual triggers)."""
        await self._check_market()
    
    def is_running(self) -> bool:
        """Check if the monitor is currently running."""
        return self.running and self.task is not None and not self.task.done()