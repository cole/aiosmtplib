from setuptools import find_packages, setup


# See setup.cfg for package metadata.
setup(
    packages=find_packages('src'), package_dir={'': 'src'},
    include_package_data=True)
