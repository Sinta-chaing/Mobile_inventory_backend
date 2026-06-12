"""
Base Django settings for core project.
Shared by development and production.
"""

from pathlib import Path
import os
from dotenv import load_dotenv
import dj_database_url

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Load environment variables from .env file
load_dotenv(BASE_DIR / '.env')

# Application definition
INSTALLED_APPS = [
    'grappelli',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework.authtoken',
    'api',
    'corsheaders',  # for CORS
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # For static files in production
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

# Database configuration from environment variables
if os.environ.get('DATABASE_URL'):
    DATABASES = {
        'default': dj_database_url.config(
            default=os.environ.get('DATABASE_URL'),
            conn_max_age=600
        )
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('DB_NAME', 'InventoryV2'),
            'USER': os.environ.get('DB_USER', 'postgres'),
            'PASSWORD': os.environ.get('DB_PASSWORD', 'vuth123321'),
            'HOST': os.environ.get('DB_HOST', 'localhost'),
            'PORT': os.environ.get('DB_PORT', '5432'),
        }
    }

AUTH_USER_MODEL = 'api.User'

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Phnom_Penh'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# REST Framework configuration
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ]
}

# KHQR Payment Configuration
KHQR_BASE_URL = os.environ.get('KHQR_BASE_URL', 'https://api-bakong.nbc.gov.kh')
KHQR_EMAIL = os.environ.get('KHQR_EMAIL', '')
KHQR_TOKEN = os.environ.get('KHQR_TOKEN', '')
KHQR_BAKONG_ACCOUNT_ID = os.environ.get('KHQR_BAKONG_ACCOUNT_ID', '')
KHQR_MERCHANT_NAME = os.environ.get('KHQR_MERCHANT_NAME', '')
KHQR_MERCHANT_CITY = os.environ.get('KHQR_MERCHANT_CITY', 'Phnom Penh')
KHQR_APP_ICON_URL = os.environ.get('KHQR_APP_ICON_URL', '')
KHQR_APP_NAME = os.environ.get('KHQR_APP_NAME', 'Inventory System')
KHQR_APP_DEEPLINK_CALLBACK = os.environ.get('KHQR_APP_DEEPLINK_CALLBACK', '')

# Image Search Configuration (Integrated in Backend)
IMAGE_SEARCH_QDRANT_PATH = os.environ.get('IMAGE_SEARCH_QDRANT_PATH', BASE_DIR / 'qdrant_storage')
IMAGE_SEARCH_COLLECTION_NAME = os.environ.get('IMAGE_SEARCH_COLLECTION_NAME', 'inventory_products')
IMAGE_SEARCH_YOLO_MODEL = os.environ.get('IMAGE_SEARCH_YOLO_MODEL', 'yolo26l.pt')
IMAGE_SEARCH_EMBEDDING_MODEL = os.environ.get('IMAGE_SEARCH_EMBEDDING_MODEL', 'clip-ViT-B-32')
IMAGE_SEARCH_DETECTION_CONFIDENCE = float(os.environ.get('IMAGE_SEARCH_DETECTION_CONFIDENCE', '0.25'))
