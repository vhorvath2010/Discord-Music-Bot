# Discord-Music-Bot

Discord music bot with voice recognition functionality. The bot listens to voice conversations and automatically plays songs when triggered!

## Features

- **Voice Recognition**: Listens to voice conversations using speech recognition
- **Smart Song Detection**: Recognizes songs mentioned in voice chat
- **Automatic Playback**: Plays songs based on voice conversation history
- **Traditional Commands**: `/play`, `/pause`, `/resume`, `/skip`, `/leave`
- **Queue Management**: Automatic song queuing and playback

## Usage

### Voice Command Feature

The bot listens to voice conversations and automatically plays songs!

**How it works:**
1. Use `/join` to connect the bot to your voice channel
2. The bot starts listening to voice conversations
3. When someone says `"nester, spin that shit"` in voice chat
4. The bot scans recent voice conversation history
5. Finds song titles mentioned and plays them automatically

**Examples of what the bot recognizes:**
- `"Bohemian Rhapsody is amazing!"` → Bot finds "Bohemian Rhapsody"
- `"play Hotel California"` → Bot finds "Hotel California"  
- `"that Stairway to Heaven song rocks"` → Bot finds "Stairway to Heaven"
- `"Sweet Child O' Mine is fire"` → Bot finds "Sweet Child O' Mine"

### Commands

- `/join` - Join voice channel and start listening
- `/play [song/url]` - Play a song or add to queue
- `/pause` - Pause current playback
- `/resume` - Resume paused playback
- `/skip` - Skip current song
- `/leave` - Leave voice channel and stop listening
- `/voice_help` - Show voice command usage

# To Run

Scripts are provided for Ubuntu Server installations. Other operating systems will require some Python knowledge.

### Ubuntu Server:

Run `wget https://raw.githubusercontent.com/kaiserjd/Discord-Music-Bot/refs/heads/main/setup.sh`

Run `chmod +x setup.sh`

Move `setup.sh` to your home directory if it isn't already there.

Run `setup.sh`.

Populate the `.env` file with both your bot's token and the guild ID to join.

Run `bot.py` when setup is complete. You should probably set this up as a service or use something like `screen`.

### Other Operating Systems:

Install ffmpeg & python3.

Clone this repository to a local directory.

Create a python virtual environment at the new directory (recommended) or install requirements manually via pip (see requirements.txt).

Run bot.py with python3.
