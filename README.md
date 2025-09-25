# Discord-Music-Bot

Discord music bot that's about as simple as it can get.

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
