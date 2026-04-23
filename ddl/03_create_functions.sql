-- FUNCTION: public.get_client_orders(integer)

-- DROP FUNCTION IF EXISTS public.get_client_orders(integer);

CREATE OR REPLACE FUNCTION public.get_client_orders(
	p_client_id integer)
    RETURNS TABLE(order_id integer, delivery_location character varying, item_name character varying, ordered_quantity integer, total_price numeric, status_name character varying, created_at timestamp without time zone) 
    LANGUAGE 'sql'
    COST 100
    STABLE PARALLEL UNSAFE
    ROWS 1000

AS $BODY$
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
$BODY$;

ALTER FUNCTION public.get_client_orders(integer)
    OWNER TO postgres;

CREATE OR REPLACE FUNCTION recalculate_courier_route(p_courier_id INT)
RETURNS VOID AS $$
DECLARE
    v_route_id INT;
BEGIN
    -- 1. Находим основной активный маршрут курьера
    SELECT route_id INTO v_route_id
    FROM deliveries
    WHERE courier_id = p_courier_id 
      AND actual_delivery_datetime IS NULL
    LIMIT 1;

    IF v_route_id IS NULL THEN
        RETURN; -- Нет активных доставок
    END IF;

    -- 2. Очищаем старые точки маршрута
    DELETE FROM route_points WHERE route_id = v_route_id;

    -- 3. Вставляем уникальные точки маршрута с правильной нумерацией
    -- Алгоритм:
    -- а) Собираем все локации (магазины + доставки) для активных доставок
    -- б) Убираем дубликаты по location_id (одна точка = одна запись в маршруте)
    -- в) Нумеруем в логическом порядке: магазины → их доставки, сгруппированные по магазину
    
    WITH raw_sequence AS (
        -- Генерируем "сырой" порядок: сначала магазины, затем доставки
        -- Сохраняем метаданные для сортировки и дедупликации
        SELECT 
            pickup_location_id AS location_id,
            1 AS pass_order,      -- первый проход: магазины (приоритет выше)
            0 AS item_order,      -- порядок внутри прохода
            pickup_location_id AS group_key  -- для группировки по магазину
        FROM deliveries
        WHERE courier_id = p_courier_id
          AND actual_delivery_datetime IS NULL
          AND pickup_location_id IS NOT NULL
        
        UNION ALL
        
        SELECT 
            location_id,
            2 AS pass_order,      -- второй проход: доставки
            delivery_id AS item_order,  -- стабильный порядок внутри группы
            pickup_location_id AS group_key  -- привязка к магазину
        FROM deliveries
        WHERE courier_id = p_courier_id
          AND actual_delivery_datetime IS NULL
          AND location_id IS NOT NULL
    ),
    deduplicated AS (
        -- Оставляем первую встречу каждой location_id
        -- Если локация и магазин, и доставка — приоритет у магазина (pass_order=1)
        SELECT DISTINCT ON (location_id)
            location_id,
            group_key,
            pass_order,
            item_order
        FROM raw_sequence
        ORDER BY location_id, pass_order ASC, item_order ASC
    ),
    final_order AS (
        -- Присваиваем sequence_num в итоговом порядке:
        -- 1. По группе магазина (group_key)
        -- 2. Внутри группы: сначала магазин (pass_order=1), потом доставки (pass_order=2)
        -- 3. Внутри типа — по item_order (стабильная сортировка)
        SELECT 
            location_id,
            ROW_NUMBER() OVER (
                ORDER BY group_key, pass_order, item_order
            ) AS sequence_num
        FROM deduplicated
    )
    INSERT INTO route_points (route_id, sequence_num, location_id)
    SELECT v_route_id, sequence_num, location_id
    FROM final_order;

    -- 4. Привязываем все активные доставки к единому маршруту
    UPDATE deliveries 
    SET route_id = v_route_id
    WHERE courier_id = p_courier_id 
      AND actual_delivery_datetime IS NULL
      AND route_id IS DISTINCT FROM v_route_id;
      
    -- 5. Логирование
    RAISE NOTICE '✅ Маршрут % пересчитан: % уникальных точек', 
        v_route_id, 
        (SELECT COUNT(*) FROM route_points WHERE route_id = v_route_id);
END;
$$ LANGUAGE plpgsql;