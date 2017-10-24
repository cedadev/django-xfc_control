
# -*- coding: utf-8 -*-

import os


# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


DEBUG = True


# Read the secret key from a file
SECRET_KEY_FILE = '/home/vagrant/XFC/conf/secret_key.txt'
with open(SECRET_KEY_FILE) as f:
    SECRET_KEY = f.read().strip()


# Logging settings


# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
        'django_extensions',
        'xfc_control',
    ]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    ]

ROOT_URLCONF = 'xfc_site.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
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

WSGI_APPLICATION = 'xfc_site.wsgi.application'


# Database
DATABASES = {
        'default' : {
                                'ENGINE' : 'django.db.backends.postgresql',
                                            'HOST' : '/tmp',
                                            'ATOMIC_REQUESTS' : True,
                                            'NAME' : 'xfc_control',
                        },
    }


# Authentication settings
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
LANGUAGE_CODE = 'en-gb'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_L10N = True
USE_TZ = False


# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = '/var/www/static'


# Email
# Email
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
SERVER_EMAIL = DEFAULT_FROM_EMAIL = 'xfc@xfc.ceda.ac.uk'



# Put your custom settings here.
ALLOWED_HOSTS=["192.168.51.25",
               "192.168.51.25"]

# App specific settings file for the xfc_control app
XFC_LOG_PATH = "/var/log/xfc"
XFC_DEFAULT_QUOTA_SIZE = 300*1024*1024*1024*1024   # default quota size (2GB)
XFC_DEFAULT_HARD_LIMIT =  40*1024*1024*1024*1024   # default hard limit size (2GB)
XFC_DEFAULT_MAX_PERSISTENCE = 365                  # default maximum time a file is allowed to persist for
XFC_LDAP_BASE_USER = "OU=jasmin,OU=People,O=hpc,DC=rl,DC=ac,DC=uk"
XFC_LDAP_PRIMARY = "ldap://homer.esc.rl.ac.uk"
XFC_LDAP_REPLICAS = ["ldap://marge.esc.rl.ac.uk", "ldap://wiggum.jc.rl.ac.uk"]

