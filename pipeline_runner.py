import os
import time
import argparse
from typing import Optional

# Local imports
import descriptionwriter
import image_fetcher
import imageuploader


PRODUCT_IMAGE_DIR = os.path.join(os.path.dirname(__file__), "product_image")
S3_LINKS_PATH = os.path.join(os.path.dirname(__file__), "s3_upload_links.txt")
PROCESSED_PATH = os.path.join(os.path.dirname(__file__), "processed_items.txt")


def tidy_workspace(clear_links: bool = True) -> None:
    # Remove all files in product_image folder
    if os.path.isdir(PRODUCT_IMAGE_DIR):
        removed = 0
        for f in os.listdir(PRODUCT_IMAGE_DIR):
            try:
                os.remove(os.path.join(PRODUCT_IMAGE_DIR, f))
                removed += 1
            except Exception:
                pass
        print(f"Tidied product_image/: removed {removed} files")
    else:
        print("product_image/ does not exist; nothing to clear")

    # Optionally truncate s3_upload_links.txt
    if clear_links:
        try:
            with open(S3_LINKS_PATH, 'w', encoding='utf-8') as f:
                f.write("")
            print("Tidied s3_upload_links.txt (truncated)")
        except Exception:
            print("Could not truncate s3_upload_links.txt (skipped)")


def print_progress(input_json: Optional[str]) -> None:
    # Count processed names
    processed = 0
    if os.path.exists(PROCESSED_PATH):
        try:
            with open(PROCESSED_PATH, 'r', encoding='utf-8') as f:
                processed = sum(1 for line in f if line.strip())
        except Exception:
            pass
    # Count total products
    total = 0
    try:
        products, _ = descriptionwriter.load_products(input_json or "nath_menu.json")
        total = len(products)
    except Exception:
        pass
    print(f"Progress: {processed}/{total} products processed")


def resolve_input_json(input_json: Optional[str]) -> str:
    if input_json:
        return input_json
    default_candidates = [
        "nath_menu.json",
        "input_products.json"
    ]
    for fname in default_candidates:
        candidate = os.path.join(os.path.dirname(__file__), fname)
        if os.path.exists(candidate):
            return fname
    return "input_products.json"


def run_pipeline(input_json: Optional[str] = None, tidy_before: bool = False, tidy_after: bool = False, clear_links: bool = True) -> None:
    print("=== Starting Automated 100-item Pipeline ===")

    input_json = resolve_input_json(input_json)

    if tidy_before:
        tidy_workspace(clear_links=clear_links)

    print("Step 1/4: Enhancing names/descriptions and generating batch names...")
    descriptionwriter.main(input_json)

    print("Step 2/4: Fetching and saving best images for current batch...")
    image_fetcher.main_cli()

    time.sleep(0.5)

    print("Step 3/4: Uploading images to S3 and generating s3_upload_links.txt...")
    links = imageuploader.upload_folder_images()
    if links:
        imageuploader.generate_output_batches(links, imageuploader.BATCH_SIZE)
    else:
        print("No uploads completed in this cycle.")

    print("Step 4/4: Replacing dummy image links in JSON for this batch...")
    descriptionwriter.replace_images_for_last_batch(input_json)
    # Safety net: also run a global replacement using only the available links file
    descriptionwriter.replace_images_from_links_all(input_json)

    if tidy_after:
        tidy_workspace(clear_links=clear_links)

    print_progress(input_json)
    print("=== Pipeline complete for this batch. ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run 100-item pipeline with optional tidy and progress")
    parser.add_argument("--input", type=str, default=None, help="Input JSON filename in this directory")
    parser.add_argument("--tidy-before", action="store_true", help="Clear local product_image and optionally truncate s3_upload_links.txt before run")
    parser.add_argument("--tidy-after", action="store_true", help="Clear local product_image and optionally truncate s3_upload_links.txt after run")
    parser.add_argument("--no-clear-links", action="store_true", help="Do not truncate s3_upload_links.txt when tidying")
    parser.add_argument("--print-progress", action="store_true", help="Print progress and exit")
    args = parser.parse_args()

    if args.print_progress:
        print_progress(resolve_input_json(args.input))
    else:
        # Default behavior: if no tidy flag provided, clear local images before each run
        effective_tidy_before = args.tidy_before or (not args.tidy_after)
        run_pipeline(
            input_json=args.input,
            tidy_before=effective_tidy_before,
            tidy_after=args.tidy_after,
            clear_links=False
        )


