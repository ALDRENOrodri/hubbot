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

# Load environment variables
load_dotenv()

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Constants
COOLDOWN_DB = "/home/ubuntu/discord-bot/portfolio_cooldowns.db"
COOLDOWN_HOURS = 72
PORTFOLIO_FORUM_CHANNEL_ID = int(os.getenv('CHANNEL_ID'))
YOUR_SERVER_ID = int(os.getenv('SERVER_ID'))
LOG_CHANNEL_ID = int(os.getenv('LOG_CHANNEL_ID'))

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
        try:
            self.repo = git.Repo("/home/ubuntu/discord-bot")
            self.origin = self.repo.remote("origin")
        except:
            self.init_repo()
            
    def init_repo(self):
        repo = git.Repo.init("/home/ubuntu/discord-bot")
        origin = repo.create_remote("origin", "https://github.com/YOUR_USERNAME/YOUR_REPO.git")
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
    await ctx.send("♻️ Reloading extensions...")
    for ext in list(bot.extensions.keys()):
        await bot.reload_extension(ext)
    await ctx.send("✅ Reload complete!")

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
            for ext in list(bot.extensions.keys()):
                await bot.reload_extension(ext)

@bot.event
async def on_ready():
    bot.loop.create_task(update_task())
    # ... [Rest of your existing on_ready] ...

@bot.tree.command(name="force_update")
@commands.has_permissions(administrator=True)
async def force_update(interaction: discord.Interaction):
    """Manually trigger a full update"""
    await interaction.response.defer(ephemeral=True)
    
    if await bot.updater.hard_reset():
        log_channel = bot.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            embed = discord.Embed(
                title="🔁 Manual Update",
                description=f"Triggered by {interaction.user.mention}\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                color=0x7289DA
            )
            await log_channel.send(embed=embed)
        
        await interaction.followup.send("✅ Update complete! Changes are live.", ephemeral=True)
    else:
        await interaction.followup.send("❌ Update failed. Check logs.", ephemeral=True)

# ... [Keep all other existing commands] ...

bot.run(os.getenv('DISCORD_TOKEN'))
