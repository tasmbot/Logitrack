CREATE USER admin_user WITH PASSWORD 'admin';
GRANT USAGE ON SCHEMA public TO admin_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO admin_user;

-- Для клиента — только на нужные представления
CREATE USER client_user WITH PASSWORD 'client';
GRANT USAGE ON SCHEMA public TO client_user;

-- Для клиента — только на нужные представления
CREATE USER operator_user WITH PASSWORD 'operator';
GRANT USAGE ON SCHEMA public TO operator_user;

-- Для курьера — только на нужные представления
CREATE USER courier_user WITH PASSWORD 'courier';
GRANT USAGE ON SCHEMA public TO courier_user;

CREATE OR REPLACE VIEW order_summary AS
SELECT
    o.order_id,
    u.full_name AS client_name,
    u.phone AS client_phone,
    l.address AS delivery_location,
    l.latitude,
    l.longitude,
    i.item_name,
    oi.ordered_quantity,
    (i.price * oi.ordered_quantity) AS total_price,
    s.status_name,
    o.created_at
FROM orders o
JOIN clients c ON o.client_id = c.client_id
JOIN users u on u.user_id=c.user_id
JOIN order_items oi ON o.order_id = oi.order_id
JOIN items i ON oi.item_id = i.item_id
JOIN deliveries d ON o.order_id = d.order_id
JOIN locations l ON d.location_id = l.location_id
JOIN statuses s ON o.status_id = s.status_id;

-- Админы и операторы видят всё
GRANT SELECT ON order_summary TO admin_user, operator_user;

CREATE OR REPLACE VIEW daily_order_stats AS
SELECT
    DATE(o.created_at) AS order_date,
    COUNT(o.order_id) AS total_orders,
    SUM(o.total_price) AS total_revenue,
    AVG(o.total_weight) AS avg_weight
FROM orders o
GROUP BY DATE(o.created_at);

GRANT SELECT ON daily_order_stats TO admin_user;

CREATE OR REPLACE FUNCTION get_client_orders(p_client_id INT)
RETURNS TABLE (
    order_id INT,
    delivery_location VARCHAR(255),
    item_name VARCHAR(100),
    ordered_quantity INT,
    total_price NUMERIC(10,2),
    status_name VARCHAR(50),
    created_at TIMESTAMP
) AS $$
    SELECT
        o.order_id,
        l.address,
        i.item_name,
        oi.ordered_quantity,
        (i.price * oi.ordered_quantity),
        s.status_name,
        o.created_at
    FROM orders o
    JOIN order_items oi ON o.order_id = oi.order_id
    JOIN items i ON oi.item_id = i.item_id
    JOIN deliveries d ON o.order_id = d.order_id
    JOIN locations l ON d.location_id = l.location_id
    JOIN statuses s ON o.status_id = s.status_id
    WHERE o.client_id = p_client_id;
$$ LANGUAGE SQL STABLE;

SELECT * FROM get_client_orders(597);

select * from clients limit 10

select * from orders limit 10

CREATE OR REPLACE FUNCTION update_order_totals()
RETURNS TRIGGER AS $$
DECLARE
    v_order_id INT;
BEGIN
    -- Определяем order_id в зависимости от операции
    IF TG_OP = 'DELETE' THEN
        v_order_id := OLD.order_id;
    ELSE
        v_order_id := NEW.order_id;
    END IF;

    -- Пересчитываем total_price и total_weight для заказа
    UPDATE orders
    SET
        total_price = (
            SELECT COALESCE(SUM(i.price * oi.ordered_quantity), 0)
            FROM order_items oi
            JOIN items i ON oi.item_id = i.item_id
            WHERE oi.order_id = v_order_id
        ),
        total_weight = (
            SELECT COALESCE(SUM(i.weight_kg * oi.ordered_quantity), 0)
            FROM order_items oi
            JOIN items i ON oi.item_id = i.item_id
            WHERE oi.order_id = v_order_id
        )
    WHERE order_id = v_order_id;

    RETURN NULL; -- для AFTER-триггера
END;
$$ LANGUAGE plpgsql;

-- Удалим, если уже существует
DROP TRIGGER IF EXISTS trg_update_order_totals ON order_items;

-- Создаём AFTER-триггер на все операции
CREATE TRIGGER trg_update_order_totals
    AFTER INSERT OR UPDATE OR DELETE
    ON order_items
    FOR EACH ROW
    EXECUTE FUNCTION update_order_totals();
