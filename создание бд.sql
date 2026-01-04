-- ========================================
-- Таблица: roles (справочник ролей пользователей)
-- ========================================
CREATE TABLE roles (
    role_id SERIAL PRIMARY KEY,
    role_name VARCHAR(50) UNIQUE NOT NULL, -- 'client', 'courier', 'operator', 'admin'
	description TEXT
);

-- ========================================
-- Таблица: users (пользователи системы)
-- ========================================
CREATE TABLE users (
    user_id SERIAL PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    phone VARCHAR(20),
    password_hash VARCHAR(255) NOT NULL,
    role_id INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (role_id) REFERENCES roles(role_id)
);

-- ========================================
-- Таблица: clients (клиенты)
-- ========================================
CREATE TABLE clients (
    client_id SERIAL PRIMARY KEY,
    user_id INT UNIQUE NOT NULL,
    address TEXT,
	date_of_birth DATE,
	sex VARCHAR(6),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

-- ========================================
-- Таблица: vehicles (транспорт)
-- ========================================
CREATE TABLE vehicles (
    vehicle_id SERIAL PRIMARY KEY,
    type VARCHAR(50),
    license_plate VARCHAR(20) UNIQUE,
    capacity NUMERIC(6,2), -- в кг или м³
    status VARCHAR(30) DEFAULT 'active' -- 'active', 'maintenance', 'out_of_service'
);

-- ========================================
-- Таблица: couriers (курьеры)
-- ========================================
CREATE TABLE couriers (
    courier_id SERIAL PRIMARY KEY,
    user_id INT UNIQUE NOT NULL,
    active BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

-- ========================================
-- Таблица: couriers_vehicles (курьеры-транспорт)
-- ========================================
CREATE TABLE couriers_vehicles (
    courier_id INT,
    vehicle_id INT,
    assigned_at TIMESTAMP,
	unassigned_at TIMESTAMP DEFAULT NULL,
	PRIMARY KEY (courier_id, vehicle_id),
    FOREIGN KEY (courier_id) REFERENCES couriers(courier_id),
	FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id)
);

-- ========================================
-- Таблица: statuses (справочник статусов)
-- ========================================
CREATE TABLE statuses (
    status_id SERIAL PRIMARY KEY,
    status_name VARCHAR(30) UNIQUE NOT NULL -- 'created', 'in_transit', 'delivered', 'cancelled'
);

-- ========================================
-- Таблица: orders (заказы)
-- ========================================
CREATE TABLE orders (
    order_id SERIAL PRIMARY KEY,
    client_id INT NOT NULL,
    status_id INT NOT NULL,
    total_weight NUMERIC(10,2),
    total_price NUMERIC(12,2),
    comments TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (client_id) REFERENCES clients(client_id),
    FOREIGN KEY (status_id) REFERENCES statuses(status_id)
);

-- ========================================
-- Таблица: items (ассортимент)
-- ========================================
CREATE TABLE items (
    item_id SERIAL PRiMARY KEY,
	item_name VARCHAR(100),
	description VARCHAR(500),
	price NUMERIC(6, 2),
	weight_kg NUMERIC(6, 2),
	length_cm NUMERIC(6, 2),
	width_cm NUMERIC(6, 2),
	height_cm NUMERIC(6, 2)
);


-- ========================================
-- Таблица: order_items (состав заказа)
-- ========================================
CREATE TABLE order_items (
    order_id INT NOT NULL,
    item_id INT NOT NULL,
	ordered_quantity INT CHECK(ordered_quantity > 0),
	PRIMARY KEY (order_id, item_id),
    FOREIGN KEY (order_id) REFERENCES orders(order_id) ON DELETE CASCADE,
	FOREIGN KEY (item_id) REFERENCES items(item_id) ON DELETE CASCADE
);

drop table order_items
-- ========================================
-- Таблица: location_types (типы локаций: клиенты, магазины и т.д.)
-- ========================================
CREATE TABLE location_types (
    location_type_id SERIAL PRIMARY KEY,
    location_type VARCHAR(50)
);


-- ========================================
-- Таблица: locations (точки маршрута: склады, клиенты и т.д.)
-- ========================================
CREATE TABLE locations (
    location_id SERIAL PRIMARY KEY,
    location_type_id INT NOT NULL, -- 'warehouse', 'pickup', 'delivery_point', 'client'
    address VARCHAR(500),
    latitude DECIMAL(9,6),
    longitude DECIMAL(9,6),
	FOREIGN KEY (location_type_id) REFERENCES location_types(location_type_id)
);

-- ========================================
-- Таблица: store_stock (запас товара в магазине)
-- ========================================
CREATE TABLE store_stock (
    location_id INT NOT NULL,
    item_id INT NOT NULL,
    quantity INT,
	updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (location_id, item_id),
	FOREIGN KEY (location_id) REFERENCES locations(location_id),
	FOREIGN KEY (item_id) REFERENCES items(item_id)
);


-- ========================================
-- Таблица: routes (маршруты)
-- ========================================
CREATE TABLE routes (
    route_id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    total_distance_km NUMERIC(6,2),
    total_time_min INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ========================================
-- Таблица: route_points (точки маршрута в порядке следования)
-- ========================================
CREATE TABLE route_points (
    route_id INT NOT NULL,
    sequence_num INT NOT NULL, -- порядок точки в маршруте
    location_id INT NOT NULL,
    expected_arrival_time TIMESTAMP,
    actual_arrival_time TIMESTAMP,
	PRIMARY KEY (route_id, sequence_num),
    FOREIGN KEY (route_id) REFERENCES routes(route_id),
    FOREIGN KEY (location_id) REFERENCES locations(location_id)
);

-- ========================================
-- Таблица: deliveries (доставки)
-- ========================================
CREATE TABLE deliveries (
    delivery_id SERIAL PRIMARY KEY,
    order_id INT NOT NULL,
    courier_id INT NOT NULL,
    route_id INT NOT NULL,
	location_id INT NOT NULL,
    actual_delivery_datetime TIMESTAMP, -- новое поле
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (order_id) REFERENCES orders(order_id),
    FOREIGN KEY (courier_id) REFERENCES couriers(courier_id),
    FOREIGN KEY (route_id) REFERENCES routes(route_id),
    FOREIGN KEY (location_id) REFERENCES locations(location_id)
);

-- ========================================
-- Таблица: audit_log (логирование изменений)
-- ========================================
drop table audit_log
CREATE TABLE audit_log (
    log_id SERIAL PRIMARY KEY,
    table_name VARCHAR(50) NOT NULL,
    action VARCHAR(10) NOT NULL, -- 'INSERT', 'UPDATE', 'DELETE'
    old_values JSONB,
    new_values JSONB,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ========================================
-- Индексы для производительности
-- ========================================
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_orders_client_id ON orders(client_id);
CREATE INDEX idx_orders_status_id ON orders(status_id);
CREATE INDEX idx_deliveries_order_id ON deliveries(order_id);
CREATE INDEX idx_deliveries_courier_id ON deliveries(courier_id);
CREATE INDEX idx_deliveries_route_id ON deliveries(route_id);
CREATE INDEX idx_route_points_route_id ON route_points(route_id);
CREATE INDEX idx_route_points_location_id ON route_points(location_id);
CREATE INDEX idx_order_items_order_id ON order_items(order_id);

INSERT INTO roles (role_name, description)
VALUES 
('admin', 'Manage users, settings, and system directories'),
('operator', 'Create orders, assign couriers, monitor deliveries'),
('courier', 'Make deliveries and update order statuses'),
('client', 'Create orders and track their status');