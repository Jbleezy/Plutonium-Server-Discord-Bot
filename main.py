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

pluto_url = "https://plutonium.pw/api/servers"
bot = commands.Bot(command_prefix="/", intents=discord.Intents.all())
db_ref = db.reference("/")

def get_pluto_server_text(pluto_servers, guild_obj):
    text = ""
    guild_games = guild_obj["games"]
    guild_server_name = guild_obj["server_name"]

    for pluto_server in pluto_servers:
        game = pluto_server["game"]
        hostname = pluto_server["hostname"]
        player_list = pluto_server["players"]
        max_player_count = pluto_server["maxplayers"]

        if guild_games != "" and game not in guild_games.split():
            continue

        if guild_server_name.lower() not in hostname.lower():
            continue

        player_count = len(player_list)

        if player_count > 0:
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
        guild_channel_id = guild_obj["channel"]
        guild_message_id = guild_obj["message"]
        guild_text = guild_obj["text"]

        if not guild_channel_id:
            continue

        text = get_pluto_server_text(pluto_servers, guild_obj)

        if guild_text == text:
            continue

        db_ref.child(id).child("text").set(text)

        channel = bot.get_channel(guild_channel_id)

        if guild_message_id:
            try:
                message = await channel.fetch_message(guild_message_id)
                db_ref.child(id).child("message").set(0)
                await message.delete()
            except Exception as e:
                print(guild.name, "-", e)

        if text != "":
            try:
                msg = await channel.send(text)
                db_ref.child(id).child("message").set(msg.id)
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
    db_ref.child(id).child("channel").set(0)
    db_ref.child(id).child("message").set(0)
    db_ref.child(id).child("text").set("")

@bot.tree.command(name="server-name", description="Set the name of the servers you want to show.")
@app_commands.describe(name="Substring of the name of the servers")
@commands.has_permissions(administrator=True)
async def set_server_name(interaction:discord.Interaction, name:str):
    id = str(interaction.guild.id)
    db_ref.child(id).child("server_name").set(name)
    await interaction.response.send_message("Server name set.")

@bot.tree.command(name="game", description="Add a game you want to show (shows all by default).")
@app_commands.describe(game="ALL, IW5, T4, T4ZM, T5, T5ZM, T6, T6ZM")
@app_commands.choices(game=[
    app_commands.Choice(name="ALL", value="all"),
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
    db_ref.child(id).child("channel").set(channel.id)
    await interaction.response.send_message("Channel set.")

bot.run(os.environ.get("DISCORD_API_TOKEN"))