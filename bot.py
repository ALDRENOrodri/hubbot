import discord
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import asyncio
import sqlite3
from pathlib import Path
import git
import subprocess
import signal
import sys
import importlib

# Load environment variables
load_dotenv()

# Configuration
COOLDOWN_HOURS = 72
PORTFOLIO_FORUM_CHANNEL_ID = int(os.getenv('CHANNEL_ID'))
YOUR_SERVER_ID = int(os.getenv('SERVER_ID'))
LOG_CHANNEL_ID = int(os.getenv('LOG_CHANNEL_ID', 0)) or None
GITHUB_REPO = "https://github.com/ALDRENOrodri/hubbot.git"
BOT_DIR = "/home/ubuntu/hubbot"

# Initialize bot
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Database setup
def setup_database():
    db_path = f"{BOT_DIR}/portfolio_cooldowns.db"
    Path(db_path).parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS cooldowns (
            user_id INTEGER PRIMARY KEY,
            last_submit TIMESTAMP,
            thread_id INTEGER
        )
    """)
    conn.commit()
    conn.close()

setup_database()

class CooldownManager:
    def __init__(self):
        self.conn = sqlite3.connect(f"{BOT_DIR}/portfolio_cooldowns.db", 
                                  check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
    
    def get_cooldown(self, user_id):
        c = self.conn.cursor()
        c.execute("SELECT * FROM cooldowns WHERE user_id = ?", (user_id,))
        return c.fetchone()
    
    def set_cooldown(self, user_id, last_submit, thread_id):
        c = self.conn.cursor()
        c.execute("""
            INSERT OR REPLACE INTO cooldowns 
            (user_id, last_submit, thread_id) 
            VALUES (?, ?, ?)
        """, (user_id, last_submit.isoformat(), thread_id))
        self.conn.commit()
    
    def clear_expired_cooldowns(self):
        c = self.conn.cursor()
        expiry_time = (datetime.now() - timedelta(hours=COOLDOWN_HOURS)).isoformat()
        c.execute("DELETE FROM cooldowns WHERE last_submit < ?", (expiry_time,))
        self.conn.commit()

class UpdateManager:
    def __init__(self):
        self.repo_path = BOT_DIR
        try:
            self.repo = git.Repo(self.repo_path)
            self.origin = self.repo.remote("origin")
        except:
            self.init_repo()
            
    def init_repo(self):
        if not os.path.exists(self.repo_path):
            os.makedirs(self.repo_path)
        repo = git.Repo.init(self.repo_path)
        origin = repo.create_remote("origin", GITHUB_REPO)
        origin.fetch()
        origin.pull("main")
        self.repo = repo
        self.origin = origin
    
    async def hard_reset(self):
        try:
            self.origin.fetch()
            self.repo.git.reset("--hard", "origin/main")
            self.repo.git.clean("-fd")
            subprocess.run(["python3", "-m", "pip", "install", "-r", "requirements.txt"], 
                          check=True, cwd=self.repo_path)
            return True
        except Exception as e:
            print(f"Update failed: {str(e)}")
            return False

# Initialize managers
bot.cooldowns = CooldownManager()
bot.updater = UpdateManager()

# Shutdown handler
def handle_shutdown():
    print("\n🛑 Received shutdown signal")
    if bot.is_closed():
        os._exit(0)
    asyncio.create_task(bot.close())

signal.signal(signal.SIGTERM, lambda *_: handle_shutdown())
signal.signal(signal.SIGINT, lambda *_: handle_shutdown())

# Portfolio form and view classes (keep your existing implementations)
class PortfolioForm(Modal, title="Submit Your Portfolio"):
    # ... [your existing form code] ...

class PortfolioView(View):
    # ... [your existing view code] ...

# Command registration
@bot.command()
@commands.is_owner()
async def reload(ctx):
    """Hot-reload the bot"""
    try:
        importlib.reload(sys.modules['__main__'])
        await ctx.send("✅ Bot reloaded successfully!")
    except Exception as e:
        await ctx.send(f"❌ Reload failed: {str(e)}")

@bot.tree.command(
    name="force_update",
    description="Manually trigger a GitHub sync",
    guild=discord.Object(id=YOUR_SERVER_ID))
@commands.has_permissions(administrator=True)
async def force_update(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    if await bot.updater.hard_reset():
        if LOG_CHANNEL_ID:
            channel = bot.get_channel(LOG_CHANNEL_ID)
            if channel:
                await channel.send(
                    f"♻️ Manual update by {interaction.user.mention} at "
                    f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
        await interaction.followup.send("✅ Update complete!", ephemeral=True)
    else:
        await interaction.followup.send("❌ Update failed", ephemeral=True)

# Core events
@bot.event
async def on_ready():
    print(f"\n✅ Logged in as {bot.user}")
    print("="*50)
    
    # Sync commands with retry
    for attempt in range(3):
        try:
            bot.tree.copy_global_to(guild=discord.Object(id=YOUR_SERVER_ID))
            synced = await bot.tree.sync(guild=discord.Object(id=YOUR_SERVER_ID))
            print(f"Synced {len(synced)} commands")
            break
        except Exception as e:
            print(f"⚠️ Sync failed (attempt {attempt + 1}): {e}")
            await asyncio.sleep(5)
    
    # Initialize systems
    bot.cooldowns.clear_expired_cooldowns()
    bot.add_view(PortfolioView())
    
    # Start background tasks
    async def update_task():
        while True:
            await asyncio.sleep(3600)  # Hourly checks
            if await bot.updater.hard_reset() and LOG_CHANNEL_ID:
                channel = bot.get_channel(LOG_CHANNEL_ID)
                if channel:
                    await channel.send(
                        f"⏩ Auto-updated at "
                        f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    )
    
    bot.loop.create_task(update_task())

# Start the bot
if __name__ == "__main__":
    try:
        bot.run(os.getenv('DISCORD_TOKEN'))
    finally:
        print("🛑 Bot process terminated")
