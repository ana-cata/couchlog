from zoneinfo import available_timezones

from django import forms

# Only the real regions, so the list does not fill up with old aliases like "US/Eastern".
REGIONS = (
    'Africa', 'America', 'Antarctica', 'Arctic', 'Asia', 'Atlantic',
    'Australia', 'Europe', 'Indian', 'Pacific',
)


def timezone_names():
    names = [name for name in available_timezones() if name.split('/')[0] in REGIONS]
    return sorted(names) + ['UTC']


class TimeZoneForm(forms.Form):
    timezone = forms.ChoiceField(label='Time zone')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['timezone'].choices = [('', 'Choose a time zone')] + [
            (name, name) for name in timezone_names()
        ]


class WatchedForm(forms.Form):
    """The date on the "Mark as watched" button: a day that has happened, or "unknown"."""

    watched_on = forms.DateField(required=False)
    date_unknown = forms.BooleanField(required=False)

    def __init__(self, *args, today, **kwargs):
        super().__init__(*args, **kwargs)
        self.today = today

    def clean(self):
        data = super().clean()
        if data.get('date_unknown'):
            data['watched_on'] = None
        elif 'watched_on' not in self.errors:
            day = data.get('watched_on')
            if day is None:
                self.add_error('watched_on', 'Pick the day you watched it, or tick “Date unknown”.')
            elif day > self.today:
                self.add_error('watched_on', 'That day has not happened yet.')
        return data
