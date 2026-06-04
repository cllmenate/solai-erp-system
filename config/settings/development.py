from .base import *

DEBUG = True

ALLOWED_HOSTS = ['*']

# Database settings
DATABASES = {
    'default': env.db(
        'DATABASE_URL',
        default='postgresql://postgres:postgres@localhost:5432/solai_erp'
    )
}

# Redis & Cache Settings
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': env('REDIS_URL', default='redis://127.0.0.1:6379/1'),
    }
}
