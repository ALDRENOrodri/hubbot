import discord
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import asyncio

# Load environment variables
load_dotenv()

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Cooldown tracker - Format: {user_id: {"last_submit": timestamp, "thread_id": thread_id}}
bot.user_cooldowns = {}

# Get values from environment variables
PORTFOLIO_FORUM_CHANNEL_ID = int(os.getenv('CHANNEL_ID'))
YOUR_SERVER_ID = int(os.getenv('SERVER_ID'))

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
        # Process form submission (same as before)
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

        # Delete old thread if exists
        user_data = bot.user_cooldowns.get(interaction.user.id, {})
        if user_data and "thread_id" in user_data:
            try:
                old_thread = await forum_channel.fetch_thread(user_data["thread_id"])
                await old_thread.delete()
            except:
                pass  # Thread already deleted or not found

        # Create new thread
        thread = await forum_channel.create_thread(
            name=f"{interaction.user.display_name}'s Portfolio",
            embed=embed
        )

        # Update cooldown tracker
        bot.user_cooldowns[interaction.user.id] = {
            "last_submit": datetime.now(),
            "thread_id": thread.thread.id
        }

        await interaction.response.send_message(
            f"✅ Portfolio {'updated' if user_data else 'created'}! {thread.thread.jump_url}",
            ephemeral=True
        )

        # Schedule cooldown cleanup
        await self._schedule_cooldown_clear(interaction.user.id)

    async def _schedule_cooldown_clear(self, user_id):
        """Automatically clear cooldown after 5 minutes"""
        await asyncio.sleep(300)
        if user_id in bot.user_cooldowns:
            del bot.user_cooldowns[user_id]

class PortfolioView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(Button(label="Submit Portfolio", style=discord.ButtonStyle.primary, custom_id="submit_portfolio"))
    
    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.data["custom_id"] == "submit_portfolio":
            # Check cooldown BEFORE showing form
            now = datetime.now()
            user_data = bot.user_cooldowns.get(interaction.user.id, {})
            
            if user_data and (now - user_data["last_submit"]).total_seconds() < 300:
                remaining = 300 - (now - user_data["last_submit"]).total_seconds()
                await interaction.response.send_message(
                    f"⏳ Please wait {int(remaining // 60)}m {int(remaining % 60)}s before updating your portfolio again!",
                    ephemeral=True
                )
                return False
            
            await interaction.response.send_modal(PortfolioForm())
            return False
        return True

@bot.event
async def on_ready():
    await bot.wait_until_ready()
    try:
        bot.tree.copy_global_to(guild=discord.Object(id=YOUR_SERVER_ID))
        synced = await bot.tree.sync(guild=discord.Object(id=YOUR_SERVER_ID))
        print(f"✅ Synced {len(synced)} commands")
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
    name="portfolio_cooldown",
    description="Check your portfolio update cooldown status",
    guild=discord.Object(id=YOUR_SERVER_ID))
async def check_cooldown(interaction: discord.Interaction):
    user_data = bot.user_cooldowns.get(interaction.user.id, {})
    
    if not user_data:
        await interaction.response.send_message("🟢 You can submit a portfolio now!", ephemeral=True)
    else:
        remaining = 300 - (datetime.now() - user_data["last_submit"]).total_seconds()
        if remaining > 0:
            await interaction.response.send_message(
                f"⏳ You can update your portfolio in {int(remaining // 60)}m {int(remaining % 60)}s",
                ephemeral=True
            )
        else:
            await interaction.response.send_message("🟢 You can update your portfolio now!", ephemeral=True)

bot.run(os.getenv('DISCORD_TOKEN'))
