CREATE TABLE IF NOT EXISTS orders (
    order_id      INTEGER PRIMARY KEY,
    user_id       INTEGER NOT NULL,
    status        VARCHAR(20) NOT NULL,
    total_amount  DECIMAL(10, 2),
    payment_method VARCHAR(20),
    created_at    TIMESTAMP NOT NULL,
    updated_at    TIMESTAMP
);

INSERT INTO orders VALUES
    (1,  101, 'completed',  299.00, 'credit_card', CURRENT_TIMESTAMP - INTERVAL '3 hours', CURRENT_TIMESTAMP - INTERVAL '2 hours'),
    (2,  102, 'completed',  159.50, 'alipay',      CURRENT_TIMESTAMP - INTERVAL '5 hours', CURRENT_TIMESTAMP - INTERVAL '4 hours'),
    (3,  101, 'cancelled',   89.00, 'wechat',      CURRENT_TIMESTAMP - INTERVAL '6 hours', CURRENT_TIMESTAMP - INTERVAL '5 hours'),
    (4,  103, 'completed',  450.00, 'credit_card', CURRENT_TIMESTAMP - INTERVAL '8 hours', CURRENT_TIMESTAMP - INTERVAL '7 hours'),
    (5,  104, 'pending',    120.00, 'alipay',      CURRENT_TIMESTAMP - INTERVAL '10 hours', NULL),
    (6,  102, 'completed',   75.50, 'wechat',      CURRENT_TIMESTAMP - INTERVAL '12 hours', CURRENT_TIMESTAMP - INTERVAL '11 hours'),
    (7,  105, 'shipped',    210.00, 'credit_card', CURRENT_TIMESTAMP - INTERVAL '14 hours', CURRENT_TIMESTAMP - INTERVAL '13 hours'),
    (8,  101, 'completed',  333.00, 'alipay',      CURRENT_TIMESTAMP - INTERVAL '16 hours', CURRENT_TIMESTAMP - INTERVAL '15 hours'),
    (9,  106, 'pending',     45.00, 'wechat',      CURRENT_TIMESTAMP - INTERVAL '18 hours', NULL),
    (10, 103, 'completed',  180.00, 'credit_card', CURRENT_TIMESTAMP - INTERVAL '20 hours', CURRENT_TIMESTAMP - INTERVAL '19 hours'),
    (11, 107, 'shipped',    520.00, 'alipay',      CURRENT_TIMESTAMP - INTERVAL '22 hours', CURRENT_TIMESTAMP - INTERVAL '21 hours'),
    (12, 104, 'completed',   99.90, 'credit_card', CURRENT_TIMESTAMP - INTERVAL '1 day', CURRENT_TIMESTAMP - INTERVAL '23 hours'),
    (13, 108, 'cancelled',  200.00, 'wechat',      CURRENT_TIMESTAMP - INTERVAL '1 day 2 hours', CURRENT_TIMESTAMP - INTERVAL '1 day 1 hour'),
    (14, 105, 'completed',  175.00, 'alipay',      CURRENT_TIMESTAMP - INTERVAL '1 day 4 hours', CURRENT_TIMESTAMP - INTERVAL '1 day 3 hours'),
    (15, 109, 'completed',  680.00, 'credit_card', CURRENT_TIMESTAMP - INTERVAL '1 day 6 hours', CURRENT_TIMESTAMP - INTERVAL '1 day 5 hours'),
    (16, 106, 'pending',     60.00, 'wechat',      CURRENT_TIMESTAMP - INTERVAL '1 day 8 hours', NULL),
    (17, 110, 'shipped',    340.00, 'credit_card', CURRENT_TIMESTAMP - INTERVAL '1 day 10 hours', CURRENT_TIMESTAMP - INTERVAL '1 day 9 hours'),
    (18, 107, 'completed',  125.00, 'alipay',      CURRENT_TIMESTAMP - INTERVAL '1 day 12 hours', CURRENT_TIMESTAMP - INTERVAL '1 day 11 hours'),
    (19, 108, 'completed',   55.00, 'wechat',      CURRENT_TIMESTAMP - INTERVAL '1 day 14 hours', CURRENT_TIMESTAMP - INTERVAL '1 day 13 hours'),
    (20, 109, 'completed',  410.00, 'credit_card', CURRENT_TIMESTAMP - INTERVAL '1 day 16 hours', CURRENT_TIMESTAMP - INTERVAL '1 day 15 hours');

