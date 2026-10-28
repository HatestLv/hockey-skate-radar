import requests
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime
import time

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'lv-LV,lv;q=0.9,en-US;q=0.8,en;q=0.7',
    'Sec-Ch-Ua': '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
    'Sec-Ch-Ua-Mobile': '?0',
    'Sec-Ch-Ua-Platform': '"Windows"',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Upgrade-Insecure-Requests': '1'
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
        # Tiešā Sportega saite uz Supreme F40:
        "url": "https://www.sportega.lv/hokeja-slidas-bauer-supreme-f40-senior/d1583973",
        "default_sizes": ["7", "7.5"],
        "default_fits": ["FIT 2"],
        "shipping": 4.0
    },
    # Bauer Supreme M40
    {
        "model": "bauer-supreme-m40",
        "retailer": "hp",
        "url": "https://hokejapasaule.lv/lv_lv/bauer-supreme-s24-m40-senior-hokeja-slidas",
        "default_sizes": ["7", "7.5"],
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
        # Tiešā Sportega saite uz Supreme M40:
        "url": "https://www.sportega.lv/hokeja-slidas-bauer-supreme-m40-senior/d1438036",
        "default_sizes": ["7", "7.5", "8"],
        "default_fits": ["FIT 2"],
        "shipping": 4.0
    }
]

def parse_hokejapasaule(url, session):
    try:
        resp = session.get(url, timeout=14)
        if resp.status_code != 200:
            print(f"[HP] Statuss: {resp.status_code}")
            return None, None, False
        html = resp.text
        soup = BeautifulSoup(html, 'html.parser')

        price = None
        old_price = None

        # 1. Magento atribūts [data-price-amount]
        for el in soup.select('[data-price-amount]'):
            try:
                val = float(el['data-price-amount'])
                if 100 <= val <= 2500:
                    price = val
                    break
            except Exception:
                continue

        # 2. Schema.org JSON-LD meklēšana
        if not price:
            for s in soup.find_all('script', type='application/ld+json'):
                try:
                    data = json.loads(s.string or '')
                    items = data if isinstance(data, list) else [data]
                    for item in items:
                        if item.get('@type') == 'Product' or 'offers' in item:
                            offers = item.get('offers', {})
                            if isinstance(offers, list) and offers:
                                offers = offers[0]
                            p = offers.get('price') or offers.get('lowPrice')
                            if p:
                                val = float(str(p).replace(',', '.'))
                                if 100 <= val <= 2500:
                                    price = val
                                    break
                except Exception:
                    continue

        # 3. Meta tagi
        if not price:
            meta_p = soup.select_one('meta[property="product:price:amount"], meta[itemprop="price"]')
            if meta_p and meta_p.get('content'):
                try:
                    val = float(meta_p['content'].replace(',', '.'))
                    if 100 <= val <= 2500:
                        price = val
                except Exception:
                    pass

        # 4. Standarta cenu klases
        if not price:
            price_el = soup.select_one('.price-wrapper .price, [data-price-type="finalPrice"] .price, .special-price .price, .price-final_price .price, .product-info-price .price')
            if price_el:
                digits = re.findall(r'\d+(?:[.,]\d+)?', price_el.text)
                if digits:
                    val = float(digits[0].replace(',', '.'))
                    if 100 <= val <= 2500:
                        price = val

        # 5. Teksta regex glābšanas riņķis (100–2000 EUR)
        if not price:
            p_matches = re.findall(r'(\d{2,4}(?:[.,]\d{2})?)\s*(?:€|EUR)', html)
            valid = [float(p.replace(' ', '').replace(',', '.')) for p in p_matches if 100 <= float(p.replace(' ', '').replace(',', '.')) <= 2000]
            if valid:
                price = min(valid)
                if len(valid) > 1 and max(valid) > min(valid):
                    old_price = max(valid)

        # Vecās cenas pārbaude
        if not old_price:
            old_el = soup.select_one('.old-price [data-price-amount], .old-price .price')
            if old_el:
                if old_el.has_attr('data-price-amount'):
                    old_price = float(old_el['data-price-amount'])
                else:
                    digits = re.findall(r'\d+(?:[.,]\d+)?', old_el.text)
                    if digits:
                        old_price = float(digits[0].replace(',', '.'))

        # Pieejamības noteikšana
        in_stock = bool(soup.select_one('#product-addtocart-button, .stock.available'))
        if not in_stock and price:
            in_stock = bool(re.search(r'Ir noliktavā|Ielikt grozā|Pārbaudiet Preču', html, re.IGNORECASE))

        return price, old_price, in_stock
    except Exception as e:
        print(f"[HP] Kļūda: {e}")
        return None, None, False

