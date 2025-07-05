import ns_docker_wrapper as nsdw
import os
import shutil

RAW_IMAGES_INPUT_PATH = "/home/jourdelune/Téléchargements/input2/"  # Replace with your actual raw images path
NERFSTUDIO_OUTPUT_PATH = (
    "./nerfstudio_output_test"  # All Nerfstudio outputs will go here
)

os.makedirs(NERFSTUDIO_OUTPUT_PATH, exist_ok=True)

nsdw.init(output_base_path=NERFSTUDIO_OUTPUT_PATH)

nsdw.process_images(
    input_image_path=nsdw.path(RAW_IMAGES_INPUT_PATH),
    output_dir="processed_data",  # This will be /workspace/processed_data in Docker
).run()

print(f"\n--- Step 2: Training a Nerfstudio Model with ns-train ---")

nsdw.train("nerfacto").data("processed_data").output_dir(
    "trained_models"
).viewer_websocket_port(7007).run()
