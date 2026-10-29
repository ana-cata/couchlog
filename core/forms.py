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
