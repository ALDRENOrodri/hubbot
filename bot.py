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
COOLDOWN_HOURS = 72  # 3-day cooldown
PORTFOLIO_FORUM_CHANNEL_ID = int(os.getenv('CHANNEL_ID'))
YOUR_SERVER_ID = int(os.getenv('SERVER_ID'))
LOG_CHANNEL_ID = int(os.getenv('LOG_CHANNEL_ID'))  # Add to .env

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
        self.repo = git.Repo("/home/ubuntu/discord-bot")
        self.origin = self.repo.remote("origin")
        
    async def sync_with_github(self):
        try:
            self.origin.fetch()
            self.repo.git.reset("--hard", "origin/main")
            self.repo.git.clean("-fd", "discord-bot")
            return True
        except Exception as e:
            print(f"Update failed: {str(e)}")
            return False

# Initialize managers
bot.cooldowns = CooldownManager()
bot.updater = UpdateManager()

class PortfolioForm(Modal, title="Submit Your Portfolio"):
    portfolio_url = TextInput(
        label="Portfolio URL",
        placeholder="https://yourportfolio.example.com",
        required=True
    )
    
    experience_level = TextInput(
        label="Experience Level",
        placeholder="Beginner/Intermediate/Advanced/Professional",
        required=True
    )
    
    editing_software = TextInput(
        label="Editing Software",
        placeholder="Adobe Premiere, DaVinci Resolve, etc.",
        required=True
    )
    
    editing_specialties = TextInput(
        label="Editing Specialties",
        placeholder="Color grading, motion graphics, etc.",
        required=True
    )
    
    additional_info = TextInput(
        label="Additional Information",
        placeholder="Any extra details",
        style=discord.TextStyle.long,
        required=False
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title=f"{interaction.user.display_name}'s Portfolio",
            color=discord.Color.blue()
        )
        
        embed.add_field(name="Portfolio URL", value=self.portfolio_url.value, inline=False)
        embed.add_field(name="Experience Level", value=self.experience_level.value, inline=False)
        embed.add_field(name="Editing Software", value=self.editing_software.value, inline=False)
        embed.add_field(name="Editing Specialties", value=self.editing_specialties.value, inline=False)
        
        if self.additional_info.value:
            embed.add_field(name="Additional Info", value=self.additional_info.value, inline=False)
        
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        
        forum_channel = bot.get_channel(PORTFOLIO_FORUM_CHANNEL_ID)
        if not forum_channel:
            return await interaction.response.send_message("❌ Error: Forum channel not found!", ephemeral=True)

        cooldown_data = bot.cooldowns.get_cooldown(interaction.user.id)
        if cooldown_data and "thread_id" in cooldown_data:
            try:
                old_thread = await forum_channel.fetch_thread(cooldown_data["thread_id"])
                await old_thread.delete()
            except:
                pass

        thread = await forum_channel.create_thread(
            name=f"{interaction.user.display_name}'s Portfolio",
            embed=embed
        )

        bot.cooldowns.set_cooldown(
            interaction.user.id,
            datetime.now(),
            thread.thread.id
        )

        await interaction.response.send_message(
            f"✅ Portfolio {'updated' if cooldown_data else 'created'}! {thread.thread.jump_url}",
            ephemeral=True
        )

class PortfolioView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(Button(label="Submit Portfolio", style=discord.ButtonStyle.primary, custom_id="submit_portfolio"))
    
    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.data["custom_id"] == "submit_portfolio":
            cooldown_data = bot.cooldowns.get_cooldown(interaction.user.id)
            
            if cooldown_data:
                last_submit = datetime.fromisoformat(cooldown_data["last_submit"])
                time_passed = datetime.now() - last_submit
                
                if time_passed < timedelta(hours=COOLDOWN_HOURS):
                    remaining = timedelta(hours=COOLDOWN_HOURS) - time_passed
                    days = remaining.days
                    hours = remaining.seconds // 3600
                    await interaction.response.send_message(
                        f"⏳ You can update your portfolio in {days}d {hours}h",
                        ephemeral=True
                    )
                    return False
            
            await interaction.response.send_modal(PortfolioForm())
            return False
        return True

async def update_task():
    while True:
        await asyncio.sleep(3600)  # Check hourly
        if await bot.updater.sync_with_github():
            log_channel = bot.get_channel(LOG_CHANNEL_ID)
            if log_channel:
                embed = discord.Embed(
                    title="🔄 Bot Updated",
                    description=f"Automatically synced with GitHub\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    color=0x00ff00
                )
                await log_channel.send(embed=embed)

@bot.event
async def on_ready():
    await bot.wait_until_ready()
    try:
        bot.tree.copy_global_to(guild=discord.Object(id=YOUR_SERVER_ID))
        synced = await bot.tree.sync(guild=discord.Object(id=YOUR_SERVER_ID))
        print(f"✅ Synced {len(synced)} commands")
        
        bot.cooldowns.clear_expired_cooldowns()
        bot.loop.create_task(update_task())
        
    except Exception as e:
        print(f"❌ Command sync failed: {e}")
    print(f"✅ Bot is online: {bot.user}")
    bot.add_view(PortfolioView())

@bot.tree.command(
    name="create_portfolio_post",
    description="Create a portfolio submission post",
    guild=discord.Object(id=YOUR_SERVER_ID))
@commands.has_permissions(manage_messages=True)
async def create_portfolio_post(interaction: discord.Interaction):
    forum_channel = bot.get_channel(PORTFOLIO_FORUM_CHANNEL_ID)
    
    if not forum_channel:
        await interaction.response.send_message("❌ Error: Forum channel not found!", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="Start Here",
        description="Click the button below to submit your portfolio.",
        color=discord.Color.green()
    )
    
    thread = await forum_channel.create_thread(
        name="Post Portfolio Here:",
        embed=embed,
        view=PortfolioView()
    )
    
    await interaction.response.send_message(
        f"✅ Portfolio post created: {thread.thread.jump_url}",
        ephemeral=True
    )

@bot.tree.command(
    name="force_update",
    description="Manually trigger a GitHub sync",
    guild=discord.Object(id=YOUR_SERVER_ID))
@commands.has_permissions(administrator=True)
async def force_update(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    if await bot.updater.sync_with_github():
        embed = discord.Embed(
            title="✅ Manual Update Successful",
            description=f"Synced with GitHub at {datetime.now().strftime('%H:%M:%S')}",
            color=0x00ff00
        )
        log_channel = bot.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            await log_channel.send(embed=embed)
        await interaction.followup.send("Bot updated successfully!", ephemeral=True)
    else:
        await interaction.followup.send("❌ Update failed. Check logs.", ephemeral=True)

bot.run(os.getenv('DISCORD_TOKEN'))
