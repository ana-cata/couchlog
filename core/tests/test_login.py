import pytest
from django.contrib.auth.models import User
from django.contrib.sessions.models import Session

from core.models import Profile

PASSWORD = 'made-up-password'


@pytest.fixture
def user(db):
    return User.objects.create_user(username='made-up-user', password=PASSWORD)


@pytest.fixture
def user_with_timezone(user):
    Profile.objects.create(user=user, timezone='Europe/Lisbon')
    return user


@pytest.mark.parametrize(
    'url, login_page',
    [('/', '/login/'), ('/profile/', '/login/'), ('/admin/', '/admin/login/')],
)
@pytest.mark.django_db
def test_pages_are_closed_when_logged_out(client, url, login_page):
    response = client.get(url)

    assert response.status_code == 302
    assert response['Location'].startswith(login_page)


@pytest.mark.django_db
def test_the_login_page_is_open_to_everyone(client):
    response = client.get('/login/')

    assert response.status_code == 200


def test_login_works_and_the_session_is_saved_in_the_database(client, user_with_timezone):
    response = client.post('/login/', {'username': 'made-up-user', 'password': PASSWORD})

    assert response.status_code == 302
    assert response['Location'] == '/'
    assert client.get('/').status_code == 200
    # Sessions are stored in the SQLite file (the temporary one in tests).
    assert Session.objects.count() == 1


def test_a_wrong_password_is_refused(client, user_with_timezone):
    response = client.post('/login/', {'username': 'made-up-user', 'password': 'wrong'})

    assert response.status_code == 200
    assert 'Wrong username or password' in response.content.decode()
    assert client.get('/').status_code == 302
    assert Session.objects.count() == 0


def test_logout_closes_the_pages_again(client, user_with_timezone):
    client.force_login(user_with_timezone)
    assert client.get('/').status_code == 200

    response = client.post('/logout/')

    assert response.status_code == 302
    assert response['Location'] == '/login/'
    assert client.get('/').status_code == 302


def test_the_profile_page_shows_the_account_and_a_log_out_button(client, user_with_timezone):
    client.force_login(user_with_timezone)

    page = client.get('/profile/').content.decode()

    assert 'made-up-user' in page
    assert 'Log out' in page
