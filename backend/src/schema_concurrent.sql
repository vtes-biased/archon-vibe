CREATE EXTENSION IF NOT EXISTS btree_gin;

-- The personal feed's own results.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_objects_tournament_finished_mine
ON objects USING GIN (
    ("full"->'organizers_uids') jsonb_path_ops,
    ("full"->'players') jsonb_path_ops,
    (COALESCE("full"->>'finish', "full"->>'start', "full"->>'modified'))
)
WHERE type = 'tournament' AND deleted_at IS NULL AND "full"->>'state' = 'Finished';
