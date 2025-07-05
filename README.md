# ns_docker_wrapper Documentation

`ns_docker_wrapper` is a Python library designed to simplify the execution of Nerfstudio commands within a Docker container. It handles Docker container management, volume mounting, and local file synchronization, allowing you to interact with Nerfstudio as if it were installed locally.

## Installation

(Assuming standard Python package installation, e.g., `pip install .` or `pip install git+https://github.com/Jourdelune/ns_docker_wrapper.git`)

## Getting Started

Here is an example of how to use `ns_docker_wrapper` to run Nerfstudio commands:

```python
import ns_docker_wrapper as nsdw
from ns_docker_wrapper.utils import select_best_model

RAW_IMAGES_INPUT_PATH = "YOUR_LOCAL_PATH_TO_RAW_IMAGES"  # Replace with your actual path

nsdw.init()

nsdw.process_images(
    input_image_path=nsdw.path(RAW_IMAGES_INPUT_PATH),
    output_dir="processed_data",
).run()


select_best_model()  # fix colmap sparse issue from nerfstudio https://github.com/nerfstudio-project/nerfstudio/issues/3435

nsdw.train("splatfacto").data(
    nsdw.path("./nerfstudio_output/processed_data")
).viewer.quit_on_train_completion(True).output_dir(
    "trained_models"
).viewer_websocket_port(
    7007
).run()
```

## Handling Local Paths with `nsdw.path()`

When you need to pass a local file system path (e.g., your raw image data) to a Nerfstudio command, use `nsdw.path()` to wrap it. This tells `ns_docker_wrapper` to automatically copy the data into a temporary volume within the Docker container before the command is executed. This ensures that Nerfstudio can access your local files.

```python
import ns_docker_wrapper as nsdw

RAW_IMAGES_INPUT_PATH = "/home/user/my_raw_images/" # Your local path

# Wrap the local path with nsdw.path()
nsdw.process_images(
    input_image_path=nsdw.path(RAW_IMAGES_INPUT_PATH),
    output_dir="processed_data",
).run()
```

## Executing Nerfstudio Commands

`ns_docker_wrapper` provides convenient functions to construct and execute common Nerfstudio commands.

### `nsdw.process_images()`

Used for processing raw images into a format suitable for Nerfstudio. This typically involves COLMAP for camera pose estimation.

```python
import ns_docker_wrapper as nsdw

RAW_IMAGES_INPUT_PATH = "/home/jourdelune/Téléchargements/input2/"

nsdw.init()

nsdw.process_images(
    input_image_path=nsdw.path(RAW_IMAGES_INPUT_PATH),
    output_dir="processed_data",
).run()
```

### `nsdw.train()`

Used for training a Nerfstudio model.

```python
import ns_docker_wrapper as nsdw

nsdw.init()

# Train a "splatfacto" model using data from "processed_data"
# The output will be saved in "nerfstudio_output/trained_models"
# The viewer will be accessible on port 7007.
nsdw.train("splatfacto").data(
    nsdw.path("./nerfstudio_output/processed_data") # Path relative to output_base_path
).viewer.quit_on_train_completion(True).output_dir("trained_models").viewer_websocket_port(7007).run()
```

### `nsdw.custom_command()`

For any Nerfstudio command not explicitly covered by `ns_docker_wrapper`'s helper functions, you can use `nsdw.custom_command()`.

```python
import ns_docker_wrapper as nsdw

nsdw.init()

# Example: Running the Nerfstudio viewer with a specific config file
nsdw.custom_command("ns-viewer --load-config outputs/blender_data/nerfacto/2023-01-01_120000/config.yml").run()
```

## Adding Arguments to Commands

`ns_docker_wrapper` offers two primary ways to add arguments to your Nerfstudio commands:

### 1. Dot-Notation Arguments (Recommended for most flags)

Most Nerfstudio command-line flags (e.g., `--data`, `--output-dir`, `--viewer.websocket-port`) can be added using a convenient dot-notation syntax. Snake-case in Python is automatically converted to kebab-case or dot-case for the command-line argument.

```python
import ns_docker_wrapper as nsdw

nsdw.init()

# Example with --data, --output-dir, and --viewer.websocket-port
nsdw.train("nerfacto")\
    .data(nsdw.path("./nerfstudio_output/processed_data"))\
    .output_dir("my_nerfacto_output")\
    .viewer_websocket_port(7008)\
    .run()

# Example with nested arguments like --pipeline.model.near-plane
nsdw.train("nerfacto")\
    .pipeline.model.near_plane(0.05)\
    .pipeline.model.far_plane(1000.0)\
    .run()
```

### 2. Positional Arguments with `add_positional_arg()`

Some Nerfstudio commands require positional arguments (arguments without a preceding flag, like `polycam` in `ns-export polycam`). Use `add_positional_arg()` for these cases.

```python
import ns_docker_wrapper as nsdw

nsdw.init()

# Example: ns-export polycam --output-dir exports/polycam
nsdw.custom_command("ns-export")\
    .add_positional_arg("polycam")\
    .output_dir("exports/polycam")\
    .run()
```

## Understanding `output_dir` and `processed_data`

In Nerfstudio, `output_dir` tells the command where to save its results.

- **`output_base_path` (in `nsdw.init()`):** This is the local folder on your computer where all Nerfstudio outputs will be stored. It is shared with the Docker container as `/workspace`.

- **`output_dir` (in commands):** This is a subfolder inside `output_base_path`. For example, if `output_base_path` is `./nerfstudio_output` and `output_dir="processed_data"`, your results will be in `./nerfstudio_output/processed_data`.

- **`processed_data`:** This is just a common name for the folder where processed input data is saved, often used as input for training.
