-- View: public.daily_order_stats

-- DROP VIEW public.daily_order_stats;

CREATE OR REPLACE VIEW public.daily_order_stats
 AS
 SELECT date(created_at) AS order_date,
    count(order_id) AS total_orders,
    sum(total_price) AS total_revenue,
    round(avg(total_weight), 2) AS avg_weight
   FROM orders o
  GROUP BY (date(created_at))
  ORDER BY (date(created_at)) DESC;

ALTER TABLE public.daily_order_stats
    OWNER TO postgres;

-- View: public.order_summary

-- DROP VIEW public.order_summary;

CREATE OR REPLACE VIEW public.order_summary
 AS
 SELECT o.order_id,
    u.full_name AS client_name,
    u.phone AS client_phone,
    l.address AS delivery_location,
    l.latitude,
    l.longitude,
    i.item_name,
    oi.ordered_quantity,
    i.price * oi.ordered_quantity::numeric AS total_price,
    s.status_name,
    o.created_at
   FROM orders o
     JOIN clients c ON o.client_id = c.client_id
     JOIN users u ON u.user_id = c.user_id
     JOIN order_items oi ON o.order_id = oi.order_id
     JOIN items i ON oi.item_id = i.item_id
     JOIN deliveries d ON o.order_id = d.order_id
     JOIN locations l ON d.location_id = l.location_id
     JOIN statuses s ON o.status_id = s.status_id;

ALTER TABLE public.order_summary
    OWNER TO postgres;

GRANT SELECT ON TABLE public.order_summary TO admin_user;
GRANT SELECT ON TABLE public.order_summary TO operator_user;
GRANT ALL ON TABLE public.order_summary TO postgres;