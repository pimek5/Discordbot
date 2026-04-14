"""
HEXBET Achievements & Badges System
Gamification layer - unlock badges for milestones
"""

import discord
from enum import Enum
from datetime import datetime, timedelta
import logging
from typing import List, Dict, Optional

logger = logging.getLogger('hexbet_achievements')


class AchievementTier(Enum):
    """Achievement rarity tiers"""
    COMMON = 0
    RARE = 1
    EPIC = 2
    LEGENDARY = 3


class Achievement:
    """Single achievement/badge definition"""
    
    def __init__(self, achievement_id: str, name: str, description: str, 
                 emoji: str, tier: AchievementTier, condition_fn=None):
        self.id = achievement_id
        self.name = name
        self.description = description
        self.emoji = emoji
        self.tier = tier
        self.condition_fn = condition_fn  # Function that checks if user earned it
    
    def get_display(self) -> str:
        """Get badge display string"""
        tier_colors = {
            AchievementTier.COMMON: "⚪",
            AchievementTier.RARE: "🔵",
            AchievementTier.EPIC: "🟣",
            AchievementTier.LEGENDARY: "🟡"
        }
        return f"{tier_colors[self.tier]} {self.emoji} **{self.name}**"


class AchievementRegistry:
    """Registry of all available achievements"""
    
    ACHIEVEMENTS = {
        # Beginner Achievements
        "first_bet": Achievement(
            "first_bet",
            "First Steps",
            "Place your first bet",
            "🎰",
            AchievementTier.COMMON
        ),
        
        "ten_bets": Achievement(
            "ten_bets",
            "Getting Started",
            "Place 10 bets",
            "🎲",
            AchievementTier.COMMON
        ),
        
        "fifty_bets": Achievement(
            "fifty_bets",
            "Dedicated Bettor",
            "Place 50 bets",
            "💯",
            AchievementTier.RARE
        ),
        
        "hundred_bets": Achievement(
            "hundred_bets",
            "Betting Veteran",
            "Place 100 bets",
            "🏆",
            AchievementTier.EPIC
        ),
        
        # Winning Achievements
        "first_win": Achievement(
            "first_win",
            "Winner!",
            "Win your first bet",
            "✅",
            AchievementTier.COMMON
        ),
        
        "streak_five": Achievement(
            "streak_five",
            "On Fire 🔥",
            "5-bet winning streak",
            "🔥",
            AchievementTier.RARE
        ),
        
        "streak_ten": Achievement(
            "streak_ten",
            "Unstoppable",
            "10-bet winning streak",
            "⚡",
            AchievementTier.EPIC
        ),
        
        "perfect_day": Achievement(
            "perfect_day",
            "Perfect Day",
            "100% win rate in a day (min 5 bets)",
            "✨",
            AchievementTier.EPIC
        ),
        
        # Profit Achievements
        "profit_1k": Achievement(
            "profit_1k",
            "1K Club",
            "Earn 1,000 tokens profit",
            "💰",
            AchievementTier.RARE
        ),
        
        "profit_5k": Achievement(
            "profit_5k",
            "5K Elite",
            "Earn 5,000 tokens profit",
            "💵",
            AchievementTier.EPIC
        ),
        
        "profit_10k": Achievement(
            "profit_10k",
            "10K Legend",
            "Earn 10,000 tokens profit",
            "👑",
            AchievementTier.LEGENDARY
        ),
        
        # Win Rate Achievements
        "wr_55": Achievement(
            "wr_55",
            "Above Average",
            "Achieve 55% win rate (min 20 bets)",
            "📈",
            AchievementTier.RARE
        ),
        
        "wr_60": Achievement(
            "wr_60",
            "Expert Bettor",
            "Achieve 60% win rate (min 30 bets)",
            "🎯",
            AchievementTier.EPIC
        ),
        
        "wr_65": Achievement(
            "wr_65",
            "Legendary Predictor",
            "Achieve 65% win rate (min 50 bets)",
            "🌟",
            AchievementTier.LEGENDARY
        ),
        
        # ROI Achievements
        "roi_50": Achievement(
            "roi_50",
            "Profit Master",
            "Achieve 50% ROI (min 25 bets)",
            "📊",
            AchievementTier.EPIC
        ),
        
        "roi_100": Achievement(
            "roi_100",
            "ROI King",
            "Achieve 100% ROI (min 40 bets)",
            "💎",
            AchievementTier.LEGENDARY
        ),
        
        # Volume Achievements
        "volume_50k": Achievement(
            "volume_50k",
            "High Roller",
            "Wager 50,000 tokens total",
            "🎲",
            AchievementTier.RARE
        ),
        
        "volume_100k": Achievement(
            "volume_100k",
            "Whale",
            "Wager 100,000 tokens total",
            "🐋",
            AchievementTier.EPIC
        ),
        
        # Special Achievements
        "comeback": Achievement(
            "comeback",
            "Comeback King",
            "Recover from -50% ROI to positive",
            "🆙",
            AchievementTier.EPIC
        ),
        
        "all_sides": Achievement(
            "all_sides",
            "Balanced",
            "60% win rate on both blue and red",
            "⚖️",
            AchievementTier.RARE
        ),
        
        "early_riser": Achievement(
            "early_riser",
            "Early Riser",
            "Claim daily reward 7 days in a row",
            "🌅",
            AchievementTier.RARE
        ),
        
        "social_butterfly": Achievement(
            "social_butterfly",
            "Social Butterfly",
            "Follow 5 different players",
            "🦋",
            AchievementTier.RARE
        ),
    }
    
    @classmethod
    def get_achievement(cls, achievement_id: str) -> Optional[Achievement]:
        """Get achievement by ID"""
        return cls.ACHIEVEMENTS.get(achievement_id)
    
    @classmethod
    def get_all(cls) -> Dict[str, Achievement]:
        """Get all achievements"""
        return cls.ACHIEVEMENTS
    
    @classmethod
    def get_by_tier(cls, tier: AchievementTier) -> List[Achievement]:
        """Get all achievements of a specific tier"""
        return [a for a in cls.ACHIEVEMENTS.values() if a.tier == tier]


