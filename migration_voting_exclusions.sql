-- Migration: Add exclusion columns to voting_sessions
-- Date: 2025-11-06

-- Add excluded_champions column (array of champion names)
ALTER TABLE voting_sessions 
ADD COLUMN IF NOT EXISTS excluded_champions TEXT[];

-- Add auto_exclude_previous column (automatically exclude previous winners)
ALTER TABLE voting_sessions 
ADD COLUMN IF NOT EXISTS auto_exclude_previous BOOLEAN DEFAULT TRUE;
