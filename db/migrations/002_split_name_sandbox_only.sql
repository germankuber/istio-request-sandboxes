ALTER TABLE products ADD COLUMN brand TEXT;
ALTER TABLE products ADD COLUMN model TEXT;

UPDATE products
SET brand = split_part(name, ' ', 1),
    model = substr(name, length(split_part(name, ' ', 1)) + 2);

ALTER TABLE products ALTER COLUMN brand SET NOT NULL;
ALTER TABLE products ALTER COLUMN model SET NOT NULL;

ALTER TABLE products DROP COLUMN name;
