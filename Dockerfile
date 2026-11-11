# Couchlog in a container: a small Python 3.14 image that builds the same way on the PC and on the Pi (64-bit ARM).
FROM python:3.14-slim

# uv installs the packages exactly as uv.lock says. It is copied from its own image.
COPY --from=ghcr.io/astral-sh/uv:0.12.16 /uv /usr/local/bin/uv

# The packages go in /app/.venv, which comes first on the PATH. uv uses the image's own Python, not a downloaded one.
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# The packages first, so a code change does not install them all again. No dev tools (pytest, ruff, Playwright).
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project

# The code. .dockerignore keeps .env, the database and the tests out.
COPY . .

# Copy the CSS, logo and htmx into staticfiles/, where WhiteNoise serves them from.
# The key below only lets Django start for this one step. It is not kept and is not the real one.
RUN DJANGO_DEBUG=false DJANGO_SECRET_KEY=only-for-collectstatic python manage.py collectstatic --noinput

# Run as a normal user, not root. /data is where the database volume goes. It belongs to that user, so the
# volume starts out writable.
RUN useradd --create-home app && mkdir /data && chown app /data
USER app

EXPOSE 8000

# Apply the migrations, then start gunicorn. The migrations run at every start, so the PC and the Pi stay in step.
# The address, the port and the number of workers are in gunicorn.conf.py (one worker in the public demo).
CMD ["sh", "-c", "python manage.py migrate --noinput && exec gunicorn config.wsgi"]
