import requests
from bs4 import BeautifulSoup
import pandas as pd
from fake_useragent import UserAgent
import os
import re
from datetime import datetime

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
        
        # Debug: Save HTML to file for inspection
        with open(f"amazon_{asin}_debug.html", "w", encoding="utf-8") as f:
            f.write(response.text)
        
        # Fix for title extraction - specifically targeting the h1 element and span with id productTitle
        title = "N/A"
        # Try multiple approaches to get the title
        title_element = soup.find("h1", {"id": "title"})
        if title_element:
            title_span = title_element.find("span", {"id": "productTitle"})
            if title_span:
                title = title_span.get_text(strip=True)
        
        # If the above approach fails, try direct selection
        if title == "N/A":
            title_span = soup.find("span", {"id": "productTitle"})
            if title_span:
                title = title_span.get_text(strip=True)
                
        # If still no title, try broader CSS selectors
        if title == "N/A":
            title_selectors = [
                "#title_feature_div span",
                ".product-title-word-break",
                "#title span",
                "h1 span#productTitle"
            ]
            for selector in title_selectors:
                title_element = soup.select_one(selector)
                if title_element and title_element.get_text(strip=True):
                    title = title_element.get_text(strip=True)
                    break
        
        # Print debug info
        print(f"Extracted title: {title}")

        bullet_points = [bp.get_text(strip=True) for bp in soup.select("#feature-bullets li span")]
        bullet_points = "\n".join(bullet_points)  # Convert list to string for Excel

        # Fix for price extraction - Focus on a-price-whole as specified
        current_price = "N/A"
        current_price_value = 0
        
        # First try the specific a-price-whole selector
        price_whole_element = soup.select_one("span.a-price-whole")
        price_fraction_element = soup.select_one("span.a-price-fraction")
        
        if price_whole_element:
            price_whole = price_whole_element.get_text(strip=True)
            price_fraction = price_fraction_element.get_text(strip=True) if price_fraction_element else "00"
            current_price = f"₹{price_whole}.{price_fraction}"
            
            # Clean and store numeric value for discount calculation
            price_whole_clean = re.sub(r'[^\d]', '', price_whole)
            price_fraction_clean = re.sub(r'[^\d]', '', price_fraction)
            try:
                current_price_value = float(f"{price_whole_clean}.{price_fraction_clean}")
            except ValueError:
                current_price_value = 0
            
        # If that fails, try alternative selectors
        if current_price == "N/A":
            price_selectors = [
                "#priceblock_ourprice",
                "#priceblock_dealprice",
                ".a-price .a-offscreen",
                "#corePrice_feature_div .a-price span.a-offscreen",
                "span.a-price:not(.a-text-price) span.a-offscreen"
            ]
            
            for selector in price_selectors:
                price_element = soup.select_one(selector)
                if price_element:
                    current_price = price_element.get_text(strip=True)
                    # Extract numeric value from price string
                    numeric_price = re.sub(r'[^\d.]', '', current_price)
                    try:
                        current_price_value = float(numeric_price)
                    except ValueError:
                        current_price_value = 0
                    break
        
        # Debug price
        print(f"Current price: {current_price}")
        print(f"Current price value: {current_price_value}")

        # Fix for MRP/Original price (the crossed-out price)
        original_price = "N/A"
        original_price_value = 0
        
        mrp_selectors = [
            "span.a-price.a-text-price span.a-offscreen",
            "span.a-price.a-text-price:not(.a-no-hover) span.a-offscreen",
            ".priceBlockStrikePriceString",
            "#priceblock_ourprice_lbl",
            ".a-text-price .a-offscreen",
            "#listPrice",
            "#priceBlockStrikePriceString"
        ]
        
        for selector in mrp_selectors:
            mrp_element = soup.select_one(selector)
            if mrp_element:
                original_price = mrp_element.get_text(strip=True)
                # Extract numeric value from price string
                numeric_price = re.sub(r'[^\d.]', '', original_price)
                try:
                    original_price_value = float(numeric_price)
                except ValueError:
                    original_price_value = 0
                break
                
        # Debug MRP
        print(f"Original price/MRP: {original_price}")
        print(f"Original price value: {original_price_value}")
        
        # Calculate discount percentage
        discount_percentage = "N/A"
        if original_price_value > 0 and current_price_value > 0 and original_price_value > current_price_value:
            discount = ((original_price_value - current_price_value) / original_price_value) * 100
            discount_percentage = f"{discount:.1f}%"
            print(f"Calculated discount: {discount_percentage}")

        # Extract and parse delivery information
        delivery_raw = None
        delivery_selectors = [
            "#deliveryBlockMessage span", 
            "#mir-layout-DELIVERY_BLOCK-slot-PRIMARY_DELIVERY_MESSAGE_LARGE span", 
            ".a-color-success",
            "#delivery-message",
            ".a-section .a-spacing-mini .a-text-bold"
        ]
        
        for selector in delivery_selectors:
            delivery_element = soup.select_one(selector)
            if delivery_element and delivery_element.get_text(strip=True):
                delivery_raw = delivery_element.get_text(strip=True)
                break
                
        delivery_raw = delivery_raw if delivery_raw else "N/A"
        
        # Improved delivery date parsing
        delivery_date = parse_delivery_date(delivery_raw)
        
        # Debug delivery
        print(f"Delivery raw: {delivery_raw}")
        print(f"Delivery parsed: {delivery_date}")

        description = soup.select_one("#productDescription p")
        description = description.get_text(strip=True) if description else "N/A"

        # Add timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Store product data
        product_data = {
            "ASIN": asin,
            "Title": title,
            "Bullet Points": bullet_points,
            "Current Price": current_price,
            "Original Price (MRP)": original_price,
            "Discount Percentage": discount_percentage,
            "Delivery Date Raw": delivery_raw,
            "Delivery Date Parsed": delivery_date,
            "Description": description,
            "URL": url,
            "Timestamp": timestamp,
        }

        return product_data

    except requests.exceptions.RequestException as e:
        print(f"Error fetching data for ASIN {asin}: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error for ASIN {asin}: {e}")
        return None

