import asyncio
import discord
import firebase_admin
import os
import re
import requests
import traceback
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv
from firebase_admin import credentials, db

load_dotenv()

cred = credentials.Certificate("credentials.json")
firebase_admin.initialize_app(cred, {
    "databaseURL": os.environ.get("FIREBASE_URL")
})

loop_interval = 5
prev_loop_time = 0
pluto_url = os.environ.get("PLUTONIUM_URL")
bot = commands.Bot(command_prefix="/", intents=discord.Intents.all())
db_ref = db.reference("/")
data = {}

def get_pluto_server_text(pluto_servers, guild_obj):
    text = {}
    code_block_text = {}
    prepend_text = {}
    append_text = {}

    for pluto_server in pluto_servers:
        game = pluto_server["game"]
        hostname = pluto_server["hostname"]
        player_list = pluto_server["players"]
        max_player_count = pluto_server["maxplayers"]

        hostname = re.sub("\^[0-9]", "", hostname) # remove text color change
        player_count = len(player_list)

        code_block_text.setdefault(game, "")
        prepend_text.setdefault(game, game.upper() + ":\n```\n")
        append_text.setdefault(game, "\n```")
        text_to_add = ""

        if guild_obj["servers_game"] != "" and game not in guild_obj["servers_game"].split():
            continue

        if guild_obj["servers_name"].lower() not in hostname.lower():
            continue

        if not guild_obj["servers_players_max"] and player_count >= max_player_count:
            continue

        if not guild_obj["servers_players_zero"] and player_count == 0:
            continue

        hostname = re.sub("`", "", hostname) # remove possible code block end

        if code_block_text[game] != "":
            text_to_add += "\n\n"

        text_to_add += hostname + "\n"
        text_to_add += str(player_count) + "/" + str(max_player_count) + " players"

        total_len = len(prepend_text[game] + code_block_text[game] + text_to_add + append_text[game])

        if total_len > 2000:
            continue

        code_block_text[game] += text_to_add

    for game in code_block_text:
        if guild_obj["message_edit"] and code_block_text[game] == "":
            code_block_text[game] = "No servers to show"

        text[game] = prepend_text[game] + code_block_text[game] + append_text[game]

    return text, code_block_text

async def guild_main(guild, db_obj, pluto_servers):
    id = str(guild.id)
    guild_obj = db_obj[id]
    guild_data = data.setdefault(id, {})
    guild_data.setdefault("text", {})
    guild_data.setdefault("message", {})

    if not guild_obj["channel_id"]:
        return

    channel = bot.get_channel(guild_obj["channel_id"])

    if not channel:
        return

    text, code_block_text = get_pluto_server_text(pluto_servers, guild_obj)

    for game in text:
        guild_data["text"].setdefault(game, "")
        guild_data["message"].setdefault(game, None)

        if guild_data["text"][game] == text[game]:
            continue

        guild_data["text"][game] = text[game]

        message = guild_data["message"][game]

        if guild_obj["message_edit"]:
            if message:
                try:
                    await message.edit(content=text[game])
                except Exception as e:
                    message = None
                    print(guild.name, "-", guild.id)
                    traceback.print_exc(limit=1)

            if not message:
                try:
                    message = await channel.send(text[game])
                    guild_data["message"][game] = message

                    if guild_obj["message_pin"]:
                        await message.pin()
                except Exception as e:
                    print(guild.name, "-", guild.id)
                    traceback.print_exc(limit=1)
        else:
            if message:
                try:
                    del guild_data["message"][game]
                    await message.delete()
                except Exception as e:
                    print(guild.name, "-", guild.id)
                    traceback.print_exc(limit=1)

            if code_block_text[game] == "":
                return

            try:
                message = await channel.send(text[game])
                guild_data["message"][game] = message

                if guild_obj["message_pin"]:
                    await message.pin()
            except Exception as e:
                print(guild.name, "-", guild.id)
                traceback.print_exc(limit=1)

@tasks.loop(seconds=loop_interval)
async def main():
    global prev_loop_time

    if bot.loop.time() - prev_loop_time < loop_interval:
        return

    prev_loop_time = bot.loop.time()

    pluto_page = requests.get(pluto_url)
    pluto_servers = pluto_page.json()
    pluto_servers = sorted(pluto_servers, key=lambda a : (a["game"], a["hostname"]))
    db_obj = db_ref.get()

    await asyncio.gather(*[guild_main(guild, db_obj, pluto_servers) for guild in bot.guilds])

@bot.event
async def on_ready():
    await bot.tree.sync()
    main.start()

