"""
Setup description for MyHargassner as a system service
"""

from setuptools import setup, find_packages

setup(
    name="myhargassner",
    version="1.0.0",
    description="Hargassner boiler gateway and MQTT integration",
    author="hlehoux2021",
    packages=find_packages(include=['myhargassner', 'myhargassner.*']),
    install_requires=[
        "paho-mqtt>=2.1.0,<3.0.0",
        "ha-mqtt-discoverable==0.20.1",  # Specific version required
        "psutil>=7.0.0",
        "pydantic>=2.11.7,<3.0.0",
        "annotated_types>=0.7.0",
    ],
    entry_points={
        'console_scripts': [
            'myhargassner = myhargassner.main:main',
        ],
    },
    include_package_data=True,
    python_requires='>=3.8',
)
