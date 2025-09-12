import discord
from discord import app_commands
from dotenv import load_dotenv
import os
import yt_dlp
import asyncio
import logging
import validators
from collections import deque
import speech_recognition as sr
import io
import wave
import threading
import re
from datetime import datetime, timedelta

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
        
        # Voice recognition setup
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = 300
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.pause_threshold = 0.8
        
        # Voice conversation history tracking
        self.voice_conversation_history = []
        self.max_voice_history_length = 20  # Keep last 20 voice segments
        
        # Voice listening state
        self.is_listening = False
        self.voice_sink = None
        self.current_voice_client = None

        # Setup disconnect timer for 5 minutes
        # disconnect_timer = DisconnectTimer(300, self.leave)

    # sync app commands to one guild so they show up to users
    async def setup_hook(self):
        self.tree.copy_global_to(guild=CURRENT_GUILD)
        await self.tree.sync(guild=CURRENT_GUILD)
    

    async def play_song_from_title(self, song_title, channel):
        """Play a song based on its title"""
        try:
            # Get voice client
            voice_client = self.current_voice_client
            
            if voice_client is None:
                await channel.send("I'm not connected to a voice channel.")
                return
            
            # Search for the song
            search_query = "ytsearch1: " + song_title
            results = await search_async(search_query)
            tracks = results.get("entries", [])
            
            if tracks is None or len(tracks) == 0:
                await channel.send(f"No results found for '{song_title}'.")
                return
            
            first_track = tracks[0]
            audio_url = first_track["url"]
            title = first_track.get("title", "Untitled")
            
            # Add to queue
            queue.append((audio_url, title))
            
            if voice_client.is_playing() or voice_client.is_paused():
                await channel.send(f"🎵 Added to queue: {title}")
            else:
                await channel.send(f"🎵 Now playing: {title}")
                await play_next(voice_client, channel)
                
        except Exception as e:
            logger.error(f"Error playing song: {e}")
            await channel.send(f"Sorry, I couldn't play '{song_title}'. Try again!")

    async def start_voice_listening(self, voice_client, channel):
        """Start listening to voice channel for speech recognition"""
        if self.is_listening:
            return
        
        self.is_listening = True
        self.current_voice_client = voice_client
        
        # Create a sink to receive audio data
        self.voice_sink = VoiceSink(self, channel)
        voice_client.start_recording(self.voice_sink)
        
        logger.info("Started voice listening")
        await channel.send("🎤 Now listening for voice commands!")

    async def stop_voice_listening(self, channel):
        """Stop listening to voice channel"""
        if not self.is_listening:
            return
        
        self.is_listening = False
        
        if self.current_voice_client:
            self.current_voice_client.stop_recording()
        
        self.voice_sink = None
        self.current_voice_client = None
        
        logger.info("Stopped voice listening")
        await channel.send("🔇 Stopped voice listening")

    def add_voice_transcript(self, text, user_id, timestamp):
        """Add a voice transcript to conversation history"""
        self.voice_conversation_history.append({
            'text': text,
            'user_id': user_id,
            'timestamp': timestamp
        })
        
        # Keep only the last max_voice_history_length segments
        if len(self.voice_conversation_history) > self.max_voice_history_length:
            self.voice_conversation_history = self.voice_conversation_history[-self.max_voice_history_length:]

    def extract_song_from_voice_history(self):
        """Extract song title from voice conversation history"""
        # Look for common song title patterns in recent voice messages
        song_patterns = [
            r'"([^"]+)"',  # Text in quotes
            r'play\s+(.+)',  # "play [song]"
            r'listen\s+to\s+(.+)',  # "listen to [song]"
            r'put\s+on\s+(.+)',  # "put on [song]"
            r'queue\s+(.+)',  # "queue [song]"
            r'(\w+(?:\s+\w+)*)\s+(?:is|was|are|were)\s+(?:a\s+)?(?:great|good|amazing|awesome|sick|fire|banger|hit|song)',  # "[song] is great"
            r'(?:that|this)\s+(\w+(?:\s+\w+)*)\s+(?:song|track)',  # "that [song] song"
        ]
        
        # Search through recent voice conversation history (last 10 segments)
        recent_segments = self.voice_conversation_history[-10:] if len(self.voice_conversation_history) >= 10 else self.voice_conversation_history
        
        for segment in reversed(recent_segments):  # Start from most recent
            text = segment['text'].lower()
            
            # Skip if it's the trigger phrase itself
            if "nester" in text and "spin" in text:
                continue
                
            # Look for song patterns
            for pattern in song_patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                if matches:
                    # Return the first match, cleaned up
                    song_title = matches[0].strip()
                    # Remove common prefixes/suffixes
                    song_title = re.sub(r'^(the|a|an)\s+', '', song_title, flags=re.IGNORECASE)
                    song_title = re.sub(r'\s+(by|from|feat\.?|ft\.?)\s+.*$', '', song_title, flags=re.IGNORECASE)
                    return song_title
        
        return None

    async def handle_voice_command_from_speech(self, channel):
        """Handle the voice command triggered from speech recognition"""
        try:
            # Extract song title from voice conversation history
            song_title = self.extract_song_from_voice_history()
            
            if song_title:
                logger.info(f"Found song title from voice: {song_title}")
                await self.play_song_from_title(song_title, channel)
            else:
                await channel.send("I couldn't find a song title in the recent voice conversation. Try mentioning a song first!")
                
        except Exception as e:
            logger.error(f"Error handling voice command from speech: {e}")
            await channel.send("Sorry, I had trouble processing that voice command!")


