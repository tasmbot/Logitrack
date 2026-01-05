-- FUNCTION: public.check_item_weight()

-- DROP FUNCTION IF EXISTS public.check_item_weight();

CREATE OR REPLACE FUNCTION public.check_item_weight()
    RETURNS trigger
    LANGUAGE 'plpgsql'
    COST 100
    VOLATILE NOT LEAKPROOF
AS $BODY$
BEGIN
    IF NEW.weight_kg IS NOT NULL AND NEW.weight_kg < 0 THEN
        RAISE EXCEPTION 'Вес товара не может быть отрицательным!';
    END IF;
    RETURN NEW;
END;
$BODY$;

ALTER FUNCTION public.check_item_weight()
    OWNER TO postgres;

-- FUNCTION: public.check_quantity_positive()

-- DROP FUNCTION IF EXISTS public.check_quantity_positive();

CREATE OR REPLACE FUNCTION public.check_quantity_positive()
    RETURNS trigger
    LANGUAGE 'plpgsql'
    COST 100
    VOLATILE NOT LEAKPROOF
AS $BODY$
BEGIN
    IF NEW.ordered_quantity <= 0 THEN
        RAISE EXCEPTION 'Количество товара в заказе должно быть больше 0!';
    END IF;
    RETURN NEW;
END;
$BODY$;

ALTER FUNCTION public.check_quantity_positive()
    OWNER TO postgres;

-- FUNCTION: public.check_sequence_positive()

-- DROP FUNCTION IF EXISTS public.check_sequence_positive();

CREATE OR REPLACE FUNCTION public.check_sequence_positive()
    RETURNS trigger
    LANGUAGE 'plpgsql'
    COST 100
    VOLATILE NOT LEAKPROOF
AS $BODY$
BEGIN
    IF NEW.sequence_num <= 0 THEN
        RAISE EXCEPTION 'Порядковый номер точки в маршруте должен быть положительным!';
    END IF;
    RETURN NEW;
END;
$BODY$;

ALTER FUNCTION public.check_sequence_positive()
    OWNER TO postgres;

-- FUNCTION: public.check_stock_on_delivery()

-- DROP FUNCTION IF EXISTS public.check_stock_on_delivery();

CREATE OR REPLACE FUNCTION public.check_stock_on_delivery()
    RETURNS trigger
    LANGUAGE 'plpgsql'
    COST 100
    VOLATILE NOT LEAKPROOF
AS $BODY$
DECLARE
    v_store_location_id INT;
    v_item_id INT;
    v_ordered_qty INT;
    v_available_qty INT;
BEGIN
    -- Находим магазин (первая точка маршрута с типом 'store')
    SELECT rp.location_id
    INTO v_store_location_id
    FROM public.route_points rp
    JOIN public.locations l ON rp.location_id = l.location_id
    JOIN public.location_types lt ON l.location_type_id = lt.location_type_id
    WHERE rp.route_id = NEW.route_id
      AND rp.sequence_num = 1
      AND lt.location_type = 'store'
    LIMIT 1;

    IF v_store_location_id IS NULL THEN
        RAISE EXCEPTION 'Не найден магазин для маршрута %', NEW.route_id;
    END IF;

    -- Проверяем каждый товар в заказе
    FOR v_item_id, v_ordered_qty IN
        SELECT item_id, ordered_quantity
        FROM public.order_items
        WHERE order_id = NEW.order_id
    LOOP
        SELECT COALESCE(quantity, 0)
        INTO v_available_qty
        FROM public.store_stock
        WHERE location_id = v_store_location_id
          AND item_id = v_item_id;

        IF v_available_qty IS NULL OR v_available_qty < v_ordered_qty THEN
            RAISE EXCEPTION 'Недостаточно товара (item_id=%) в магазине (location_id=%). Доступно: %, Запрошено: %',
                v_item_id, v_store_location_id, COALESCE(v_available_qty, 0), v_ordered_qty;
        END IF;
    END LOOP;

    RETURN NEW;
END;
$BODY$;

ALTER FUNCTION public.check_stock_on_delivery()
    OWNER TO postgres;

-- FUNCTION: public.create_notification_on_status_change()

-- DROP FUNCTION IF EXISTS public.create_notification_on_status_change();

CREATE OR REPLACE FUNCTION public.create_notification_on_status_change()
    RETURNS trigger
    LANGUAGE 'plpgsql'
    COST 100
    VOLATILE NOT LEAKPROOF
AS $BODY$
DECLARE
    v_client_id INT;
    v_message TEXT;
