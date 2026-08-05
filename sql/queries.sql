-- Exploratory SQL queries against data/processed/housing.db (table: sales)
--
-- Run these with the sqlite3 CLI (`sqlite3 data/processed/housing.db`) or
-- from Python via sqlite3/pandas.read_sql_query — notebooks/01_sql_exploration.ipynb
-- runs every query below and renders the results as tables/charts.
--
-- Schema:
--   sale_date              TEXT  ISO date, e.g. '2010-01-01'
--   year                    INT   year of sale
--   address                 TEXT
--   county                  TEXT  one of the 26 counties
--   eircode                 TEXT  mostly blank (rarely filled in by filers)
--   price                   REAL  euro, full precision
--   not_full_market_price   INT   1 if the sale wasn't at open-market price
--                                 (e.g. family transfer) — see query 7
--   vat_exclusive           INT   1 if the price excludes VAT (new builds)
--   property_type           TEXT  'New' or 'Second-Hand'
--   size_description        TEXT  floor area band, mostly blank (only
--                                 required to be filled in for some sales)


-- 1. Shape of the dataset: row count and date range.
SELECT
    COUNT(*)      AS total_sales,
    MIN(sale_date) AS earliest_sale,
    MAX(sale_date) AS latest_sale
FROM sales;


-- 2. National average & median-ish price by year -- the headline trend.
-- (SQLite has no MEDIAN() function -- AVG() is enough to see the shape of the trend.)
SELECT
    year,
    COUNT(*)               AS n_sales,
    ROUND(AVG(price))      AS avg_price
FROM sales
WHERE not_full_market_price = 0   -- exclude non-market transfers (see query 7)
GROUP BY year
ORDER BY year;


-- 3. Average price by county, most to least expensive.
-- This is the single clearest illustration of why "county" belongs in the
-- model: the gap between the priciest and cheapest county is enormous.
SELECT
    county,
    COUNT(*)          AS n_sales,
    ROUND(AVG(price)) AS avg_price
FROM sales
WHERE not_full_market_price = 0
GROUP BY county
ORDER BY avg_price DESC;


-- 4. New vs. Second-Hand: how many of each, and how much pricier is new?
SELECT
    property_type,
    COUNT(*)          AS n_sales,
    ROUND(AVG(price)) AS avg_price
FROM sales
WHERE not_full_market_price = 0
GROUP BY property_type;


-- 5. Dublin specifically, year by year -- Dublin is roughly a third of all
-- sales nationally, so its trend is worth looking at on its own rather
-- than only as part of the national average in query 2.
SELECT
    year,
    COUNT(*)          AS n_sales,
    ROUND(AVG(price)) AS avg_price
FROM sales
WHERE county = 'Dublin' AND not_full_market_price = 0
GROUP BY year
ORDER BY year;


-- 6. Which counties grew the fastest? Compare each county's average price
-- in the earliest full year of data (2011, since 2010 is a partial/odd
-- post-crash year) against 2025, the latest complete year (2026 is still
-- in progress in this extract, so it's excluded to keep the comparison fair).
WITH by_county_year AS (
    SELECT county, year, AVG(price) AS avg_price
    FROM sales
    WHERE not_full_market_price = 0
    GROUP BY county, year
)
SELECT
    early.county,
    ROUND(early.avg_price)                                   AS avg_price_2011,
    ROUND(late.avg_price)                                     AS avg_price_2025,
    ROUND(100.0 * (late.avg_price - early.avg_price) / early.avg_price, 1) AS pct_change
FROM by_county_year early
JOIN by_county_year late
    ON early.county = late.county AND early.year = 2011 AND late.year = 2025
ORDER BY pct_change DESC;


-- 7. What share of all sales are NOT full market price (e.g. family
-- transfers)? These get excluded before modeling since they don't reflect
-- what a buyer would actually pay on the open market -- worth checking
-- how big a slice of the data that decision throws away.
SELECT
    not_full_market_price,
    COUNT(*)                                          AS n_sales,
    ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM sales), 1) AS pct_of_all_sales,
    ROUND(AVG(price))                                  AS avg_price
FROM sales
GROUP BY not_full_market_price;


-- 8. The 10 highest-priced sales on record -- a quick outlier/sanity check
-- before trusting the data in a model (are these real mansions, or data
-- entry errors?).
SELECT sale_date, address, county, price, property_type
FROM sales
WHERE not_full_market_price = 0
ORDER BY price DESC
LIMIT 10;


-- 9. The 10 lowest-priced "full market price" sales -- the flip side of
-- query 8. A handful of very low full-market-price sales despite being
-- flagged as market-rate hints that the flag alone doesn't catch every
-- non-representative transaction.
SELECT sale_date, address, county, price, property_type
FROM sales
WHERE not_full_market_price = 0
ORDER BY price ASC
LIMIT 10;


-- 10. How complete is the floor-area field? This motivates why the ML
-- model in notebooks/02_modeling.ipynb doesn't use property size as a
-- feature, even though it would likely be one of the strongest predictors.
SELECT
    ROUND(100.0 * SUM(CASE WHEN size_description = '' THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_missing_size
FROM sales;