CREATE TABLE IF NOT EXISTS users (
    user_id    INTEGER PRIMARY KEY,
    username   VARCHAR(50) NOT NULL,
    email      VARCHAR(100),
    status     VARCHAR(20) DEFAULT 'active',
    region     VARCHAR(20),
    created_at TIMESTAMP NOT NULL
);

INSERT INTO users VALUES
    (101, 'alice',   'alice@example.com',   'active',    'east',  CURRENT_TIMESTAMP - INTERVAL '30 days'),
    (102, 'bob',     'bob@example.com',     'active',    'west',  CURRENT_TIMESTAMP - INTERVAL '29 days'),
    (103, 'charlie', 'charlie@example.com',  'active',    'east',  CURRENT_TIMESTAMP - INTERVAL '25 days'),
    (104, 'diana',   'diana@example.com',   'inactive',  'north', CURRENT_TIMESTAMP - INTERVAL '20 days'),
    (105, 'eve',     'eve@example.com',     'active',    'south', CURRENT_TIMESTAMP - INTERVAL '15 days'),
    (106, 'frank',   NULL,                   'active',    'west',  CURRENT_TIMESTAMP - INTERVAL '12 days'),
    (107, 'grace',   'grace@example.com',   'active',    'east',  CURRENT_TIMESTAMP - INTERVAL '8 days'),
    (108, 'heidi',   'heidi@example.com',   'suspended', 'north', CURRENT_TIMESTAMP - INTERVAL '5 days'),
    (109, 'ivan',    'ivan@example.com',    'active',    'south', CURRENT_TIMESTAMP - INTERVAL '3 days'),
    (110, 'judy',    'judy@example.com',    'active',    'west',  CURRENT_TIMESTAMP - INTERVAL '1 day');

CREATE TABLE IF NOT EXISTS products (
    product_id  INTEGER PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    category    VARCHAR(50),
    price       DECIMAL(10, 2) NOT NULL,
    stock       INTEGER DEFAULT 0,
    status      VARCHAR(20) DEFAULT 'on_sale',
    created_at  TIMESTAMP NOT NULL
);

INSERT INTO products VALUES
    (1,  'Wireless Mouse',       'Electronics',   49.90,  150, 'on_sale',     CURRENT_TIMESTAMP - INTERVAL '45 days'),
    (2,  'Mechanical Keyboard',   'Electronics',  129.00,  80, 'on_sale',     CURRENT_TIMESTAMP - INTERVAL '45 days'),
    (3,  'USB-C Hub',            'Electronics',    39.90, 200, 'on_sale',     CURRENT_TIMESTAMP - INTERVAL '40 days'),
    (4,  'Monitor Stand',        'Furniture',      89.00,  50, 'on_sale',     CURRENT_TIMESTAMP - INTERVAL '35 days'),
    (5,  'Webcam HD',            'Electronics',    79.00,  30, 'on_sale',     CURRENT_TIMESTAMP - INTERVAL '25 days'),
    (6,  'Desk Lamp',            'Furniture',      45.00, 100, 'on_sale',     CURRENT_TIMESTAMP - INTERVAL '20 days'),
    (7,  'Laptop Sleeve',        'Accessories',    29.90, 300, 'on_sale',     CURRENT_TIMESTAMP - INTERVAL '15 days'),
    (8,  'Noise Cancelling Buds', 'Electronics',  199.00,  60, 'on_sale',     CURRENT_TIMESTAMP - INTERVAL '10 days'),
    (9,  'Ergonomic Chair',      'Furniture',     450.00,  20, 'discontinued', CURRENT_TIMESTAMP - INTERVAL '8 days'),
    (10, 'Cable Organizer',      'Accessories',    15.90, 500, 'on_sale',     CURRENT_TIMESTAMP - INTERVAL '3 days');
