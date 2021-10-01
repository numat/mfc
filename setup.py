"""Python driver for MKS mass flow controllers."""
from platform import python_version
from setuptools import setup

if python_version() < '3.5':
    raise ImportError("This module requires Python >=3.5")

with open('README.md', 'r') as in_file:
    long_description = in_file.read()

setup(
    name="mfc",
    version="0.4.0",
    description="Python driver for MKS mass flow controllers.",
    long_description=long_description,
    long_description_content_type='text/markdown',
    url="http://github.com/numat/mfc/",
    author="Patrick Fuller",
    author_email="pat@numat-tech.com",
    packages=['mfc'],
    entry_points={
        'console_scripts': [('mfc = mfc:command_line')]
    },
    install_requires=['aiohttp>=3.3'],
    license='GPLv2',
    classifiers=[
        'License :: OSI Approved :: GNU General Public License v2 (GPLv2)',
        'Development Status :: 4 - Beta',
        'Natural Language :: English',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Topic :: Scientific/Engineering :: Human Machine Interfaces'
    ]
)
