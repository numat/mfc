from setuptools import setup

setup(
    name="mfc",
    version="0.2.9",
    description="Python driver for MKS mass flow controllers.",
    url="http://github.com/numat/mfc/",
    author="Patrick Fuller",
    author_email="pat@numat-tech.com",
    packages=['mfc'],
    entry_points={
        'console_scripts': [('mfc = mfc:command_line')]
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