@bot.event
async def on_guild_join(guild):
    id = str(guild.id)
    db_ref.child(id).child("channel_id").set(0)
    db_ref.child(id).child("servers_name").set("")
    db_ref.child(id).child("servers_game").set("")
    db_ref.child(id).child("servers_players_max").set(True)
    db_ref.child(id).child("servers_players_zero").set(False)
    db_ref.child(id).child("message_edit").set(False)
    db_ref.child(id).child("message_pin").set(False)

@bot.tree.command(name="channel", description="Set the channel where you want the servers to show.")
@app_commands.describe(channel="Channel where you want the servers to show")
@commands.has_guild_permissions(manage_messages=True)
async def set_channel_id(interaction:discord.Interaction, channel:discord.TextChannel):
    id = str(interaction.guild.id)
    db_ref.child(id).child("channel_id").set(channel.id)
    await interaction.response.send_message("Channel set to: " + channel.name)

servers_group = app_commands.Group(name="servers", description="Commands for servers.")

@servers_group.command(name="name", description="Set the name of the servers you want to show.")
@app_commands.describe(name="Substring of the name of the servers")
@commands.has_guild_permissions(manage_messages=True)
async def set_servers_name(interaction:discord.Interaction, name:str):
    id = str(interaction.guild.id)
    db_ref.child(id).child("servers_name").set(name)
    await interaction.response.send_message("Name of servers set to: " + name)

@servers_group.command(name="game", description="Add a game you want to show (default: All).")
@app_commands.describe(game="All, IW5MP, T4MP, T4SP, T5MP, T5SP, T6MP, T6ZM")
@app_commands.choices(game=[
    app_commands.Choice(name="All", value="all"),
    app_commands.Choice(name="IW5MP", value="iw5mp"),
    app_commands.Choice(name="T4MP", value="t4mp"),
    app_commands.Choice(name="T4SP", value="t4sp"),
    app_commands.Choice(name="T5MP", value="t5mp"),
    app_commands.Choice(name="T5SP", value="t5sp"),
    app_commands.Choice(name="T6MP", value="t6mp"),
    app_commands.Choice(name="T6ZM", value="t6zm")
])
@commands.has_guild_permissions(manage_messages=True)
async def set_servers_game(interaction:discord.Interaction, game:app_commands.Choice[str]):
    id = str(interaction.guild.id)

    if game.value == "all":
        db_ref.child(id).child("servers_game").set("")
    else:
        db_games = db_ref.child(id).child("servers_game").get()

        if game.value in db_games.split():
            await interaction.response.send_message("Game already added.")
            return

        if db_games == "":
            db_ref.child(id).child("servers_game").set(game.value)
        else:
            db_ref.child(id).child("servers_game").set(db_games + " " + game.value)

    await interaction.response.send_message("Game added: " + game.name)

players_group = app_commands.Group(name="players", description="Commands for players on servers.", parent=servers_group)

@players_group.command(name="max", description="Show servers that have max players (default: True).")
@app_commands.describe(option="True or False")
@commands.has_guild_permissions(manage_messages=True)
async def set_servers_players_max(interaction:discord.Interaction, option:bool):
    id = str(interaction.guild.id)
    db_ref.child(id).child("servers_players_max").set(option)
    await interaction.response.send_message("Show max player servers set to: " + str(option))

@players_group.command(name="zero", description="Show servers that have zero players (default: False).")
@app_commands.describe(option="True or False")
@commands.has_guild_permissions(manage_messages=True)
async def set_servers_players_zero(interaction:discord.Interaction, option:bool):
    id = str(interaction.guild.id)
    db_ref.child(id).child("servers_players_zero").set(option)
    await interaction.response.send_message("Show zero player servers set to: " + str(option))

bot.tree.add_command(servers_group)

message_group = app_commands.Group(name="message", description="Commands for message.")

@message_group.command(name="edit", description="Edit existing message instead of creating a new message (default: False).")
@app_commands.describe(option="True or False")
@commands.has_guild_permissions(manage_messages=True)
async def set_message_edit(interaction:discord.Interaction, option:bool):
    id = str(interaction.guild.id)
    db_ref.child(id).child("message_edit").set(option)
    await interaction.response.send_message("Edit message set to: " + str(option))

@message_group.command(name="pin", description="Pin message when it is created (default: False).")
@app_commands.describe(option="True or False")
@commands.has_guild_permissions(manage_messages=True)
async def set_message_pin(interaction:discord.Interaction, option:bool):
    id = str(interaction.guild.id)
    db_ref.child(id).child("message_pin").set(option)
    await interaction.response.send_message("Pin message set to: " + str(option))

bot.tree.add_command(message_group)

bot.run(os.environ.get("DISCORD_API_TOKEN"))