class VoiceSink(discord.AudioSink):
    """Custom sink to handle voice data and perform speech recognition"""
    
    def __init__(self, bot, channel):
        self.bot = bot
        self.channel = channel
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = 300
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.pause_threshold = 0.8
        
    def write(self, data, user):
        """Process incoming voice data"""
        if not self.bot.is_listening:
            return
            
        # Convert Discord audio data to format suitable for speech recognition
        try:
            # Create audio data from raw bytes
            audio_data = io.BytesIO(data)
            
            # Use threading to avoid blocking the voice receive
            threading.Thread(target=self._process_audio, args=(audio_data, user)).start()
            
        except Exception as e:
            logger.error(f"Error processing voice data: {e}")
    
    def _process_audio(self, audio_data, user):
        """Process audio data in a separate thread"""
        try:
            # Convert Discord audio format to something speech_recognition can handle
            # Discord sends 48kHz 16-bit stereo PCM data
            audio_data.seek(0)
            
            # Create a temporary WAV file
            with wave.open(audio_data, 'wb') as wav_file:
                wav_file.setnchannels(2)  # Stereo
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(48000)  # 48kHz
                wav_file.writeframes(audio_data.read())
            
            # Reset for reading
            audio_data.seek(0)
            
            # Use speech recognition
            with sr.AudioFile(audio_data) as source:
                audio = self.recognizer.record(source, duration=5)  # 5 second chunks
                
                try:
                    # Recognize speech using Google's service
                    text = self.recognizer.recognize_google(audio)
                    
                    if text:
                        logger.info(f"Voice transcript from {user}: {text}")
                        
                        # Add to voice conversation history
                        self.bot.add_voice_transcript(text, user.id, datetime.now())
                        
                        # Check for trigger phrase
                        if "nester" in text.lower() and "spin" in text.lower() and "shit" in text.lower():
                            logger.info(f"Voice command detected from {user}")
                            # Schedule the command handling in the event loop
                            asyncio.run_coroutine_threadsafe(
                                self.bot.handle_voice_command_from_speech(self.channel),
                                self.bot.loop
                            )
                            
                except sr.UnknownValueError:
                    # Speech not recognized, that's okay
                    pass
                except sr.RequestError as e:
                    logger.error(f"Speech recognition error: {e}")
                    
        except Exception as e:
            logger.error(f"Error in voice processing: {e}")
    
    def cleanup(self):
        """Cleanup when recording stops"""
        pass

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
client = MusicBot(intents=intents)


# Basic logging - end of setup tasks
@client.event
async def on_ready():
    logger.info("Starting MusicBot. Logged in as %s", client.user)
    logger.info("Discord.py version: %s", discord.version_info)


# Track conversation history (keeping for potential future use)
@client.event
async def on_message(message):
    # Ignore bot messages
    if message.author.bot:
        return
    
    # For now, we're focusing on voice recognition, but keeping this for potential future features
    pass





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


@client.tree.command()
async def voice_help(interaction: discord.Interaction):
    """ Shows how to use the voice command feature """
    help_text = """
🎤 **Voice Command Feature**

The bot listens to voice conversations and automatically plays songs!

**How it works:**
1. Use `/join` to connect the bot to your voice channel
2. The bot will start listening to voice conversations
3. When someone says: `"nester, spin that shit"` in voice chat
4. The bot scans recent voice conversation history
5. Finds song titles mentioned and plays them automatically

**Examples of what the bot recognizes:**
- `"Bohemian Rhapsody is amazing!"` → Bot finds "Bohemian Rhapsody"
- `"play Hotel California"` → Bot finds "Hotel California"  
- `"that Stairway to Heaven song rocks"` → Bot finds "Stairway to Heaven"
- `"Sweet Child O' Mine is fire"` → Bot finds "Sweet Child O' Mine"

**Voice Commands:**
- `/join` - Join voice channel and start listening
- `/leave` - Leave voice channel and stop listening
- `/voice_help` - Show this help message

The bot listens to the last 10 voice conversation segments to find songs!
    """
    await interaction.response.send_message(help_text)



# Join the user's current voice channel
@client.tree.command(name='join')
async def join(interaction : discord.Interaction):
    """ Join the current voice channel of the user and start voice listening. """

    if(interaction.user.voice):
        await interaction.response.send_message(f"Joining channel {interaction.user.voice.channel.name}...")
        voice_client = await interaction.user.voice.channel.connect()
        client.current_vc = voice_client
        
        # Start voice listening
        await client.start_voice_listening(voice_client, interaction.channel)
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
    
    # Stop voice listening
    await client.stop_voice_listening(interaction.channel)
    
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