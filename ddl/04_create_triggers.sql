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
AS $BODY$
DECLARE
    v_store_location_id INT;
    v_item_id INT;
    v_ordered_qty INT;
    v_available_qty INT;
BEGIN
    -- 1. Берём магазин из явно заданной колонки (быстро и надёжно)
    v_store_location_id := NEW.pickup_location_id;

    -- 2. Фолбэк для старых записей, если колонка вдруг NULL
    IF v_store_location_id IS NULL THEN
        SELECT rp.location_id
        INTO v_store_location_id
        FROM public.route_points rp
        JOIN public.locations l ON rp.location_id = l.location_id
        JOIN public.location_types lt ON l.location_type_id = lt.location_type_id
        WHERE rp.route_id = NEW.route_id
          AND rp.sequence_num = 1
          AND lt.location_type = 'store'
        LIMIT 1;
    END IF;

    -- 3. Если магазин всё ещё не найден → понятная ошибка
    IF v_store_location_id IS NULL THEN
        RAISE EXCEPTION 'Не найден магазин для маршрута %. Убедитесь, что в deliveries указан pickup_location_id или route_points содержит точку типа store.', NEW.route_id;
    END IF;

    -- 4. Проверка остатков (оптимизировано)
    FOR v_item_id, v_ordered_qty IN
        SELECT oi.item_id, oi.ordered_quantity
        FROM public.order_items oi
        WHERE oi.order_id = NEW.order_id
    LOOP
        SELECT COALESCE(ss.quantity, 0)
        INTO v_available_qty
        FROM public.store_stock ss
        WHERE ss.location_id = v_store_location_id
          AND ss.item_id = v_item_id;

        IF v_available_qty < v_ordered_qty THEN
            RAISE EXCEPTION 'Недостаточно товара (item_id=%) в магазине (location_id=%). Доступно: %, Запрошено: %',
                v_item_id, v_store_location_id, v_available_qty, v_ordered_qty;
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

CREATE OR REPLACE FUNCTION log_audit()
RETURNS TRIGGER AS $$
DECLARE
    v_user_id INT;
    v_pk_col TEXT;
    v_record_id INT;
    v_json_old JSONB;
    v_json_new JSONB;
BEGIN
    -- 1. Безопасное получение user_id из сессии
    BEGIN
        v_user_id := NULLIF(current_setting('myapp.user_id', true), '')::INT;
    EXCEPTION WHEN OTHERS THEN
        v_user_id := NULL;
    END;

    -- 2. Динамический поиск первичного ключа таблицы
    SELECT kcu.column_name INTO v_pk_col
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu 
      ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
    WHERE tc.table_name = TG_TABLE_NAME 
      AND tc.table_schema = TG_TABLE_SCHEMA 
      AND tc.constraint_type = 'PRIMARY KEY'
    LIMIT 1;

    -- Fallback: если PK не найден, берём первую колонку таблицы
    IF v_pk_col IS NULL THEN
        SELECT column_name INTO v_pk_col
        FROM information_schema.columns
        WHERE table_name = TG_TABLE_NAME AND table_schema = TG_TABLE_SCHEMA
        ORDER BY ordinal_position LIMIT 1;
    END IF;

    -- 3. Подготовка JSON (защита от NULL в NEW/OLD)
    IF TG_OP != 'INSERT' THEN v_json_old := row_to_json(OLD)::JSONB; END IF;
    IF TG_OP != 'DELETE' THEN v_json_new := row_to_json(NEW)::JSONB; END IF;

    -- 4. Извлечение ID записи из JSON по найденному имени PK
    IF TG_OP = 'DELETE' THEN
        v_record_id := (v_json_old->>v_pk_col)::INT;
    ELSE
        v_record_id := (v_json_new->>v_pk_col)::INT;
    END IF;

    -- 5. Единая запись в журнал (упрощает поддержку)
    INSERT INTO audit_log (table_name, record_id, action, old_values, new_values, user_id)
    VALUES (
        TG_TABLE_NAME,
        COALESCE(v_record_id, 0),  -- защита от нарушения NOT NULL
        TG_OP,
        v_json_old,
        v_json_new,
        v_user_id
    );

    RETURN NULL; -- Обязательно для AFTER триггеров
END;
$$ LANGUAGE plpgsql;

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

-- 1. Создаём функцию-триггер (универсальную, можно переиспользовать)
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 2. Создаём триггер на таблицу delivery_coordinates
DROP TRIGGER IF EXISTS trg_delivery_coordinates_updated ON public.delivery_coordinates;

CREATE TRIGGER trg_delivery_coordinates_updated
    BEFORE INSERT OR UPDATE ON public.delivery_coordinates
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- 1. Автоматическое создание записи в таблице couriers при регистрации нового пользователя с role_id=3
CREATE OR REPLACE FUNCTION auto_create_courier()
RETURNS TRIGGER AS $$
BEGIN
    -- Срабатывает только если назначена роль "Курьер"
    IF NEW.role_id = 3 THEN
        INSERT INTO couriers (user_id, active)
        VALUES (NEW.user_id, true)
        ON CONFLICT (user_id) DO NOTHING;  -- Защита от дублей при повторных вставках
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 2. Привязка триггера к таблице users
DROP TRIGGER IF EXISTS trg_auto_courier ON public.users;
CREATE TRIGGER trg_auto_courier
    AFTER INSERT OR UPDATE ON public.users
    FOR EACH ROW
    EXECUTE FUNCTION auto_create_courier();