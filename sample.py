import requests
from bs4 import BeautifulSoup
import pandas as pd
from fake_useragent import UserAgent
import os

# Function to scrape Amazon India product details
def get_amazon_product(asin):
    url = f"https://www.amazon.in/dp/{asin}"

    # Rotate User-Agent to mimic real browsers
    ua = UserAgent()
    headers = {
        "User-Agent": ua.random,
        "Accept-Language": "en-IN,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.google.com/",
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)

        # Check if request was successful
        if response.status_code != 200:
            print(f"Failed to fetch data for ASIN {asin}. Status Code: {response.status_code}")
            return None

        soup = BeautifulSoup(response.text, "html.parser")

        # Extract product details
        title = soup.find(id="productTitle")
        title = title.get_text(strip=True) if title else "N/A"

        bullet_points = [bp.get_text(strip=True) for bp in soup.select("#feature-bullets li span")]
        bullet_points = "\n".join(bullet_points)  # Convert list to string for Excel

        price = soup.select_one(".a-price .a-offscreen")
        price = price.get_text(strip=True) if price else "N/A"

        discount_price = soup.select_one(".priceBlockStrikePriceString")
        discount_price = discount_price.get_text(strip=True) if discount_price else "N/A"

        delivery = soup.select_one("#deliveryBlockMessage span")
        delivery = delivery.get_text(strip=True) if delivery else "N/A"

        description = soup.select_one("#productDescription p")
        description = description.get_text(strip=True) if description else "N/A"

        # Store product data
        product_data = {
            "ASIN": asin,
            "Title": title,
            "Bullet Points": bullet_points,
            "Selling Price": price,
            "Discount Price": discount_price,
            "Delivery Date": delivery,
            "Description": description,
            "URL": url,
        }

        return product_data

    except requests.exceptions.RequestException as e:
        print(f"Error fetching data for ASIN {asin}: {e}")
        return None

# Function to save data to an Excel file
def save_to_excel(product_data, filename="amazon_products.xlsx"):
    df = pd.DataFrame([product_data])  # Convert dictionary to DataFrame

    # Check if file exists, append if yes, create new if no
    if os.path.exists(filename):
        existing_df = pd.read_excel(filename)
        df = pd.concat([existing_df, df], ignore_index=True)

    df.to_excel(filename, index=False)
    print(f"Data saved to {filename}")

# Example usage (Scrape multiple ASINs)
asins = ["B0CGW18S6Y"]  # Add more ASINs as needed

for asin in asins:
    product_details = get_amazon_product(asin)
    if product_details:
        save_to_excel(product_details)
