-- Migration: Add "day0_ready" status to projects table
-- This allows the frontend to show clickable project cards once Day 0 content is ready

-- Drop the existing check constraint
ALTER TABLE projects DROP CONSTRAINT IF EXISTS "Projects_status_check";

-- Add the updated check constraint with "day0_ready" status
ALTER TABLE projects ADD CONSTRAINT "Projects_status_check"
CHECK (status IN ('created', 'processing', 'day0_ready', 'ready', 'failed'));
