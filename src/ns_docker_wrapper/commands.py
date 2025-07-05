from __future__ import annotations
import os
from typing import Optional, Union, List
from .manager import _get_manager


class PathArgument:
    """
    A special wrapper for local paths that need to be copied into the Docker container's
    internal temporary volume before being passed to Nerfstudio.
    """

    def __init__(self, local_path: str):
        self.local_path = local_path


class ArgumentBuilder:
    """A helper class to recursively build dot-notation arguments."""

    def __init__(self, command: Command, prefix: str):
        self._command = command
        self._prefix = prefix

    def __getattr__(self, name: str) -> ArgumentBuilder:
        """
        Chains attributes to build the argument name (e.g., pipeline.model).
        Converts snake_case to kebab-case for the argument name.
        """
        new_prefix = f"{self._prefix}.{name.replace('_', '-')}"
        return ArgumentBuilder(self._command, new_prefix)

    def __call__(
        self, value: Optional[Union[str, int, float, bool, PathArgument]] = None
    ) -> Command:
        """
        Sets the value for the constructed argument.
        If value is a PathArgument, it will be copied to the internal Docker volume.
        """
        if isinstance(value, PathArgument):
            container_path = self._command._manager.copy_to_ns_temp_data(
                value.local_path
            )
            return self._command._add_arg(self._prefix, container_path)

        return self._command._add_arg(self._prefix, value)


class Command:
    """Represents a Nerfstudio command to be executed."""

    def __init__(self, base_command: str):
        self._manager = _get_manager()
        self._command_args: List[str] = [base_command]

    def _add_arg(
        self, key: str, value: Optional[Union[str, int, float, bool]]
    ) -> Command:
        """Adds a standard --key value argument."""

        self._command_args.append(f"--{key}")
        if value is not None:
            self._command_args.append(str(value))
        return self

    def add_positional_arg(self, value: str) -> Command:
        """
        Adds a positional argument (e.g., 'colmap') in the current position.
        Note: Positional arguments are not automatically copied to the internal volume.
        If a positional argument is a path, it must be relative to the output_base_path (mounted at /workspace).
        """
        self._command_args.append(value)
        return self

    def run(self) -> int:
        """Builds and executes the final command in the container."""
        return self._manager.execute_command(self._command_args)

    def __getattr__(self, name: str) -> ArgumentBuilder:
        """
        Magic method to dynamically create methods for any Nerfstudio argument.
        This is the entry point for creating both simple and complex arguments.
        e.g., .viewer_port(7008) or .pipeline.model.some_arg(True)
        """
        # Convert snake_case to kebab-case or dot.case for the argument name
        if name.startswith("viewer_"):
            key = "viewer." + name.split("_", 1)[1].replace("_", "-")
        else:
            key = name.replace("_", "-")
        return ArgumentBuilder(self, key)


# --- Command Factory Functions ---


def train(method: str) -> Command:
    """
    Creates a 'ns-train' command.
    e.g., nsdw.train("nerfacto").data(nsdw.path("/local/path/to/data")).run()
    """
    return Command(f"ns-train {method}")


def process_data(processor: str, data_path: Union[str, PathArgument]) -> Command:
    """
    Creates a 'ns-process-data' command.
    data_path can be a local path wrapped with nsdw.path() or a path relative to output_base_path.
    e.g., nsdw.process_data("images", nsdw.path("/local/path/to/images")).output_dir("processed_data").run()
    """
    cmd = Command(f"ns-process-data {processor}")

    # Handle data_path argument based on its type
    if isinstance(data_path, PathArgument):
        container_path = cmd._manager.copy_to_ns_temp_data(data_path.local_path)
        cmd._add_arg("data", container_path)
    else:
        # Assume it's a path relative to /workspace
        cmd._add_arg("data", data_path)
    return cmd


def process_images(
    input_image_path: Union[str, PathArgument], output_dir: str
) -> Command:
    """
    Creates a 'ns-process-data images' command for typical image processing.
    input_image_path can be a local path wrapped with nsdw.path() or a path relative to output_base_path.
    output_dir must be a path relative to output_base_path.
    e.g., nsdw.process_images(nsdw.path("/local/path/to/raw_images"), "processed_data").run()
    """
    cmd = Command("ns-process-data images")
    if isinstance(input_image_path, PathArgument):
        container_path = cmd._manager.copy_to_ns_temp_data(input_image_path.local_path)
        cmd._add_arg("data", container_path)
    else:
        cmd._add_arg("data", input_image_path)

    cmd._add_arg("output-dir", output_dir)
    return cmd


def custom_command(command_string: str) -> Command:
    """
    Creates a custom command to be run.
    e.g., nsdw.custom_command("ns-viewer").run()
    """
    return Command(command_string)


def path(local_path: str) -> PathArgument:
    """
    Wraps a local file system path, indicating that it should be copied into the
    Docker container's internal temporary volume before being used by Nerfstudio.
    """
    return PathArgument(local_path)
