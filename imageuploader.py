import os
import io
import boto3
from PIL import Image
from typing import List, Dict, Optional


AWS_ACCESS_KEY_ID = ''
AWS_SECRET_ACCESS_KEY = ''
AWS_REGION = 'eu-north-1'       # Correct Region Code
S3_BUCKET_NAME = '' # Correct Bucket Name
INPUT_FOLDER = ''  # Local folder containing images
S3_UPLOAD_FOLDER = '' # Folder inside your S3 bucket
MAX_FILE_SIZE_KB = 30
BATCH_SIZE = 50

s3_client = boto3.client(
    's3',
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION
)

# --- Helper Functions ---

def resize_image_for_size(image: Image.Image, max_kb: int = 30) -> tuple[Image.Image, int]:
    """Resizes and compresses image to be under max_kb (250KB), returning the image and final quality."""
    
    # Convert image to RGB if necessary for JPEG saving
    if image.mode in ('RGBA', 'LA', 'P'):
        image = image.convert('RGB')
    
    quality = 95
    max_bytes = max_kb * 1024
    
    # Make a copy to work with
    working_image = image.copy()
    
    # Iteratively reduce quality and then size until target size is met
    while True:
        img_byte_arr = io.BytesIO()
        working_image.save(img_byte_arr, format='JPEG', quality=quality, optimize=True)
        current_size = img_byte_arr.tell()
        
        print(f"  Testing: quality={quality}, size={current_size/1024:.1f}KB, dimensions={working_image.size}")
        
        if current_size <= max_bytes:
            print(f"  ✓ Target size achieved with quality={quality}")
            break
            
        if quality <= 10:
            print(f"  ! Minimum quality reached, size={current_size/1024:.1f}KB")
            break
            
        quality -= 15
        
        # If quality is too low and still oversized, reduce dimensions
        if quality < 10:
            width, height = working_image.size
            
            # Stop if image size is already small
            if width * 0.8 < 100 or height * 0.8 < 100:
                print("  ! Compression stopped (too small to resize further)")
                quality = 10 
                break 
                
            # Reduce dimensions and reset quality high
            print(f"  ! Reducing dimensions from {working_image.size} to {int(width * 0.8)}x{int(height * 0.8)}")
            working_image = working_image.resize((int(width * 0.8), int(height * 0.8)), Image.Resampling.LANCZOS)
            quality = 85 
    
    # Return the ACTUALLY compressed image and quality
    # We need to reload the image from the compressed bytes to ensure it's properly compressed
    img_byte_arr.seek(0)
    final_image = Image.open(img_byte_arr)
    
    # Verify final size
    verification_buffer = io.BytesIO()
    final_image.save(verification_buffer, format='JPEG', quality=quality, optimize=True)
    final_size_kb = verification_buffer.tell() / 1024
    print(f"  Final: {final_size_kb:.1f}KB, quality={quality}, dimensions={final_image.size}")
    
    return final_image, quality

def resize_and_compress_image(image_path: str, max_kb: int) -> Optional[io.BytesIO]:
    """Open image from path, compress to ~max_kb, and return a BytesIO buffer ready for upload."""
    try:
        with Image.open(image_path) as img:
            final_img, quality = resize_image_for_size(img, max_kb=max_kb)
            buffer = io.BytesIO()
            final_img.save(buffer, format='JPEG', quality=quality, optimize=True)
            buffer.seek(0)
            return buffer
    except Exception as e:
        print(f"  -> ERROR processing image '{image_path}': {e}")
        return None

def upload_to_s3(file_buffer: io.BytesIO, filename: str, s3_key: str, bucket_name: str) -> Optional[str]:
    """
    Uploads the image buffer to S3 and returns the public URL.
    """
    try:
        s3_client.upload_fileobj(
            file_buffer,
            bucket_name,
            s3_key,
            ExtraArgs={'ContentType': 'image/jpeg'} # Assuming output is JPEG
        )
        # Construct the public URL (this format works for most regions unless block public access is on)
        url = f"https://{bucket_name}.s3.{AWS_REGION}.amazonaws.com/{s3_key}"
        print(f"  -> UPLOADED: {url}")
        return url
    except Exception as e:
        print(f"  -> ERROR uploading {filename} to S3: {e}")
        return None

def generate_output_batches(uploaded_links: Dict[str, str], batch_size: int, output_filename: str = 's3_upload_links.txt'):
    """
    Writes the uploaded image links to a file in batches.
    """
    items = list(uploaded_links.items())
    num_items = len(items)
    
    with open(output_filename, 'w') as f:
        f.write("--- S3 Upload Links Batch Output ---\n\n")
        
        for i in range(0, num_items, batch_size):
            batch = items[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            
            f.write(f"===== BATCH {batch_num} (Images {i+1} to {min(i + batch_size, num_items)}) =====\n")
            for filename, url in batch:
                # Format: original_filename, s3_url
                f.write(f"{filename},{url}\n")
            f.write("\n")
            
    print(f"\n✅ All {num_items} links saved to '{output_filename}' in batches of {batch_size}.")


# --- Main Execution ---

def upload_folder_images(input_folder: str = INPUT_FOLDER, target_kb: int = MAX_FILE_SIZE_KB) -> Dict[str, str]:
    """Uploads all images from a folder to S3 with compression to ~target_kb. Returns {filename: url}."""
    if not os.path.exists(input_folder):
        print(f"ERROR: Input folder '{input_folder}' not found. Please create it and add images.")
        return {}

    # Dictionary to store successfully uploaded links: {filename: s3_url}
    uploaded_links: Dict[str, str] = {}
    
    # Supported image extensions
    allowed_extensions = ('.jpg', '.jpeg', '.png', '.webp')

    print(f"Starting image upload process from '{input_folder}'...")
    
    # Get all image files in the input folder
    image_files = [f for f in os.listdir(input_folder) if f.lower().endswith(allowed_extensions)]
    
    if not image_files:
        print("No images found in the input folder.")
        return

    for filename in image_files:
        full_path = os.path.join(input_folder, filename)
        
        # 1. Resize and Compress Image
        image_buffer = resize_and_compress_image(full_path, target_kb)
        
        if image_buffer:
            # 2. Define S3 Key and Upload
            # Ensure the S3 key is clean (e.g., using a .jpeg extension)
            s3_filename = os.path.splitext(filename)[0] + '.jpeg' 
            s3_key = S3_UPLOAD_FOLDER + s3_filename
            
            s3_url = upload_to_s3(image_buffer, filename, s3_key, S3_BUCKET_NAME)
            
            if s3_url:
                uploaded_links[filename] = s3_url
            
            # Clean up the buffer
            image_buffer.close()
    
    return uploaded_links


def main():
    links = upload_folder_images(INPUT_FOLDER, MAX_FILE_SIZE_KB)
    if links:
        generate_output_batches(links, BATCH_SIZE)
    else:
        print("No successful uploads to generate a link file.")

if __name__ == '__main__':
    main()