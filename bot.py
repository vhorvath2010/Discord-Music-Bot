import discord
from discord import app_commands
from dotenv import load_dotenv
import os
import yt_dlp
import asyncio
import logging
import validators
from collections import deque

# Get our guild ID configured
load_dotenv()
CURRENT_GUILD = discord.Object(int(os.getenv('GUILD')))

# Make our queue of songs
queue = deque()

ytdl_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
}

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -c:a libopus -b:a 96k'
}

ytdl = yt_dlp.YoutubeDL(ytdl_options)

# Logging setup

logFormatter = logging.Formatter("%(asctime)s [%(levelname)s]     %(message)s", "%Y-%m-%d %H:%M:%S")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s]     %(message)s")

logger = logging.getLogger("MusicBot")



class DisconnectTimer:
    def __init__(self, timeout, callback):
        self.timeout = timeout
        self.disconnect_callback = callback
        self._task = None

    def start(self):
        self.cancel()
        self._task = asyncio.create_task(self._run())
        logger.info("All songs have ended. Starting timer.")

    def cancel(self):
        if self._task and not self._task.done():
            self._task.cancel()
    
    async def _run(self):
        try:
            await asyncio.sleep(self.timeout)
            await self.disconnect_callback()
        except asyncio.CancelledError:
            logger.info("Song added. Timer cancelled.")



class MusicBot(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)

        # Use a CommandTree for storing application commands
        self.tree = app_commands.CommandTree(self)
        self.current_vc = None

        # Setup disconnect timer for 5 minutes
        # disconnect_timer = DisconnectTimer(300, self.leave)

    # sync app commands to one guild so they show up to users
    async def setup_hook(self):
        self.tree.copy_global_to(guild=CURRENT_GUILD)
        await self.tree.sync(guild=CURRENT_GUILD)

intents = discord.Intents.default()
client = MusicBot(intents=intents)


# Basic logging - end of setup tasks
@client.event
async def on_ready():
    logger.info("Starting MusicBot. Logged in as %s", client.user)
    logger.info("Discord.py version: %s", discord.version_info)



async def search_async(query):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: _extract(query))



def _extract(query):
    return ytdl.extract_info(query, download=False)



# Register commands
@client.tree.command()
async def hello(interaction: discord.Interaction):
    """ Says hi back to user """
    await interaction.response.send_message(f"Hi there, {interaction.user.mention}!")



# Join the user's current voice channel
@client.tree.command(name='join')
async def join(interaction : discord.Interaction):
    """ Join the current voice channel of the user. """

    if(interaction.user.voice):
        await interaction.response.send_message(f"Joining channel {interaction.user.voice.channel.name}...")
        client.current_vc = await interaction.user.voice.channel.connect()
    else:
        await interaction.response.send_message(f"You aren't currently in a channel!")



# Play audio track from specified URL
@client.tree.command()
@app_commands.describe(
    query="URL to play or query to search for."
)
async def play(interaction: discord.Interaction, query: str):
    """ Plays either a specific URL or the first result from 'query'. """

    await interaction.response.defer()

    #MusicBot.disconnect_timer.cancel()

    voice_channel = interaction.user.voice.channel
    voice_client = interaction.guild.voice_client
    
    if voice_channel is None:
        await interaction.response.send_message(f"You must be in a voice channel to use this command.")
        return
    
    if voice_client is None:
        voice_client = await voice_channel.connect()
    elif voice_client.channel != voice_channel:
        await voice_client.move_to(voice_channel)

    if validators.url(query):

        queryinfo = ytdl.extract_info(query, download=False)

        audio_url = queryinfo.get("url", None)
        title = queryinfo.get("title", "Untitled")

    else:
        search_query = "ytsearch1: " + query

        results = await search_async(search_query)
        tracks = results.get("entries", [])
        
        if tracks is None:
            await interaction.response.send_message("No results found for query.")
            return
        
        first_track = tracks[0]
        audio_url = first_track["url"]
        title = first_track.get("title", "Untitled")


    queue.append((audio_url, title))

    if voice_client.is_playing() or voice_client.is_paused():
        await interaction.followup.send(f"Added to queue: {title}")
    else:
        await interaction.followup.send(f"Added to queue: {title}")
        await play_next(voice_client, interaction.channel)
    


# Pause the current audio stream
@client.tree.command()
async def pause(interaction: discord.Interaction):
    """ Pauses the current audio """
    await interaction.response.defer()

    if(client.current_vc):
        if(client.current_vc.is_paused()):
            await interaction.response.send_message(f"Audio is already paused.")
            return
        client.current_vc.pause()
        await interaction.response.send_message(f"Audio paused.")
    else:
        await interaction.response.send_message("Not currently in a voice channel.")



# Resume the audio stream if paused
@client.tree.command()
async def resume(interaction: discord.Interaction):
    """ Resumes the current audio """
    if(client.current_vc):
        if(client.current_vc.is_paused()):
            await interaction.response.send_message(f"Resuming audio...")
            client.current_vc.resume()
        else:
            await interaction.response.send_message(f"Audio is not paused.")
    else:
        await interaction.response.send_message("Not currently in a voice channel.")

@client.tree.command(name="skip", description="Skip the current playing song.")
async def skip(interaction: discord.Interaction):
    """ Skips the currently playing song. """

    if interaction.guild.voice_client and (interaction.guild.voice_client.is_playing() or interaction.guild.voice_client.is_paused()):
        interaction.guild.voice_client.stop()
        await interaction.response.send_message("Skipped the current song.")
    else:
        await interaction.response.send_message("Not playing a song to skip.")


# Leave the user's current voice channel
@client.tree.command()
async def leave(interaction: discord.Interaction):
    """ Leave the user's current voice channel """
    voice_client = interaction.guild.voice_client

    if not voice_client or not voice_client.is_connected():
        return await interaction.response.send_message("I'm not currently connected to any voice channel.")
    
    queue.clear()

    if voice_client.is_playing() or voice_client.is_paused():
        voice_client.stop()

    await voice_client.disconnect()
    await interaction.response.send_message("Stopped playback and disconnected from the voice channel.")


# Not a command. Helper function to play the next song in the queue.
async def play_next(voice_client, channel):
    if queue:
        audio_url, title = queue.popleft()

        source = discord.FFmpegOpusAudio(audio_url, **ffmpeg_options)

        def after_play(error):
            if error:
                print(f"Error playing {title}: {error}")
            asyncio.run_coroutine_threadsafe(play_next(voice_client, channel), client.loop)

        voice_client.play(source, after=after_play)

        asyncio.create_task(channel.send(f'Now playing: "{title}"'))
    # No more songs in queue, time to leave
    else:
        asyncio.create_task(channel.send(f'All songs have finished playing. Goodbye!'))
        await voice_client.disconnect()
        queue.clear()
        #MusicBot.disconnect_timer.start()


# Actually run the bot
client.run(os.getenv('BOT_TOKEN'), log_handler=None)