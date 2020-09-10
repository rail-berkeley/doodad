from distutils.core import setup
from setuptools import find_packages

setup(
    name='doodad',
    version='0.3.0dev',
    packages=find_packages(),
    license='MIT License',
    long_description=open('README.md').read(),
)
