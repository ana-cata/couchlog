import pytest


@pytest.fixture(autouse=True)
def fast_password_hasher(settings):
    # Django hashes passwords slowly on purpose (about 0.4 seconds each), and almost every test creates a user
    # with a password. A fast hasher makes the tests much quicker. It only applies while tests run: the real
    # app keeps its strong hashing. The login tests still check that a right password logs in and a wrong one does not.
    settings.PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