def parse_hokejam(url, session):
    try:
        resp = session.get(url, timeout=14)
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
        print(f"[Hokejam] Kļūda: {e}")
        return None, None, False

def parse_sportega(url, session):
    try:
        resp = session.get(url, timeout=14)
        if resp.status_code != 200:
            print(f"[Sportega] Statuss: {resp.status_code}")
            return None, None, False
        html = resp.text

        # 1. Rekursīvs JSON-LD
        for s in re.finditer(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.DOTALL | re.IGNORECASE):
            try:
                raw_data = json.loads(s.group(1).strip())
                def find_offer(obj):
                    if isinstance(obj, list):
                        for el in obj:
                            res = find_offer(el)
                            if res: return res
                    elif isinstance(obj, dict):
                        if '@graph' in obj:
                            return find_offer(obj['@graph'])
                        if obj.get('@type') == 'Product' or 'offers' in obj:
                            offers = obj.get('offers', {})
                            if isinstance(offers, list) and offers:
                                offers = offers[0]
                            if isinstance(offers, dict):
                                p = offers.get('price') or offers.get('lowPrice')
                                if p:
                                    avail = str(offers.get('availability', '')).lower()
                                    return float(str(p).replace(',', '.')), ('instock' in avail or 'preorder' in avail)
                    return None

                res = find_offer(raw_data)
                if res and res[0] >= 100:
                    return res[0], None, res[1]
            except Exception:
                continue

        # 2. Meta itemprop="price"
        meta_match = re.search(r'<meta[^>]+(?:itemprop=["\']price["\']|property=["\']product:price:amount["\'])[^>]+content=["\']([\d.,]+)["\']', html, re.IGNORECASE)
        if not meta_match:
            meta_match = re.search(r'<meta[^>]+content=["\']([\d.,]+)["\'][^>]+(?:itemprop=["\']price["\']|property=["\']product:price:amount["\'])', html, re.IGNORECASE)
        if meta_match:
            val = float(meta_match.group(1).replace(',', '.'))
            if val >= 100:
                return val, None, ('izpārdots' not in html.lower())

        # 3. dataLayer / JS scripts
        js_prices = re.findall(r'["\'](?:price|unit_price|finalPrice)["\']\s*:\s*["\']?(\d+(?:\.\d+)?)["\']?', html)
        valid_js = [float(p) for p in js_prices if 100 <= float(p) <= 2000]
        if valid_js:
            return valid_js[0], None, ('izpārdots' not in html.lower())

        # 4. Teksta regex (100–2000 EUR)
        text_prices = re.findall(r'(\d{2,4}(?:[.,]\d{2})?)\s*(?:€|EUR)', html)
        valid_text = [float(p.replace(' ', '').replace(',', '.')) for p in text_prices if 100 <= float(p.replace(' ', '').replace(',', '.')) <= 2000]
        if valid_text:
            return valid_text[0], None, ('izpārdots' not in html.lower())

        return None, None, False
    except Exception as e:
        print(f"[Sportega] Kļūda: {e}")
        return None, None, False

def scrape_all():
    print("Sākas hokeja slidu cenu skenēšana...")
    session = requests.Session()
    session.headers.update(HEADERS)
    updated_offers = []

    for t in TARGET_SKATES:
        print(f"Pārbauda: {t['retailer'].upper()} -> {t['model']}")
        try:
            if t['retailer'] == 'hp':
                price, old_price, stock = parse_hokejapasaule(t['url'], session)
            elif t['retailer'] == 'hj':
                price, old_price, stock = parse_hokejam(t['url'], session)
            elif t['retailer'] == 'sp':
                price, old_price, stock = parse_sportega(t['url'], session)
            else:
                price, old_price, stock = None, None, False
        except Exception as e:
            print(f"Neapstrādāta kļūda pie {t['url']}: {e}")
            price, old_price, stock = None, None, False

        time.sleep(1)

        status = 'VERIFIED' if (price is not None and stock and price > 0) else 'UNVERIFIED'
        print(f" -> Rezultāts: Cena = {price}, Noliktavā = {stock}, Statuss = {status}")

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
