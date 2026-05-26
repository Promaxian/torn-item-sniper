"""
Torn API client for the market monitor bot.
Uses aiohttp for async requests to Torn V2 API.
"""

import aiohttp
import logging
from typing import Optional, Dict, List, Any
from config import TORN_API_KEY

logger = logging.getLogger(__name__)

class TornAPI:
    def __init__(self, api_key: str = TORN_API_KEY):
        self.api_key = api_key
        self.base_url = "https://api.torn.com/v2"
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def close(self):
        """Close the aiohttp session."""
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info("Torn API session closed")
    
    async def _request(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Make an authenticated request to the Torn API."""
        session = await self._get_session()
        
        if params is None:
            params = {}
        
        # Add API key to parameters
        params["key"] = self.api_key
        
        url = f"{self.base_url}/{endpoint}"
        
        try:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return data
                elif response.status == 429:
                    logger.warning(f"Rate limited by Torn API. Retry after: {response.headers.get('Retry-After', 'unknown')}")
                    return None
                elif response.status == 401:
                    logger.error("Invalid Torn API key")
                    return None
                elif response.status == 403:
                    logger.error(f"Access forbidden: {endpoint}")
                    return None
                else:
                    logger.error(f"Torn API error ({response.status}): {endpoint}")
                    return None
        except aiohttp.ClientError as e:
            logger.error(f"Network error fetching {endpoint}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching {endpoint}: {e}")
            return None
    
    async def get_item_market(self, item_id: int, limit: int = 100) -> Optional[Dict[str, Any]]:
        """
        Get item market listings for a specific item.
        Returns the API response containing item info, listings, and metadata.
        Listings are sorted by lowest price first.
        """
        endpoint = f"market/{item_id}/itemmarket"
        params = {
            "limit": limit,
            "offset": 0
        }
        
        data = await self._request(endpoint, params)
        
        if data and "itemmarket" in data:
            # Cache item info if available
            item_info = data["itemmarket"].get("item", {})
            if item_info.get("name"):
                return data
            
            return data
        
        return None
    
    async def get_item_bazaar(self, item_id: int) -> Optional[Dict[str, Any]]:
        """
        Get bazaar listings for a specific item.
        Returns specialized bazaars selling this item.
        """
        endpoint = f"market/{item_id}/bazaar"
        
        data = await self._request(endpoint)
        
        if data and "bazaar" in data:
            return data
        
        return None
    
    def extract_market_data(self, data: Dict) -> Optional[Dict[str, Any]]:
        """
        Extract relevant data from item market API response.
        Returns a dictionary with item info, listings, and cache info.
        """
        if not data or "itemmarket" not in data:
            return None
        
        itemmarket = data["itemmarket"]
        
        return {
            "item": itemmarket.get("item", {}),
            "listings": itemmarket.get("listings", []),
            "cache_timestamp": itemmarket.get("cache_timestamp"),
            "cache_delay": itemmarket.get("cache_delay", 30),
            "total_listings": data.get("_metadata", {}).get("total", 0)
        }
    
    def get_cheapest_listing(self, market_data: Dict) -> Optional[Dict]:
        """
        Get the cheapest listing from market data.
        Listings are already sorted by price (lowest first).
        """
        listings = market_data.get("listings", [])
        if listings:
            return listings[0]
        return None
    
    def format_price(self, price: int) -> str:
        """Format price with commas for readability."""
        return f"${price:,}"
    
    def calculate_discount(self, market_price: int, listing_price: int) -> float:
        """Calculate discount percentage compared to average market price."""
        if market_price == 0:
            return 0.0
        return ((market_price - listing_price) / market_price) * 100