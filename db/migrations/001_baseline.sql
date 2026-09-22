CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    price_cents INTEGER NOT NULL,
    stock INTEGER NOT NULL DEFAULT 0
);

INSERT INTO products (name, price_cents, stock) VALUES
    ('Acme Laptop Pro 14', 189900, 12),
    ('Acme Laptop Air 13', 129900, 30),
    ('Globex Monitor 27', 44900, 8),
    ('Globex Keyboard K2', 8900, 54),
    ('Initech Mouse M1', 3900, 120)
ON CONFLICT DO NOTHING;
