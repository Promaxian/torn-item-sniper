# Torn Market Monitor Discord Bot

A Python Discord bot that monitors the Torn item market and sends Discord notifications whenever tracked items are listed below user-defined price thresholds.

## Features

- **Real-time Price Monitoring**: Continuously checks Torn's item market every 30-35 seconds
- **Notification Cooldown**: Prevents spam with configurable cooldown periods (default: 5 minutes)
- **Item Caching**: Locally caches item names and details to reduce API calls
- **Rich Discord Integration**: Embed notifications with price, discount, and item details

## Commands

- `!track <item_id> <max_price>` - Start tracking an item (e.g., `!track 206 900000`)
- `!untrack <item_id>` - Stop tracking an item
- `!price <item_id> <new_price>` - Update price threshold for a tracked item
- `!list` - Show all items you're currently tracking
- `!iteminfo <item_id>` - Get information about an item
- `!status` - Show bot status and configuration
- `!help` - Display help information

1. **Push to GitHub**
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin <your-github-repo-url>
   git push -u origin main
   ```

## Project Structure

```
Bot/
├── .env                   # Environment variables
├── .gitignore             # Git ignore rules
├── requirements.txt       # Python dependencies
├── main.py                # Bot entry point and commands
├── config.py              # Configuration management
├── database.py            # SQLite database layer
├── torn_api.py            # Torn API client
├── notifier.py            # Discord notification handler
├── market_monitor.py      # Market monitoring logic
└── README.md              # This file
```

## How It Works

1. **User Configuration**: Users add items to track using `!track <item_id> <max_price>`
2. **Database Storage**: All tracking data is stored in SQLite
3. **Polling Loop**: Every 30-35 seconds, the bot:
   - Collects all unique item IDs being tracked
   - Fetches market data for each item
   - Compares cheapest listing against each user's threshold
   - Checks cooldown to prevent notification spam
   - Sends Discord DM notifications for qualifying deals
4. **Item Caching**: Item names and details are cached locally to reduce API calls
5. **Error Handling**: Automatic retries and error recovery

## API Rate Limiting
The bot respects Torn's API rate limits:
- Polls every 30-35 seconds (based on `cache_delay` from API)
- Handles 429 (Too Many Requests) responses gracefully
- Deduplicates requests across all users

## Database Schema

- **users**: Discord user IDs
- **tracked_items**: User tracking preferences (item_id, max_price)
- **item_cache**: Cached item information (name, type, average_price)
- **notification_history**: Tracks sent notifications for cooldown

## Troubleshooting

### Bot doesn't respond to commands
- Ensure the bot has proper permissions in your Discord server
- Check that Message Content Intent is enabled in Discord Developer Portal
- Verify the bot token is correct in `.env`

### No notifications received
- Check that your DMs are open for the server
- Verify you're tracking items with realistic price thresholds
- Check bot logs for any errors

### API errors
- Verify your Torn API key is valid
- Check that you have API access enabled on your Torn account
- Ensure you're not hitting rate limits

## License
Copyright © 2026 Promaxian

All rights reserved.

This source code may not be copied, modified, redistributed, or used without explicit permission from the author.

## Support

For issues, questions, or suggestions, please contact Promaxian[] in-game
**Note**: This bot is not affiliated with or endorsed by Torn or Discord.