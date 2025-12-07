# 🧠 The Big Inventory Maker

**The Big Inventory Maker** is an intelligent automation tool built with **Python** that simplifies and accelerates the process of creating large-scale product inventories.  

Simply provide the **names of the products**, and the script will automatically:
- Fetch accurate product images using the **Google Search API**
- Validate and upload them to your **cloud storage**
- Generate detailed product descriptions using the **Gemini API**
- Output a ready-to-use **JSON file** for seamless database integration

---

## 🚀 Features

- 🔍 **Automated Image Fetching** — Fetches relevant product images using Google Search API.  
- 🧠 **AI Description Generation** — Generates descriptive and SEO-friendly product descriptions via Gemini API.  
- ✅ **Image Validation** — Automatically filters and validates images before saving.  
- ☁️ **Cloud Sync** — Uploads valid images directly to your cloud storage.  
- 🔄 **Progress Tracking** — Keeps track of processed products to prevent repetition.  
- 🧾 **JSON Export** — Produces structured JSON output, easily mappable to your database schema.  
- 🖼️ **Manual Review Option** — Allows you to review and manually remove unwanted images in the `/product_images` folder.  

---

## 🧰 Tech Stack

| Tool | Purpose |
|------|----------|
| 🐍 **Python 3.11+** | Core scripting language |
| 🌐 **Google Search Engine API** | Image fetching |
| 🤖 **Gemini API** | Product description and metadata generation |
| ☁️ **Cloud Storage (custom)** | Image storage and linking |

---


## ⚙️ Setup & Installation

### 1️⃣ Clone the Repository
```bash
git clone https://github.com/kumarvishwajeettrivedi/The_Big_inventory_Maker.git
cd The_Big_inventory_Maker

2️⃣ Set Up Python Environment

Make sure you have Python 3.11+ installed.
You can use pyenv or venv to manage environments:

pyenv shell 3.11.6
pip install -r requirements.txt

3️⃣ Configure API Keys

Before running the script, configure your API keys:

In description_writer.py → add your Gemini API Key

In image_fetch.py → add your Google Search API Key

Example:

# description_writer.py
GEMINI_API_KEY = "your_gemini_api_key_here"

# image_fetch.py
GOOGLE_API_KEY = "your_google_api_key_here"
SEARCH_ENGINE_ID = "your_search_engine_id_here"

▶️ How to Use

Run the script:

python piped-piper.py


When prompted:

Enter product names (one or multiple).

The script will:

Fetch relevant product images.

Validate and store them inside /product_images.

Generate detailed product descriptions.

Upload images to your cloud storage (if configured).

Output a clean, structured JSON file (output.json) for your database.

You can manually review the images — delete or deselect any that you don’t want before finalizing your data.

📦 Example JSON Output
[
  {
    "name": "Dettol Antiseptic Liquid",
    "description": "A trusted antiseptic for first aid, cleaning, and personal hygiene.",
    "image_url": "https://your-cloud-storage.com/images/dettol.jpg",
    "category": "Health & Hygiene",
    "price": "",
    "brand": "Dettol"
  }
]


This JSON can be directly inserted into your database — just map the fields to your schema.

📊 Accuracy & Performance

🔹 Accuracy: ~87% (Most fetched images and descriptions are correct)

🔹 Recommendation: Use clear, specific product names for best results

🔹 Efficiency: Keeps a progress log to avoid reprocessing already-completed items

🧠 Best Practices

Verify /product_images/ after each run to ensure correctness.

Clean up any duplicates manually if needed.

Ensure API keys have sufficient quota limits.

The script automatically tracks what’s done — so no repetition occurs even after restarts.

pip install -r requirements.txt

👨‍💻 Author

Vishwajeet Kumar
🎓 B.Tech — NIT Sikkim
💼 Full Stack Developer | AI Engineer | Embedded Systems Enthusiast

📬 LinkedIn

🐙 GitHub

🪄 License

This project is released under the MIT License.
You are free to use, modify, and distribute it with proper attribution.

⭐ If you find this project useful, please consider giving it a star on GitHub!


---

This version is **GitHub-optimized**, uses professional documentation tone, proper markdown formatting, and is fully ready to paste as your `README.md`.  

Would you like me to add a **“Future Improvements”** section (e.g., support for more image sources, multilingual descriptions, or cloud integrations)?

