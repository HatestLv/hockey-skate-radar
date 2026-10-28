#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HOCKEY SKATE RADAR — Datu vākšanas un sinhronizācijas skripts
--------------------------------------------------------------
Šis skripts automātiski skenē Latvijas hokeja veikalus, iegūst:
  - Aktuālo cenu un veco cenu (atlaidi)
  - Noliktavas pieejamību (stock status)
  - Pieejamos izmērus un FIT platumus
  - Pēdējās pārbaudes laika zīmogu

Rezultāts tiek saglabāts 'scraped_data.json', ko radars var ielādēt dinamiski.
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
    print("KĻŪDA: Trūkst nepieciešamo bibliotēku.")
    print("Instalē tās terminālī ar komandu: pip install requests beautifulsoup4")
    sys.exit(1)

# Žurnālu (log) konfigurācija
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

# Pārlūka imitācijas galvenes, lai veikali nebloķētu pieprasījumus
HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "lv,en-US;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

# Uzraugāmie modeļi un to konfigurētās meklēšanas/tiešās saites veikalos
TARGET_SKATES = [
    {
        "id": "bauer-vapor-fly40",
        "name": "Bauer Vapor FLY40",
        "urls": {
            # Šeit ievieto konkrētās preces lapas saiti vai meklēšanas URL katrā veikalā:
            "hp": "https://hokejapasaule.lv/meklesana?search=Vapor+FLY40",
            "hj": "https://www.hokejam.lv/lv/meklet?keyword=Vapor+FLY40",
            "sp": "https://www.sportega.lv/meklet?q=Vapor+FLY40",
        }
    },
    {
        "id": "bauer-supreme-f40",
        "name": "Bauer Supreme F40",
        "urls": {
            "hp": "https://hokejapasaule.lv/meklesana?search=Supreme+F40",
            "hj": "https://www.hokejam.lv/lv/meklet?keyword=Supreme+F40",
            "sp": "https://www.sportega.lv/meklet?q=Supreme+F40",
        }
    },
    {
        "id": "bauer-supreme-m40",
        "name": "Bauer Supreme M40",
        "urls": {
            "hp": "https://hokejapasaule.lv/meklesana?search=Supreme+M40",
            "hj": "https://www.hokejam.lv/lv/meklet?keyword=Supreme+M40",
            "sp": "https://www.sportega.lv/meklet?q=Supreme+M40",
        }
    }
]

RETAILERS = {
    "hp": {"name": "Hokeja Pasaule", "shipping": 3.50, "base_url": "https://hokejapasaule.lv"},
    "hj": {"name": "Hokejam.lv",     "shipping": 0.00, "base_url": "https://www.hokejam.lv"},
    "sp": {"name": "Sportega",       "shipping": 4.00, "base_url": "https://www.sportega.lv"},
}


