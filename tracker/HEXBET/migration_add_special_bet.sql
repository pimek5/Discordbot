-- Add special_bet column to hexbet_matches table
-- Run this migration to enable SPECIAL BET feature

ALTER TABLE hexbet_matches 
ADD COLUMN IF NOT EXISTS special_bet BOOLEAN DEFAULT FALSE;

-- Also add game_start_at if missing (for older databases)
ALTER TABLE hexbet_matches 
ADD COLUMN IF NOT EXISTS game_start_at TIMESTAMP;

-- Update comment
COMMENT ON COLUMN hexbet_matches.special_bet IS 'Special bets from /hxfind get 1.5x bonus on winnings';
