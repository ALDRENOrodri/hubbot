import discord
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput
import os
from dotenv import load_dotenv  # Add this import

# Load environment variables
load_dotenv()  # Add this line

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Get values from environment variables
PORTFOLIO_FORUM_CHANNEL_ID = int(os.getenv('CHANNEL_ID'))  # Updated
YOUR_SERVER_ID = int(os.getenv('SERVER_ID'))  # Updated

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
            await interaction.response.send_message("❌ Error: Forum channel not found!", ephemeral=True)
            return
        
        thread = await forum_channel.create_thread(
            name=f"{interaction.user.display_name}'s Portfolio",
            embed=embed
        )
        
        await interaction.response.send_message(
            f"✅ Portfolio created! Check it here: {thread.thread.jump_url}",
            ephemeral=True
        )

class PortfolioView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(Button(label="Submit Portfolio", style=discord.ButtonStyle.primary, custom_id="submit_portfolio"))
    
    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.data["custom_id"] == "submit_portfolio":
            await interaction.response.send_modal(PortfolioForm())
            return False
        return True

@bot.event
async def on_ready():
    await bot.wait_until_ready()
    try:
        # Sync commands to specific guild
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

# Get token from environment variable
bot.run(os.getenv('DISCORD_TOKEN'))  # Updated
