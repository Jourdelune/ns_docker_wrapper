from __future__ import annotations

import os
from typing import List, Optional, Union

from .manager import _get_manager


class PathArgument:
    """A special wrapper for local paths.

    This wrapper indicates that the path needs to be copied into the Docker
    container's internal temporary volume before being passed to Nerfstudio.

    Args:
        local_path (str): The local path to the file or directory.
        copy_depth (int): The depth to copy the directory structure.
    """

    def __init__(self, local_path: str, copy_depth: int):
        self.local_path = local_path
        self.copy_depth = copy_depth


class ArgumentBuilder:
    """A helper class to recursively build dot-notation arguments.

    Args:
        command (Command): The command to build arguments for.
        original_name (str): The original snake_case name of the argument.
        formatted_name (str): The formatted (kebab-case) name of the argument.
    """

    def __init__(self, command: Command, original_name: str, formatted_name: str):
        self._command = command
        self._original_name = original_name
        self._formatted_name = formatted_name

    def __getattr__(self, name: str) -> ArgumentBuilder:
        """Chains attributes to build the argument name.

        Args:
            name (str): The name of the attribute.

        Returns:
            ArgumentBuilder: A new ArgumentBuilder with the updated names.
        """
        new_original_name = f"{self._original_name}.{name}"
        new_formatted_name = f"{self._formatted_name}.{name.replace('_', '-')}"
        return ArgumentBuilder(self._command, new_original_name, new_formatted_name)

    def __call__(
        self,
        value: Optional[Union[str, int, float, bool, PathArgument]] = None,
        keep_underscore: bool = False,
    ) -> Command:
        """Sets the value for the constructed argument.

        If the value is a PathArgument, it will be copied to an internal temporary volume.

        Args:
            value (Optional[Union[str, int, float, bool, PathArgument]]): The value
                to set for the argument.
            keep_underscore (bool): If True, the argument name will retain underscores
                                    instead of being converted to hyphens.

        Returns:
            Command: The command with the new argument.
        """
        if isinstance(value, PathArgument):
            container_path = self._command._manager.copy_to_ns_temp_data(
                value.local_path, value.copy_depth
            )
            return self._command._add_arg(
                self._original_name, container_path, keep_underscore
            )

        return self._command._add_arg(self._original_name, value, keep_underscore)


class Command:
    """Represents a Nerfstudio command to be executed."""

    def __init__(self, base_command: str):
        """Initializes the Command.

        Args:
            base_command (str): The base command to execute.
        """
        self._manager = _get_manager()
        self._command_args: List[str] = [base_command]

    def _add_arg(
        self, key: str, value: Optional[Union[str, int, float, bool]], keep_underscore: bool = False
    ) -> Command:
        """Adds a standard --key value argument.

        Args:
            key (str): The name of the argument.
            value (Optional[Union[str, int, float, bool]]): The value of the
                argument.
            keep_underscore (bool): If True, the argument name will retain underscores
                                    instead of being converted to hyphens.

        Returns:
            Command: The command with the new argument.
        """
        arg_name = key if keep_underscore else key.replace('_', '-')
        self._command_args.append(f"--{arg_name}")
        if value is not None:
            self._command_args.append(str(value))
        return self

    def add_positional_arg(self, value: str) -> Command:
        """Adds a positional argument.

        Note:
            Positional arguments are not automatically copied to the internal temporary volume.
            If a positional argument is a path, it must be relative to the
            output_base_path (which corresponds to /workspace in Docker mode).

        Args:
            value (str): The value of the positional argument.

        Returns:
            Command: The command with the new argument.
        """
        self._command_args.append(value)
        return self

    def run(self) -> tuple[int, str]:
        """
        Executes the command and returns the exit code or output.

        Returns:
            tuple[int, str]: The exit code or output of the command execution.
        """

        return self._manager.execute_command(self._command_args)

    def __getattr__(self, name: str) -> ArgumentBuilder:
        """Dynamically creates methods for Nerfstudio arguments.

        This is the entry point for creating both simple and complex arguments.
        e.g., .viewer_port(7008) or .pipeline.model.some_arg(True)

        Args:
            name (str): The name of the attribute.

        Returns:
            ArgumentBuilder: An ArgumentBuilder for the new argument.
        """
        # Determine the original and formatted names
        original_name = name
        if name.startswith("viewer_"):
            formatted_name = "viewer." + name.split("_", 1)[1].replace("_", "-")
        else:
            formatted_name = name.replace("_", "-")
        return ArgumentBuilder(self, original_name, formatted_name)


# --- Command Factory Functions ---


def train(method: str) -> Command:
    """Creates a 'ns-train' command.

    When executed with .run(), this command returns the absolute path to the
    training config.yml file.

    Args:
        method (str): The training method to use.

    Returns:
        Command: A new Command object for the train command.
    """
    return Command(f"ns-train {method}")


def process_data(processor: str, data_path: Union[str, PathArgument]) -> Command:
    """Creates a 'ns-process-data' command.

    Args:
        processor (str): The processor to use.
        data_path (Union[str, PathArgument]): The path to the data. Can be a local
            path wrapped with nsdw.path() or a path relative to output_base_path
            (which corresponds to /workspace in Docker mode).

    Returns:
        Command: A new Command object for the process-data command.
    """
    cmd = Command(f"ns-process-data {processor}")

    # Handle data_path argument based on its type
    if isinstance(data_path, PathArgument):
        container_path = cmd._manager.copy_to_ns_temp_data(
            data_path.local_path, data_path.copy_depth
        )
        cmd._add_arg("data", container_path)
    else:
        # Assume it's a path relative to /workspace
        cmd._add_arg("data", data_path)
    return cmd


def process_images(
    input_image_path: Union[str, PathArgument], output_dir: str
) -> Command:
    """Creates a 'ns-process-data images' command.

    Args:
        input_image_path (Union[str, PathArgument]): The path to the input images.
            Can be a local path wrapped with nsdw.path() or a path relative to
            output_base_path (which corresponds to /workspace in Docker mode).
        output_dir (str): The path to the output directory, relative to
            output_base_path.

    Returns:
        Command: A new Command object for the process-images command.
    """
    cmd = Command("ns-process-data images")
    if isinstance(input_image_path, PathArgument):
        container_path = cmd._manager.copy_to_ns_temp_data(
            input_image_path.local_path, input_image_path.copy_depth
        )
        cmd._add_arg("data", container_path)
    else:
        cmd._add_arg("data", input_image_path)

    cmd._add_arg("output-dir", output_dir)
    return cmd


def custom_command(command_string: str) -> Command:
    """Creates a custom command to be run.

    Args:
        command_string (str): The command to run.

    Returns:
        Command: A new Command object for the custom command.
    """
    return Command(command_string)


def path(local_path: str, copy_depth: int = 0) -> PathArgument:
    """Wraps a local file system path.

    This indicates that it should be copied into an internal temporary volume
    before being used by Nerfstudio. This is useful for data that is not
    already in the output_base_path.

    Args:
        local_path (str): The local path to the file or directory.
        copy_depth (int): The depth to copy the directory structure.

    Returns:
        PathArgument: A new PathArgument object.
    """
    return PathArgument(local_path, copy_depth)
