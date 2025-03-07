from flask import Flask, render_template, request, send_file, session, jsonify
import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
import re
from datetime import datetime
import io
import json
import html
import time
import random
import logging
from requests.exceptions import RequestException
import traceback

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("amazon_scraper_app.log"),
        logging.StreamHandler()
    ]
)

app = Flask(__name__)
app.secret_key = "ecombuddha_secret_key_change_in_production"  # Change this in production
app.config['SESSION_TYPE'] = 'filesystem'
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Limit file upload size to 16MB

# Create logs directory if it doesn't exist
if not os.path.exists('logs'):
    os.makedirs('logs')

# Create debug_html directory if it doesn't exist
if not os.path.exists('debug_html'):
    os.makedirs('debug_html')

class AmazonScraper:
    def __init__(self, country="in"):
        self.country = country
        self.base_url = f"https://www.amazon.{country}"
        self.session = requests.Session()
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0'
        ]

    def _get_random_user_agent(self):
        return random.choice(self.user_agents)

    def _make_request(self, url, max_retries=3, delay=2):
        """Make a request with retries and random delays"""
        headers = {
            "User-Agent": self._get_random_user_agent(),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://www.google.com/",
            "sec-ch-ua": '"Not A(Brand";v="99", "Google Chrome";v="120", "Chromium";v="120"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "cross-site",
            "sec-fetch-user": "?1",
            "upgrade-insecure-requests": "1"
        }

        for attempt in range(max_retries):
            try:
                # Add random delay between requests
                time.sleep(random.uniform(delay, delay * 2))

                response = self.session.get(
                    url,
                    headers=headers,
                    timeout=15
                )

                # Check if response contains captcha challenge
                if "captcha" in response.text.lower() or response.status_code == 503:
                    logging.warning(f"CAPTCHA detected or service unavailable (503). Attempt {attempt+1}/{max_retries}")
                    time.sleep(delay * 5)  # Longer delay when CAPTCHA is detected
                    continue

                if response.status_code != 200:
                    logging.warning(f"Request failed with status code {response.status_code}. Attempt {attempt+1}/{max_retries}")
                    time.sleep(delay * 2)
                    continue

                return response

            except RequestException as e:
                logging.error(f"Request error on attempt {attempt+1}/{max_retries}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(delay * 3)

        return None

    def get_product(self, asin):
        """Scrape Amazon product details by ASIN"""
        url = f"{self.base_url}/dp/{asin}"
        logging.info(f"Scraping product with ASIN: {asin}")

        response = self._make_request(url)
        if not response:
            logging.error(f"Failed to retrieve product page for ASIN: {asin}")
            return None

        # Save HTML for debugging if needed
        with open(f"debug_html/amazon_{asin}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html", "w", encoding="utf-8") as f:
            f.write(response.text)

        soup = BeautifulSoup(response.text, "html.parser")

        # Extract product data with improved selectors
        product_data = {
            "ASIN": asin,
            "URL": url,
            "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        # Extract product title - new selectors based on latest Amazon HTML structure
        product_data["Title"] = self._extract_title(soup)

        # Extract prices - current and original
        price_data = self._extract_prices(soup)
        product_data.update(price_data)

        # Extract bullet points
        bullet_points = self._extract_bullet_points(soup)
        product_data["Bullet Points"] = "\n".join(bullet_points) if bullet_points else "N/A"

        # Add individual bullet points
        for i, bullet in enumerate(bullet_points, 1):
            if i <= 10:  # Limit to 10 bullet points to avoid too many columns
                product_data[f"Bullet Point {i}"] = bullet

        # Extract delivery information
        delivery_data = self._extract_delivery_info(soup)
        product_data.update(delivery_data)

        # Extract description
        product_data["Description"] = self._extract_description(soup)

        # Extract technical details and product information
        tech_details = self._extract_technical_details(soup)
        product_data.update(tech_details)

        return product_data

    def _extract_title(self, soup):
        """Extract product title with multiple fallback selectors"""
        title_selectors = [
            "#productTitle",
            "#title span",
            ".product-title-word-break",
            "h1.a-size-large",
            "h1 span#productTitle",
            "#centerCol h1 span",
            "#title h1 span"
        ]

        for selector in title_selectors:
            title_element = soup.select_one(selector)
            if title_element and title_element.get_text(strip=True):
                return title_element.get_text(strip=True)

        logging.warning("Failed to extract product title")
        return "N/A"

    def _extract_prices(self, soup):
        """Extract current and original prices with improved selectors"""
        price_data = {
            "Current Price": "N/A",
            "Original Price (MRP)": "N/A",
            "Discount Percentage": "N/A"
        }

        # Current price selectors (updated for latest Amazon HTML)
        current_price_selectors = [
            ".priceToPay span.a-offscreen",
            ".a-price:not(.a-text-price) .a-offscreen",
            "#corePrice_feature_div .a-price .a-offscreen",
            "#priceblock_ourprice",
            "#priceblock_dealprice",
            ".apexPriceToPay .a-offscreen",
            "#corePriceDisplay_desktop_feature_div .a-price:not(.a-text-price) .a-offscreen",
            "#apex_desktop .a-price .a-offscreen",
            "span.a-price-whole"  # Legacy selector from original code
        ]

        current_price_value = 0
        for selector in current_price_selectors:
            element = soup.select_one(selector)
            if element and element.get_text(strip=True):
                current_price = element.get_text(strip=True)

                # Handle the special case for a-price-whole + a-price-fraction
                if selector == "span.a-price-whole":
                    price_fraction_element = soup.select_one("span.a-price-fraction")
                    price_fraction = price_fraction_element.get_text(strip=True) if price_fraction_element else "00"
                    current_price = f"₹{current_price}.{price_fraction}"

                price_data["Current Price"] = current_price

                # Extract numeric value
                numeric_price = re.sub(r'[^\d.]', '', current_price)
                try:
                    current_price_value = float(numeric_price)
                    break
                except ValueError:
                    continue

        # Original price / MRP selectors
        original_price_selectors = [
            "span.a-price.a-text-price span.a-offscreen",
            ".a-price.a-text-price:not(.a-no-hover) span.a-offscreen",
            ".a-text-price .a-offscreen",
            "#listPrice",
            "#priceBlockStrikePriceString",
            ".priceBlockStrikePriceString",
            "#corePriceDisplay_desktop_feature_div .a-price.a-text-price .a-offscreen",
            "#apex_desktop .a-price.a-text-price .a-offscreen"
        ]

        original_price_value = 0
        for selector in original_price_selectors:
            element = soup.select_one(selector)
            if element and element.get_text(strip=True):
                original_price = element.get_text(strip=True)
                price_data["Original Price (MRP)"] = original_price

                # Extract numeric value
                numeric_price = re.sub(r'[^\d.]', '', original_price)
                try:
                    original_price_value = float(numeric_price)
                    break
                except ValueError:
                    continue

        # Calculate discount percentage
        if original_price_value > 0 and current_price_value > 0 and original_price_value > current_price_value:
            discount = ((original_price_value - current_price_value) / original_price_value) * 100
            price_data["Discount Percentage"] = f"{discount:.1f}%"

        return price_data

    def _extract_bullet_points(self, soup):
        """Extract product bullet points from various possible locations"""
        bullet_selectors = [
            "#feature-bullets ul li:not(.aok-hidden) span.a-list-item",
            "#feature-bullets ul li",
            ".a-unordered-list .a-list-item",
            "#feature-bullets span.a-list-item",
            "#buybox_feature_div .a-section li"
        ]

        all_bullets = []
        for selector in bullet_selectors:
            bullets = soup.select(selector)
            if bullets:
                bullet_texts = [b.get_text(strip=True) for b in bullets if b.get_text(strip=True)]
                if bullet_texts:
                    all_bullets = bullet_texts
                    break

        return all_bullets

    def _extract_delivery_info(self, soup):
        """Extract delivery information with improved parsing"""
        delivery_data = {
            "Delivery Date Raw": "N/A",
            "Delivery Date Parsed": "N/A"
        }

        delivery_selectors = [
            "#mir-layout-DELIVERY_BLOCK-slot-PRIMARY_DELIVERY_MESSAGE_LARGE",
            "#deliveryBlockMessage",
            ".a-color-success.a-text-bold",
            "#delivery-message",
            ".deliveryMessageMedium",
            "#mir-layout-DELIVERY_BLOCK .a-box-inner",
            "#ddmDeliveryMessage",
            "#amazonGlobal_feature_div"
        ]

        for selector in delivery_selectors:
            element = soup.select_one(selector)
            if element and element.get_text(strip=True):
                delivery_raw = element.get_text(strip=True)
                delivery_data["Delivery Date Raw"] = delivery_raw
                delivery_data["Delivery Date Parsed"] = self._parse_delivery_date(delivery_raw)
                break

        return delivery_data

    def _parse_delivery_date(self, delivery_text):
        """Parse delivery text into a standardized date format with improved patterns"""
        if delivery_text == "N/A":
            return "N/A"

        # Common patterns in Amazon delivery texts
        date_patterns = [
            r'Delivery by (\w+ \d+ - \w+ \d+)',         # "Delivery by Monday, Mar 4 - Wednesday, Mar 6"
            r'Delivery by (\w+, \w+ \d+)',              # "Delivery by Monday, Mar 4"
            r'Get it by (\w+, \w+ \d+)',                # "Get it by Monday, Mar 4"
            r'Delivery (\w+, \w+ \d+)',                 # "Delivery Monday, Mar 4"
            r'(\d{1,2} \w+ - \d{1,2} \w+)',             # "4 March - 6 March"
            r'(\d{1,2}-\d{1,2} \w+)',                   # "4-6 March"
            r'Arrives: (\w+, \w+ \d+)',                 # "Arrives: Monday, Mar 4"
            r'delivery between (\w+ \d+ - \w+ \d+)',    # "delivery between Mar 4 - Mar 6"
            r'delivery: (\w+, \w+ \d+)'                 # "delivery: Monday, Mar 4"
        ]

        for pattern in date_patterns:
            match = re.search(pattern, delivery_text, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        # If no pattern matches but contains delivery-related keywords, attempt to extract date portions
        delivery_keywords = ["delivery", "delivered", "arrive", "get it", "by", "between", "shipped"]
        if any(keyword in delivery_text.lower() for keyword in delivery_keywords):
            # Try to extract date-like parts
            date_parts = re.findall(r'(\d{1,2} \w+|\w+ \d{1,2}|\d{1,2}-\d{1,2} \w+|\w+ \d{1,2} - \w+ \d{1,2})', delivery_text)
            if date_parts:
                return date_parts[0].strip()

        return "Unable to parse date"

    def _extract_description(self, soup):
        """Extract product description from various possible locations"""
        description_selectors = [
            "#productDescription p",
            "#productDescription",
            "#feature-bullets",
            "#aplus",
            ".a-expander-content p",
            "#dpx-aplus-product-description_feature_div",
            "#productDetails_feature_div",
            "#detailBullets_feature_div"
        ]

        for selector in description_selectors:
            element = soup.select_one(selector)
            if element and element.get_text(strip=True):
                return element.get_text(strip=True)[:1000]  # Limit description length

        return "N/A"

    def _extract_technical_details(self, soup):
        """Extract technical details and product information with improved selectors"""
        tech_data = {}

        # Common table selectors that contain product details
        table_selectors = [
            "#productDetails_techSpec_section_1",
            "#productDetails_techSpec_section_2",
            "#productDetails_detailBullets_sections1",
            "#detailBulletsWrapper_feature_div",
            ".detail-bullets-wrapper",
            ".prodDetTable",
            ".a-keyvalue"
        ]

        # Process detail bullets style
        detail_bullets = soup.select("#detailBullets_feature_div li .a-list-item, #detailBulletsWrapper_feature_div li .a-list-item")
        for item in detail_bullets:
            text = item.get_text(strip=True)
            if ":" in text:
                key, value = [part.strip() for part in text.split(":", 1)]
                # Clean up the key name for better column headers
                clean_key = re.sub(r'[^a-zA-Z0-9 ]', '', key)
                clean_key = clean_key.strip().replace(' ', '_')
                tech_data[f"Tech_{clean_key}"] = value

        # Process all potential table formats
        for selector in table_selectors:
            # Try to find the table
            table = soup.select_one(selector)
            if not table:
                continue

            # Process rows in the table
            rows = table.select("tr") or table.select(".a-spacing-small")
            for row in rows:
                # Try different selector combinations for header/key and value
                header = row.select_one("th, .prodDetSectionEntry, .a-span3, .a-color-secondary")
                value_cell = row.select_one("td, .prodDetAttrValue, .a-span9, .a-span7")

                if header and value_cell:
                    key = header.get_text(strip=True)
                    value = value_cell.get_text(strip=True)

                    # Clean up the key name
                    clean_key = re.sub(r'[^a-zA-Z0-9 ]', '', key)
                    clean_key = clean_key.strip().replace(' ', '_')

                    # Use a consistent prefix for all technical details
                    tech_data[f"Tech_{clean_key}"] = value

        # Additional format often used for ASIN, product dimensions, etc.
        detail_sections = soup.select("#detailBulletsWrapper_feature_div .a-section")
        for section in detail_sections:
            section_title = section.select_one("h3")
            if section_title:
                section_name = section_title.get_text(strip=True)
                items = section.select("li span")

                for item in items:
                    text = item.get_text(strip=True)
                    if ":" in text:
                        key, value = [part.strip() for part in text.split(":", 1)]
                        # Use the section name as part of the key
                        section_prefix = re.sub(r'[^a-zA-Z0-9 ]', '', section_name)
                        section_prefix = section_prefix.strip().replace(' ', '_')
                        clean_key = re.sub(r'[^a-zA-Z0-9 ]', '', key)
                        clean_key = clean_key.strip().replace(' ', '_')
                        tech_data[f"Tech_{section_prefix}_{clean_key}"] = value

        # Also try the newer "About this item" format that's in tables
        about_tables = soup.select(".a-section table.a-keyvalue")
        for table in about_tables:
            rows = table.select("tr")
            for row in rows:
                cells = row.select("th, td")
                if len(cells) >= 2:
                    key = cells[0].get_text(strip=True)
                    value = cells[1].get_text(strip=True)
                    if key and value:
                        clean_key = re.sub(r'[^a-zA-Z0-9 ]', '', key)
                        clean_key = clean_key.strip().replace(' ', '_')
                        tech_data[f"Tech_{clean_key}"] = value

        # Log technical details to help troubleshoot
        if tech_data:
            logging.info(f"Extracted {len(tech_data)} technical details")
        else:
            logging.warning("No technical details found")

        return tech_data

# Initialize Amazon scraper
amazon_scraper = AmazonScraper(country="in")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/scrape_single_product', methods=['POST'])
def scrape_single_product():
    if request.method == 'POST':
        try:
            asin = request.form.get('asin', '').strip()

            if not asin:
                return render_template("index.html", error="Please enter a valid ASIN")

            # Log the scraping attempt
            logging.info(f"Scrape request for ASIN: {asin}")

            # Get product data using improved scraper
            product_data = amazon_scraper.get_product(asin)

            if product_data:
                # Store product data in session
                session['products'] = [product_data]
                # Pass product_data to the template
                return render_template("index.html", products=[product_data])
            else:
                return render_template("index.html", error=f"Could not scrape product with ASIN: {asin}")

        except Exception as e:
            logging.error(f"Error in scrape_single_product: {str(e)}")
            logging.error(traceback.format_exc())
            return render_template("index.html", error=f"An error occurred: {str(e)}")
    else:
        return render_template("index.html", error="Only POST requests are allowed for this route")

@app.route('/scrape_bulk_products', methods=['POST'])
def scrape_bulk_products():
    if request.method == 'POST':
        try:
            if 'excelFile' not in request.files:
                return render_template("index.html", error="No file part")

            file = request.files['excelFile']

            if file.filename == '':
                return render_template("index.html", error="No selected file")

            if not file.filename.endswith(('.xls', '.xlsx')):
                return render_template("index.html", error="Invalid file format. Please upload an Excel file (.xls or .xlsx)")

            # Read the Excel file
            try:
                df = pd.read_excel(file)
            except Exception as e:
                logging.error(f"Error reading Excel file: {str(e)}")
                return render_template("index.html", error=f"Error reading Excel file: {str(e)}")

            # Check if the expected column exists
            if 'ASINS' not in df.columns:
                possible_columns = [col for col in df.columns if 'asin' in col.lower()]

                if possible_columns:
                    asin_column = possible_columns[0]
                    logging.info(f"Using alternative column for ASINs: {asin_column}")
                else:
                    return render_template("index.html", error="Excel file must contain a column named 'ASINS'")
            else:
                asin_column = 'ASINS'

            # Extract ASINs, remove duplicates, and clean
            asins = df[asin_column].dropna().astype(str).tolist()
            asins = [asin.strip() for asin in asins if asin.strip()]
            asins = list(dict.fromkeys(asins))  # Remove duplicates while preserving order

            if not asins:
                return render_template("index.html", error="No valid ASINs found in the file")

            logging.info(f"Bulk scraping {len(asins)} ASINs")

            # Set a reasonable limit to avoid overwhelming the server
            max_asins = 100
            if len(asins) > max_asins:
                asins = asins[:max_asins]
                logging.warning(f"Limited bulk scraping to {max_asins} ASINs")

            products = []
            success_count = 0
            failed_count = 0

            # Process each ASIN with a delay between requests
            for i, asin in enumerate(asins):
                try:
                    # Add delay between requests to avoid getting blocked
                    if i > 0:
                        delay = random.uniform(2, 5)
                        time.sleep(delay)

                    product_data = amazon_scraper.get_product(asin)
                    if product_data:
                        products.append(product_data)
                        success_count += 1
                        logging.info(f"Successfully scraped {asin} ({success_count}/{len(asins)})")
                    else:
                        failed_count += 1
                        logging.warning(f"Failed to scrape {asin} ({failed_count} failures)")
                except Exception as e:
                    failed_count += 1
                    logging.error(f"Error scraping {asin}: {str(e)}")

            # Store products in session
            session['products'] = products

            if products:
                return render_template('index.html', products=products, success_count=success_count, failed_count=failed_count)
            else:
                return render_template("index.html", error="Failed to scrape any products")

        except Exception as e:
            logging.error(f"Error in scrape_bulk_products: {str(e)}")
            logging.error(traceback.format_exc())
            return render_template("index.html", error=f"An error occurred: {str(e)}")
    else:
        return render_template("index.html", error="Only POST requests are allowed for this route")

def remove_control_characters(s):
    """Remove control characters from string"""
    return re.sub(r'[\x00-\x1F\x7F-\x9F]', '', s)

@app.route('/download_excel', methods=['POST'])
def download_excel():
    try:
        # Get the list of products from the session
        products = session.get('products', [])

        if not products:
            # If no products in session, check if any were passed in the form
            if 'products' in request.form:
                try:
                    products_json = request.form.get('products')
                    products_json = html.unescape(products_json)
                    products_json = remove_control_characters(products_json)
                    products = json.loads(products_json)
                except json.JSONDecodeError as e:
                    logging.error(f"JSON Decode Error: {str(e)}")
                    return render_template("index.html", error=f"Error processing JSON data: {str(e)}")

        # Make sure we have a list of products, even if only one product is passed
        if not isinstance(products, list):
            products = [products]

        if products:
            # Log technical details keys for debugging
            for product in products:
                tech_keys = [k for k in product.keys() if k.startswith('Tech_')]
                if tech_keys:
                    logging.info(f"Technical details found for ASIN {product.get('ASIN', 'Unknown')}: {tech_keys}")
                else:
                    logging.warning(f"No technical details found for ASIN {product.get('ASIN', 'Unknown')}")

            # Convert to DataFrame
            df = pd.DataFrame(products)

            # Find bullet point columns
            bullet_point_cols = [col for col in df.columns if col.startswith('Bullet Point ')]

            # Determine technical and product detail columns
            tech_detail_cols = [col for col in df.columns if col.startswith('Tech_')]

            # Rearrange columns in the desired order
            column_order = [
                "Timestamp",
                "ASIN",
                "Title",
                "Description",
            ]

            # Add bullet point columns in order
            sorted_bullet_cols = sorted(bullet_point_cols,
                                       key=lambda x: int(x.split(' ')[-1]) if x.split(' ')[-1].isdigit() else 0)
            column_order.extend(sorted_bullet_cols)

            # Add the original combined bullet points at the end
            column_order.append("Bullet Points")

            # Continue with other standard columns
            column_order.extend([
                "Current Price",
                "Original Price (MRP)",
                "Discount Percentage",
                "Delivery Date Raw",
                "Delivery Date Parsed",
            ])

            # Add technical detail columns
            column_order.extend(sorted(tech_detail_cols))

            # Finish with URL
            column_order.append("URL")

            # Make sure all columns in the order list exist in the DataFrame
            existing_columns = [col for col in column_order if col in df.columns]
            extra_columns = [col for col in df.columns if col not in column_order]
            final_column_order = existing_columns + extra_columns

            # Reorder the DataFrame columns
            df = df[final_column_order]
        else:
            # Create an empty DataFrame with the basic column order
            df = pd.DataFrame(columns=[
                "Timestamp",
                "ASIN",
                "Title",
                "Description",
                "Bullet Point 1",
                "Bullet Point 2",
                "Bullet Point 3",
                "Bullet Point 4",
                "Bullet Point 5",
                "Bullet Points",
                "Current Price",
                "Original Price (MRP)",
                "Discount Percentage",
                "Delivery Date Raw",
                "Delivery Date Parsed",
                "URL"
            ])

        # Create an in-memory Excel file
        excel_buffer = io.BytesIO()

        # Use ExcelWriter for more control
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
             df.to_excel(writer, index=False, sheet_name='Product Data')

        # Important: Move pointer to beginning of buffer
        excel_buffer.seek(0)

        # Set the appropriate headers for file download
        filename = f"amazon_products_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return send_file(
            excel_buffer,
            download_name=filename,
            as_attachment=True,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    except Exception as e:
        logging.error(f"Error in download_excel: {str(e)}")
        logging.error(traceback.format_exc())
        return render_template("index.html", error=f"Error processing the download request: {str(e)}")

@app.route('/api/scrape', methods=['POST'])
def api_scrape():
    """API endpoint for scraping product data"""
    try:
        data = request.get_json()
        if not data or 'asin' not in data:
            return jsonify({"error": "No ASIN provided"}), 400

        asin = data['asin'].strip()
        if not asin:
            return jsonify({"error": "Empty ASIN provided"}), 400

        product_data = amazon_scraper.get_product(asin)
        if product_data:
            return jsonify({"success": True, "data": product_data})
        else:
            return jsonify({"success": False, "error": "Failed to scrape product"}), 404

    except Exception as e:
        logging.error(f"API error: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.errorhandler(413)
def request_entity_too_large(error):
    return render_template("index.html", error="File too large. Please upload a smaller file."), 413

@app.errorhandler(404)
def page_not_found(error):
    return render_template("index.html", error="Page not found"), 404

@app.errorhandler(500)
def internal_server_error(error):
    return render_template("index.html", error="Internal server error"), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)