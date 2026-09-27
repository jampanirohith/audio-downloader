# Runtime Notes

Python 3.11+ is supported. FFmpeg and FFprobe are required for audio conversion and inspection. Current yt-dlp may require a supported external JavaScript runtime for some YouTube extraction paths; `python main.py --doctor` checks this.

Spotify uses the Client Credentials flow and requires a client ID/secret when enabled. The project does not download Spotify audio. Spotify album artwork is used only as catalog artwork and is preserved in the original returned form.

LRCLIB uses only `GET /api/get`. Network rate-limit and retry handling is implemented; plain-only lyrics are ignored.

The final MP3 + LRC + JSON output is designed for Windows filesystem safety and atomic finalization.