class UserAchievements:
    """Manages user achievements"""
    
    def __init__(self, user_id: int, db):
        self.user_id = user_id
        self.db = db
        self.earned_achievements = set()
        self._load_earned()
    
    def _load_earned(self):
        """Load earned achievements from database"""
        try:
            earned = self.db.get_user_achievements(self.user_id)
            self.earned_achievements = set(a['achievement_id'] for a in earned)
            logger.debug(f"Loaded {len(self.earned_achievements)} achievements for user {self.user_id}")
        except Exception as e:
            logger.error(f"Failed to load achievements for user {self.user_id}: {e}")
    
    def has_achievement(self, achievement_id: str) -> bool:
        """Check if user has earned achievement"""
        return achievement_id in self.earned_achievements
    
    def earn_achievement(self, achievement_id: str) -> bool:
        """Award achievement to user"""
        if achievement_id in self.earned_achievements:
            return False  # Already earned
        
        try:
            self.db.add_user_achievement(self.user_id, achievement_id)
            self.earned_achievements.add(achievement_id)
            logger.info(f"User {self.user_id} earned achievement: {achievement_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to award achievement to user {self.user_id}: {e}")
            return False
    
    def get_earned_count(self) -> int:
        """Get total earned achievements"""
        return len(self.earned_achievements)
    
    def get_sorted_achievements(self) -> List[Achievement]:
        """Get earned achievements sorted by tier"""
        achieved = [
            AchievementRegistry.get_achievement(aid) 
            for aid in self.earned_achievements
        ]
        return sorted(
            [a for a in achieved if a],
            key=lambda x: x.tier.value,
            reverse=True
        )
    
    def format_badges(self) -> str:
        """Get formatted badge string for user profile"""
        achievements = self.get_sorted_achievements()
        if not achievements:
            return "*No achievements yet*"
        
        # Show top 5 by tier
        badge_str = " ".join(a.emoji for a in achievements[:5])
        if len(achievements) > 5:
            badge_str += f" +{len(achievements)-5}"
        return badge_str


class AchievementChecker:
    """System to check and award achievements"""
    
    def __init__(self, db, hexbet_cog):
        self.db = db
        self.hexbet_cog = hexbet_cog
    
    async def check_achievements(self, user_id: int, trigger: str = None):
        """Check and award achievements based on user stats"""
        try:
            user_achievements = UserAchievements(user_id, self.db)
            stats = self.db.get_user_betting_stats(user_id)
            
            if not stats:
                return []
            
            newly_earned = []
            
            # Check each achievement
            if not user_achievements.has_achievement("first_bet"):
                if stats['total_bets'] >= 1:
                    if user_achievements.earn_achievement("first_bet"):
                        newly_earned.append("first_bet")
            
            if not user_achievements.has_achievement("ten_bets"):
                if stats['total_bets'] >= 10:
                    if user_achievements.earn_achievement("ten_bets"):
                        newly_earned.append("ten_bets")
            
            if not user_achievements.has_achievement("fifty_bets"):
                if stats['total_bets'] >= 50:
                    if user_achievements.earn_achievement("fifty_bets"):
                        newly_earned.append("fifty_bets")
            
            if not user_achievements.has_achievement("hundred_bets"):
                if stats['total_bets'] >= 100:
                    if user_achievements.earn_achievement("hundred_bets"):
                        newly_earned.append("hundred_bets")
            
            if not user_achievements.has_achievement("first_win"):
                if stats['wins'] >= 1:
                    if user_achievements.earn_achievement("first_win"):
                        newly_earned.append("first_win")
            
            if not user_achievements.has_achievement("wr_55"):
                if stats['total_bets'] >= 20 and stats['win_rate'] >= 55:
                    if user_achievements.earn_achievement("wr_55"):
                        newly_earned.append("wr_55")
            
            if not user_achievements.has_achievement("wr_60"):
                if stats['total_bets'] >= 30 and stats['win_rate'] >= 60:
                    if user_achievements.earn_achievement("wr_60"):
                        newly_earned.append("wr_60")
            
            if not user_achievements.has_achievement("profit_1k"):
                if stats['roi'] > 0 and (stats['total_payout'] - stats['total_wagered']) >= 1000:
                    if user_achievements.earn_achievement("profit_1k"):
                        newly_earned.append("profit_1k")
            
            # Check streak achievements
            if stats['streak'] >= 5 and not user_achievements.has_achievement("streak_five"):
                if user_achievements.earn_achievement("streak_five"):
                    newly_earned.append("streak_five")
            
            if stats['streak'] >= 10 and not user_achievements.has_achievement("streak_ten"):
                if user_achievements.earn_achievement("streak_ten"):
                    newly_earned.append("streak_ten")
            
            return newly_earned
        
        except Exception as e:
            logger.error(f"Error checking achievements for user {user_id}: {e}")
            return []
