import discord
import os
import requests
from discord.ext import tasks
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.environ.get("DISCORD_API_TOKEN")

pluto_url = "https://plutonium.pw/api/servers"
pluto_server_game = ""
pluto_server_name = ""
channel_name = ""
client = discord.Client(intents=discord.Intents.default())
channel_msgs = {}
pluto_server_player_counts = {}

def get_pluto_server_info(pluto_servers):
    pluto_servers_info = []

    for pluto_server in pluto_servers:
        if len(pluto_server_game) > 0 and pluto_server["game"] != pluto_server_game:
            continue

        if pluto_server_name.lower() not in pluto_server["hostname"].lower():
            continue

        pluto_server_info = {}

        pluto_server_info["hostname"] = pluto_server["hostname"]
        pluto_server_info["players"] = pluto_server["players"]
        pluto_server_info["maxplayers"] = pluto_server["maxplayers"]

        pluto_servers_info.append(pluto_server_info)

    return pluto_servers_info

def get_channel_id(guild):
    for channel in guild.channels:
        if not isinstance(channel, discord.channel.TextChannel):
            continue

        if channel_name.lower() not in channel.name.lower():
            continue

        return channel.id

    return None

@tasks.loop(seconds=5)
async def main():
    text = ""
    update_msg = False

    pluto_page = requests.get(pluto_url)
    pluto_servers = pluto_page.json()
    pluto_servers_info = get_pluto_server_info(pluto_servers)

    for pluto_server_info in pluto_servers_info:
        hostname = pluto_server_info["hostname"]
        player_list = pluto_server_info["players"]
        max_player_count = pluto_server_info["maxplayers"]

        player_count = len(player_list)

        if hostname not in pluto_server_player_counts or pluto_server_player_counts[hostname] != player_count:
            pluto_server_player_counts[hostname] = player_count
            update_msg = True

        if player_count > 0:
            if len(text) > 0:
                text += "\n\n"

            text += hostname + "\n"
            text += str(player_count) + "/" + str(max_player_count) + " players"

        if len(text) >= 1000:
            break

    if update_msg:
        for guild in client.guilds:
            channel_id = get_channel_id(guild)

            if not channel_id:
                continue

            channel = client.get_channel(channel_id)

            if channel_id in channel_msgs:
                try:
                    await channel_msgs[channel_id].delete()
                except Exception as e:
                    print(channel.guild.name, "-", e)

                del channel_msgs[channel_id]

            if len(text) > 0:
                try:
                    channel_msgs[channel_id] = await channel.send(text)
                except Exception as e:
                    print(channel.guild.name, "-", e)

@client.event
async def on_ready():
    main.start()

client.run(TOKEN)