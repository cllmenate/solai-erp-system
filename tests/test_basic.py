from django.conf import settings


def test_settings_testing():
    assert settings.DEBUG is False
    assert settings.DATABASES['default']['ENGINE'] == 'django.db.backends.sqlite3'

def test_homepage_unauthorized(client):
    # Tests that client requests work within testing environment
    response = client.get('/admin/login/')
    assert response.status_code == 200
