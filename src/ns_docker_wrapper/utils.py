import argparse
from pathlib import Path
import pycolmap
import shutil


def select_largest_model(
    sfm_model_path: Path,
) -> tuple[pycolmap.Reconstruction, Path, Path] | None:
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

    if largest_model_rec:
        print(f"Found {len(all_reconstructions_info)} model(s).")
        print(
            f"Selected the largest model with {largest_num_images} registered images."
        )

        # Find the path of the largest model
        largest_model_path = None
        for rec, path in all_reconstructions_info:
            if rec == largest_model_rec:
                largest_model_path = path
                break

        # Find the path of the other model (assuming exactly two models)
        other_model_path = None
        if len(all_reconstructions_info) == 2:
            for rec, path in all_reconstructions_info:
                if rec != largest_model_rec:
                    other_model_path = path
                    break
        elif len(all_reconstructions_info) > 2:
            print(
                "Warning: More than two models found. Only handling the largest and one 'other' for moving."
            )
            # For simplicity, if more than two, just pick the first non-largest as 'other'
            for rec, path in all_reconstructions_info:
                if rec != largest_model_path:  # Compare paths directly
                    other_model_path = path
                    break

        return largest_model_rec, largest_model_path, other_model_path

    return None


def move_models(
    sfm_model_path: Path, largest_model_path: Path, other_model_path: Path | None
):
    """
    Moves the largest model to the '0' directory and the other model to the '1' directory.
    """
    print(f"Reorganizing models in {sfm_model_path}...")

    target_largest_path = sfm_model_path / "0"
    target_other_path = sfm_model_path / "1"

    # If the largest model is already in the '0' position, and the other is in '1', we are done.
    if largest_model_path == target_largest_path and (
        other_model_path is None or other_model_path == target_other_path
    ):
        print("Models are already in the desired configuration.")
        return

    # If the largest model is not in '0', we need to swap them.
    # This assumes there are exactly two models (0 and 1) and the largest is in '1' and other in '0'.
    if (
        largest_model_path == target_other_path
        and other_model_path == target_largest_path
    ):
        print(f"Swapping {target_largest_path} and {target_other_path}...")
        temp_path = sfm_model_path / "_temp_model_swap"
        shutil.move(str(target_largest_path), str(temp_path))  # Move '0' to temp
        shutil.move(str(target_other_path), str(target_largest_path))  # Move '1' to '0'
        shutil.move(str(temp_path), str(target_other_path))  # Move temp to '1'
        print("Models reorganized successfully.")
    elif (
        largest_model_path != target_largest_path
    ):  # If largest is not in 0, and not a simple swap case
        print(
            "Warning: Complex model reorganization scenario. Attempting to move largest to 0."
        )
        # This handles cases where there might be more than two models or unexpected naming.
        # It will move the largest model to '0' and remove any existing '0' first.
        if target_largest_path.exists():
            shutil.rmtree(target_largest_path)
        shutil.move(str(largest_model_path), str(target_largest_path))
        print(f"Moved {largest_model_path} to {target_largest_path}")

        # If there's an 'other' model and it's not in '1', move it to '1'
        if other_model_path and other_model_path != target_other_path:
            if target_other_path.exists():
                shutil.rmtree(target_other_path)
            shutil.move(str(other_model_path), str(target_other_path))
            print(f"Moved {other_model_path} to {target_other_path}")
        elif other_model_path is None:
            print("No 'other' model to move to '1'.")


def select_best_model(
    colmap_sparse_path: Path = Path("./nerfstudio_output/processed_data/colmap/sparse"),
):
    """Selects the largest COLMAP model from the specified path and moves it to the '0' directory."""

    result = select_largest_model(colmap_sparse_path)

    _, largest_model_path, other_model_path = result
    move_models(colmap_sparse_path, largest_model_path, other_model_path)
