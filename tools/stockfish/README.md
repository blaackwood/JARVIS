# Stockfish (external engine)

JARVIS includes chess-assistant, chess-coach and chess-teacher integrations that
communicate with the Stockfish UCI engine. The Stockfish executable is not
bundled in this repository. Download a build from the official Stockfish site:
https://stockfishchess.org/download/

Place the executable in tools/stockfish/ (or configure STOCKFISH_PATH / the
engine path in the chess settings). The integration also requires python-chess
and the screen-capture dependencies listed in requirements.txt.

Stockfish is a separate GPL-3.0 project. Its upstream attribution and GPL text
are retained here. The JARVIS MIT licence does not apply to Stockfish.
