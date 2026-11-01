"""The line under a title's name on its page, like '2023 · Movie · 1h 40min · Drama, Thriller'."""


def length(minutes):
    """A number of minutes as '45 min', '1h 40min' or '2h'."""
    hours, rest = divmod(minutes, 60)
    if not hours:
        return f'{rest} min'
    return f'{hours}h {rest}min' if rest else f'{hours}h'


def title_line(kind, year, status, runtime, genres):
    """The year, the kind, a series' status, the length and the genres, with a part left out when there is none.

    `runtime` is in minutes: a movie's length, or for a series its typical episode length ('~45 min per episode').
    `genres` is the list of {'id', 'name'} that TMDB gives. A missing year says 'Year unknown'.
    """
    parts = [year or 'Year unknown', kind.capitalize()]
    if status:
        parts.append(status)
    if runtime:
        parts.append(f'~{length(runtime)} per episode' if kind == 'series' else length(runtime))
    if genres:
        parts.append(', '.join(genre['name'] for genre in genres))
    return ' · '.join(parts)
