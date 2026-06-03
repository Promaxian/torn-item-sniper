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
        self.running = True
        self.task = asyncio.create_task(self._monitor_loop())
        logger.info("Market monitor started")
    
    async def stop(self):
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("Market monitor stopped")
    
    async def _monitor_loop(self):
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
                await asyncio.sleep(POLL_INTERVAL)
    
    async def _check_market(self):
        tracked_items = await self.db.get_all_tracked_items_with_users()

        if not tracked_items:
            logger.debug("No items being tracked, skipping market check")
            return

        logger.info(f"Checking market for {len(tracked_items)} unique items")

        # Get all unique API keys from users
        api_keys = await self.db.get_all_api_keys()
        logger.info(f"Using {len(api_keys)} user API keys for market monitoring")

        for item_id, user_list in tracked_items.items():
            try:
                raw_data = None
                successful_key = None

                # Try each API key until we get successful data
                for api_key in api_keys:
                    try:
                        # Temporarily set the API key
                        original_key = self.api.api_key
                        self.api.api_key = api_key

                        raw_data = await self.api.get_item_market(item_id)

                        # Restore original key
                        self.api.api_key = original_key

                        if raw_data:
                            successful_key = api_key
                            break

                    except Exception as e:
                        logger.debug(f"Failed with API key {api_key[:4]}...: {e}")
                        continue

                if not raw_data:
                    logger.warning(f"Failed to fetch market data for item {item_id} with all available API keys")
                    continue

                market_data = self.api.extract_market_data(raw_data)
                if not market_data:
                    continue

                item_info = market_data["item"]
                if item_info.get("name"):
                    await self.db.cache_item_info(
                        item_id=item_id,
                        name=item_info.get("name", ""),
                        item_type=item_info.get("type", ""),
                        average_price=item_info.get("average_price", 0)
                    )

                cheapest = self.api.get_cheapest_listing(market_data)
                if not cheapest:
                    logger.debug(f"No listings available for item {item_id}")
                    continue

                listing_price = cheapest["price"]
                listing_amount = cheapest["amount"]

                logger.debug(f"Item {item_id}: cheapest price = {self.api.format_price(listing_price)} (using key {successful_key[:4]}...)")

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
        should_notify = await self.db.should_notify(user_id, item_id)
        
        if not should_notify:
            logger.debug(f"Cooldown active for user {user_id}, item {item_id}")
            return
        
        success = await self.notifier.send_deal_notification(
            user_id=user_id,
            item_data=item_info,
            listing=listing,
            max_price=max_price
        )
        
        if success:
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
        await self._check_market()
    
    def is_running(self) -> bool:
        return self.running and self.task is not None and not self.task.done()