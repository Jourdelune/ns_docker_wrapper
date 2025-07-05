"""
ns_docker_wrapper

A Python wrapper for the Nerfstudio Docker image, inspired by ffmpeg-python.
"""

__version__ = "0.2.0"

from .manager import init
from .commands import train, process_data, process_images, custom_command, path

__all__ = [
    "init",
    "train",
    "process_data",
    "process_images",
    "custom_command",
    "path",
]
