import atexit
import os
import shutil
import sys
import tempfile
from typing import Optional
import logging
import re
import subprocess


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
        image_name: Optional[str] = "ghcr.io/nerfstudio-project/nerfstudio:latest",
        ipc: str = "host",
    ):
        """Initializes the DockerManager.
        Args:
            output_base_path (str): The base path for the output data.
            image_name (Optional[str]): The name of the Docker image to use. If None, commands are run on the host.
            ipc (str): The IPC mode to use for the container.
        """

        os.makedirs(output_base_path, exist_ok=True)

        if hasattr(self, "_initialized") and self._initialized:
            return

        self.image_name = image_name
        self.use_docker = self.image_name is not None
        self.container = None
        self.output_base_path = os.path.abspath(output_base_path)
        self.ipc = ipc
        self._initialized = True

        # Temporary directory for internal data processing (mounted to /ns_temp_data)
        temp_dir_base = os.path.join(self.output_base_path, ".tmp")
        os.makedirs(temp_dir_base, exist_ok=True)
        self._internal_temp_data_host_path = tempfile.TemporaryDirectory(
            dir=temp_dir_base
        )
        logging.info(
            f"Created internal temporary data directory: {self._internal_temp_data_host_path.name}"
        )

        if self.use_docker:
            try:
                import docker
                self.docker = docker
                self.client = self.docker.from_env()
            except ImportError:
                raise ImportError(
                    "The 'docker' package is required to run with a Docker image. Please install it with 'pip install docker'"
                )
            except Exception as e:
                if "No such file or directory" in str(e):
                    logging.error(
                        "Docker is not available. Please start Docker and try again."
                    )
                    sys.exit(1)
                raise e
            self.workspace_path = "/workspace"
            self.internal_temp_data_container_path = "/ns_temp_data"
            self._pull_image_if_needed()
            self._start_container()
        else:
            logging.info("Running in local mode (no Docker).")
            self.docker = None
            self.client = None
            self.workspace_path = self.output_base_path
            self.internal_temp_data_container_path = (
                self._internal_temp_data_host_path.name
            )

        atexit.register(self.cleanup)

    def _pull_image_if_needed(self):
        """Pulls the Docker image if it is not already present."""

        try:
            self.client.images.get(self.image_name)
            logging.info(f"Image {self.image_name} found locally.")
        except self.docker.errors.ImageNotFound:
            logging.info(f"Image {self.image_name} not found. Pulling from registry...")
            self.client.images.pull(self.image_name)
            logging.info("Image pulled successfully.")

    def _start_container(self):
        """Starts the Docker container."""

        volumes = {
            self.output_base_path: {"bind": self.workspace_path, "mode": "rw"},
            self._internal_temp_data_host_path.name: {
                "bind": self.internal_temp_data_container_path,
                "mode": "rw",
            },
        }

        device_requests = [
            self.docker.types.DeviceRequest(count=-1, capabilities=[["gpu"]])
        ]

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
                    "XDG_DATA_HOME": f"{self.workspace_path}/.local/share",
                    "TORCH_HOME": f"{self.workspace_path}/.cache/torch",
                    "TMPDIR": f"{self.internal_temp_data_container_path}/torch_tmp",
                    "TORCHINDUCTOR_CACHE_DIR": f"{self.internal_temp_data_container_path}/torch_inductor_cache",
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
        if self.use_docker and self.container:
            logging.info(f"Stopping container {self.container.short_id}...")
            try:
                self.container.stop()
                logging.info("Container stopped.")
            except self.docker.errors.NotFound:
                logging.info("Container already stopped or removed.")
            except Exception as e:
                logging.error(f"An error occurred while stopping the container: {e}")
            self.container = None

        self._internal_temp_data_host_path.cleanup()
        logging.info(
            f"Removed internal temporary data directory: {self._internal_temp_data_host_path.name}"
        )

    def execute_command(self, command: list[str]) -> tuple[int, str]:
        """Executes a command in the Docker container or on the host.
        Args:
            command (list[str]): The command to execute as a list of strings.
        Returns:
            tuple[int, str]: A tuple containing the exit code and the command output.
        """
        if not self.use_docker:
            logging.info(f"Executing command on host: {' '.join(command)}")
            process = subprocess.Popen(
                command[0].split() + command[1:],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=self.output_base_path,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            output_chunks = []
            if process.stdout:
                for line in iter(process.stdout.readline, ""):
                    sys.stdout.write(line)
                    sys.stdout.flush()
                    output_chunks.append(line)

            process.wait()
            output = "".join(output_chunks)
            exit_code = process.returncode

            if exit_code != 0:
                logging.error(f"Command execution failed with exit code {exit_code}")

            return exit_code, output

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
            workdir=self.workspace_path,
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

        # If path is already in the main output volume, just calculate container path
        if src_path.startswith(self.output_base_path):
            return os.path.join(
                self.workspace_path,
                os.path.relpath(abs_local_path, self.output_base_path),
            )

        # Otherwise, copy to temp volume and return container path
        base_name = os.path.basename(src_path)
        dest_host_path = os.path.join(
            self._internal_temp_data_host_path.name, base_name
        )

        if os.path.isdir(src_path):
            shutil.copytree(
                src_path,
                dest_host_path,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("*.tmp"),
            )
        elif os.path.isfile(src_path):
            os.makedirs(os.path.dirname(dest_host_path), exist_ok=True)
            shutil.copy(src_path, dest_host_path)
        else:
            # If path doesn't exist, return it as is, assuming it's not a path
            return local_path

        relative_path_from_src = os.path.relpath(abs_local_path, start=src_path)

        base_dest = os.path.join(
            self.internal_temp_data_container_path, os.path.basename(src_path)
        )

        final_path = os.path.join(base_dest, relative_path_from_src)

        return os.path.normpath(final_path)


_manager: Optional[DockerManager] = None


def init(
    output_base_path: str = "./nerfstudio_output",
    image_name: Optional[str] = "jourdelune876/nerfstudio-full-dep:latest",
):
    """Initializes the Docker wrapper.
    Args:
        output_base_path (str): Local path where Nerfstudio will store its outputs
            (mounted to /workspace).
        image_name (Optional[str]): The name of the Docker image to use. If None, commands are run on the host.
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
