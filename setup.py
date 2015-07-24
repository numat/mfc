from setuptools import setup

setup(
    name="mks",
    version="0.1.0",
    description="Python driver for MKS EtherCAT mass flow controllers.",
    url="http://github.com/numat/mks/",
    author="Patrick Fuller",
    author_email="pat@numat-tech.com",
    packages=['mks'],
    entry_points={
        'console_scripts': [('mks = mks:command_line')]
    },
    license='GPLv2',
    classifiers=[
        'License :: OSI Approved :: GNU General Public License v2 (GPLv2)',
        'Development Status :: 4 - Beta',
        'Natural Language :: English',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 2',
        'Topic :: Scientific/Engineering :: Human Machine Interfaces'
    ]
)
