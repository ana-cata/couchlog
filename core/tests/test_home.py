import pytest
from django.contrib.auth.models import User

from core.models import Profile


@pytest.mark.django_db
def test_home_page_shows_up_next(client):
    user = User.objects.create_user(username='made-up-user', password='made-up-password')
    Profile.objects.create(user=user, timezone='Europe/Lisbon')
    client.force_login(user)

    response = client.get('/')

    assert response.status_code == 200
    page = response.content.decode()
    assert 'Couchlog' in page
    assert 'Up Next' in page
