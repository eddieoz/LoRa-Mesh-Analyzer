from setuptools import setup, find_packages

setup(
    name="mesh_analyzer",
    version="0.1.0",
    description="LoRa Mesh Analyzer for Meshtastic networks",
    packages=find_packages(),
    install_requires=[
        "meshtastic",
        "pypubsub",
        "PyYAML",
        "markdown",
    ],
    entry_points={
        "console_scripts": [
            "mesh-analyzer=mesh_analyzer.monitor:main",
        ],
    },
)
