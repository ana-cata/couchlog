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


NOTE_MAX_LENGTH = 500
# What the page offers besides "No rating": 1 to 5 whole stars, each with the characters that show it.
STAR_CHOICES = [(number, '★' * number) for number in range(1, 6)]


class RatingForm(forms.Form):
    """The stars and the note on a title's page. Leaving the stars on "No rating" or the note empty removes it."""

    stars = forms.TypedChoiceField(
        choices=[('', 'No rating'), *((str(number), text) for number, text in STAR_CHOICES)],
        coerce=int,
        empty_value=None,
        required=False,
    )
    note = forms.CharField(required=False)

    def clean_note(self):
        # A browser sends a line break as two characters, but counts it as one in the box, so count it as one here too.
        note = self.cleaned_data['note'].replace('\r\n', '\n')
        if len(note) > NOTE_MAX_LENGTH:
            raise forms.ValidationError(
                f'The note can be at most {NOTE_MAX_LENGTH} characters, and yours has {len(note)}. Nothing was saved.'
            )
        return note


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
