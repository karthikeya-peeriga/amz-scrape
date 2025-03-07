from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import time, json

# Setup Chrome Options
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--disable-blink-features=AutomationControlled")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--log-level=3")

# Initialize WebDriver
service = Service("chromedriver.exe")  # Ensure chromedriver.exe is in your project folder
driver = webdriver.Chrome(service=service, options=chrome_options)

def scrape_amazon_product(asin, country_code="com"):
    url = f"https://www.amazon.{country_code}/dp/{asin}"
    driver.get(url)
    time.sleep(5)  # Allow JavaScript to load

    soup = BeautifulSoup(driver.page_source, "html.parser")

    product_details = {
        "asin": asin,
        "title": None,
        "brand": None,
        "manufacturer": None,
        "price": None,
        "original_price": None,
        "currency": None,
        "discount": None,
        "availability": None,
        "seller": None,
        "shipping_info": None,
        "features": [],
        "description": None,
        "main_image": None,
        "additional_images": [],
        "tech_details": {},
        "best_seller_rank": None,
        "category": None,
        "variations": [],
        "customer_qa_count": None,
        "customer_qa": [],
        "reviews_breakdown": {},
        "review_sentiments": {"positive": [], "negative": []},
        "videos": [],
        "similar_products": [],
        "frequently_bought_together": [],
        "upc_ean": None,
        "model_number": None,
        "warranty": None,
        "return_policy": None,
        "badges": None,
        "documents": []
    }

    # Extract Title
    title = soup.find("span", id="productTitle")
    product_details["title"] = title.text.strip() if title else None

    # Extract Brand
    brand = soup.find("a", id="bylineInfo")
    product_details["brand"] = brand.text.strip() if brand else None

    # Extract Manufacturer
    manufacturer = soup.find("table", id="productDetails_techSpec_section_1")
    if manufacturer:
        for row in manufacturer.find_all("tr"):
            if "Manufacturer" in row.text:
                product_details["manufacturer"] = row.find("td").text.strip()

    # Extract Prices
    price_whole = soup.find("span", class_="a-price-whole")
    price_fraction = soup.find("span", class_="a-price-fraction")
    currency_symbol = soup.find("span", class_="a-price-symbol")
    original_price = soup.find("span", class_="priceBlockStrikePriceString")
    
    if price_whole and price_fraction:
        product_details["price"] = f"{price_whole.text.strip()}.{price_fraction.text.strip()}"
    product_details["currency"] = currency_symbol.text.strip() if currency_symbol else None
    product_details["original_price"] = original_price.text.strip() if original_price else None

    # Extract Discount
    if product_details["original_price"] and product_details["price"]:
        product_details["discount"] = f"{round((1 - (float(product_details['price']) / float(product_details['original_price']))) * 100, 2)}% OFF"

    # Extract Availability
    availability = soup.find("div", id="availability")
    product_details["availability"] = availability.text.strip() if availability else None

    # Extract Seller
    seller = soup.find("a", id="sellerProfileTriggerId")
    product_details["seller"] = seller.text.strip() if seller else None

    # Extract Shipping Info
    shipping_info = soup.find("div", id="mir-layout-DELIVERY_BLOCK-slot-PRIMARY_DELIVERY_MESSAGE_LARGE")
    product_details["shipping_info"] = shipping_info.text.strip() if shipping_info else None

    # Extract Features (Bullet Points)
    features = soup.find_all("span", class_="a-list-item")
    product_details["features"] = [feature.text.strip() for feature in features if feature.text.strip()]

    # Extract Full Product Description
    description = soup.find("div", id="productDescription")
    product_details["description"] = description.text.strip() if description else None

    # Extract Main Image
    main_image = soup.find("img", id="landingImage")
    product_details["main_image"] = main_image["src"] if main_image else None

    # Extract Additional Images
    img_elements = soup.find_all("img", class_="a-dynamic-image")
    product_details["additional_images"] = list(set(img["src"] for img in img_elements if "src" in img.attrs))

    # Extract Best Seller Rank & Category
    best_seller_rank = soup.find("span", class_="zg_hrsr_rank")
    product_details["best_seller_rank"] = best_seller_rank.text.strip() if best_seller_rank else None

    category = soup.find("span", class_="nav-a-content")
    product_details["category"] = category.text.strip() if category else None

    # Extract Customer Q&A Count
    customer_qa = soup.find("a", id="askATFLink")
    product_details["customer_qa_count"] = customer_qa.text.strip() if customer_qa else None

    # Extract Review Breakdown
    for i in range(1, 6):
        review_tag = soup.find("span", class_=f"a-size-base a-nowrap", string=lambda x: x and f"{i} star" in x)
        if review_tag:
            review_count = review_tag.find_next("span").text.strip()
            product_details["reviews_breakdown"][f"{i} stars"] = review_count

    # Extract Videos
    videos = soup.find_all("video", class_="a-dynamic-image")
    product_details["videos"] = [video["src"] for video in videos if "src" in video.attrs]

    # Extract Frequently Bought Together Items
    bought_together = soup.find("div", id="sims-fbt")
    if bought_together:
        products = bought_together.find_all("img")
        product_details["frequently_bought_together"] = [img["alt"] for img in products if "alt" in img.attrs]

    # Extract UPC/EAN
    upc_ean = soup.find("td", string="UPC") or soup.find("td", string="EAN")
    product_details["upc_ean"] = upc_ean.find_next("td").text.strip() if upc_ean else None

    return product_details

# Run the scraper
asin = "B0C9WHSZZN"  # Replace with actual ASIN
data = scrape_amazon_product(asin)
print(json.dumps(data, indent=4))

driver.quit()
