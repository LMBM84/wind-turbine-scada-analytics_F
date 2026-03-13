from setuptools import setup, find_packages

setup(
    name="scada-shared",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "pydantic>=2.5",
        "pydantic-settings>=2.1",
        "python-dotenv>=1.0",
        "structlog>=23.0",
    ],
)