def parse_delivery_date(delivery_text):
    """
    Parse delivery text into a standardized date format.
    """
    if delivery_text == "N/A":
        return "N/A"
    
    # Common patterns in Amazon delivery texts
    date_patterns = [
        r'Delivery by (\w+ \d+ - \w+ \d+)',  # "Delivery by Monday, Mar 4 - Wednesday, Mar 6"
        r'Delivery by (\w+, \w+ \d+)',       # "Delivery by Monday, Mar 4"
        r'Get it by (\w+, \w+ \d+)',         # "Get it by Monday, Mar 4"
        r'Delivery (\w+, \w+ \d+)',          # "Delivery Monday, Mar 4"
        r'(\d{1,2} \w+ - \d{1,2} \w+)',      # "4 March - 6 March"
        r'(\d{1,2}-\d{1,2} \w+)'             # "4-6 March"
    ]
    
    for pattern in date_patterns:
        match = re.search(pattern, delivery_text)
        if match:
            return match.group(1)
    
    # If no pattern matches but contains delivery-related keywords, attempt to extract date portions
    delivery_keywords = ["delivery", "delivered", "arrive", "get it", "by"]
    if any(keyword in delivery_text.lower() for keyword in delivery_keywords):
        # Try to extract date-like parts
        date_parts = re.findall(r'(\d{1,2} \w+|\w+ \d{1,2}|\d{1,2}-\d{1,2} \w+)', delivery_text)
        if date_parts:
            return date_parts[0]
    
    # Return "Unknown" if we can't parse the date
    return "Unable to parse date"

# Function to save data to an Excel file
def save_to_excel(product_data, filename="amazon_products.xlsx"):
    df = pd.DataFrame([product_data])  # Convert dictionary to DataFrame

    # Check if file exists, append if yes, create new if no
    if os.path.exists(filename):
        existing_df = pd.read_excel(filename)
        df = pd.concat([existing_df, df], ignore_index=True)

    df.to_excel(filename, index=False)
    print(f"Data saved to {filename}")

# Example usage
if __name__ == "__main__":
    asins = ["B0CGW18S6Y"]  # Add more ASINs as needed

    for asin in asins:
        product_details = get_amazon_product(asin)
        if product_details:
            save_to_excel(product_details)
            print(f"Successfully scraped data for ASIN: {asin}")
        else:
            print(f"Failed to scrape data for ASIN: {asin}")