import os
import requests
from PIL import Image
import io
import time
from typing import List, Tuple
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# 1. Google API Key: Get this from the Google Cloud Console.
# 2. Custom Search Engine ID (CSE ID): Set up a Custom Search Engine 
#    and enable 'Image Search' under 'Search Features'.
API_KEYS = [
  
]#add your google api keys here

CSE_IDS = ""#add your custom search engine id here



CURRENT_KEY_INDEX = 0

MAX_COMPRESSION_KB = 30 

def ensure_product_image_folder():
    """Ensures the 'product_image' folder exists and returns its name."""
    folder_name = "product_image"
    try:
        if not os.path.exists(folder_name):
            os.makedirs(folder_name)
            print(f"Created folder: {folder_name}")
        return folder_name
    except OSError as e:
        print(f"Error creating directory {folder_name}: {e}")
        return None
def search_product_images_api(product_name: str, num_images: int = 5) -> list[str]:
    """
    Searches for product images using the Google Custom Search API with key rotation (CSE ID fixed).
    
    Args:
        product_name: The query string for the product best images as possible.
        num_images: The maximum number of image URLs to retrieve.

    Returns:
        A list of image URLs.
    """
    if not API_KEYS or not CSE_IDS:
        print("\n!! ERROR: Please update API_KEYS and CSE_ID in the configuration section.")
        print("!! Using placeholder URLs for demonstration only.")
        sanitized_name = product_name.replace(' ', '+')
        return [
            f"https://placehold.co/600x400/3498db/ffffff?text={sanitized_name}+{i}"
            for i in range(1, num_images + 1)
        ]

    print(f"Searching API for '{product_name}' images...")

    global CURRENT_KEY_INDEX
    for attempt in range(len(API_KEYS)):
        current_key = API_KEYS[CURRENT_KEY_INDEX]

        try:
            service = build("customsearch", "v1", developerKey=current_key)

            res = service.cse().list(
                q=product_name,
                cx=CSE_IDS,                     
                searchType='image',
                num=num_images,
                fileType='jpg|jpeg|png',
                safe='active'
            ).execute()

            image_urls = []
            if 'items' in res:
                for item in res['items']:
                    if 'link' in item:
                        image_urls.append(item['link'])

            print(f"API Search found {len(image_urls)} image URLs (Key #{CURRENT_KEY_INDEX + 1}).")
            return image_urls[:num_images]

        except HttpError as e:
            error_details = e.content.decode()
            if 'rateLimitExceeded' in error_details:
                print(f"!! Rate limit exceeded for Key #{CURRENT_KEY_INDEX + 1}. Switching to next key...")
                CURRENT_KEY_INDEX += 1
                if CURRENT_KEY_INDEX < len(API_KEYS):
                    time.sleep(2 ** attempt + 1) 
                    continue
                else:
                    break
            elif 'invalid_key' in error_details:
                print(f"!! Invalid API Key #{CURRENT_KEY_INDEX + 1}. Switching to next key...")
                CURRENT_KEY_INDEX += 1
                if CURRENT_KEY_INDEX < len(API_KEYS):
                    continue
                else:
                    break
            else:
                print(f"!! API HTTP Error: {e.resp.status}. Details: {error_details[:100]}...")
                CURRENT_KEY_INDEX += 1
                if CURRENT_KEY_INDEX < len(API_KEYS):
                    time.sleep(1)
                    continue
                else:
                    break

        except Exception as e:
            print(f"!! General API Search Error: {e}")
            CURRENT_KEY_INDEX += 1
            if CURRENT_KEY_INDEX < len(API_KEYS):
                time.sleep(1)
                continue
            else:
                break

    print("!! All API keys exhausted. No results.")
    return []


def download_image(image_url: str) -> Image.Image | None:
    """Downloads an image from a URL and returns a PIL Image object."""
    try:
        # User-Agent is essential for many websites to allow the request
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        print(f"Downloading from: {image_url[:80]}...")
        response = requests.get(image_url, headers=headers, timeout=15, allow_redirects=True)
        response.raise_for_status() # Raises an HTTPError for bad responses (4xx or 5xx)
        
        content_type = response.headers.get('content-type', '').lower()
        if not content_type.startswith('image/'):
            print(f"Warning: URL returned non-image content: {content_type}")
            return None
        
        return Image.open(io.BytesIO(response.content))
        
    except requests.exceptions.Timeout:
        print(f"Error: Timeout downloading image from {image_url[:40]}...")
    except requests.exceptions.RequestException as e:
        print(f"Error downloading image: {e}")
    except IOError:
        print("Error: PIL could not open the image data (Corrupted or unsupported format).")
    except Exception as e:
        print(f"Unknown download error: {e}")
    return None

