from pathlib import Path

from setuptools import setup


setup(
    name='aiosmtplib',
    packages=['aiosmtplib'],
    version='0.1.5rc2',
    description='asyncio version of smtplib',
    long_description=Path(__file__).with_name('README.rst').read_text('utf-8'),
    author='Cole Maclean',
    author_email='hi@cole.io',
    url='https://github.com/cole/aiosmtplib',
    download_url='https://github.com/cole/aiosmtplib/tarball/0.1.5rc2',
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
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: Implementation :: CPython',
        'Topic :: Communications :: Email',
        'Topic :: System :: Networking',
    ],
    extras_require={
        'testing': [
            'pytest < 4.0',
            'pytest-asyncio ~= 0.5.0',
            'pytest-cov ~= 2.4',
            'wheel[signatures]'
        ]
    }
)
