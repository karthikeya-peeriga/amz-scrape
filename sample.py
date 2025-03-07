import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
from datetime import datetime
import time
import random
from requests.exceptions import RequestException
import logging
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("amazon_scraper.log"),
        logging.StreamHandler()
    ]
)

class AmazonScraper:
    def __init__(self, country="in", use_proxy=False, proxy_list=None):
        self.country = country
        self.base_url = f"https://www.amazon.{country}"
        self.use_proxy = use_proxy
        self.proxy_list = proxy_list
        self.session = requests.Session()
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0'
        ]
        
    def _get_random_user_agent(self):
        return random.choice(self.user_agents)
    
    def _get_random_proxy(self):
        if not self.use_proxy or not self.proxy_list:
            return None
        return random.choice(self.proxy_list)
    
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
        
        proxy = self._get_random_proxy()
        proxies = {"http": proxy, "https": proxy} if proxy else None
        
        for attempt in range(max_retries):
            try:
                # Add random delay between requests
                time.sleep(random.uniform(delay, delay * 2))
                
                response = self.session.get(
                    url, 
                    headers=headers, 
                    proxies=proxies, 
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
        debug_dir = "debug_html"
        if not os.path.exists(debug_dir):
            os.makedirs(debug_dir)
            
        with open(f"{debug_dir}/amazon_{asin}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html", "w", encoding="utf-8") as f:
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
        product_data["Bullet Points"] = self._extract_bullet_points(soup)
        
        # Extract delivery information
        delivery_data = self._extract_delivery_info(soup)
        product_data.update(delivery_data)
        
        # Extract description
        product_data["Description"] = self._extract_description(soup)
        
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
            "#apex_desktop .a-price .a-offscreen"
        ]
        
        current_price_value = 0
        for selector in current_price_selectors:
            element = soup.select_one(selector)
            if element and element.get_text(strip=True):
                current_price = element.get_text(strip=True)
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
        
        return "\n".join(all_bullets) if all_bullets else "N/A"
    
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
    
    def save_to_excel(self, product_data, filename="amazon_products.xlsx"):
        """Save product data to Excel file with error handling"""
        if not product_data:
            logging.error("No product data to save")
            return False
            
        try:
            df = pd.DataFrame([product_data])
            
            # Check if file exists, append if yes, create new if no
            if os.path.exists(filename):
                existing_df = pd.read_excel(filename)
                
                # Check if this ASIN is already in the file
                if product_data["ASIN"] in existing_df["ASIN"].values:
                    # Update the existing row
                    existing_df = existing_df[existing_df["ASIN"] != product_data["ASIN"]]
                    
                df = pd.concat([existing_df, df], ignore_index=True)
            
            df.to_excel(filename, index=False)
            logging.info(f"Data saved to {filename}")
            return True
            
        except Exception as e:
            logging.error(f"Error saving data to Excel: {e}")
            return False


# Example usage
if __name__ == "__main__":
    # Optional proxy setup
    proxies = [
        # Add proxies if needed, format: "http://user:pass@ip:port"
    ]
    
    # Initialize scraper
    scraper = AmazonScraper(country="in", use_proxy=False, proxy_list=proxies)
    
    # Test with a few ASINs
    asins = ["B0CGW18S6Y", "B09G9D8KRQ"]  # Add your ASINs here
    
    # Set delay between requests to avoid blocking
    delay_between_products = random.uniform(5, 10)
    
    successful = 0
    failed = 0
    
    for i, asin in enumerate(asins):
        if i > 0:
            logging.info(f"Waiting {delay_between_products:.2f} seconds before next request")
            time.sleep(delay_between_products)
            
        try:
            product_details = scraper.get_product(asin)
            if product_details:
                if scraper.save_to_excel(product_details):
                    successful += 1
                    logging.info(f"Successfully scraped ASIN: {asin}")
                else:
                    failed += 1
                    logging.error(f"Failed to save data for ASIN: {asin}")
            else:
                failed += 1
                logging.error(f"Failed to scrape ASIN: {asin}")
                
        except Exception as e:
            failed += 1
            logging.error(f"Error processing ASIN {asin}: {e}")
        
        # Vary delay for next request
        delay_between_products = random.uniform(5, 15)
    
    logging.info(f"Scraping complete. Successful: {successful}, Failed: {failed}")