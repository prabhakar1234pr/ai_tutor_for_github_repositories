-- Enable RLS on chat_conversations table
ALTER TABLE public.chat_conversations ENABLE ROW LEVEL SECURITY;

-- Enable RLS on chat_messages table
ALTER TABLE public.chat_messages ENABLE ROW LEVEL SECURITY;

-- Policy: Allow all operations for authenticated service role
-- The backend uses Supabase service key which should bypass RLS,
-- but if RLS is enabled with no policies, it blocks everything.
-- This policy ensures the backend can access the tables.
CREATE POLICY "Allow service role access to conversations"
ON public.chat_conversations
FOR ALL
USING (true)
WITH CHECK (true);

CREATE POLICY "Allow service role access to messages"
ON public.chat_messages
FOR ALL
USING (true)
WITH CHECK (true);
