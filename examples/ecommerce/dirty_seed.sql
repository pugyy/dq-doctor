CREATE SCHEMA IF NOT EXISTS main;

DROP TABLE IF EXISTS main.dirty_orders;
DROP TABLE IF EXISTS main.dirty_users;

CREATE TABLE main.dirty_users (
    user_id INTEGER PRIMARY KEY,
    email VARCHAR(100),
    phone VARCHAR(20),
    region VARCHAR(20)
);

INSERT INTO main.dirty_users VALUES
    (1, 'alice@example.com', '13800138001', 'beijing'),
    (2, NULL, 'bob@invalid', 'shanghai'),
    (3, 'charlie@test.org', '1391234567', NULL),
    (4, 'diana@example.com', '1588888', 'guangzhou'),
    (5, 'eve@example.com', '13700137001', 'shenzhen'),
    (6, NULL, NULL, NULL),
    (7, 'frank@example', '13600136001', 'beijing'),
    (8, 'grace@example.com', '1551234', 'chengdu'),
    (9, 'heidi@example.com', '15900159001', 'hangzhou'),
    (10, 'ivan@example.com', '13700137002', 'beijing');

CREATE TABLE main.dirty_orders (
    order_id INTEGER,
    user_id INTEGER,
    status VARCHAR(20),
    total_amount DECIMAL(10,2),
    payment_method VARCHAR(20),
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

INSERT INTO main.dirty_orders VALUES
    (1, 1, 'pending', 100.00, 'alipay', CURRENT_TIMESTAMP - INTERVAL '1 hour', CURRENT_TIMESTAMP - INTERVAL '30 minute'),
    (2, 2, 'shipped', -50.00, 'credit_card', CURRENT_TIMESTAMP - INTERVAL '2 hour', CURRENT_TIMESTAMP - INTERVAL '1 hour'),
    (3, NULL, 'delivered', 200.00, 'wechat', CURRENT_TIMESTAMP - INTERVAL '3 hour', CURRENT_TIMESTAMP - INTERVAL '2 hour'),
    (4, 1, 'unknown_status', 300.00, 'alipay', CURRENT_TIMESTAMP - INTERVAL '4 hour', CURRENT_TIMESTAMP - INTERVAL '3 hour'),
    (5, 99, 'pending', 0.00, 'bitcoin', CURRENT_TIMESTAMP - INTERVAL '5 hour', CURRENT_TIMESTAMP - INTERVAL '4 hour'),
    (6, 3, 'shipped', 150.00, 'credit_card', CURRENT_TIMESTAMP - INTERVAL '6 hour', CURRENT_TIMESTAMP - INTERVAL '5 hour'),
    (7, 1, 'pending', -10.00, 'alipay', CURRENT_TIMESTAMP - INTERVAL '48 hour', CURRENT_TIMESTAMP - INTERVAL '47 hour'),
    (8, 4, 'cancelled', 250.00, NULL, CURRENT_TIMESTAMP - INTERVAL '7 hour', CURRENT_TIMESTAMP - INTERVAL '6 hour'),
    (9, 5, 'delivered', 180.00, 'wechat', CURRENT_TIMESTAMP - INTERVAL '8 hour', CURRENT_TIMESTAMP - INTERVAL '7 hour'),
    (10, 1, 'shipped', 99999.99, 'credit_card', CURRENT_TIMESTAMP - INTERVAL '9 hour', CURRENT_TIMESTAMP - INTERVAL '8 hour'),
    (11, NULL, 'pending', 50.00, 'alipay', CURRENT_TIMESTAMP - INTERVAL '10 hour', CURRENT_TIMESTAMP - INTERVAL '9 hour'),
    (12, 6, 'shipped', 75.00, 'cash', CURRENT_TIMESTAMP - INTERVAL '72 hour', CURRENT_TIMESTAMP - INTERVAL '71 hour'),
    (13, 2, 'delivered', 120.00, 'wechat', CURRENT_TIMESTAMP - INTERVAL '12 hour', CURRENT_TIMESTAMP - INTERVAL '11 hour'),
    (14, 7, 'pending', -5.00, 'alipay', CURRENT_TIMESTAMP - INTERVAL '13 hour', CURRENT_TIMESTAMP - INTERVAL '12 hour'),
    (15, 1, 'cancelled', 0.00, 'credit_card', CURRENT_TIMESTAMP - INTERVAL '14 hour', CURRENT_TIMESTAMP - INTERVAL '13 hour'),
    (16, 8, 'shipped', 400.00, 'bitcoin', CURRENT_TIMESTAMP - INTERVAL '15 hour', CURRENT_TIMESTAMP - INTERVAL '14 hour'),
    (17, 3, 'delivered', 60.00, 'alipay', CURRENT_TIMESTAMP - INTERVAL '16 hour', CURRENT_TIMESTAMP - INTERVAL '15 hour'),
    (18, 99, 'pending', -200.00, 'wechat', CURRENT_TIMESTAMP - INTERVAL '17 hour', CURRENT_TIMESTAMP - INTERVAL '16 hour'),
    (19, NULL, NULL, 350.00, NULL, CURRENT_TIMESTAMP - INTERVAL '18 hour', CURRENT_TIMESTAMP - INTERVAL '17 hour'),
    (20, 5, 'unknown_status', 90.00, 'cash', CURRENT_TIMESTAMP - INTERVAL '168 hour', CURRENT_TIMESTAMP - INTERVAL '167 hour');
