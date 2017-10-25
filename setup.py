import os
from setuptools import setup

with open(os.path.join(os.path.dirname(__file__), 'README.rst')) as readme:
    README = readme.read()

# allow setup.py to be run from any path
os.chdir(os.path.normpath(os.path.join(os.path.abspath(__file__), os.pardir)))

setup(
    name='xfc_control',
    version='0.4.5',
    packages=['xfc_control'],
    install_requires=[
        'django',
        'django-sizefield',
        'django-extensions',
        'django-multiselectfield',
        'psycopg2',
        'jasmin-ldap',
    ],
    dependency_links=[
        'git+https://github.com/cedadev/jasmin-ldap.git@v0.3#egg=jasmin-ldap-0.3',
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
        # Replace these appropriately if you are stuck on Python 2.
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
    ],
)
