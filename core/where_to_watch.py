"""Which country's streaming services a title's page shows: the country of the account's time zone."""

from functools import cache
from importlib.resources import files

# A time zone that belongs to no one country (UTC, or none chosen yet) shows Portugal's services.
FALLBACK_COUNTRY = 'PT'


def _rows(name):
    """The lines of one of the tables in the time zone data (the tzdata package), split at the tabs, without comments."""
    text = (files('tzdata.zoneinfo') / name).read_text(encoding='utf-8')
    return [line.split('\t') for line in text.splitlines() if line and not line.startswith('#')]


@cache
def _tables():
    """zone.tab gives each time zone its country (Europe/Lisbon -> PT); iso3166.tab gives each country its name.
    Read once, then kept: they only change when the tzdata package is updated."""
    zones = {row[2]: row[0] for row in _rows('zone.tab')}
    names = {row[0]: row[1] for row in _rows('iso3166.tab')}
    return zones, names


def country_of(zone_name):
    """The two-letter code and the name of the country of a time zone, like ('PT', 'Portugal'). Portugal when the time
    zone belongs to no one country."""
    zones, names = _tables()
    code = zones.get(zone_name or '', FALLBACK_COUNTRY)
    return code, names[code]
