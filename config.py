import os
import sys
from dotenv import load_dotenv

load_dotenv()

TORN_API_KEY = os.getenv("TORN_API_KEY")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "32"))
COOLDOWN_MINUTES = int(os.getenv("COOLDOWN_MINUTES", "5"))
DATABASE_PATH = os.getenv("DATABASE_PATH", "torn_monitor.db")


def get_api_key_interactive():
    global TORN_API_KEY
    
    if TORN_API_KEY and TORN_API_KEY != "your_torn_api_key_here":
        return TORN_API_KEY
    
    print("=" * 50)
    print("Torn Market Monitor - API Key Setup")
    print("=" * 50)
    print()
    print("Please enter your Torn API key.")
    print("You can get one from: https://www.torn.com/settings.php")
    print()
    print("Note: The key will not be saved. Enter it each time you run the bot,")
    print("or set it in a .env file for permanent storage.")
    print()
    
    while True:
        api_key = input("Enter Torn API Key: ").strip()
        if api_key:
            TORN_API_KEY = api_key
            return api_key
        print("API key cannot be empty. Please try again.")


def validate_config():
    errors = []
    
    if not TORN_API_KEY or TORN_API_KEY == "your_torn_api_key_here":
        errors.append("TORN_API_KEY is not configured properly")
    
    if not DISCORD_BOT_TOKEN or DISCORD_BOT_TOKEN == "your_discord_bot_token_here":
        errors.append("DISCORD_BOT_TOKEN is not configured properly")
    
    if errors:
        raise ValueError("Configuration errors:\n" + "\n".join(errors))
    
    return True


def get_config_summary():
    return {
        "poll_interval": POLL_INTERVAL,
        "cooldown_minutes": COOLDOWN_MINUTES,
        "database_path": DATABASE_PATH,
        "torn_api_key_configured": bool(TORN_API_KEY and TORN_API_KEY != "your_torn_api_key_here"),
        "discord_token_configured": bool(DISCORD_BOT_TOKEN and DISCORD_BOT_TOKEN != "your_discord_bot_token_here"),
    }