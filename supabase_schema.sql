create table if not exists products (
	product_id text primary key,
	merchant text,
	title text,
	description text,
	brand text,
	price numeric,
	currency text,
	image_url text,
	product_url text,
	affiliate_url text,
	in_stock boolean,
	last_seen timestamptz default now()
);

-- Helpful indexes
create index if not exists products_merchant_idx on products(merchant);
create index if not exists products_brand_idx on products(brand);
create index if not exists products_last_seen_idx on products(last_seen);

