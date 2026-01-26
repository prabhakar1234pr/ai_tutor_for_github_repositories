-- Allow multiple conversations per user/project/task by dropping the unique constraint.
-- NOTE: Run this in Supabase SQL editor.

ALTER TABLE public.chat_conversations
DROP CONSTRAINT IF EXISTS chat_conversations_user_id_project_id_task_id_key;
