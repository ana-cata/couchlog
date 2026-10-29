import pytest
from django.contrib.auth.models import User

from core.forms import timezone_names
from core.models import Profile


@pytest.fixture
def user(db):
    return User.objects.create_user(username='made-up-user', password='made-up-password')


@pytest.fixture
def logged_in(client, user):
    client.force_login(user)
    return client


def saved_timezone(user):
    return Profile.objects.get(user=user).timezone


def test_without_a_time_zone_every_page_leads_to_the_profile_page(logged_in):
    for url in ['/', '/admin/']:
        response = logged_in.get(url)

        assert response.status_code == 302
        assert response['Location'] == '/profile/'


def test_the_profile_page_asks_for_a_time_zone_at_the_first_login(logged_in):
    page = logged_in.get('/', follow=True).content.decode()

    assert 'Choose your time zone to continue.' in page


def test_the_first_time_zone_is_saved_with_the_account(logged_in, user):
    response = logged_in.post('/profile/', {'timezone': 'Europe/Lisbon'})

    assert response.status_code == 302
    assert saved_timezone(user) == 'Europe/Lisbon'
    # Now that a time zone exists, the other pages open.
    assert logged_in.get('/').status_code == 200


def test_the_saved_time_zone_is_shown_and_selected_on_the_profile_page(logged_in, user):
    Profile.objects.create(user=user, timezone='Asia/Tokyo')

    page = logged_in.get('/profile/').content.decode()

    assert '<option value="Asia/Tokyo" selected>' in page


@pytest.mark.parametrize('value', ['', 'Mars/Olympus_Mons', 'US/Eastern', 'Etc/GMT+5'])
def test_a_time_zone_that_is_not_in_the_list_is_refused(logged_in, user, value):
    Profile.objects.create(user=user, timezone='Europe/Lisbon')

    response = logged_in.post('/profile/', {'timezone': value})

    assert response.status_code == 200
    assert 'Choose a time zone from the list.' in response.content.decode()
    assert saved_timezone(user) == 'Europe/Lisbon'


def test_changing_the_time_zone_can_be_undone_by_choosing_the_old_one(logged_in, user):
    logged_in.post('/profile/', {'timezone': 'Europe/Lisbon'})
    before = Profile.objects.filter(user=user).values()[0]

    logged_in.post('/profile/', {'timezone': 'America/New_York'})
    assert saved_timezone(user) == 'America/New_York'
    logged_in.post('/profile/', {'timezone': 'Europe/Lisbon'})

    assert Profile.objects.filter(user=user).values()[0] == before
    assert Profile.objects.count() == 1


def test_each_account_has_its_own_time_zone(client, user):
    other = User.objects.create_user(username='other-user', password='made-up-password')
    Profile.objects.create(user=user, timezone='Europe/Lisbon')
    Profile.objects.create(user=other, timezone='Asia/Tokyo')

    client.force_login(other)
    client.post('/profile/', {'timezone': 'Australia/Sydney'})

    assert saved_timezone(user) == 'Europe/Lisbon'
    assert saved_timezone(other) == 'Australia/Sydney'


def test_the_time_zone_list_has_real_regions_only():
    names = timezone_names()

    assert 'Europe/Lisbon' in names
    assert 'America/Argentina/Buenos_Aires' in names
    assert 'UTC' in names
    assert 'US/Eastern' not in names
    assert not any(name.startswith('Etc/') for name in names)
