from flask import Flask, render_template, request, send_file, redirect, url_for
import requests
from bs4 import BeautifulSoup
import pandas as pd
from fake_useragent import UserAgent
import os
import re
from datetime import datetime
import io
import json

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

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

@app.route('/scrape_single_product', methods=['POST'])
def scrape_single_product():
    if request.method == 'POST':
        asin = request.form['asin']
        product_data = get_amazon_product(asin)

        if product_data:
            # Pass product_data to the template
            return render_template("index.html", products=[product_data]) # Changed product to products, and wrapped in a list
        else:
            return "Error: Could not scrape the product."
    else:
        return "Error: Only POST requests are allowed for this route."

@app.route('/scrape_bulk_products', methods=['POST'])
def scrape_bulk_products():
    if request.method == 'POST':
        if 'excelFile' not in request.files:
            return "Error: No file part"

        file = request.files['excelFile']

        if file.filename == '':
            return "Error: No selected file"

        if file:
            try:
                df = pd.read_excel(file)
                asins = df['ASINS'].tolist()  # Assuming column name is "ASINS"
                products = []

                for asin in asins:
                    product_data = get_amazon_product(asin)
                    if product_data:
                        products.append(product_data)

                return render_template('index.html', products=products)  # Pass the list of products

            except Exception as e:
                print(f"Error processing file: {e}")
                return f"Error: Could not process the file - {str(e)}"

    return "Error: Only POST requests are allowed for this route."

@app.route('/download_excel', methods=['POST'])
def download_excel():
    try:
        # Get the product data from the form
        product_data_json = request.form.get('product')

        # Parse the JSON data
        product_data = json.loads(product_data_json)

        # Convert to DataFrame
        df = pd.DataFrame([product_data])

        # Rearrange columns in the desired order
        column_order = [
            "Timestamp",
            "ASIN",
            "Title",
            "Description",
            "Bullet Points",
            "Current Price",
            "Original Price (MRP)",
            "Discount Percentage",
            "Delivery Date Raw",
            "Delivery Date Parsed",
            "URL"
        ]

        # Make sure all columns in the order list exist in the DataFrame
        # and keep any extra columns that might be in the data but not in our order list
        existing_columns = [col for col in column_order if col in df.columns]
        extra_columns = [col for col in df.columns if col not in column_order]
        final_column_order = existing_columns + extra_columns

        # Reorder the DataFrame columns
        df = df[final_column_order]

        # Create an in-memory Excel file
        excel_buffer = io.BytesIO()

        # Use ExcelWriter for more control
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Product Data')

        # Important: Move pointer to beginning of buffer
        excel_buffer.seek(0)

        # Set the appropriate headers for file download
        filename = f"amazon_product_{product_data['ASIN']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

        return send_file(
            excel_buffer,
            download_name=filename,
            as_attachment=True,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    except json.JSONDecodeError as e:
        print(f"JSON decode error: {e}")
        return f"Error: Invalid JSON data - {str(e)}"
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error in download_excel: {e}")
        return f"Error processing the request: {str(e)}"

if __name__ == '__main__':
    app.run(debug=True)