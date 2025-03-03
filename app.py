from flask import Flask, render_template, request

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/scrape_single_product', methods=['POST'])
def scrape_single_product():
    if request.method == 'POST':
        asin = request.form['asin']  # Access the ASIN value from the form
        # Now you can use the 'asin' variable to perform the scraping
        # (Replace this with your actual scraping code)
        result = f"Scraping product with ASIN: {asin}"
        return result  # Or render a template with the result

    else:
        return "Error: Only POST requests are allowed for this route."

if __name__ == '__main__':
    app.run(debug=True)