from setuptools import setup, find_packages

setup(
    name="bluetools",
    version="0.1.0",
    description="Bluetooth-based device management service for ARM64 boards",
    author="Bluetools",
    packages=find_packages(),
    python_requires=">=3.6",
    install_requires=[
        "dbus-python>=1.3.1",
        "PyGObject>=3.42.0",
        "PyYAML>=6.0",
    ],
    entry_points={
        "console_scripts": [
            "bluetools=bluetools.__main__:main",
        ],
    },
)
