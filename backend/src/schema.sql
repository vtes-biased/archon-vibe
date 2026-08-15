-- Database schema for archon. Applied by db.init_db() on every startup.
--
-- Idempotent by construction: every statement uses IF NOT EXISTS /
-- CREATE OR REPLACE / DROP ... IF EXISTS, so re-running is a no-op. Executed as a
-- single multi-statement script (no parameters), which PostgreSQL parses
-- server-side — including the $$-quoted plpgsql bodies — so no client-side
-- statement splitting is needed.

-- Trigger function to auto-update modified timestamp
CREATE OR REPLACE FUNCTION update_modified_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.modified = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Auth methods table
CREATE TABLE IF NOT EXISTS auth_methods (
    uid TEXT PRIMARY KEY,
    modified TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    data JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_auth_methods_modified
ON auth_methods(modified);
-- Index on user_uid for efficient lookups
CREATE INDEX IF NOT EXISTS idx_auth_methods_user_uid
ON auth_methods((data->>'user_uid'));
-- Unique constraint on method_type + identifier (e.g., only one email per address)
CREATE UNIQUE INDEX IF NOT EXISTS idx_auth_methods_type_identifier
ON auth_methods((data->>'method_type'), (data->>'identifier'));
DROP TRIGGER IF EXISTS auth_methods_modified_trigger ON auth_methods;
CREATE TRIGGER auth_methods_modified_trigger
BEFORE INSERT OR UPDATE ON auth_methods
FOR EACH ROW
EXECUTE FUNCTION update_modified_column();

-- Avatars table - binary storage for user profile images
CREATE TABLE IF NOT EXISTS avatars (
    user_uid TEXT PRIMARY KEY,
    data BYTEA NOT NULL,
    content_type TEXT NOT NULL DEFAULT 'image/webp',
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Banners table - binary storage for per-tournament hero / social-share images.
-- Like avatars: a large binary blob served over HTTP, kept out of the synced
-- objects table (the small banner_path string rides the Tournament object).
CREATE TABLE IF NOT EXISTS banners (
    tournament_uid TEXT PRIMARY KEY,
    data BYTEA NOT NULL,
    content_type TEXT NOT NULL DEFAULT 'image/webp',
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Promo ledger - inventory movements for promotional material. Source of truth
-- for the server-computed stock aggregates (Promo.holdings / User.promo_stock);
-- deliberately NOT a synced object type: officials-only, online-only back-office
-- read via REST (see the wiki/sync.md offline-first carve-out). Rows are
-- append-mostly; corrections are compensating rows (negative qty), never edits.
CREATE TABLE IF NOT EXISTS promo_ledger (
    uid TEXT PRIMARY KEY,
    kind TEXT NOT NULL,       -- 'intake' (BCP -> from) | 'assignment' (from -> to) | 'distribution' (from -> out)
    promo_uid TEXT NOT NULL,
    qty INTEGER NOT NULL,     -- negative = compensating correction
    from_uid TEXT NOT NULL,   -- holder the stock moves from (for intake: the receiving holder)
    to_uid TEXT,              -- assignment target; NULL for intake/distribution
    note TEXT NOT NULL DEFAULT '',
    happened_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT NOT NULL, -- actor who entered the row
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Promo images - binary storage for promo card art (IC-uploaded). Like
-- avatars/banners: the blob stays out of the synced objects table (a versioned
-- image_path string rides the Promo object). Served unauthenticated so the
-- service worker can cache it for offline display (raffle winner, picker).
CREATE TABLE IF NOT EXISTS promo_images (
    promo_uid TEXT PRIMARY KEY,
    data BYTEA NOT NULL,
    content_type TEXT NOT NULL DEFAULT 'image/webp',
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- OAuth clients
CREATE TABLE IF NOT EXISTS oauth_clients (
    uid TEXT PRIMARY KEY,
    modified TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    data JSONB NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_oauth_clients_client_id
ON oauth_clients((data->>'client_id'));
DROP TRIGGER IF EXISTS oauth_clients_modified_trigger ON oauth_clients;
CREATE TRIGGER oauth_clients_modified_trigger
BEFORE INSERT OR UPDATE ON oauth_clients
FOR EACH ROW
EXECUTE FUNCTION update_modified_column();

-- OAuth authorization codes
CREATE TABLE IF NOT EXISTS oauth_authorization_codes (
    uid TEXT PRIMARY KEY,
    modified TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    data JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_oauth_codes_code
ON oauth_authorization_codes((data->>'code'));
DROP TRIGGER IF EXISTS oauth_codes_modified_trigger ON oauth_authorization_codes;
CREATE TRIGGER oauth_codes_modified_trigger
BEFORE INSERT OR UPDATE ON oauth_authorization_codes
FOR EACH ROW
EXECUTE FUNCTION update_modified_column();

-- OAuth tokens
CREATE TABLE IF NOT EXISTS oauth_tokens (
    uid TEXT PRIMARY KEY,
    modified TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    data JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_oauth_tokens_jti
ON oauth_tokens((data->>'token_jti'));
CREATE INDEX IF NOT EXISTS idx_oauth_tokens_client_user
ON oauth_tokens((data->>'client_id'), (data->>'user_uid'));
DROP TRIGGER IF EXISTS oauth_tokens_modified_trigger ON oauth_tokens;
CREATE TRIGGER oauth_tokens_modified_trigger
BEFORE INSERT OR UPDATE ON oauth_tokens
FOR EACH ROW
EXECUTE FUNCTION update_modified_column();

-- OAuth consents
CREATE TABLE IF NOT EXISTS oauth_consents (
    uid TEXT PRIMARY KEY,
    modified TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    data JSONB NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_oauth_consents_user_client
ON oauth_consents((data->>'user_uid'), (data->>'client_id'));
DROP TRIGGER IF EXISTS oauth_consents_modified_trigger ON oauth_consents;
CREATE TRIGGER oauth_consents_modified_trigger
BEFORE INSERT OR UPDATE ON oauth_consents
FOR EACH ROW
EXECUTE FUNCTION update_modified_column();

-- Transient tokens table (auth challenges, magic links, discord state, etc.)
CREATE TABLE IF NOT EXISTS transient_tokens (
    key TEXT PRIMARY KEY,
    data JSONB NOT NULL,
    expires_at TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_transient_tokens_expires
ON transient_tokens(expires_at);

-- Web Push subscriptions (server-side send credentials; never synced — see #314).
-- Like avatars/banners/oauth_*, a side table kept OUT of the synced objects table:
-- these are push endpoints the backend SENDS to, not user-visible display data, so
-- the public/member/full projection pipeline buys nothing and would leak push keys.
-- One row per (browser, endpoint); a user may hold many across devices. Rows are
-- pruned on 404/410 at send time and on owner hard-delete (purge_deleted_objects).
CREATE TABLE IF NOT EXISTS push_subscriptions (
    endpoint TEXT PRIMARY KEY,
    user_uid TEXT NOT NULL,
    p256dh TEXT NOT NULL,
    auth TEXT NOT NULL,
    ua TEXT,
    locale TEXT NOT NULL DEFAULT 'en',  -- browser locale; payload bodies render per-row
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
-- Idempotent for a dev DB that created the table before locale existed.
ALTER TABLE push_subscriptions ADD COLUMN IF NOT EXISTS locale TEXT NOT NULL DEFAULT 'en';
CREATE INDEX IF NOT EXISTS idx_push_subscriptions_user_uid
ON push_subscriptions(user_uid);

-- ---------------------------------------------------------------
-- Unified objects table (users, tournaments, sanctions, leagues, etc.)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS objects (
    uid TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    modified_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP,
    "public" JSONB,
    "member" JSONB,
    "full" JSONB NOT NULL,
    -- calendar_token: per-user secret for the personal .ics feed.
    -- It CANNOT live in public/member/full because all three
    -- projections are broadcast over SSE (the "full" overlay reaches
    -- the owner AND IC / same-country NC/Prince). It is therefore
    -- more private than the most-private projection and gets its own
    -- column, never serialized into any JSONB level. save_object
    -- COALESCEs it (NULL writes preserve), so RMW keeps it; clearing
    -- goes through clear_calendar_token().
    calendar_token TEXT
);
-- Migrate existing deployments to the dedicated column (see above).
ALTER TABLE objects ADD COLUMN IF NOT EXISTS calendar_token TEXT;
-- Composite index for SSE catch-up queries (type + modified_at + uid)
CREATE INDEX IF NOT EXISTS idx_objects_type_modified
ON objects(type, modified_at, uid);
-- Type filter for non-deleted objects
CREATE INDEX IF NOT EXISTS idx_objects_type
ON objects(type) WHERE deleted_at IS NULL;
-- User-specific lookups
CREATE UNIQUE INDEX IF NOT EXISTS idx_objects_user_vekn_id
ON objects(("full"->>'vekn_id'))
WHERE type = 'user' AND "full"->>'vekn_id' IS NOT NULL AND "full"->>'vekn_id' != '';
-- Drop the stale expression index (token is no longer in "full").
DROP INDEX IF EXISTS idx_objects_user_calendar_token;
CREATE INDEX IF NOT EXISTS idx_objects_user_calendar_token
ON objects(calendar_token)
WHERE type = 'user' AND calendar_token IS NOT NULL;
-- Tournament VEKN external ID lookup
CREATE INDEX IF NOT EXISTS idx_objects_tournament_vekn
ON objects(("full"->'external_ids'->>'vekn'))
WHERE type = 'tournament' AND "full"->'external_ids'->>'vekn' IS NOT NULL;
-- Backs the personal-overlay organizer lookup (`organizers_uids @> [uid]`), run on every
-- member reconnect (ungated by `since`) — else a seq-scan of all tournaments each time.
-- jsonb_path_ops is smaller than the default opclass and supports @> (but not `?`, hence @>).
CREATE INDEX IF NOT EXISTS idx_objects_tournament_organizers
ON objects USING GIN (("full"->'organizers_uids') jsonb_path_ops)
WHERE type = 'tournament';
-- Deck lookups by tournament and user
CREATE INDEX IF NOT EXISTS idx_objects_deck_tournament
ON objects(("full"->>'tournament_uid'))
WHERE type = 'deck';
CREATE INDEX IF NOT EXISTS idx_objects_deck_user
ON objects(("full"->>'user_uid'))
WHERE type = 'deck';
-- Sanction lookup by user
CREATE INDEX IF NOT EXISTS idx_objects_sanction_user
ON objects(("full"->>'user_uid'))
WHERE type = 'sanction';
-- Sanction lookup by tournament
CREATE INDEX IF NOT EXISTS idx_objects_sanction_tournament
ON objects(("full"->>'tournament_uid'))
WHERE type = 'sanction';
-- Trigger function for objects table (uses modified_at, not modified)
CREATE OR REPLACE FUNCTION update_objects_modified_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.modified_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS objects_modified_trigger ON objects;
CREATE TRIGGER objects_modified_trigger
BEFORE INSERT OR UPDATE ON objects
FOR EACH ROW
EXECUTE FUNCTION update_objects_modified_at();

-- Note: vekn_id_counter table is no longer used.
-- VEKN IDs are now allocated by finding the first gap >= 1000000.
