"""How gunicorn (the program that serves Couchlog in Docker) runs it. Gunicorn reads this file by itself when it starts.

The Pi: two worker processes, on port 8000 (docker-compose.yml opens it as 3000).
The public demo on Render: one worker, so it fits the free plan's 512 MB of memory, on the port Render gives in PORT.
"""

import os

bind = f'0.0.0.0:{os.environ.get("PORT") or 8000}'
workers = 1 if os.environ.get('DEMO_MODE', '').strip().lower() == 'true' else 2
# Each worker serves 4 requests at once, so a page waiting for TMDB does not hold up the others.
threads = 4