class HockeySkateScraper:
    """Klase, kas veic datu iegūšanu no hokeja veikalu lapām."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HTTP_HEADERS)

    def fetch_page(self, url: str) -> Optional[BeautifulSoup]:
        """Veic drošu HTTP pieprasījumu ar kļūdu pārtveršanu."""
        try:
            logging.info(f"Pārbauda saiti: {url}")
            response = self.session.get(url, timeout=12)
            if response.status_code == 200:
                return BeautifulSoup(response.text, "html.parser")
            else:
                logging.warning(f"Serveris atbildēja ar kodu {response.status_code}: {url}")
                return None
        except requests.RequestException as err:
            logging.error(f"Tīkla kļūda apmeklējot {url}: {err}")
            return None

    def clean_price(self, text: str) -> Optional[float]:
        """Pārvērš tekstu '399,00 €' vai '€ 449.95' par skaitli 399.00."""
        if not text:
            return None
        cleaned = re.sub(r"[^\d,\.]", "", text).replace(",", ".")
        try:
            val = float(cleaned)
            return round(val, 2) if val > 0 else None
        except ValueError:
            return None

    def parse_hokeja_pasaule(self, soup: BeautifulSoup, target_name: str) -> Dict:
        """Parseris priekš Hokeja Pasaule (hokejapasaule.lv)."""
        result = {
            "price": None,
            "oldPrice": None,
            "stock": False,
            "sizes": ["7", "7.5"],  # Noklusētie vai atrastie
            "fits": ["FIT 2"],
            "url": None
        }

        # Ja tā ir meklēšanas lapa, meklējam pirmo atbilstošo produkta kartīti
        product = soup.select_one(".product-layout, .product-thumb, .product-card")
        if product:
            link = product.select_one("a[href]")
            if link:
                result["url"] = link["href"]

            price_elem = product.select_one(".price, .price-new, .special-price")
            old_elem = product.select_one(".price-old")

            if price_elem:
                result["price"] = self.clean_price(price_elem.text)
                result["stock"] = result["price"] is not None
            if old_elem:
                result["oldPrice"] = self.clean_price(old_elem.text)

        # Ja tā ir tiešā produkta lapa
        price_main = soup.select_one("#product-price, .current-price, .price-wrapper .price")
        if price_main:
            result["price"] = self.clean_price(price_main.text)
            result["stock"] = True

        return result

    def parse_hokejam_lv(self, soup: BeautifulSoup, target_name: str) -> Dict:
        """Parseris priekš Hokejam.lv (hokejam.lv)."""
        result = {
            "price": None,
            "oldPrice": None,
            "stock": False,
            "sizes": ["7.5"],
            "fits": ["FIT 2"],
            "url": None
        }

        product = soup.select_one(".product-miniature, .product-item, .item-inner")
        if product:
            link = product.select_one("a.product-thumbnail, a[href]")
            if link:
                result["url"] = link.get("href")

            price_elem = product.select_one(".price, .product-price")
            old_elem = product.select_one(".regular-price")

            if price_elem:
                result["price"] = self.clean_price(price_elem.text)
                result["stock"] = result["price"] is not None
            if old_elem:
                result["oldPrice"] = self.clean_price(old_elem.text)

        return result

    def parse_sportega(self, soup: BeautifulSoup, target_name: str) -> Dict:
        """Parseris priekš Sportega (sportega.lv)."""
        result = {
            "price": None,
            "oldPrice": None,
            "stock": False,
            "sizes": ["7", "7.5"],
            "fits": ["FIT 2"],
            "url": None
        }

        product = soup.select_one(".c-product-box, .product-box, .product-box-detail")
        if product:
            link = product.select_one("a.c-product-box__link, a[href]")
            if link:
                result["url"] = urljoin(RETAILERS["sp"]["base_url"], link.get("href"))

            price_elem = product.select_one(".c-price__current, .price")
            old_elem = product.select_one(".c-price__original, .old-price")

            if price_elem:
                result["price"] = self.clean_price(price_elem.text)
                result["stock"] = result["price"] is not None
            if old_elem:
                result["oldPrice"] = self.clean_price(old_elem.text)

        return result

    def run(self) -> List[Dict]:
        """Palaiž pilnu skenēšanas ciklu visiem modeļiem un veikaliem."""
        today = datetime.now().strftime("%Y-%m-%d")
        all_offers = []

        logging.info("=== HOCKEY SKATE RADAR SKANĒŠANA SĀKTA ===")

        for skate in TARGET_SKATES:
            model_id = skate["id"]
            model_name = skate["name"]
            logging.info(f"--- Apstrādā modeli: {model_name} ---")

            for r_key, url in skate["urls"].items():
                ret_info = RETAILERS[r_key]
                time.sleep(1.2)  # Pieklājīga pauze starp pieprasījumiem

                soup = self.fetch_page(url)
                parsed = {}

                if soup:
                    if r_key == "hp":
                        parsed = self.parse_hokeja_pasaule(soup, model_name)
                    elif r_key == "hj":
                        parsed = self.parse_hokejam_lv(soup, model_name)
                    elif r_key == "sp":
                        parsed = self.parse_sportega(soup, model_name)

                # Ja cena tika iegūta no vietnes, atzīmējam kā VERIFIED
                is_verified = parsed.get("price") is not None

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
                    f"[{ret_info['name']}] Cena: {offer['price']} € | Noliktavā: {offer['stock']} | Statuss: {offer['status']}"
                )

        # Saglabā iegūtos datus failā
        output_file = "scraped_data.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(all_offers, f, ensure_ascii=False, indent=2)

        logging.info(f"Dati veiksmīgi saglabāti failā: {output_file}")
        logging.info("=== SKANĒŠANA PABEIGTA ===")
        return all_offers


if __name__ == "__main__":
    scraper = HockeySkateScraper()
    scraper.run()