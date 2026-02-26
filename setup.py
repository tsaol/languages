import re
from setuptools import setup, find_packages

# Read version from englearn/__init__.py (single source of truth)
with open('englearn/__init__.py') as f:
    version = re.search(r'__version__\s*=\s*"(.+?)"', f.read()).group(1)

setup(
    name='englearn',
    version=version,
    packages=find_packages(),
    install_requires=[
        'requests',
        'mem0ai',
        'qdrant-client',
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
