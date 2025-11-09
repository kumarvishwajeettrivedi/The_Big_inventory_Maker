import json
import requests
import time
import os
from typing import List, Dict, Any, Tuple, Optional, Set

# --- Configuration ---
API_KEYS = []  # Add all your API keys here
CURRENT_KEY_INDEX = 0
MODEL_NAME = "gemini-2.5-flash-preview-05-20"
BATCH_SIZE = 50  
MAX_RETRIES = 5

# Files for coordination
PROCESSED_TRACK_FILE = "processed_items.txt"           # Accumulates all processed product names across runs
BATCH_NAMES_OUTPUT_FILE = "image_batch_names.txt"      # Names for the image pipeline for this run
S3_LINKS_FILE = "s3_upload_links.txt"                 # Produced by uploader; filename,url lines
DUMMY_IMAGE_URL = ""# add a dummy image url here

def get_api_url() -> str:
    """Returns the current API URL using the active API key."""
    return f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={API_KEYS[CURRENT_KEY_INDEX]}"

def switch_api_key() -> bool:
    """Switches to the next available API key. Returns False if no keys left."""
    global CURRENT_KEY_INDEX
    if CURRENT_KEY_INDEX < len(API_KEYS) - 1:
        CURRENT_KEY_INDEX += 1
        print(f"⚡ Switching to next API key (Key #{CURRENT_KEY_INDEX + 1})...")
        return True
    else:
        print("❌ All API keys exhausted.")
        return False

# --- Helper Functions ---

def _resolve_path(local_filename: str) -> str:
    """Resolve a filename relative to this script's directory."""
    return os.path.join(os.path.dirname(__file__), local_filename)

