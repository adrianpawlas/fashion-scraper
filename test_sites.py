#!/usr/bin/env python3

from scraper.config import load_sites_config

def main():
    sites = load_sites_config()
    print(f"Total sites loaded: {len(sites)}")
    for i, site in enumerate(sites):
        print(f"  {i+1}. {site.get('brand')}")

if __name__ == "__main__":
    main()
