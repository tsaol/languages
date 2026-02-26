from setuptools import setup, find_packages

setup(
    name='englearn',
    version='0.3.0',
    packages=find_packages(),
    install_requires=[
        'requests',
    ],
    entry_points={
        'console_scripts': [
            'englearn=englearn.cli:main',
        ],
    },
    python_requires='>=3.8',
    package_data={
        'englearn': ['db/schema.sql'],
    },
)
