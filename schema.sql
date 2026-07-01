-- ═══════════════════════════════════════════════════════════════════════════
-- LIVROTO SaaS — Schéma PostgreSQL complet
-- À exécuter sur Railway PostgreSQL via psql ou l'interface Railway
-- ═══════════════════════════════════════════════════════════════════════════

-- Extensions
CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "unaccent";   -- recherche sans accents

-- ── TENANTS (Multi-entreprises) ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tenants (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(255) NOT NULL,
    slug        VARCHAR(100) UNIQUE NOT NULL,
    plan        VARCHAR(50) DEFAULT 'free',       -- free | pro | enterprise
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ── UTILISATEURS & AUTH ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email            VARCHAR(255) UNIQUE NOT NULL,
    phone            VARCHAR(30),
    hashed_password  VARCHAR(255) NOT NULL,
    full_name        VARCHAR(255),
    role             VARCHAR(50) DEFAULT 'customer',
    -- Rôles : super_admin | admin | manager | vendor | rider | customer
    is_active        BOOLEAN DEFAULT TRUE,
    is_verified      BOOLEAN DEFAULT FALSE,
    last_login       TIMESTAMPTZ,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_id);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token       VARCHAR(512) UNIQUE NOT NULL,
    expires_at  TIMESTAMPTZ NOT NULL,
    revoked     BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_token ON refresh_tokens(token);

-- ── CATÉGORIES & PRODUITS ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS categories (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name        VARCHAR(255) NOT NULL,
    parent_id   UUID REFERENCES categories(id)
);

CREATE TABLE IF NOT EXISTS products (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    category_id   UUID REFERENCES categories(id),
    name          VARCHAR(255) NOT NULL,
    description   TEXT,
    price         DECIMAL(12,2) NOT NULL CHECK (price > 0),
    price_promo   DECIMAL(12,2) CHECK (price_promo > 0),
    currency      VARCHAR(10) DEFAULT 'USD',
    stock_qty     INTEGER DEFAULT 0 CHECK (stock_qty >= 0),
    stock_alert   INTEGER DEFAULT 5,
    sku           VARCHAR(100),
    is_active     BOOLEAN DEFAULT TRUE,
    images        JSONB DEFAULT '[]',
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_products_tenant ON products(tenant_id);
CREATE INDEX IF NOT EXISTS idx_products_active ON products(tenant_id, is_active);
CREATE INDEX IF NOT EXISTS idx_products_name ON products USING gin(to_tsvector('french', name));

-- Trigger auto updated_at
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER products_updated_at
BEFORE UPDATE ON products
FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ── COMMANDES ─────────────────────────────────────────────────────────────────
CREATE TYPE order_status AS ENUM (
    'pending', 'confirmed', 'preparing', 'delivering', 'delivered', 'cancelled', 'refunded'
);

CREATE TABLE IF NOT EXISTS orders (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    customer_id      UUID NOT NULL REFERENCES users(id),
    rider_id         UUID REFERENCES users(id),
    status           order_status DEFAULT 'pending',
    total_amount     DECIMAL(12,2) NOT NULL CHECK (total_amount >= 0),
    currency         VARCHAR(10) DEFAULT 'USD',
    delivery_address TEXT,
    delivery_lat     DECIMAL(10,8),
    delivery_lng     DECIMAL(11,8),
    notes            TEXT,
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at       TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_orders_tenant ON orders(tenant_id);
CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(tenant_id, status);

CREATE TRIGGER orders_updated_at
BEFORE UPDATE ON orders
FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TABLE IF NOT EXISTS order_items (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id    UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id  UUID NOT NULL REFERENCES products(id),
    quantity    INTEGER NOT NULL CHECK (quantity > 0),
    unit_price  DECIMAL(12,2) NOT NULL,
    subtotal    DECIMAL(12,2) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id);

-- ── PAIEMENTS ─────────────────────────────────────────────────────────────────
CREATE TYPE payment_provider AS ENUM ('flexpay', 'stripe');
CREATE TYPE payment_status AS ENUM ('pending', 'success', 'failed', 'refunded', 'expired');

CREATE TABLE IF NOT EXISTS payments (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id            UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    order_id             UUID REFERENCES orders(id),
    provider             payment_provider NOT NULL,
    provider_ref         VARCHAR(255),
    amount               DECIMAL(12,2) NOT NULL,
    currency             VARCHAR(10) DEFAULT 'USD',
    status               payment_status DEFAULT 'pending',
    phone_number         VARCHAR(30),
    metadata             JSONB DEFAULT '{}',
    webhook_received_at  TIMESTAMPTZ,
    created_at           TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_payments_tenant ON payments(tenant_id);
CREATE INDEX IF NOT EXISTS idx_payments_provider_ref ON payments(provider_ref);
CREATE INDEX IF NOT EXISTS idx_payments_order ON payments(order_id);

-- ── NOTIFICATIONS LOG ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS notifications_log (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id     UUID REFERENCES users(id),
    channel     VARCHAR(30) NOT NULL,     -- whatsapp | sms | push
    recipient   VARCHAR(255) NOT NULL,
    content     TEXT,
    status      VARCHAR(30) DEFAULT 'sent',
    provider_id VARCHAR(255),
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_notif_tenant ON notifications_log(tenant_id, created_at DESC);

-- ── GPS / LOCALISATION ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS location_tracking (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id      UUID NOT NULL REFERENCES users(id),
    order_id     UUID REFERENCES orders(id),
    latitude     DECIMAL(10,8) NOT NULL,
    longitude    DECIMAL(11,8) NOT NULL,
    accuracy     FLOAT,
    speed_kmh    FLOAT,
    recorded_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_location_user ON location_tracking(user_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_location_order ON location_tracking(order_id, recorded_at DESC);

-- ── AUDIT LOG ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_logs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID REFERENCES tenants(id),
    user_id     UUID REFERENCES users(id),
    action      VARCHAR(100) NOT NULL,
    resource    VARCHAR(100),
    resource_id VARCHAR(255),
    ip_address  INET,
    details     JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_tenant ON audit_logs(tenant_id, created_at DESC);

-- ── DONNÉES INITIALES ─────────────────────────────────────────────────────────
INSERT INTO tenants (name, slug, plan) VALUES
    ('LIVROTO Bunia', 'livroto-bunia', 'pro')
ON CONFLICT (slug) DO NOTHING;
