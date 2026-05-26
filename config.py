"""
Configuration management for the Torn Market Monitor bot.
Loads settings from environment variables and provides defaults.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Required configuration
TORN_API_KEY = os.getenv("TORN_API_KEY")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# Optional configuration with defaults
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "32"))  # Seconds between market checks
COOLDOWN_MINUTES = int(os.getenv("COOLDOWN_MINUTES", "5"))  # Notification cooldown per user/item
DATABASE_PATH = os.getenv("DATABASE_PATH", "torn_monitor.db")

# Validation
def validate_config():
    """Validate that all required configuration is present."""
    errors = []
    
    if not TORN_API_KEY or TORN_API_KEY == "your_torn_api_key_here":
        errors.append("TORN_API_KEY is not configured properly")
    
    if not DISCORD_BOT_TOKEN or DISCORD_BOT_TOKEN == "your_discord_bot_token_here":
        errors.append("DISCORD_BOT_TOKEN is not configured properly")
    
    if errors:
        raise ValueError("Configuration errors:\n" + "\n".join(errors))
    
    return True

def get_config_summary():
    """Return a summary of the current configuration (without secrets)."""
    return {
        "poll_interval": POLL_INTERVAL,
        "cooldown_minutes": COOLDOWN_MINUTES,
        "database_path": DATABASE_PATH,
        "torn_api_key_configured": bool(TORN_API_KEY and TORN_API_KEY != "your_torn_api_key_here"),
        "discord_token_configured": bool(DISCORD_BOT_TOKEN and DISCORD_BOT_TOKEN != "your_discord_bot_token_here"),
    }