def resize_image_for_size(image: Image.Image, max_kb: int = 50) -> tuple[Image.Image, int]:
    """
    Resizes and compresses image to be under max_kb (20KB), returning the image and final quality.
    Prioritizes quality reduction first, then falls back to dimension reduction.
    """
    
    # 1. Initialization
    if image.mode in ('RGBA', 'LA', 'P'):
        image = image.convert('RGB')
        
    quality = 90  # Start with a high quality
    max_bytes = max_kb * 1024
    
    # 2. Iterative Compression Loop
    print(f"Target size: {max_kb} KB. Starting compression...")
    
    while True:
        img_byte_arr = io.BytesIO()
        
        # Save attempt with current settings
        image.save(img_byte_arr, format='JPEG', quality=quality, optimize=True)
        current_size = img_byte_arr.tell()
        
        current_size_kb = current_size / 1024
        
        # Check 1: Success or failure
        if current_size <= max_bytes:
            print(f"  -> SUCCESS: Final size {current_size_kb:.2f} KB (Quality: {quality})")
            break # Target met!
        
        # Check 2: Aggressive Quality Reduction
        if quality > 25:
            # Reduce quality by a small, controlled step to preserve visual fidelity
            quality -= 5 
            continue
            
        # Check 3: Dimension Reduction (Fallback)
        # If quality is low (25 or less) and size is still too big, reduce dimensions aggressively
        width, height = image.size
        
        # Prevent resizing images that are already small (e.g., less than 300px on any side)
        if min(width, height) < 300 and quality <= 10:
            print(f"  -> WARNING: Failed to meet 20 KB. Size is {current_size_kb:.2f} KB. Cannot resize further.")
            break 
            
        # Reduce dimensions by 20% and reset quality high to restart compression
        new_width = int(width * 0.8)
        new_height = int(height * 0.8)

        print(f"  -> INFO: Size is {current_size_kb:.2f} KB (Q={quality}). Reducing dimensions to {new_width}x{new_height}.")
        
        image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # Reset quality to high (80) to try compression on the smaller image aggressively
        quality = 80 
        
        # Hard stop if we hit extremely low quality without meeting the size goal
        if quality <= 10 and current_size > max_bytes:
            print(f"  -> FAILURE: Image is too large to fit in 20 KB without severe quality loss.")
            break

    # 3. Final Save and Return
    # Re-save the final image data into a fresh buffer to ensure the returned image object 
    # and the size match the final quality value.
    final_buffer = io.BytesIO()
    image.save(final_buffer, format='JPEG', quality=quality, optimize=True)
    
    # Optional: You can reset the image object from the buffer if you need the Image object 
    # to accurately reflect the final compression settings.
    final_buffer.seek(0)
    final_image = Image.open(final_buffer)
    
    return final_image, quality

def save_selected_image(image: Image.Image, product_name: str, folder_name: str) -> str:
    """Cleans name, ensures uniqueness, resizes, and saves the image."""
    
    # Sanitize product name for filename
    clean_name = "".join(c for c in product_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
    clean_name = clean_name.replace(' ', '_')
    
    file_extension = ".jpg"
    filename_base = clean_name
    
    # Ensure unique filename
    counter = 1
    filename = f"{filename_base}{file_extension}"
    filepath = os.path.join(folder_name, filename)
    
    while os.path.exists(filepath):
        filename = f"{filename_base}_{counter}{file_extension}"
        filepath = os.path.join(folder_name, filename)
        counter += 1
    
    print(f"Optimizing image size (max {MAX_COMPRESSION_KB}KB)...")
    resized_image, quality = resize_image_for_size(image, max_kb=MAX_COMPRESSION_KB)
    
    # Final save operation
    try:
        resized_image.save(filepath, 'JPEG', quality=quality, optimize=True)
        
        final_size_kb = os.path.getsize(filepath) / 1024
        print(f"Image saved as: {filename}")
        print(f"Final size: {final_size_kb:.1f} KB")
        print(f"Image dimensions: {resized_image.size}")
        
        return filepath
    except Exception as e:
        print(f"Error during final image saving: {e}")
        return "Save failed."

def _score_image(image: Image.Image) -> float:
    """Heuristic score for an image: prefer higher resolution and aspect ratios near square or 4:3."""
    width, height = image.size
    min_side = min(width, height)
    if height == 0:
        return 0.0
    aspect = width / height
    aspect_penalty = min(abs(aspect - 1.0), abs(aspect - 4/3), abs(aspect - 3/4))
    return float(min_side) - float(aspect_penalty * 50.0)

def fetch_and_save_best_image(product_name: str, num_candidates: int = 5) -> Tuple[bool, str]:
    folder_name = ensure_product_image_folder()
    if not folder_name:
        return False, "Cannot create product_image folder"
    downloaded: List[Tuple[Image.Image, str]] = []
    attempts = 0
    while attempts < 3 and not downloaded:
        attempts += 1
        image_urls = search_product_images_api(product_name, num_images=num_candidates)
        if not image_urls:
            if attempts >= 3:
                return False, "No image URLs found after retries"
            time.sleep(2 ** attempts)  # Exponential backoff: 2, 4, 8 seconds
            continue
        for url in image_urls:
            time.sleep(0.5)  # Slightly longer delay between downloads
            img = download_image(url)
            if img:
                downloaded.append((img, url))
        if not downloaded and attempts < 3:
            # Exponential backoff: 2, 4, 8 seconds
            time.sleep(2 ** attempts)
    if not downloaded:
        return False, "No images downloaded after retries"
    best_img, _ = max(downloaded, key=lambda t: _score_image(t[0]))
    path = save_selected_image(best_img, product_name, folder_name)
    return True, path

def main_cli():
    print("=== Non-interactive Product Image Batch Fetcher ===")
    print(f"Target file size: {MAX_COMPRESSION_KB}KB (JPEG)")
    folder_name = ensure_product_image_folder()
    if not folder_name:
        print("Cannot proceed without a save folder.")
        return
    batch_file = os.path.join(os.path.dirname(__file__), "image_batch_names.txt")
    if not os.path.exists(batch_file):
        print("image_batch_names.txt not found. Nothing to fetch.")
        return
    with open(batch_file, 'r', encoding='utf-8') as f:
        names = [line.strip() for line in f if line.strip()]
    print(f"Processing {len(names)} products from image_batch_names.txt...")
    successes = 0
    for name in names:
        ok, msg = fetch_and_save_best_image(name, num_candidates=5)
        if ok:
            successes += 1
            print(f"✓ {name}: {msg}")
        else:
            print(f"✗ {name}: {msg}")
    print(f"Done. Saved {successes}/{len(names)} images to 'product_image'.")

if __name__ == "__main__":
    main_cli()
