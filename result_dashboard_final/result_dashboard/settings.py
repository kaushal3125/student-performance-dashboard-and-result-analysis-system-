import os
import dj_database_url
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-result-hub-dev-secret-key-change-in-production-2024')
DEBUG = os.environ.get('DEBUG', 'True').lower() == 'true'

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '0.0.0.0', '.vercel.app', '.now.sh']

# Support Render if ever needed
RENDER_EXTERNAL_HOSTNAME = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'results',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'result_dashboard.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'result_dashboard.wsgi.application'

# --- Database ---
# On Vercel, the filesystem is read-only except /tmp.
# We copy the pre-built db.sqlite3 to /tmp on first run so it is writable.
_DB_SOURCE = BASE_DIR / 'db.sqlite3'
_DB_TMP = Path('/tmp/db.sqlite3')

def _get_db_path():
    """Return a writable path for the SQLite database."""
    if os.environ.get('VERCEL'):
        import shutil
        if not _DB_TMP.exists() and _DB_SOURCE.exists():
            shutil.copy2(_DB_SOURCE, _DB_TMP)
        return _DB_TMP
    return _DB_SOURCE

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': _get_db_path(),
    }
}

database_url = os.environ.get("DATABASE_URL")
if database_url:
    DATABASES['default'] = dj_database_url.parse(database_url)

# --- Static Files ---
STATIC_URL = '/static/'
_STATIC_DIR = BASE_DIR / 'static'
STATICFILES_DIRS = [_STATIC_DIR] if _STATIC_DIR.exists() else []
STATIC_ROOT = BASE_DIR / 'staticfiles'

# WhiteNoise compressed static files
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

LOGIN_REDIRECT_URL = '/'
LOGIN_URL = 'login'
LOGOUT_REDIRECT_URL = '/login/'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Message tags
from django.contrib.messages import constants as messages
MESSAGE_TAGS = {
    messages.DEBUG: 'secondary',
    messages.INFO: 'info',
    messages.SUCCESS: 'success',
    messages.WARNING: 'warning',
    messages.ERROR: 'danger',
}