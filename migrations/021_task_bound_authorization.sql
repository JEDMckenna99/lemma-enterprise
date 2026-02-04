-- Task-Bound Authorization for Agent Credentials
--
-- Extends agent credentials with task-specific authorization:
-- - task_description: What the agent is supposed to do
-- - task_hash: SHA256 of task for verification
-- - allowed_paths: API path patterns the agent can access
-- - max_operations: Cap on total operations
-- - task_deviation_count: How many times agent went off-task
--
-- This enables:
-- 1. Scoping authorization to specific tasks, not just time windows
-- 2. Detecting when agents deviate from stated task
-- 3. Rate limiting by operation count, not just time

-- Add task-bound fields to agent_credentials
ALTER TABLE agent_credentials
ADD COLUMN IF NOT EXISTS task_description TEXT,
ADD COLUMN IF NOT EXISTS task_hash VARCHAR(64),
ADD COLUMN IF NOT EXISTS allowed_paths JSONB,
ADD COLUMN IF NOT EXISTS max_operations INTEGER,
ADD COLUMN IF NOT EXISTS task_deviation_count INTEGER DEFAULT 0;

-- Add task tracking to audit log
ALTER TABLE agent_audit_log
ADD COLUMN IF NOT EXISTS path_allowed BOOLEAN DEFAULT TRUE,
ADD COLUMN IF NOT EXISTS task_deviation BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS deviation_reason VARCHAR(255);

-- Index for finding credentials by task hash (for task verification)
CREATE INDEX IF NOT EXISTS idx_agent_credentials_task_hash
    ON agent_credentials(task_hash)
    WHERE task_hash IS NOT NULL;

-- Index for finding deviating agents
CREATE INDEX IF NOT EXISTS idx_agent_audit_log_deviations
    ON agent_audit_log(credential_id, task_deviation)
    WHERE task_deviation = TRUE;

COMMENT ON COLUMN agent_credentials.task_description IS 'Human-readable description of what the agent is authorized to do';
COMMENT ON COLUMN agent_credentials.task_hash IS 'SHA256 hash of task_description for verification';
COMMENT ON COLUMN agent_credentials.allowed_paths IS 'JSON array of allowed API path patterns (supports * wildcards)';
COMMENT ON COLUMN agent_credentials.max_operations IS 'Maximum number of operations allowed (null = unlimited)';
COMMENT ON COLUMN agent_credentials.task_deviation_count IS 'Number of times agent accessed paths outside allowed_paths';
COMMENT ON COLUMN agent_audit_log.path_allowed IS 'Whether the requested path was in allowed_paths';
COMMENT ON COLUMN agent_audit_log.task_deviation IS 'Whether this action was flagged as a task deviation';
COMMENT ON COLUMN agent_audit_log.deviation_reason IS 'Why this action was flagged as a deviation';
