## AI Fashion Scraper (Minimal, Low-Cost)

### What this is
Lightweight scraper/importer to populate a `products` table in Supabase from brand APIs/feeds or HTML pages. Prefers JSON/XHR endpoints; falls back to HTML parsing.

### Stack
- Python `requests`, `BeautifulSoup`, `jmespath`
- Supabase REST for upserts
- Optional GitHub Actions scheduler

### Legal & Ethics
- Respect `robots.txt` and Terms. Ask brands or use affiliate feeds where possible.
- Use polite crawling: real `User-Agent`, delays, low frequency.

### Setup
1. Python 3.11+
2. Create virtualenv and install deps:
   ```bash
   python -m venv .venv && . .venv/bin/activate  # Windows: .venv\\Scripts\\activate
   pip install -r requirements.txt
   ```
3. Copy `env.example` to `.env` and fill values:
   - `SUPABASE_URL`, `SUPABASE_KEY` (service role or anon for tests)
   - `USER_AGENT`
4. Create table in Supabase (SQL editor):
   - Paste `supabase_schema.sql`
5. Configure target sites in `sites.yaml`.

### Run
```bash
python -m scraper.cli --sites all --config sites.yaml
```

### Config notes (`sites.yaml`)
- API mode: specify `endpoint`, `items_path` (JMESPath), and `field_map` (destination -> JMESPath). Include `external_id` if available; set `source` per site.
- HTML mode: category URLs + CSS selectors. Product pages produce minimal fields; you can extend selectors. Set `source: manual`.

### Schema mapping
- Upserts use unique key `(source, external_id)`.
- Minimal fields we map: `source`, `external_id`, `merchant_name`, `title`, `price`, `currency`, `image_url`, `product_url`, `affiliate_url`, `brand`, `availability`.
- Add optional fields if you have them: `sku`, `gtin_upc_ean`, `category`, `subcategory`, `gender`, `tags`.

### Migration for unique index
- Run `migrations/20251003_add_unique_index.sql` in Supabase SQL editor if your table does not yet have `(source, external_id)` and its unique index.

### Scheduling (GitHub Actions)
- Use `github_actions_scrape.yml` as a template. Place it at `.github/workflows/scrape.yml` in your repo. Add secrets `SUPABASE_URL`, `SUPABASE_KEY`.

### Next steps
- Add affiliate feeds ingestion
- Store images or compute hashes later if needed
- Add proxy only if you hit blocks

