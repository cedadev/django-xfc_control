import os
from setuptools import setup

with open(os.path.join(os.path.dirname(__file__), 'README.rst')) as readme:
    README = readme.read()

# allow setup.py to be run from any path
os.chdir(os.path.normpath(os.path.join(os.path.abspath(__file__), os.pardir)))

setup(
    name='xfc_control',
    version='1.0.0',
    packages=['xfc_control', 'xfc_site'],
    install_requires=[
        'appdirs',
        'django==4.2',
        'django-sizefield',
        'django-extensions',
        'django-multiselectfield',
        'psycopg2-binary',
        'packaging',
        'pyparsing',
        'pytz',
        'six',
        'jasmin-ldap @ git+https://github.com/cedadev/jasmin-ldap.git@v1.0.2#egg=jasmin-ldap',
    ],
    include_package_data=True,
    license='my License',  # example license
    description='A Django app to control temporary file caching on groupworkspaces on JASMIN.',
    long_description=README,
    url='http://www.ceda.ac.uk/',
    author='Neil Massey',
    author_email='neil.massey@stfc.ac.uk',
    classifiers=[
        'Environment :: Web Environment',
        'Framework :: Django',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License', # example license
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.9',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
    ],
)
