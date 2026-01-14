"""
HEXBET Webhook Notifications
Sends bet updates to configured webhooks
"""

import aiohttp
import asyncio
import logging
from typing import Dict, List, Optional
from datetime import datetime

from HEXBET.hexbet_config_database import get_hexbet_config_db

logger = logging.getLogger('hexbet_webhooks')


class HexbetWebhookManager:
    """Manages webhook notifications for HEXBET events"""
    
    def __init__(self):
        self.config_db = get_hexbet_config_db()
    
    async def send_new_bet_notification(
        self,
        match_id: int,
        match_data: Dict,
        game_mode: str = "soloq"
    ):
        """Send notification about a new bet being posted"""
        try:
            webhooks = self.config_db.get_all_webhooks()
            active_webhooks = [wh for wh in webhooks if wh.get('notify_new_bets')]
            
            if not active_webhooks:
                logger.debug("No webhooks configured for new bet notifications")
                return
            
            # Prepare payload - simplified to avoid serialization issues
            payload = {
                "event": "new_bet",
                "match_id": match_id,
                "game_mode": game_mode,
                "data": {
                    "platform": match_data.get('platform'),
                    "game_id": match_data.get('game_id'),
                    "odds": {
                        "blue": match_data.get('odds_blue', 1.5),
                        "red": match_data.get('odds_red', 1.5)
                    },
                    "special_bet": match_data.get('special_bet', False),
                    "posted_at": datetime.now().isoformat()
                },
                "timestamp": datetime.now().isoformat()
            }
            
            # Send to all active webhooks
            await self._send_to_webhooks(active_webhooks, payload, "new bet")
            
        except Exception as e:
            logger.error(f"Error sending new bet notification: {e}")
    
    async def send_bet_result_notification(
        self,
        match_id: int,
        winner: str,
        match_data: Dict
    ):
        """Send notification about bet result"""
        try:
            webhooks = self.config_db.get_all_webhooks()
            active_webhooks = [wh for wh in webhooks if wh.get('notify_bet_results')]
            
            if not active_webhooks:
                logger.debug("No webhooks configured for bet result notifications")
                return
            
            # Prepare payload
            payload = {
                "event": "bet_result",
                "match_id": match_id,
                "winner": winner,
                "data": {
                    "platform": match_data.get('platform'),
                    "game_id": match_data.get('game_id'),
                    "final_odds": {
                        "blue": match_data.get('blue_team', {}).get('odds', 1.5),
                        "red": match_data.get('red_team', {}).get('odds', 1.5)
                    },
                    "payouts_count": len(match_data.get('payouts', [])),
                    "total_payout": sum(p['payout'] for p in match_data.get('payouts', [])),
                    "winners_count": sum(1 for p in match_data.get('payouts', []) if p['won']),
                    "settled_at": datetime.now().isoformat()
                },
                "timestamp": datetime.now().isoformat()
            }
            
            # Send to all active webhooks
            await self._send_to_webhooks(active_webhooks, payload, "bet result")
            
        except Exception as e:
            logger.error(f"Error sending bet result notification: {e}")
    
    async def send_leaderboard_update(
        self,
        leaderboard_data: List[Dict],
        update_type: str = "periodic"
    ):
        """Send leaderboard update notification"""
        try:
            webhooks = self.config_db.get_all_webhooks()
            active_webhooks = [wh for wh in webhooks if wh.get('notify_leaderboard')]
            
            if not active_webhooks:
                logger.debug("No webhooks configured for leaderboard notifications")
                return
            
            # Prepare payload
            payload = {
                "event": "leaderboard_update",
                "update_type": update_type,
                "data": {
                    "top_10": leaderboard_data[:10] if len(leaderboard_data) > 10 else leaderboard_data,
                    "total_players": len(leaderboard_data),
                    "updated_at": datetime.now().isoformat()
                },
                "timestamp": datetime.now().isoformat()
            }
            
            # Send to all active webhooks
            await self._send_to_webhooks(active_webhooks, payload, "leaderboard update")
            
        except Exception as e:
            logger.error(f"Error sending leaderboard update: {e}")
    
    async def send_live_odds_update(
        self,
        match_id: int,
        new_odds: Dict
    ):
        """Send live odds update (during game)"""
        try:
            webhooks = self.config_db.get_all_webhooks()
            active_webhooks = [wh for wh in webhooks if wh.get('notify_new_bets')]  # Reuse new_bets filter
            
            if not active_webhooks:
                return
            
            # Prepare payload
            payload = {
                "event": "odds_update",
                "match_id": match_id,
                "data": {
                    "blue_odds": new_odds.get('blue'),
                    "red_odds": new_odds.get('red'),
                    "blue_bets": new_odds.get('blue_bets', 0),
                    "red_bets": new_odds.get('red_bets', 0),
                    "updated_at": datetime.now().isoformat()
                },
                "timestamp": datetime.now().isoformat()
            }
            
            # Send to all active webhooks
            await self._send_to_webhooks(active_webhooks, payload, "odds update")
            
        except Exception as e:
            logger.error(f"Error sending odds update: {e}")
    
    async def _send_to_webhooks(
        self,
        webhooks: List[Dict],
        payload: Dict,
        event_name: str
    ):
        """Send payload to all webhooks"""
        webhook_count = 0
        
        async with aiohttp.ClientSession() as session:
            for webhook in webhooks:
                webhook_url = webhook.get('webhook_url')
                guild_id = webhook.get('guild_id')
                
                if not webhook_url:
                    continue
                
                webhook_count += 1
                
                try:
                    async with session.post(
                        webhook_url,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as response:
                        if response.status == 200:
                            logger.info(f"🪝 Webhook sent to guild {guild_id}: {event_name}")
                        else:
                            response_text = await response.text()
                            logger.warning(f"⚠️ Webhook failed for guild {guild_id} (status: {response.status}): {response_text[:200]}")
                except asyncio.TimeoutError:
                    logger.warning(f"⚠️ Webhook timeout for guild {guild_id}")
                except Exception as e:
                    logger.warning(f"⚠️ Error sending webhook to guild {guild_id}: {e}")
        
        if webhook_count > 0:
            logger.info(f"✅ Webhook notifications sent: {webhook_count} guild(s) notified for {event_name}")


# Singleton instance
_webhook_manager = None


def get_webhook_manager() -> HexbetWebhookManager:
    """Get singleton webhook manager"""
    global _webhook_manager
    if _webhook_manager is None:
        _webhook_manager = HexbetWebhookManager()
    return _webhook_manager