BEGIN
    -- Получаем client_id
    SELECT client_id INTO v_client_id FROM orders WHERE order_id = NEW.order_id;

    -- Формируем сообщение
    CASE NEW.status_id
        WHEN 1 THEN v_message = 'Ваш заказ принят и ожидает обработки.';
        WHEN 2 THEN v_message = 'Заказ в пути! Курьер уже выехал к вам.';
        WHEN 3 THEN v_message = 'Заказ успешно доставлен. Спасибо!';
        ELSE v_message = 'Статус вашего заказа обновлён: ' || (SELECT status_name FROM statuses WHERE status_id = NEW.status_id);
    END CASE;

    -- Вставляем уведомление
    INSERT INTO notifications (client_id, order_id, status_id, message)
    VALUES (v_client_id, NEW.order_id, NEW.status_id, v_message);

    RETURN NEW;
END;
$BODY$;

ALTER FUNCTION public.create_notification_on_status_change()
    OWNER TO postgres;

-- FUNCTION: public.deduct_stock_on_order_dispatch()

-- DROP FUNCTION IF EXISTS public.deduct_stock_on_order_dispatch();

CREATE OR REPLACE FUNCTION public.deduct_stock_on_order_dispatch()
    RETURNS trigger
    LANGUAGE 'plpgsql'
    COST 100
    VOLATILE NOT LEAKPROOF
AS $BODY$
DECLARE
    v_store_location_id INT;
    v_item_id INT;
    v_quantity INT;
BEGIN
    -- Работаем только при переходе в статус "в пути"
    IF OLD.status_id = NEW.status_id OR NEW.status_id != 2 THEN
        RETURN NEW;
    END IF;

    -- Находим магазин (аналогично предыдущему триггеру)
    SELECT rp.location_id
    INTO v_store_location_id
    FROM deliveries d
    JOIN route_points rp ON d.route_id = rp.route_id
    JOIN locations l ON rp.location_id = l.location_id
    JOIN location_types lt ON l.location_type_id = lt.location_type_id
    WHERE d.order_id = NEW.order_id
      AND lt.location_type = 'store'
    LIMIT 1;

    IF v_store_location_id IS NULL THEN
        RAISE EXCEPTION 'Магазин не найден для заказа %', NEW.order_id;
    END IF;

    -- Списываем каждый товар из заказа
    FOR v_item_id, v_quantity IN
        SELECT item_id, ordered_quantity
        FROM order_items
        WHERE order_id = NEW.order_id
    LOOP
        UPDATE store_stock
        SET quantity = GREATEST(0, quantity - v_quantity),
            updated_at = CURRENT_TIMESTAMP
        WHERE location_id = v_store_location_id
          AND item_id = v_item_id;

        -- (Опционально) проверить, что запись существовала
    END LOOP;

    RETURN NEW;
END;
$BODY$;

ALTER FUNCTION public.deduct_stock_on_order_dispatch()
    OWNER TO postgres;

-- FUNCTION: public.log_audit()

-- DROP FUNCTION IF EXISTS public.log_audit();

CREATE OR REPLACE FUNCTION public.log_audit()
    RETURNS trigger
    LANGUAGE 'plpgsql'
    COST 100
    VOLATILE NOT LEAKPROOF
AS $BODY$
DECLARE
    v_user_id INT;
BEGIN
    -- Получаем user_id из сессии (устанавливается приложением)
    BEGIN
        v_user_id := NULLIF(current_setting('myapp.user_id', true), '')::INT;
    EXCEPTION WHEN undefined_object OR invalid_text_representation THEN
        v_user_id := NULL;
    END;

    IF TG_OP = 'INSERT' THEN
        INSERT INTO audit_log (table_name, record_id, action, new_values, user_id)
        VALUES (
            TG_TABLE_NAME,
            NEW.order_id,  -- или другой PK в зависимости от таблицы
            'INSERT',
            row_to_json(NEW)::JSONB,
            v_user_id
        );

    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO audit_log (table_name, record_id, action, old_values, new_values, user_id)
        VALUES (
            TG_TABLE_NAME,
            NEW.order_id,
            'UPDATE',
            row_to_json(OLD)::JSONB,
            row_to_json(NEW)::JSONB,
            v_user_id
        );

    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO audit_log (table_name, record_id, action, old_values, user_id)
        VALUES (
            TG_TABLE_NAME,
            OLD.order_id,
            'DELETE',
            row_to_json(OLD)::JSONB,
            v_user_id
        );
    END IF;

    RETURN NULL;
END;
$BODY$;

ALTER FUNCTION public.log_audit()
    OWNER TO postgres;

-- FUNCTION: public.update_order_totals()

-- DROP FUNCTION IF EXISTS public.update_order_totals();

CREATE OR REPLACE FUNCTION public.update_order_totals()
    RETURNS trigger
    LANGUAGE 'plpgsql'
    COST 100
    VOLATILE NOT LEAKPROOF
AS $BODY$
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
$BODY$;

ALTER FUNCTION public.update_order_totals()
    OWNER TO postgres;
