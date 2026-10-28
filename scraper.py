import requests
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime
import time

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'lv,en;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
}

TARGET_SKATES = [
    # Bauer Vapor FLY40
    {
        "model": "bauer-vapor-fly40",
        "retailer": "hp",
        "url": "https://hokejapasaule.lv/lv_lv/bauer-vapor-s25-fly40-senior-hokeja-slidas",
        "default_sizes": ["7", "7.5"],
        "default_fits": ["FIT 2"],
        "shipping": 3.5
    },
    {
        "model": "bauer-vapor-fly40",
        "retailer": "hj",
        "url": "https://www.hokejam.lv/lv/meklesana?search=FLY40",
        "default_sizes": ["7", "7.5"],
        "default_fits": ["FIT 2"],
        "shipping": 0.0
    },
    {
        "model": "bauer-vapor-fly40",
        "retailer": "sp",
        "url": "https://www.sportega.lv/hokeja-slidas-bauer-vapor-fly40-senior/d1502757",
        "default_sizes": ["7", "7.5"],
        "default_fits": ["FIT 2"],
        "shipping": 4.0
    },
    # Bauer Supreme F40
    {
        "model": "bauer-supreme-f40",
        "retailer": "hp",
        "url": "https://hokejapasaule.lv/lv_lv/bauer-supreme-s26-f40-senior-hokeja-slidas",
        "default_sizes": ["7", "7.5"],
        "default_fits": ["FIT 2"],
        "shipping": 3.5
    },
    {
        "model": "bauer-supreme-f40",
        "retailer": "hj",
        "url": "https://www.hokejam.lv/lv/pieauguso-hokeja-slidas/5455-bauer-supreme-s26-f40-pieauguso-hokeja-slidas",
        "default_sizes": ["7", "7.5"],
        "default_fits": ["FIT 2"],
        "shipping": 0.0
    },
    {
        "model": "bauer-supreme-f40",
        "retailer": "sp",
        "url": "https://www.sportega.lv/hladat?q=Supreme+F40",
        "default_sizes": ["7", "7.5"],
        "default_fits": ["FIT 3"],
        "shipping": 4.0
    },
    # Bauer Supreme M40
    {
        "model": "bauer-supreme-m40",
        "retailer": "hp",
        "url": "https://hokejapasaule.lv/lv_lv/bauer-supreme-s24-m40-senior-hokeja-slidas",
        "default_sizes": ["7.5"],
        "default_fits": ["FIT 2"],
        "shipping": 3.5
    },
    {
        "model": "bauer-supreme-m40",
        "retailer": "hj",
        "url": "https://www.hokejam.lv/lv/pieauguso-hokeja-slidas/4507-bauer-supreme-m40-pieauguso-hokeja-slidas",
        "default_sizes": ["7", "7.5"],
        "default_fits": ["FIT 2"],
        "shipping": 0.0
    },
    {
        "model": "bauer-supreme-m40",
        "retailer": "sp",
        "url": "https://www.sportega.lv/hladat?q=Supreme+M40",
        "default_sizes": ["8"],
        "default_fits": ["FIT 2"],
        "shipping": 4.0
    }
]

def parse_hokejapasaule(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=12)
        if resp.status_code != 200:
            return None, None, False
        soup = BeautifulSoup(resp.text, 'html.parser')

        # 1. Cenas meklēšana Schema.org datos
        for s in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(s.string or '')
                if isinstance(data, list):
                    data = data[0]
                if data.get('@type') == 'Product' or 'offers' in data:
                    offers = data.get('offers', {})
                    if isinstance(offers, list):
                        offers = offers[0]
                    p = offers.get('price')
                    if p:
                        avail = str(offers.get('availability', '')).lower()
                        in_stock = 'instock' in avail
                        return float(p), None, in_stock
            except Exception:
                continue

        # 2. Rezerves meklēšana HTML celtnē
        price_el = soup.select_one('[data-price-type="finalPrice"] .price, .special-price .price, .price-final_price .price')
        price = None
        if price_el:
            digits = re.findall(r'\d+(?:[.,]\d+)?', price_el.text)
            if digits:
                price = float(digits[0].replace(',', '.'))

        old_el = soup.select_one('.old-price .price')
        old_price = None
        if old_el:
            digits = re.findall(r'\d+(?:[.,]\d+)?', old_el.text)
            if digits:
                old_price = float(digits[0].replace(',', '.'))

        in_stock = bool(soup.select_one('#product-addtocart-button, .stock.available'))
        return price, old_price, in_stock
    except Exception as e:
        print(f"Kļūda HP lapā: {e}")
        return None, None, False

