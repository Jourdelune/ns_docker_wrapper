import os
from pathlib import Path

import ns_docker_wrapper as nsdw

RAW_IMAGES_INPUT_PATH = "./examples"
OUTPUT_BASE_PATH = "./nerfstudio_output/"

nsdw.init(output_base_path=OUTPUT_BASE_PATH, image_name=None)

nsdw.process_data("images", nsdw.path(RAW_IMAGES_INPUT_PATH)).output_dir(
    "processed_data"
).run()