def load_products(filename: str) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Load products from a JSON file. Supports either a top-level list, or an object with key 'menu'.
    Returns (products_list, wrapper_key) where wrapper_key is None for list files, or a string like 'menu'.
    """
    try:
        resolved = _resolve_path(filename)
        with open(resolved, 'r', encoding='utf-8') as f:
            print(f"Loading data from {resolved}...")
            data = json.load(f)
            if isinstance(data, list):
                print(f"Successfully loaded {len(data)} products (list root).")
                return data, None
            if isinstance(data, dict):
                # Common pattern in this repo: { "menu": [ ... ] }
                for key in ("menu", "items", "products"):
                    if key in data and isinstance(data[key], list):
                        print(f"Successfully loaded {len(data[key])} products (under '{key}').")
                        return data[key], key
            print("Error: JSON file must contain a list of products or a 'menu' key with a list.")
            return [], None
    except Exception as e:
        print(f"Error loading file: {e}")
        return [], None

def save_products(filename: str, products: List[Dict[str, Any]], wrapper_key: Optional[str], inplace: bool = True) -> str:
    """
    Save updated products either in-place or to an 'updated_' copy, preserving original structure.
    Returns the path written.
    """
    try:
        resolved = _resolve_path(filename)
        if inplace:
            output_path = resolved
        else:
            dirname = os.path.dirname(resolved)
            basename = os.path.basename(resolved)
            output_path = os.path.join(dirname, f"updated_{basename}")

        data_to_write: Any
        if wrapper_key is None:
            data_to_write = products
        else:
            # Read full original to preserve other keys
            with open(resolved, 'r', encoding='utf-8') as f:
                original = json.load(f)
            original[wrapper_key] = products
            data_to_write = original

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data_to_write, f, indent=2, ensure_ascii=False)
        return output_path
    except Exception as e:
        print(f"Error saving products: {e}")
        return ""

def read_processed_names() -> Set[str]:
    path = _resolve_path(PROCESSED_TRACK_FILE)
    if not os.path.exists(path):
        return set()
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return set([line.strip() for line in f if line.strip()])
    except Exception:
        return set()

def append_processed_names(names: List[str]) -> None:
    path = _resolve_path(PROCESSED_TRACK_FILE)
    try:
        with open(path, 'a', encoding='utf-8') as f:
            for n in names:
                f.write(n + "\n")
    except Exception as e:
        print(f"Warning: Could not append to {PROCESSED_TRACK_FILE}: {e}")

def write_batch_names(names: List[str]) -> None:
    path = _resolve_path(BATCH_NAMES_OUTPUT_FILE)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            for n in names:
                f.write(n + "\n")
        print(f"Batch names written to {BATCH_NAMES_OUTPUT_FILE} (count={len(names)}).")
    except Exception as e:
        print(f"Warning: Could not write {BATCH_NAMES_OUTPUT_FILE}: {e}")

def read_batch_names() -> List[str]:
    path = _resolve_path(BATCH_NAMES_OUTPUT_FILE)
    if not os.path.exists(path):
        return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]
    except Exception:
        return []

def _sanitize_name_for_filename(name: str) -> str:
    clean = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).rstrip()
    return clean.replace(' ', '_').lower()

def parse_s3_links_file() -> Dict[str, str]:
    """
    Parse s3_upload_links.txt into a dict mapping filename (as written in file) -> url.
    Ignores header/separator lines.
    """
    links: Dict[str, str] = {}
    path = _resolve_path(S3_LINKS_FILE)
    if not os.path.exists(path):
        return links
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("-") or line.startswith("="):
                    continue
                if "," in line:
                    filename, url = line.split(",", 1)
                    filename = filename.strip()
                    url = url.strip()
                    if filename and url:
                        links[filename] = url
    except Exception as e:
        print(f"Warning: Could not parse {S3_LINKS_FILE}: {e}")
    return links

def _match_url_for_name(base_to_url: Dict[str, str], product_name: str) -> Optional[str]:
    """Find best matching URL for a given product name using sanitized, case-insensitive rules.
    Tries exact, numbered suffixes, and bidirectional prefix checks.
    """
    base = _sanitize_name_for_filename(product_name)
    # 1) exact and numbered variants
    for key in (base, f"{base}_1", f"{base}_2", f"{base}_3"):
        if key in base_to_url:
            return base_to_url[key]
    # 2) filename starts with base
    for b, url in base_to_url.items():
        if b.startswith(base):
            return url
    # 3) base starts with filename (e.g., longer product name)
    for b, url in base_to_url.items():
        if base.startswith(b):
            return url
    return None

def call_gemini_api_with_retry(payload: Dict[str, Any]) -> Dict[str, Any]:
    for attempt in range(MAX_RETRIES):
        try:
            headers = {'Content-Type': 'application/json'}
            response = requests.post(get_api_url(), headers=headers, json=payload)
            
            if response.status_code == 429:
                print(f"Rate limit reached for current key (Key #{CURRENT_KEY_INDEX + 1}).")
                if switch_api_key():
                    continue  # Retry with next API key
                else:
                    return {"error": "All API keys exhausted due to rate limits."}
            
            response.raise_for_status()
            return response.json()
        
        except requests.exceptions.RequestException as e:
            wait_time = 2 ** attempt + (time.monotonic() % 1)
            print(f"API Error (Attempt {attempt + 1}/{MAX_RETRIES}): {e}. Retrying in {wait_time:.2f} seconds...")
            time.sleep(wait_time)
    
    return {"error": "API call failed after multiple retries."}

def process_batch(batch: List[Dict[str, Any]], batch_index: int) -> List[Dict[str, Any]]:
    print(f"\n--- Processing Batch {batch_index + 1} ({len(batch)} items) ---")

    system_prompt = (
        "You are an expert e-commerce catalog manager optimizing for substring-based search. "
        "For each product, do TWO tasks:\n"
        "1) Enhance the product name by expanding short forms to clear, generic, search-friendly names (e.g., 'Panteen SS' -> 'Pantene Smooth & Shine Shampoo') but dont do cotage cheese for paneer or potato for aloo in food items, make them native to indian origin.\n"
        "2) Write an ultra-concise description (<= 30 words) that is search-optimized and includes:\n"
        "   - Brand name (if obvious),\n"
        "   - 2-3 plausible key ingredients (only if relevant),\n"
        "   - Local/common product type,\n"
        "   - A short trailing search tag list in parentheses with synonyms/variations a user might type (e.g., '(cold drink, lemon lime, soda, Coca-Cola)').\n"
        "Keep tone simple. Avoid fluff. No line breaks. Return strict JSON only."
    )

    product_text_list = "\n".join([
        f"| ID: {p.get('id', idx)} | Original Name: '{p.get('name', '')}' | Original Description: '{p.get('description', '')}' |"
        for idx, p in enumerate(batch)
    ])

    user_query = "Process the following list of products. Output JSON array with same number of entries as input.\n\n" + product_text_list

    response_schema = {
        "type": "ARRAY",
        "items": {
            "type": "OBJECT",
            "properties": {
                "id": {"type": "INTEGER"},
                "originalName": {"type": "STRING"},
                "enhancedName": {"type": "STRING"},
                "enhancedDescription": {"type": "STRING"}
            },
            "required": ["id", "originalName", "enhancedName", "enhancedDescription"]
        }
    }

    payload = {
        "contents": [{ "parts": [{ "text": user_query }] }],
        "systemInstruction": { "parts": [{ "text": system_prompt }] },
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": response_schema
        }
    }

    api_response = call_gemini_api_with_retry(payload)

    if 'error' in api_response:
        print(f"Skipping Batch {batch_index + 1} due to API error: {api_response['error']}")
        return []

    try:
        json_text = api_response['candidates'][0]['content']['parts'][0]['text']
        processed_data = json.loads(json_text)
        print(f"Successfully processed {len(processed_data)} items.")
        return processed_data
    except Exception as e:
        print(f"Error parsing Gemini response: {e}")
        return []

def _select_next_batch(all_products: List[Dict[str, Any]], batch_size: int) -> List[Dict[str, Any]]:
    processed = read_processed_names()
    next_batch: List[Dict[str, Any]] = []
    for p in all_products:
        name = p.get("name", "").strip()
        if not name:
            continue
        if name in processed:
            continue
        next_batch.append(p)
        if len(next_batch) >= batch_size:
            break
    return next_batch

def _apply_enhancements_to_products(all_products: List[Dict[str, Any]], processed_results: List[Dict[str, Any]]) -> Tuple[int, List[str]]:
    """
    Update 'name' and 'description' in-place by matching on originalName. Returns (count_updated, enhanced_names_list).
    """
    name_to_index: Dict[str, int] = {}
    for idx, p in enumerate(all_products):
        n = p.get("name", "")
        if n:
            name_to_index.setdefault(n, idx)

    updated = 0
    enhanced_names: List[str] = []
    for item in processed_results:
        original = item.get("originalName", "")
        enhanced_name = item.get("enhancedName", "")
        enhanced_desc = item.get("enhancedDescription", "")
        if not original or original not in name_to_index:
            continue
        idx = name_to_index[original]
        if enhanced_name:
            all_products[idx]["name"] = enhanced_name
        if enhanced_desc:
            all_products[idx]["description"] = enhanced_desc
        updated += 1
        if enhanced_name:
            enhanced_names.append(enhanced_name)
        else:
            enhanced_names.append(original)
    return updated, enhanced_names

def _replace_dummy_images_for_batch(all_products: List[Dict[str, Any]], batch_names: Any, debug: bool = False) -> int:
    """
    Attempt to replace dummy image links for the provided names using S3 links file.
    Returns the number of images updated.
    """
    links = parse_s3_links_file()
    if not links:
        print("No S3 links found to apply.")
        return 0

    # Build lookup by sanitized base name (without extension)
    base_to_url: Dict[str, str] = {}
    for filename, url in links.items():
        base, _ = os.path.splitext(filename)
        base_to_url[base.lower()] = url

    updated = 0
    skipped_not_in_batch = 0
    skipped_not_dummy = 0
    skipped_no_link = 0
    batch_names_lower: Optional[Set[str]] = None
    if isinstance(batch_names, set) or isinstance(batch_names, list):
        batch_names_lower = set([str(n).strip().lower() for n in batch_names])
    for p in all_products:
        name = p.get("name", "").strip()
        if not name:
            continue
        if batch_names_lower is not None and name.lower() not in batch_names_lower:
            skipped_not_in_batch += 1
            continue
        # Replace only if current image is dummy
        current_image = p.get("image", "").strip()
        if current_image != DUMMY_IMAGE_URL:
            skipped_not_dummy += 1
            continue
        target_url = _match_url_for_name(base_to_url, name)
        if target_url:
            p["image"] = target_url
            updated += 1
        else:
            skipped_no_link += 1
    if debug:
        print(f"Replacement debug → updated={updated}, not_in_batch={skipped_not_in_batch}, not_dummy={skipped_not_dummy}, no_link_match={skipped_no_link}, links_available={len(base_to_url)}")
    return updated

def main(input_filename: str, debug: bool = False, batch_size: Optional[int] = None):
    # 1) Load products
    all_products, wrapper_key = load_products(input_filename)
    if not all_products:
        return

    # 2) Determine next batch using processed tracker
    effective_batch_size = BATCH_SIZE if batch_size is None else int(batch_size)
    batch = _select_next_batch(all_products, effective_batch_size)
    if not batch:
        # No new items to enhance; attempt replacement-only pass using last batch names file
        batch_names = read_batch_names()
        if not batch_names:
            print("Nothing to process and no batch names available for replacement.")
            return
        replaced = _replace_dummy_images_for_batch(all_products, set(batch_names), debug=debug)
        print(f"Replacement-only pass: replaced image links for {replaced} items.")
        written_path = save_products(input_filename, all_products, wrapper_key, inplace=True)
        if written_path:
            print(f"Saved updates to: {written_path}")
        else:
            print("Warning: Could not save updates.")
        return

    # 3) Run model to enhance batch
    results = process_batch(batch, 0)
    if not results:
        print("No results returned for this batch. Aborting this cycle.")
        return

    # 4) Apply enhancements back into products
    updated_count, enhanced_names = _apply_enhancements_to_products(all_products, results)
    print(f"Applied enhancements to {updated_count} items.")

    # 5) Write batch names for image pipeline and append to processed tracker
    write_batch_names(enhanced_names)
    append_processed_names(enhanced_names)

    # 6) Attempt to replace dummy image links for this batch using S3 links
    replaced = _replace_dummy_images_for_batch(all_products, set(enhanced_names), debug=debug)
    print(f"Replaced image links for {replaced} items from S3 links file (if available).")

    # 7) Save JSON in-place
    written_path = save_products(input_filename, all_products, wrapper_key, inplace=True)
    if written_path:
        print(f"Saved updates to: {written_path}")
    else:
        print("Warning: Could not save updates.")

def replace_images_for_last_batch(input_filename: str, debug: bool = False) -> None:
    """
    Replace dummy image URLs for the most recently processed batch using names from image_batch_names.txt
    and links from s3_upload_links.txt. Does not run enhancement.
    """
    all_products, wrapper_key = load_products(input_filename)
    if not all_products:
        return
    batch_names = read_batch_names()
    if not batch_names:
        print("No batch names available for replacement.")
        return
    replaced = _replace_dummy_images_for_batch(all_products, set(batch_names), debug=debug)
    print(f"Image replacement pass: replaced image links for {replaced} items.")
    written_path = save_products(input_filename, all_products, wrapper_key, inplace=True)
    if written_path:
        print(f"Saved updates to: {written_path}")
    else:
        print("Warning: Could not save updates.")

def replace_images_from_links_all(input_filename: str, debug: bool = False) -> None:
    """
    Replace dummy image URLs across ALL products using only s3_upload_links.txt, ignoring batch names.
    """
    all_products, wrapper_key = load_products(input_filename)
    if not all_products:
        return
    links = parse_s3_links_file()
    if not links:
        print("No S3 links found to apply.")
        return
    base_to_url: Dict[str, str] = {}
    for filename, url in links.items():
        base, _ = os.path.splitext(filename)
        base_to_url[base.lower()] = url
    updated = 0
    skipped_not_dummy = 0
    skipped_no_link = 0
    for p in all_products:
        name = p.get("name", "").strip()
        if not name:
            continue
        current_image = p.get("image", "").strip()
        if current_image != DUMMY_IMAGE_URL:
            skipped_not_dummy += 1
            continue
        target_url = _match_url_for_name(base_to_url, name)
        if target_url:
            p["image"] = target_url
            updated += 1
        else:
            skipped_no_link += 1
    if debug:
        print(f"Global replacement debug → updated={updated}, not_dummy={skipped_not_dummy}, no_link_match={skipped_no_link}, links_available={len(base_to_url)}")
    written_path = save_products(input_filename, all_products, wrapper_key, inplace=True)
    if written_path:
        print(f"Saved updates to: {written_path}")
    else:
        print("Warning: Could not save updates.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Enhance products and/or replace image links")
    parser.add_argument("--replace-only", action="store_true", help="Only replace dummy image links for last batch using s3_upload_links.txt")
    parser.add_argument("--input", type=str, default=None, help="Input JSON filename in this directory (default: auto-detect nath_menu.json)")
    parser.add_argument("--debug", action="store_true", help="Print replacement diagnostics")
    parser.add_argument("--replace-from-links-all", action="store_true", help="Replace dummy images across all products using s3_upload_links.txt only")
    parser.add_argument("--batch-size", type=int, default=None, help="Override batch size for this run (e.g., 5 for testing)")
    args = parser.parse_args()

    # Prefer a known file in this directory if not provided; fallback to input_products.json
    default_candidates = [
        "nath_menu.json",
        "input_products.json"
    ]
    chosen = args.input
    if not chosen:
        for fname in default_candidates:
            if os.path.exists(_resolve_path(fname)):
                chosen = fname
                break
    if not chosen:
        chosen = "input_products.json"

    if args.replace_from_links_all:
        replace_images_from_links_all(chosen, debug=args.debug)
    elif args.replace_only:
        replace_images_for_last_batch(chosen, debug=args.debug)
    else:
        main(chosen, debug=args.debug, batch_size=args.batch_size)
