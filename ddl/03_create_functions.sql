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