def parse_hokejam(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=12)
        if resp.status_code != 200:
            return None, None, False
        soup = BeautifulSoup(resp.text, 'html.parser')

        price_el = soup.select_one('.current-price [itemprop="price"], .current-price-value, .product-price')
        price = None
        if price_el:
            val = price_el.get('content') or price_el.text
            digits = re.findall(r'\d+(?:[.,]\d+)?', val)
            if digits:
                price = float(digits[0].replace(',', '.'))

        old_el = soup.select_one('.regular-price, .old-price')
        old_price = None
        if old_el:
            digits = re.findall(r'\d+(?:[.,]\d+)?', old_el.text)
            if digits:
                old_price = float(digits[0].replace(',', '.'))

        cart_btn = soup.select_one('.add-to-cart, button[data-button-action="add-to-cart"]')
        in_stock = cart_btn is not None and not cart_btn.has_attr('disabled')
        return price, old_price, in_stock
    except Exception as e:
        print(f"Kļūda Hokejam.lv: {e}")
        return None, None, False

def parse_sportega(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=12)
        if resp.status_code != 200:
            return None, None, False
        soup = BeautifulSoup(resp.text, 'html.parser')

        for s in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(s.string or '')
                if isinstance(data, list):
                    data = data[0]
                if data.get('@type') == 'Product' or 'offers' in data:
                    offers = data.get('offers', {})
                    if isinstance(offers, list):
                        offers = offers[0]
                    p = offers.get('price')
                    if p:
                        avail = str(offers.get('availability', '')).lower()
                        in_stock = 'instock' in avail or 'preorder' in avail
                        return float(p), None, in_stock
            except Exception:
                continue

        p_match = re.search(r'(\d+[\d\s]*(?:[.,]\d{2})?)\s*€', soup.text)
        if p_match:
            clean = re.sub(r'[^\d.]', '', p_match.group(1).replace(',', '.'))
            if clean:
                return float(clean), None, True

        return None, None, False
    except Exception as e:
        print(f"Kļūda Sportega: {e}")
        return None, None, False

def scrape_all():
    print("Sākas hokeja slidu cenu skenēšana...")
    updated_offers = []

    for t in TARGET_SKATES:
        print(f"Pārbauda: {t['retailer'].upper()} -> {t['model']}")
        try:
            if t['retailer'] == 'hp':
                price, old_price, stock = parse_hokejapasaule(t['url'])
            elif t['retailer'] == 'hj':
                price, old_price, stock = parse_hokejam(t['url'])
            elif t['retailer'] == 'sp':
                price, old_price, stock = parse_sportega(t['url'])
            else:
                price, old_price, stock = None, None, False
        except Exception as e:
            print(f"Neapstrādāta kļūda pie {t['url']}: {e}")
            price, old_price, stock = None, None, False

        time.sleep(1)

        status = 'VERIFIED' if (price is not None and stock) else 'UNVERIFIED'

        offer = {
            "model": t["model"],
            "retailer": t["retailer"],
            "section": "new",
            "price": price if price is not None else 0.0,
            "oldPrice": old_price,
            "shipping": t["shipping"],
            "sizes": t["default_sizes"],
            "fits": t["default_fits"],
            "stock": stock,
            "checked": datetime.now().strftime("%Y-%m-%d"),
            "url": t["url"],
            "status": status
        }
        updated_offers.append(offer)

    payload = {
        "updatedAt": datetime.now().isoformat(),
        "offers": updated_offers
    }

    with open('scraped_data.json', 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print("Skenēšana pabeigta un scraped_data.json veiksmīgi atjaunināts.")

if __name__ == '__main__':
    scrape_all()
