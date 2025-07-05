import ns_docker_wrapper as nsdw

RAW_IMAGES_INPUT_PATH = "/home/jourdelune/Téléchargements/input2/"  # Replace with your actual raw images path
NERFSTUDIO_OUTPUT_PATH = "./nerfstudio_output_test"

nsdw.init(
    output_base_path=NERFSTUDIO_OUTPUT_PATH,
    image_name="ghcr.io/nerfstudio-project/nerfstudio:1.1.3",
)

nsdw.process_images(
    input_image_path=nsdw.path(RAW_IMAGES_INPUT_PATH),
    output_dir="processed_data",
).matching_method("exhaustive").run()
