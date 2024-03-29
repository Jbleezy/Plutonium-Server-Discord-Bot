import asyncio
import discord
import firebase_admin
import os
import re
import requests
import traceback
from datetime import datetime, timedelta
from discord import app_commands, utils
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

@tasks.loop()
async def main():
    start_time = datetime.now()

    pluto_page = requests.get(pluto_url)
    pluto_servers = pluto_page.json()
    pluto_servers = pluto_servers["servers"]
    pluto_servers = sorted(pluto_servers, key=lambda a : (a["game"], a["hostname"]))
    db_obj = db_ref.get()

    await asyncio.gather(*[guild_main(guild, db_obj, pluto_servers) for guild in bot.guilds])

    await utils.sleep_until(start_time + timedelta(seconds=60))

async def guild_main(guild, db_obj, pluto_servers):
    id = str(guild.id)

    guild_obj = db_obj.setdefault(id, {})
    guild_obj.setdefault("channel_id", 0)
    guild_obj.setdefault("servers_name", "")
    guild_obj.setdefault("servers_game", "")
    guild_obj.setdefault("servers_players_max", True)
    guild_obj.setdefault("servers_players_zero", False)
    guild_obj.setdefault("message_edit", False)
    guild_obj.setdefault("message_pin", False)

    if guild_obj["servers_name"] == "":
        return

    if not guild_obj["channel_id"]:
        return

    channel = bot.get_channel(guild_obj["channel_id"])

    if not channel:
        return

    guild_data = data.setdefault(id, {})
    guild_data.setdefault("text", {})
    guild_data.setdefault("message", {})

    text, code_block_text = get_pluto_server_text(pluto_servers, guild_obj)

    for game in text:
        guild_data["text"].setdefault(game, "")
        guild_data["message"].setdefault(game, None)

        if guild_data["text"][game] == text[game]:
            continue

        guild_data["text"][game] = text[game]

        message = guild_data["message"][game]

        if code_block_text[game] == "":
            if message:
                try:
                    del guild_data["message"][game]
                    await message.delete()
                except Exception as e:
                    print(guild.name, "-", guild.id)
                    traceback.print_exc(limit=1)

            continue

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

            try:
                message = await channel.send(text[game])
                guild_data["message"][game] = message

                if guild_obj["message_pin"]:
                    await message.pin()
            except Exception as e:
                print(guild.name, "-", guild.id)
                traceback.print_exc(limit=1)

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

        if guild_obj["servers_name"].lower() not in hostname.lower():
            continue

        if guild_obj["servers_game"] != "" and game not in guild_obj["servers_game"].split():
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
            if guild_obj["servers_game"] == "" or game in guild_obj["servers_game"].split():
                code_block_text[game] = "No servers to show"

        text[game] = prepend_text[game] + code_block_text[game] + append_text[game]

    return text, code_block_text

@main.before_loop
async def delete_prev_messages():
    db_obj = db_ref.get()

    await asyncio.gather(*[guild_delete_prev_messages(guild, db_obj) for guild in bot.guilds])

async def guild_delete_prev_messages(guild, db_obj):
    id = str(guild.id)

    guild_obj = db_obj.setdefault(id, {})
    guild_obj.setdefault("channel_id", 0)

    if not guild_obj["channel_id"]:
        return

    channel = bot.get_channel(guild_obj["channel_id"])

    if not channel:
        return

    bot_messages = []

    async for message in channel.history(limit=100):
        if message.author == bot.user:
            bot_messages.append(message)

    await channel.delete_messages(bot_messages)

@bot.event
async def on_ready():
    await bot.tree.sync()
    main.start()

@bot.tree.command(name="channel", description="Set the channel where you want the servers to show.")
@app_commands.describe(channel="Channel where you want the servers to show")
@commands.has_guild_permissions(manage_messages=True)
async def set_channel_id(interaction:discord.Interaction, channel:discord.TextChannel):
    await interaction.response.send_message("Channel set to: " + channel.name)

    id = str(interaction.guild.id)
    db_ref.child(id).child("channel_id").set(channel.id)

servers_group = app_commands.Group(name="servers", description="Commands for servers.")

@servers_group.command(name="name", description="Set the name of the servers you want to show.")
@app_commands.describe(name="Substring of the name of the servers")
@commands.has_guild_permissions(manage_messages=True)
async def set_servers_name(interaction:discord.Interaction, name:str):
    await interaction.response.send_message("Name of servers set to: " + name)

    id = str(interaction.guild.id)
    db_ref.child(id).child("servers_name").set(name)

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
    await interaction.response.send_message("Game added: " + game.name)

    id = str(interaction.guild.id)

    if game.value == "all":
        db_ref.child(id).child("servers_game").set("")
    else:
        db_games = db_ref.child(id).child("servers_game").get()

        if not db_games:
            db_ref.child(id).child("servers_game").set(game.value)
            return

        if game.value in db_games.split():
            return

        db_ref.child(id).child("servers_game").set(db_games + " " + game.value)

players_group = app_commands.Group(name="players", description="Commands for players on servers.", parent=servers_group)

@players_group.command(name="max", description="Show servers that have max players (default: True).")
@app_commands.describe(option="True or False")
@commands.has_guild_permissions(manage_messages=True)
async def set_servers_players_max(interaction:discord.Interaction, option:bool):
    await interaction.response.send_message("Show max player servers set to: " + str(option))

    id = str(interaction.guild.id)
    db_ref.child(id).child("servers_players_max").set(option)

@players_group.command(name="zero", description="Show servers that have zero players (default: False).")
@app_commands.describe(option="True or False")
@commands.has_guild_permissions(manage_messages=True)
async def set_servers_players_zero(interaction:discord.Interaction, option:bool):
    await interaction.response.send_message("Show zero player servers set to: " + str(option))

    id = str(interaction.guild.id)
    db_ref.child(id).child("servers_players_zero").set(option)

bot.tree.add_command(servers_group)

message_group = app_commands.Group(name="message", description="Commands for message.")

@message_group.command(name="edit", description="Edit existing message instead of creating a new message (default: False).")
@app_commands.describe(option="True or False")
@commands.has_guild_permissions(manage_messages=True)
async def set_message_edit(interaction:discord.Interaction, option:bool):
    await interaction.response.send_message("Edit message set to: " + str(option))

    id = str(interaction.guild.id)
    db_ref.child(id).child("message_edit").set(option)

@message_group.command(name="pin", description="Pin message when it is created (default: False).")
@app_commands.describe(option="True or False")
@commands.has_guild_permissions(manage_messages=True)
async def set_message_pin(interaction:discord.Interaction, option:bool):
    await interaction.response.send_message("Pin message set to: " + str(option))

    id = str(interaction.guild.id)
    db_ref.child(id).child("message_pin").set(option)

bot.tree.add_command(message_group)

bot.run(os.environ.get("DISCORD_API_TOKEN"))