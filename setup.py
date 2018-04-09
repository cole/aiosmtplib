import re
from pathlib import Path

from setuptools import find_packages, setup


VERSION_REGEX = r'^__version__\s*=\s*[\'"]([^\'"]*)[\'"]'

init = Path('src/aiosmtplib/__init__.py')
readme = Path(__file__).with_name('README.rst')
version_match = re.search(VERSION_REGEX, init.read_text('utf-8'), re.MULTILINE)

if version_match:
    version = version_match.group(1)
else:
    raise RuntimeError('Cannot find version information')

setup(
    name='aiosmtplib',
    version=version,
    description='asyncio SMTP client',
    long_description=readme.read_text('utf-8'),
    author='Cole Maclean',
    author_email='hi@cole.io',
    url='https://github.com/cole/aiosmtplib',
    packages=find_packages('src'),
    package_dir={'': 'src'},
    license='MIT',
    keywords=['smtp', 'email', 'asyncio'],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: No Input/Output (Daemon)',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: Implementation :: CPython',
        'Topic :: Communications :: Email',
        'Topic :: System :: Networking',
    ],
    extras_require={
        'docs': [
            'sphinx>=1.8,<2.0',
            'sphinx_autodoc_typehints>=1.3,<2.0',
        ],
        'testing': [
            'hypothesis>=3.0,<4.0',
            'pytest>=3.0,<4.0',
            'pytest-asyncio>=0.8,<1.0',
            'pytest-cov>=2.5,<3.0',
            'wheel[signatures]',
        ]
    }
)
