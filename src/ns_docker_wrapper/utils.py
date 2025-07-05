import argparse
import shutil
from pathlib import Path

import pycolmap


def select_largest_model(
    sfm_model_path: Path,
) -> Path | None:
    """
    Loads COLMAP reconstruction models from the specified path and returns the largest one
    (the model with the most registered images) along with its path and the path of the other model.
    """
    if not sfm_model_path.exists():
        raise FileNotFoundError(f"COLMAP model path not found: {sfm_model_path}")

    largest_model_rec = None
    largest_num_images = -1
    all_reconstructions_info = []  # Store (rec, path) tuples

    # Iterate through subdirectories (e.g., 0, 1, 2, ...)
    for model_dir in sfm_model_path.iterdir():
        if model_dir.is_dir():
            try:
                rec = pycolmap.Reconstruction(model_dir)
                all_reconstructions_info.append((rec, model_dir))
                num_images = rec.num_reg_images()
                if num_images > largest_num_images:
                    largest_num_images = num_images
                    largest_model_rec = rec
            except Exception as e:
                print(f"Could not load model from {model_dir}: {e}")
                continue

    if not all_reconstructions_info:
        print(f"No valid COLMAP models found in {sfm_model_path}")
        return None

    print(f"Found {len(all_reconstructions_info)} model(s).")
    print(f"Selected the largest model with {largest_num_images} registered images.")

    # Find the path of the largest model
    largest_model_path = None
    for rec, path in all_reconstructions_info:
        if rec == largest_model_rec:
            largest_model_path = path
            break

    return largest_model_path


def select_best_model(
    colmap_sparse_path: Path = Path("./nerfstudio_output/processed_data/colmap/sparse"),
) -> Path | None:
    """Selects the largest COLMAP model from the specified path and moves it to the '0' directory."""

    result = select_largest_model(colmap_sparse_path)

    return result
