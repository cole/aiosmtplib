import os

from setuptools import setup


def read(f):
    return open(os.path.join(os.path.dirname(__file__), f)).read().strip()


setup(
    name='aiosmtplib',
    packages=['aiosmtplib'],
    version='0.1.3',
    description='asyncio version of smtplib',
    long_description=read('README.rst'),
    author='Cole Maclean',
    author_email='hi@cole.io',
    url='https://github.com/cole/aiosmtplib',
    download_url='https://github.com/cole/aiosmtplib/tarball/0.1.3',
    license='MIT',
    keywords=['smtp', 'email', 'asyncio'],
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: No Input/Output (Daemon)',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: Implementation :: CPython',
        'Topic :: Communications :: Email',
        'Topic :: System :: Networking',
    ],
)
