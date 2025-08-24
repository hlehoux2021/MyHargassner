"""
Setup description for MyHargassner as a system service
"""

from setuptools import setup, find_packages

setup(
    name="myghargassner",
    version="1.0.0",
    description="Hargassner boiler gateway and MQTT integration",
    author="hlehoux2021",
    packages=find_packages(),
    install_requires=[
        "paho-mqtt",
        "ha-mqtt-discoverable",
        "psutil",
        "pydantic",
        "annotated_types",
    ],
    entry_points={
        'console_scripts': [
            'myghargassner = main:main',
        ],
    },
    include_package_data=True,
    python_requires='>=3.8',
)
