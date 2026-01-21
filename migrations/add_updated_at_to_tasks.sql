-- Ensure update_updated_at_column() function exists (used by triggers)
-- This function is typically created once and reused across tables

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Note: The tasks table schema should already have:
-- - updated_at TIMESTAMPTZ NULL DEFAULT NOW()
-- - Trigger: update_tasks_updated_at BEFORE UPDATE ON tasks
--
-- This migration ensures the trigger function exists.
-- If the column or trigger don't exist, they should be added via your main schema migration.
