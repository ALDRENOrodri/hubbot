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
import importlib
import sys

# Load environment variables
load_dotenv()

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Constants
COOLDOWN_DB = "/home/ubuntu/hubbot/portfolio_cooldowns.db"  # Changed path to hubbot
COOLDOWN_HOURS = 72
PORTFOLIO_FORUM_CHANNEL_ID = int(os.getenv('CHANNEL_ID'))
YOUR_SERVER_ID = int(os.getenv('SERVER_ID'))
LOG_CHANNEL_ID = int(os.getenv('LOG_CHANNEL_ID'))
GITHUB_REPO = "https://github.com/ALDRENOrodri/hubbot.git"  # Your repo

# Database setup
def setup_database():
    Path(COOLDOWN_DB).parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(COOLDOWN_DB)
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
        self.conn = sqlite3.connect(COOLDOWN_DB, check_same_thread=False)
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
        self.repo_path = "/home/ubuntu/hubbot"  # Changed to hubbot
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
            self.repo.git.reset("--hard", "origin/main")
            self.repo.git.clean("-fd")
            # Reinstall dependencies
            subprocess.run(["python3", "-m", "pip", "install", "-r", "requirements.txt"], check=True)
            return True
        except Exception as e:
            print(f"Hard reset failed: {str(e)}")
            return False

# Initialize managers
bot.cooldowns = CooldownManager()
bot.updater = UpdateManager()

# ... [Keep all your existing PortfolioForm, PortfolioView classes] ...

@bot.command()
@commands.is_owner()
async def reload(ctx):
    """Hot-reload the bot"""
    try:
        # Reload the main module
        importlib.reload(sys.modules['__main__'])
        await ctx.send("✅ Successfully reloaded bot.py!")
    except Exception as e:
        await ctx.send(f"❌ Reload failed: {str(e)}")

async def update_task():
    while True:
        await asyncio.sleep(3600)  # Hourly checks
        if await bot.updater.hard_reset():
            log_channel = bot.get_channel(LOG_CHANNEL_ID)
            if log_channel:
                embed = discord.Embed(
                    title="🔄 Auto-Update Complete",
                    description=f"Synced at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    color=0x00ff00
                )
                await log_channel.send(embed=embed)
            # Hot-reload
            importlib.reload(sys.modules['__main__'])

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    bot.loop.create_task(update_task())
    bot.cooldowns.clear_expired_cooldowns()
    
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands")
    except Exception as e:
        print(f"Error syncing commands: {e}")

    bot.add_view(PortfolioView())

# ... [Keep all other existing commands and bot.run()] ...

bot.run(os.getenv('DISCORD_TOKEN'))
