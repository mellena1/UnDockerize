from setuptools import setup
from os import path


setup(
    name='UnDockerize',
    version='0.0.1',
    description='Creates an ansible file from a Dockerfile',
    long_description='Creates an ansible file from a Dockerfile',
    url='https://github.com/mellena1/UnDockerize',
    author='Andrew Mellen',
    author_email='andrew_mellen@icloud.com',
    license='MIT',
    entry_points={
        'console_scripts': ['undockerize = undockerize.undockerize:main']
    }
)
