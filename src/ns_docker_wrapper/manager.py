import atexit
import docker
import os
import shutil
import sys
import tempfile
from typing import Optional
import logging
import re

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


class DockerManager:
    """A singleton class to manage the Docker container for Nerfstudio.

    This class handles the lifecycle of the Docker container, including pulling the
    image, starting the container, executing commands, and cleaning up resources.
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(DockerManager, cls).__new__(cls)
        return cls._instance

    def __init__(
        self,
        output_base_path: str,
        image_name: str = "ghcr.io/nerfstudio-project/nerfstudio:latest",
        ipc: str = "host",
    ):
        """Initializes the DockerManager.

        Args:
            output_base_path (str): The base path for the output data.
            image_name (str): The name of the Docker image to use.
            ipc (str): The IPC mode to use for the container.
        """

        os.makedirs(output_base_path, exist_ok=True)

        if hasattr(self, "_initialized") and self._initialized:
            return

        self.client = docker.from_env()
        self.image_name = image_name
        self.container = None
        self.output_base_path = os.path.abspath(output_base_path)
        self.ipc = ipc
        self._initialized = True

        # Temporary directory for internal data processing (mounted to /ns_temp_data)
        self._internal_temp_data_host_path = tempfile.TemporaryDirectory()
        self.internal_temp_data_container_path = "/ns_temp_data"
        logging.info(
            f"Created internal temporary data directory: {self._internal_temp_data_host_path.name}"
        )

        self._pull_image_if_needed()
        self._start_container()
        atexit.register(self.cleanup)

    def _pull_image_if_needed(self):
        """Pulls the Docker image if it is not already present."""

        try:
            self.client.images.get(self.image_name)
            logging.info(f"Image {self.image_name} found locally.")
        except docker.errors.ImageNotFound:
            logging.info(f"Image {self.image_name} not found. Pulling from registry...")
            self.client.images.pull(self.image_name)
            logging.info("Image pulled successfully.")

    def _start_container(self):
        """Starts the Docker container."""

        volumes = {
            self.output_base_path: {"bind": "/workspace", "mode": "rw"},
            self._internal_temp_data_host_path.name: {
                "bind": self.internal_temp_data_container_path,
                "mode": "rw",
            },
        }

        device_requests = [docker.types.DeviceRequest(count=-1, capabilities=[["gpu"]])]

        try:
            self.container = self.client.containers.run(
                self.image_name,
                detach=True,
                tty=True,
                stdin_open=True,
                device_requests=device_requests,
                volumes=volumes,
                ports={"7007/tcp": 7007},
                ipc_mode=self.ipc,
                remove=True,
                user=f"{os.getuid()}" if hasattr(os, "getuid") else None,
                environment={
                    "XDG_DATA_HOME": "/workspace/.local/share",
                    "TORCH_HOME": "/workspace/.cache/torch",
                    "TMPDIR": "/ns_temp_data/torch_tmp",
                    "TORCHINDUCTOR_CACHE_DIR": "/ns_temp_data/torch_inductor_cache",
                    "TORCH_COMPILE_DISABLE": "1",
                },
                command="sleep infinity",
            )
            logging.info(f"Container {self.container.short_id} started.")
        except Exception as e:
            logging.error(f"Failed to start container: {e}")
            sys.exit(1)

    def cleanup(self):
        """Cleans up the resources used by the DockerManager."""

        logging.info("Cleaning up resources...")
        if self.container:
            logging.info(f"Stopping container {self.container.short_id}...")
            try:
                self.container.stop()
                logging.info("Container stopped.")
            except docker.errors.NotFound:
                logging.info("Container already stopped or removed.")
            except Exception as e:
                logging.error(f"An error occurred while stopping the container: {e}")
            self.container = None

        self._internal_temp_data_host_path.cleanup()
        logging.info(
            f"Removed internal temporary data directory: {self._internal_temp_data_host_path.name}"
        )

    def execute_command(self, command: list[str]) -> tuple[int, str]:
        """Executes a command in the Docker container.

        Args:
            command (list[str]): The command to execute as a list of strings.

        Returns:
            tuple[int, str]: A tuple containing the exit code and the command output.
        """
        if not self.container:
            raise RuntimeError("Container is not running. Please call init() first.")

        full_command = " ".join(command)
        logging.info(f"Executing command in container: {full_command}")

        exec_instance = self.client.api.exec_create(
            self.container.id,
            cmd=full_command,
            stdout=True,
            stderr=True,
            tty=True,
            workdir="/workspace",
        )
        exec_id = exec_instance["Id"]

        output_stream = self.client.api.exec_start(exec_id, stream=True, tty=True)

        output_chunks = []
        for chunk in output_stream:
            decoded_chunk = chunk.decode("utf-8", errors="replace")
            sys.stdout.write(decoded_chunk)
            sys.stdout.flush()
            output_chunks.append(decoded_chunk)

        output = "".join(output_chunks)

        exec_result = self.client.api.exec_inspect(exec_id)
        exit_code = exec_result["ExitCode"]

        if exit_code != 0:
            logging.error(f"Command execution failed with exit code {exit_code}")

        return exit_code, output

    def copy_to_ns_temp_data(self, local_path: str, copy_depth: int = 0) -> str:
        """Copies a local file or directory to the internal temporary data volume.

        Args:
            local_path (str): The path to the local file or directory.
            copy_depth (int): The number of parent directories to include in the copy.

        Returns:
            str: The path of the file or directory inside the container.
        """
        abs_local_path = os.path.abspath(local_path)

        # Determine the effective source path based on copy_depth
        src_path = abs_local_path
        for i in range(copy_depth):
            src_path = os.path.dirname(src_path)

        dest_host_path = os.path.join(
            self._internal_temp_data_host_path.name, os.path.basename(src_path)
        )

        logging.info(f"dest_host_path: {dest_host_path}")

        # Calculate the relative path from src_path to abs_local_path
        relative_path_in_copy = os.path.relpath(abs_local_path, src_path)

        # Full path to the file/directory within the new unique directory
        full_dest_path = os.path.join(dest_host_path, relative_path_in_copy)

        if os.path.isdir(src_path):
            shutil.copytree(src_path, dest_host_path, dirs_exist_ok=True)
        elif os.path.isfile(src_path):
            os.makedirs(os.path.dirname(full_dest_path), exist_ok=True)
            shutil.copy(src_path, full_dest_path)
        else:
            raise FileNotFoundError(f"Local path does not exist: {src_path}")

        # Calculate the relative path from src_path to abs_local_path
        relative_path_in_copy = os.path.relpath(abs_local_path, src_path)

        # Return the path inside the container
        return os.path.join(
            self.internal_temp_data_container_path,
            os.path.basename(src_path),
            relative_path_in_copy,
        )

    def copy_to_workspace(self, local_path: str, copy_depth: int = 0) -> str:
        """Copies a local file or directory to a unique subdirectory in the workspace.

        Args:
            local_path (str): The path to the local file or directory.
            copy_depth (int): The number of parent directories to include in the copy.

        Returns:
            str: The path of the file or directory inside the container's workspace.
        """
        abs_local_path = os.path.abspath(local_path)

        # Determine the effective source path based on copy_depth
        src_root_path = abs_local_path  # This will be the root of what we copy
        for _ in range(copy_depth):
            src_root_path = os.path.dirname(src_root_path)

        # Create a unique subdirectory in the host's output path
        unique_dir_name = "processed_data_" + os.urandom(4).hex()
        # The destination on the host will be within 'trained_models'
        dest_host_root_path = os.path.join(
            self.output_base_path, "trained_models", unique_dir_name
        )
        logging.info(f"dest_host_root_path: {dest_host_root_path}")

        # Copy the entire src_root_path to dest_host_root_path
        if os.path.isdir(src_root_path):
            shutil.copytree(src_root_path, dest_host_root_path)
        elif os.path.isfile(src_root_path):
            # If src_root_path is a file, we need to create its parent directory
            os.makedirs(os.path.dirname(dest_host_root_path), exist_ok=True)
            shutil.copy(src_root_path, dest_host_root_path)
        else:
            raise FileNotFoundError(f"Local path does not exist: {src_root_path}")

        # Calculate the relative path of the original local_path within the copied structure
        relative_path_in_copied_structure = os.path.relpath(
            abs_local_path, src_root_path
        )
        logging.info(
            f"relative_path_in_copied_structure: {relative_path_in_copied_structure}"
        )

        # The full path to the specific file (e.g., config.yml) within the copied structure on the host
        full_dest_file_path = os.path.join(
            dest_host_root_path, relative_path_in_copied_structure
        )
        logging.info(f"full_dest_file_path: {full_dest_file_path}")

        # Return the path inside the container, which should reflect the full path
        # relative to /workspace, including the 'trained_models' and unique_dir_name
        return os.path.join(
            "/workspace",
            "trained_models",
            unique_dir_name,
            relative_path_in_copied_structure,
        )


_manager: Optional[DockerManager] = None


def init(
    output_base_path: str = "./nerfstudio_output",
    image_name: str = "jourdelune876/nerfstudio-full-dep:latest",
):
    """Initializes the Docker wrapper.

    Args:
        output_base_path (str): Local path where Nerfstudio will store its outputs
            (mounted to /workspace).
        image_name (str): The name of the Docker image to use.
    """
    global _manager
    if _manager is None:
        _manager = DockerManager(
            output_base_path=output_base_path, image_name=image_name
        )


def _get_manager() -> DockerManager:
    """Returns the DockerManager instance.

    Returns:
        DockerManager: The DockerManager instance.

    Raises:
        RuntimeError: If the DockerManager has not been initialized.
    """
    if _manager is None:
        raise RuntimeError(
            "You must call nsdw.init() before using any other functions."
        )
    return _manager
