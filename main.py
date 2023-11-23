import discord
import firebase_admin
import os
import requests
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv
from firebase_admin import credentials, db

load_dotenv()

cred = credentials.Certificate("credentials.json")
firebase_admin.initialize_app(cred, {
    "databaseURL": os.environ.get("FIREBASE_URL")
})

pluto_url = os.environ.get("PLUTONIUM_URL")
bot = commands.Bot(command_prefix="/", intents=discord.Intents.all())
db_ref = db.reference("/")
data = {}

def get_pluto_server_text(pluto_servers, guild_obj):
    text = ""
    guild_games = guild_obj["games"]
    guild_server_name = guild_obj["server_name"]
    guild_max_player_servers = guild_obj["max_player_servers"]
    guild_zero_player_servers = guild_obj["zero_player_servers"]

    for pluto_server in pluto_servers:
        game = pluto_server["game"]
        hostname = pluto_server["hostname"]
        player_list = pluto_server["players"]
        max_player_count = pluto_server["maxplayers"]
        player_count = len(player_list)

        if guild_games != "" and game not in guild_games.split():
            continue

        if guild_server_name.lower() not in hostname.lower():
            continue

        if not guild_max_player_servers and player_count >= max_player_count:
            continue

        if not guild_zero_player_servers and player_count == 0:
            continue

        if text != "":
            text += "\n\n"

        text += hostname + "\n"
        text += str(player_count) + "/" + str(max_player_count) + " players"

        if len(text) >= 1000:
            break

    return text

@tasks.loop(seconds=5)
async def main():
    pluto_page = requests.get(pluto_url)
    pluto_servers = pluto_page.json()
    db_obj = db_ref.get()

    for guild in bot.guilds:
        id = str(guild.id)
        guild_obj = db_obj[id]
        guild_data = data.setdefault(id, {})
        guild_data.setdefault("text", "")
        guild_data.setdefault("message_id", 0)

        if not guild_obj["channel_id"]:
            continue

        channel = bot.get_channel(guild_obj["channel_id"])

        if not channel:
            continue

        text = get_pluto_server_text(pluto_servers, guild_obj)

        if guild_data["text"] == text:
            continue

        guild_data["text"] = text

        message = None

        if guild_data["message_id"]:
            try:
                message = await channel.fetch_message(guild_data["message_id"])
            except Exception as e:
                print(guild.name, "-", e)

        if guild_obj["edit_message"]:
            if text == "":
                text = "No servers to show"

            if message:
                try:
                    await message.edit(content=text)
                except Exception as e:
                    print(guild.name, "-", e)
            else:
                try:
                    message = await channel.send(text)
                    guild_data["message_id"] = message.id

                    if guild_obj["pin_message"]:
                        await message.pin()
                except Exception as e:
                    print(guild.name, "-", e)
        else:
            if message:
                try:
                    del guild_data["message_id"]
                    await message.delete()
                except Exception as e:
                    print(guild.name, "-", e)

            if text == "":
                return

            try:
                message = await channel.send(text)
                guild_data["message_id"] = message.id

                if guild_obj["pin_message"]:
                    await message.pin()
            except Exception as e:
                print(guild.name, "-", e)

@bot.event
async def on_ready():
    await bot.tree.sync()
    main.start()

@bot.event
async def on_guild_join(guild):
    id = str(guild.id)
    db_ref.child(id).child("server_name").set("")
    db_ref.child(id).child("games").set("")
    db_ref.child(id).child("channel_id").set(0)
    db_ref.child(id).child("edit_message").set(False)
    db_ref.child(id).child("pin_message").set(False)
    db_ref.child(id).child("zero_player_servers").set(False)
    db_ref.child(id).child("max_player_servers").set(True)

@bot.tree.command(name="server-name", description="Set the name of the servers you want to show.")
@app_commands.describe(name="Substring of the name of the servers")
@commands.has_permissions(administrator=True)
async def set_server_name(interaction:discord.Interaction, name:str):
    id = str(interaction.guild.id)
    db_ref.child(id).child("server_name").set(name)
    await interaction.response.send_message("Server name set.")

@bot.tree.command(name="game", description="Add a game you want to show (default: All).")
@app_commands.describe(game="All, IW5, T4, T4ZM, T5, T5ZM, T6, T6ZM")
@app_commands.choices(game=[
    app_commands.Choice(name="All", value="all"),
    app_commands.Choice(name="IW5", value="iw5"),
    app_commands.Choice(name="T4", value="t4"),
    app_commands.Choice(name="T4ZM", value="t4zm"),
    app_commands.Choice(name="T5", value="t5"),
    app_commands.Choice(name="T5ZM", value="t5zm"),
    app_commands.Choice(name="T6", value="t6"),
    app_commands.Choice(name="T6ZM", value="t6zm")
])
@commands.has_permissions(administrator=True)
async def set_game(interaction:discord.Interaction, game:app_commands.Choice[str]):
    id = str(interaction.guild.id)

    if game.value == "all":
        db_ref.child(id).child("games").set("")
    else:
        db_games = db_ref.child(id).child("games").get()

        if game.value in db_games.split():
            await interaction.response.send_message("Game already added.")
            return

        if db_games == "":
            db_ref.child(id).child("games").set(game.value)
        else:
            db_ref.child(id).child("games").set(db_games + " " + game.value)

    await interaction.response.send_message("Game added.")

@bot.tree.command(name="channel", description="Set the channel where you want the servers to show.")
@app_commands.describe(channel="Channel where you want the servers to show")
@commands.has_permissions(administrator=True)
async def set_channel(interaction:discord.Interaction, channel:discord.TextChannel):
    id = str(interaction.guild.id)
    db_ref.child(id).child("channel_id").set(channel.id)
    await interaction.response.send_message("Channel set.")

@bot.tree.command(name="edit-message", description="Edit existing message instead of creating a new message (default: False).")
@app_commands.describe(option="True or False")
@commands.has_permissions(administrator=True)
async def set_edit_message(interaction:discord.Interaction, option:bool):
    id = str(interaction.guild.id)
    db_ref.child(id).child("edit_message").set(option)
    await interaction.response.send_message("Edit message set.")

@bot.tree.command(name="pin-message", description="Pin message when it is created (default: False).")
@app_commands.describe(option="True or False")
@commands.has_permissions(administrator=True)
async def set_pin_message(interaction:discord.Interaction, option:bool):
    id = str(interaction.guild.id)
    db_ref.child(id).child("pin_message").set(option)
    await interaction.response.send_message("Pin message set.")

@bot.tree.command(name="show-zero-player-servers", description="Show servers that have zero players (default: False).")
@app_commands.describe(option="True or False")
@commands.has_permissions(administrator=True)
async def set_zero_player_servers(interaction:discord.Interaction, option:bool):
    id = str(interaction.guild.id)
    db_ref.child(id).child("zero_player_servers").set(option)
    await interaction.response.send_message("Show zero player servers set.")

@bot.tree.command(name="show-max-player-servers", description="Show servers that have max players (default: True).")
@app_commands.describe(option="True or False")
@commands.has_permissions(administrator=True)
async def set_max_player_servers(interaction:discord.Interaction, option:bool):
    id = str(interaction.guild.id)
    db_ref.child(id).child("max_player_servers").set(option)
    await interaction.response.send_message("Show max player servers set.")

bot.run(os.environ.get("DISCORD_API_TOKEN"))