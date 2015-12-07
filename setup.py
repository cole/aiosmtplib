import os

from setuptools import setup

__docformat__ = 'markdown'


def read(f):
    return open(os.path.join(os.path.dirname(__file__), f)).read().strip()


setup(name='aiosmtplib',
      version='0.0.1',
      description= 'Aiosmtplib is an implementation of the python stdlib smtplib using asyncio, for use in asynchronous applications..',
      long_description=read('README.markdown'),
      classifiers=[
          'Development Status :: 5 - Production/Stable',
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
      platforms=['OS Independent'],
      author='Cole Maclean',
      author_email='hi@cole.io',
      url='https://github.com/cole/aiosmtplib',
      # download_url='https://github.com/cole/aiosmtplib',
      keywords = ['asyncio', 'smtp'],
      license='Apache 2',
      packages=['aiosmtplib'],
      # install_requires=install_requires,
      # tests_require = tests_require,
      # test_suite = 'py.test',
      provides=['aiosmtplib'],
      include_package_data=True,
      # entry_points="""
      # [console_scripts]
      # api_hour=api_hour.application:run
      # """,
      )
