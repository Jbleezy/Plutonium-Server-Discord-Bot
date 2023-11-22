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
db_root = db.reference("/")

def get_pluto_server_text(id, pluto_servers):
    text = ""
    db_games = db_root.child(id).child("games").get()
    db_server_name = db_root.child(id).child("server_name").get()

    for pluto_server in pluto_servers:
        game = pluto_server["game"]
        hostname = pluto_server["hostname"]
        player_list = pluto_server["players"]
        max_player_count = pluto_server["maxplayers"]

        valid_game = db_games == ""

        for db_game in db_games.split():
            if game.lower() == db_game.lower():
                valid_game = True
                break

        if not valid_game:
            continue

        if db_server_name.lower() not in hostname.lower():
            continue

        player_count = len(player_list)

        if player_count > 0:
            if len(text) > 0:
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

    for guild in bot.guilds:
        id = str(guild.id)
        db_channel_id = db_root.child(id).child("channel").get()
        db_message_id = db_root.child(id).child("message").get()
        db_text = db_root.child(id).child("text").get()

        if not db_channel_id:
            continue

        text = get_pluto_server_text(id, pluto_servers)

        if db_text == text:
            continue

        db_root.child(id).child("text").set(text)

        channel = bot.get_channel(db_channel_id)

        if db_message_id:
            try:
                message = await channel.fetch_message(db_message_id)
                db_root.child(id).child("message").set(0)
                await message.delete()
            except Exception as e:
                print(guild.name, "-", e)

        if len(text) > 0:
            try:
                msg = await channel.send(text)
                db_root.child(id).child("message").set(msg.id)
            except Exception as e:
                print(guild.name, "-", e)

@bot.event
async def on_ready():
    await bot.tree.sync()

    main.start()

@bot.event
async def on_guild_join(guild):
    id = str(guild.id)
    db_root.child(id).child("server_name").set("")
    db_root.child(id).child("games").set("")
    db_root.child(id).child("channel").set(0)
    db_root.child(id).child("message").set(0)
    db_root.child(id).child("text").set("")

@bot.tree.command(name="set_server_name", description="Set the name of the servers you want to show.")
@app_commands.describe(name="Substring of the name of the servers")
@commands.has_permissions(administrator=True)
async def set_server_name(interaction:discord.Interaction, name:str):
    id = str(interaction.guild.id)
    db_root.child(id).child("server_name").set(name)
    await interaction.response.send_message("Server name set.")

@bot.tree.command(name="set_games", description="Set which games you want to show (space separated).")
@app_commands.describe(games="IW5, T4, T4ZM, T5, T5ZM, T6, T6ZM")
@commands.has_permissions(administrator=True)
async def set_games(interaction:discord.Interaction, games:str=""):
    id = str(interaction.guild.id)
    db_root.child(id).child("games").set(games)
    await interaction.response.send_message("Server games set.")

@bot.tree.command(name="set_channel", description="Set the channel where you want the servers to show.")
@app_commands.describe(channel="Channel where you want the servers to show")
@commands.has_permissions(administrator=True)
async def set_channel(interaction:discord.Interaction, channel:discord.TextChannel):
    id = str(interaction.guild.id)
    db_root.child(id).child("channel").set(channel.id)
    await interaction.response.send_message("Channel set.")

bot.run(os.environ.get("DISCORD_API_TOKEN"))