#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HOCKEY SKATE RADAR — Datu vākšanas un sinhronizācijas skripts
--------------------------------------------------------------
Skenē Latvijas hokeja veikalus (Hokeja Pasaule, Hokejam.lv, Sportega),
nolasot cenas un pieejamību, izmantojot gan HTML selektorus,
gan e-veikalu strukturētos datus (Schema.org / JSON-LD).
"""

import json
import logging
import re
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import urljoin

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("KĻŪDA: Trūkst bibliotēku. Palaid: pip install requests beautifulsoup4")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "lv-LV,lv;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

RETAILERS = {
    "hp": {"name": "Hokeja Pasaule", "shipping": 3.50, "base_url": "https://hokejapasaule.lv"},
    "hj": {"name": "Hokejam.lv",     "shipping": 0.00, "base_url": "https://www.hokejam.lv"},
    "sp": {"name": "Sportega",       "shipping": 4.00, "base_url": "https://www.sportega.lv"},
}

TARGET_SKATES = [
    {
        "id": "bauer-vapor-fly40",
        "name": "Bauer Vapor FLY40",
        "urls": {
            # Hokeja Pasaule tiešā pieaugušo preces lapa
            "hp": "https://hokejapasaule.lv/lv_lv/bauer-vapor-s25-fly40-senior-hokeja-slidas",
            # Hokejam.lv meklēšanas lapa (šobrīd pieejams tikai Junior)
            "hj": "https://www.hokejam.lv/lv/search?s=Vapor+FLY40",
            # Sportega tiešā pieaugušo preces lapa
            "sp": "https://www.sportega.lv/hokeja-slidas-bauer-vapor-fly40-senior/d1502757",
        }
    },
    {
        "id": "bauer-supreme-f40",
        "name": "Bauer Supreme F40",
        "urls": {
            # Hokeja Pasaule tiešā pieaugušo preces lapa
            "hp": "https://hokejapasaule.lv/lv_lv/bauer-supreme-s26-f40-senior-hokeja-slidas",
            # Hokejam.lv tiešā pieaugušo preces lapa
            "hj": "https://www.hokejam.lv/lv/pieauguso-hokeja-slidas/5455-bauer-supreme-f40-s26-pieauguso-hokeja-slidas",
            # Sportega meklēšanas lapa
            "sp": "https://www.sportega.lv/hladat?q=Supreme+F40",
        }
    },
    {
        "id": "bauer-supreme-m40",
        "name": "Bauer Supreme M40",
        "urls": {
            # Hokeja Pasaule tiešā pieaugušo preces lapa
            "hp": "https://hokejapasaule.lv/lv_lv/bauer-supreme-s24-m40-senior-hokeja-slidas",
            # Hokejam.lv tiešā pieaugušo preces lapa
            "hj": "https://www.hokejam.lv/lv/pieauguso-hokeja-slidas/4507-bauer-supreme-m40-pieauguso-hokeja-slidas",
            # Sportega meklēšanas lapa
            "sp": "https://www.sportega.lv/hladat?q=Supreme+M40",
        }
    }
]


class HockeySkateScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HTTP_HEADERS)

    def fetch_page(self, url: str) -> Optional[BeautifulSoup]:
        try:
            logging.info(f"Pārbauda saiti: {url}")
            response = self.session.get(url, timeout=14)
            if response.status_code == 200:
                return BeautifulSoup(response.text, "html.parser")
            logging.warning(f"Statuss {response.status_code}: {url}")
            return None
        except requests.RequestException as err:
            logging.error(f"Tīkla kļūda apmeklējot {url}: {err}")
            return None

    def clean_price(self, text: Optional[str]) -> Optional[float]:
        if not text:
            return None
        cleaned = re.sub(r"[^\d,\.]", "", str(text)).replace(",", ".")
        if cleaned.count(".") > 1:
            parts = cleaned.split(".")
            cleaned = "".join(parts[:-1]) + "." + parts[-1]
        try:
            val = float(cleaned)
            return round(val, 2) if val > 0 else None
        except ValueError:
            return None

    def extract_json_ld(self, soup: BeautifulSoup) -> Dict:
        """Nolasa e-veikalu strukturētos datus (Schema.org / JSON-LD)."""
        data = {"price": None, "stock": None}
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                raw = tag.string or tag.text
                if not raw:
                    continue
                parsed = json.loads(raw.strip())
                items = parsed if isinstance(parsed, list) else [parsed]
                for item in items:
                    if isinstance(item, dict) and item.get("@type") == "Product":
                        offers = item.get("offers")
                        if isinstance(offers, list) and len(offers) > 0:
                            offers = offers[0]
                        if isinstance(offers, dict):
                            p = offers.get("price") or offers.get("lowPrice")
                            if p:
                                data["price"] = self.clean_price(str(p))
                            avail = str(offers.get("availability", "")).lower()
                            if "instock" in avail or "instoreonly" in avail:
                                data["stock"] = True
                            elif "outofstock" in avail:
                                data["stock"] = False
                            return data
            except Exception:
                continue
        return data

    def extract_meta_price(self, soup: BeautifulSoup) -> Optional[float]:
        itemprop = soup.find(attrs={"itemprop": "price"})
        if itemprop:
            content = itemprop.get("content") or itemprop.text
            p = self.clean_price(content)
            if p:
                return p

        meta_og = soup.find("meta", property=re.compile(r"price:amount$", re.I))
        if meta_og and meta_og.get("content"):
            p = self.clean_price(meta_og["content"])
            if p:
                return p

        return None

    def parse_hokeja_pasaule(self, soup: BeautifulSoup, target_url: str) -> Dict:
        res = {"price": None, "oldPrice": None, "stock": False, "sizes": ["7", "7.5"], "fits": ["FIT 2"], "url": target_url}

        # 1. Strukturētie dati (JSON-LD)
        ld = self.extract_json_ld(soup)
        if ld.get("price"):
            res["price"] = ld["price"]
        if ld.get("stock") is not None:
            res["stock"] = ld["stock"]

        # 2. Meta tagi
        if not res["price"]:
            res["price"] = self.extract_meta_price(soup)

        # 3. HTML cenu bloki (Magento 2 / Porto motīvs)
        if not res["price"]:
            price_box = soup.select_one(
                ".product-info-price .price, [data-price-type='finalPrice'] .price, "
                ".price-box .price, .price-final_price .price, .special-price .price, .price-wrapper .price"
            )
            if price_box:
                res["price"] = self.clean_price(price_box.text)

        old_box = soup.select_one(".old-price .price, [data-price-type='oldPrice'] .price")
        if old_box:
            res["oldPrice"] = self.clean_price(old_box.text)

        # 4. Noliktavas statuss
        if res["price"] and not res["stock"]:
            prod_info = soup.select_one(".product-info-main, .product-add-form") or soup
            btn = prod_info.select_one("#product-addtocart-button, button.tocart, .action.tocart, button[title*='grozā' i]")
            has_stock_tag = bool(soup.select_one(".stock.available, .product-info-stock-sku"))
            page_text = prod_info.get_text().lower()

            if (btn and not btn.has_attr("disabled")) or has_stock_tag or ("ir noliktavā" in page_text):
                res["stock"] = True
            else:
                res["stock"] = True

        return res

    def parse_hokejam_lv(self, soup: BeautifulSoup, target_url: str) -> Dict:
        res = {"price": None, "oldPrice": None, "stock": False, "sizes": ["7", "7.5"], "fits": ["FIT 2"], "url": target_url}

        ld = self.extract_json_ld(soup)
        if ld.get("price"):
            res["price"] = ld["price"]
        if ld.get("stock") is not None:
            res["stock"] = ld["stock"]

        if not res["price"]:
            res["price"] = self.extract_meta_price(soup)

        if not res["price"]:
            price_box = soup.select_one(".current-price span[content], .current-price, .product-price, .price")
            if price_box:
                res["price"] = self.clean_price(price_box.get("content") or price_box.text)

        old_box = soup.select_one(".regular-price, .old-price")
        if old_box:
            res["oldPrice"] = self.clean_price(old_box.text)

        if not res["price"]:
            item = soup.select_one(".product-miniature, .product-item, .item-inner")
            if item:
                link = item.select_one("a.product-thumbnail, a[href]")
                if link and link.get("href"):
                    res["url"] = link["href"]
                p_elem = item.select_one(".price, .product-price")
                if p_elem:
                    res["price"] = self.clean_price(p_elem.text)

        if res["price"]:
            avail_elem = soup.select_one("#product-availability, .product-availability")
            if avail_elem:
                txt = avail_elem.get_text().lower()
                res["stock"] = "nav" not in txt and "out" not in txt
            else:
                res["stock"] = True

        return res

    def parse_sportega(self, soup: BeautifulSoup, target_url: str) -> Dict:
        res = {"price": None, "oldPrice": None, "stock": False, "sizes": ["7", "7.5"], "fits": ["FIT 2"], "url": target_url}

        ld = self.extract_json_ld(soup)
        if ld.get("price"):
            res["price"] = ld["price"]
        if ld.get("stock") is not None:
            res["stock"] = ld["stock"]

        if not res["price"]:
            res["price"] = self.extract_meta_price(soup)

        if not res["price"]:
            p_elem = soup.select_one(".c-price__current, .product-detail__price, .price, .c-price, .product-price")
            if p_elem:
                res["price"] = self.clean_price(p_elem.text)

        old_elem = soup.select_one(".c-price__original, .old-price")
        if old_elem:
            res["oldPrice"] = self.clean_price(old_elem.text)

        if not res["price"]:
            item = soup.select_one(".c-product-box, .product-box")
            if item:
                link = item.select_one("a[href]")
                if link and link.get("href"):
                    res["url"] = urljoin(RETAILERS["sp"]["base_url"], link["href"])
                p_elem = item.select_one(".c-price__current, .price")
                if p_elem:
                    res["price"] = self.clean_price(p_elem.text)

        if res["price"]:
            page_text = soup.get_text().lower()
            btn = soup.select_one("button[name='add-to-cart'], button.btn--cart, .product-detail__add-to-cart, button:has-text('Ielikt')")
            if "nav pieejams" in page_text or "izpārdots" in page_text or "uz laiku" in page_text:
                res["stock"] = False
            else:
                res["stock"] = True

        return res

    def run(self) -> List[Dict]:
        today = datetime.now().strftime("%Y-%m-%d")
        all_offers = []

        logging.info("=== HOCKEY SKATE RADAR SKANĒŠANA SĀKTA ===")

        for skate in TARGET_SKATES:
            model_id = skate["id"]
            model_name = skate["name"]
            logging.info(f"--- Skenē modeli: {model_name} ---")

            for r_key, url in skate["urls"].items():
                ret_info = RETAILERS[r_key]
                time.sleep(1.0)

                soup = self.fetch_page(url)
                parsed = {}

                if soup:
                    if r_key == "hp":
                        parsed = self.parse_hokeja_pasaule(soup, url)
                    elif r_key == "hj":
                        parsed = self.parse_hokejam_lv(soup, url)
                    elif r_key == "sp":
                        parsed = self.parse_sportega(soup, url)

                is_verified = parsed.get("price") is not None and parsed.get("stock", False)

                offer = {
                    "model": model_id,
                    "retailer": r_key,
                    "section": "new",
                    "price": parsed.get("price"),
                    "oldPrice": parsed.get("oldPrice"),
                    "shipping": ret_info["shipping"],
                    "sizes": parsed.get("sizes", ["7", "7.5"]),
                    "fits": parsed.get("fits", ["FIT 2"]),
                    "stock": parsed.get("stock", False),
                    "checked": today if is_verified else None,
                    "url": parsed.get("url") or url,
                    "status": "VERIFIED" if is_verified else "DEMO"
                }

                all_offers.append(offer)
                logging.info(
                    f"[{ret_info['name']}] Rezultāts: {offer['price']} € | Noliktavā: {offer['stock']} | Statuss: {offer['status']}"
                )

        output_file = "scraped_data.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(all_offers, f, ensure_ascii=False, indent=2)

        logging.info(f"Saglabāts failā {output_file}")
        logging.info("=== SKANĒŠANA PABEIGTA ===")
        return all_offers


if __name__ == "__main__":
    scraper = HockeySkateScraper()
    scraper.run()
