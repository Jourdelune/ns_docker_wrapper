from pathlib import Path

import pycolmap


def select_largest_model(
    sfm_model_path: Path = Path("./nerfstudio_output/processed_data/colmap/sparse"),
) -> Path:
    """Selects the largest COLMAP model from a directory.

    Loads all COLMAP reconstruction models from the specified path and returns the
    path to the largest one (the model with the most registered images).

    Args:
        sfm_model_path (Path): The path to the directory containing COLMAP models.
            Defaults to "./nerfstudio_output/processed_data/colmap/sparse".

    Returns:
        Path: The path to the largest COLMAP model directory.

    Raises:
        FileNotFoundError: If the specified path does not exist.
        ValueError: If no COLMAP models are found in the specified path.
    """
    if not sfm_model_path.exists():
        raise FileNotFoundError(f"COLMAP model path not found: {sfm_model_path}")

    largest_model_rec = None
    largest_num_images = -1
    all_reconstructions_info = []  # Store (rec, path) tuples

    # Iterate through subdirectories (e.g., 0, 1, 2, ...)
    for model_dir in sfm_model_path.iterdir():
        if model_dir.is_dir():
            rec = pycolmap.Reconstruction(model_dir)
            all_reconstructions_info.append((rec, model_dir))
            num_images = rec.num_reg_images()
            if num_images > largest_num_images:
                largest_num_images = num_images
                largest_model_rec = rec

    if not all_reconstructions_info:
        raise ValueError(
            f"No COLMAP models found in the specified path: {sfm_model_path}"
        )

    # Find the path of the largest model
    largest_model_path = None
    for rec, path in all_reconstructions_info:
        if rec == largest_model_rec:
            largest_model_path = path
            break

    return largest_model_path
