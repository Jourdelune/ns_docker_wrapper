import atexit
import docker
import os
import shutil
import sys
import tempfile
from typing import Optional

class DockerManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(DockerManager, cls).__new__(cls)
        return cls._instance

    def __init__(self, output_base_path: str, image_name="ghcr.io/nerfstudio-project/nerfstudio:latest", shm_size="12gb"):
        if hasattr(self, '_initialized') and self._initialized:
            return

        self.client = docker.from_env()
        self.image_name = image_name
        self.container = None
        self.output_base_path = os.path.abspath(output_base_path)
        self.shm_size = shm_size
        self._initialized = True

        # Temporary directory for Docker cache (mounted to /home/user/.cache)
        self._temp_cache_dir = tempfile.TemporaryDirectory()
        self.cache_path = self._temp_cache_dir.name
        print(f"Created temporary cache directory: {self.cache_path}")

        # Temporary directory for internal data processing (mounted to /ns_temp_data)
        self._internal_temp_data_host_path = tempfile.TemporaryDirectory()
        self.internal_temp_data_container_path = "/ns_temp_data"
        print(f"Created internal temporary data directory: {self._internal_temp_data_host_path.name}")

        self._pull_image_if_needed()
        self._start_container()
        atexit.register(self.cleanup)

    def _pull_image_if_needed(self):
        try:
            self.client.images.get(self.image_name)
            print(f"Image {self.image_name} found locally.")
        except docker.errors.ImageNotFound:
            print(f"Image {self.image_name} not found. Pulling from registry...")
            self.client.images.pull(self.image_name)
            print("Image pulled successfully.")

    def _start_container(self):
        volumes = {
            self.output_base_path: {'bind': '/workspace', 'mode': 'rw'},
            self.cache_path: {'bind': '/home/user/.cache', 'mode': 'rw'},
            self._internal_temp_data_host_path.name: {'bind': self.internal_temp_data_container_path, 'mode': 'rw'}
        }
        
        device_requests = [
            docker.types.DeviceRequest(count=-1, capabilities=[['gpu']])
        ]

        try:
            self.container = self.client.containers.run(
                self.image_name,
                detach=True,
                tty=True,
                stdin_open=True,
                device_requests=device_requests,
                volumes=volumes,
                ports={'7007/tcp': 7007},
                shm_size=self.shm_size,
                remove=True,
                user=f"{os.getuid()}",
                environment={
                    "XDG_DATA_HOME": "/workspace/.local/share",
                    "TORCH_HOME": "/workspace/.cache/torch"
                },
                command="sleep infinity"
            )
            print(f"Container {self.container.short_id} started.")
        except Exception as e:
            print(f"Failed to start container: {e}", file=sys.stderr)
            sys.exit(1)

    def cleanup(self):
        print("Cleaning up resources...")
        if self.container:
            print(f"Stopping container {self.container.short_id}...")
            try:
                self.container.stop()
                print("Container stopped.")
            except docker.errors.NotFound:
                print("Container already stopped or removed.")
            except Exception as e:
                print(f"An error occurred while stopping the container: {e}", file=sys.stderr)
            self.container = None
        
        self._temp_cache_dir.cleanup()
        print(f"Removed temporary cache directory: {self.cache_path}")
        
        self._internal_temp_data_host_path.cleanup()
        print(f"Removed internal temporary data directory: {self._internal_temp_data_host_path.name}")

    def execute_command(self, command: list[str]):
        if not self.container:
            raise RuntimeError("Container is not running. Please call init() first.")

        full_command = " ".join(command)
        print(f"Executing command in container: {full_command}")

        exec_instance = self.client.api.exec_create(
            self.container.id, cmd=full_command, stdout=True, stderr=True, tty=True, workdir='/workspace'
        )
        exec_id = exec_instance['Id']

        output_stream = self.client.api.exec_start(exec_id, stream=True, tty=True)

        for chunk in output_stream:
            print(chunk.decode('utf-8'), end='')

        exec_result = self.client.api.exec_inspect(exec_id)
        exit_code = exec_result['ExitCode']
        
        if exit_code != 0:
            print(f"\nCommand execution failed with exit code {exit_code}", file=sys.stderr)

        return exit_code

    def copy_to_ns_temp_data(self, local_path: str) -> str:
        """
        Copies a local file or directory to the internal temporary data volume
        and returns its corresponding path inside the Docker container.
        """
        abs_local_path = os.path.abspath(local_path)
        
        # Create a unique subdirectory in the temporary host path
        unique_dir_name = os.path.basename(abs_local_path) + "_" + os.urandom(4).hex()
        dest_host_path = os.path.join(self._internal_temp_data_host_path.name, unique_dir_name)
        
        if os.path.isdir(abs_local_path):
            shutil.copytree(abs_local_path, dest_host_path)
        elif os.path.isfile(abs_local_path):
            os.makedirs(dest_host_path, exist_ok=True) # Create dir for the file
            shutil.copy(abs_local_path, dest_host_path)
        else:
            raise FileNotFoundError(f"Local path does not exist: {abs_local_path}")

        # Return the path inside the container
        return f"{self.internal_temp_data_container_path}/{unique_dir_name}/{os.path.basename(abs_local_path) if os.path.isfile(abs_local_path) else ''}"


_manager: Optional[DockerManager] = None

def init(output_base_path: str, image_name: str = "ghcr.io/nerfstudio-project/nerfstudio:latest", shm_size: str = "12gb"):
    """
    Initializes the Docker wrapper.
    output_base_path: Local path where Nerfstudio will store its outputs (mounted to /workspace).
    """
    global _manager
    if _manager is None:
        _manager = DockerManager(
            output_base_path=output_base_path,
            image_name=image_name,
            shm_size=shm_size
        )

def _get_manager() -> DockerManager:
    if _manager is None:
        raise RuntimeError("You must call nsdw.init() before using any other functions.")
    return _manager