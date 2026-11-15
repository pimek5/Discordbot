"""SQLite persistence for music playback and server settings."""

import sqlite3
from contextlib import closing
from datetime import datetime
from typing import Optional


class MusicDatabase:
    SETTING_COLUMNS = {
        'dj_role_id',
        'mode_247',
        'default_volume',
        'eq_preset',
        'music_channel_id',
    }

    def __init__(self, db_path='music_stats.db'):
        self.db_path = db_path
        self.init_db()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def init_db(self):
        with closing(self._connect()) as connection:
            with connection:
                connection.execute('''
                    CREATE TABLE IF NOT EXISTS play_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        guild_id TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        username TEXT NOT NULL,
                        song_title TEXT NOT NULL,
                        song_url TEXT NOT NULL,
                        song_duration INTEGER,
                        played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        year INTEGER,
                        month INTEGER
                    )
                ''')
                connection.execute('''
                    CREATE TABLE IF NOT EXISTS favorites (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        guild_id TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        song_title TEXT NOT NULL,
                        song_url TEXT NOT NULL,
                        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(guild_id, user_id, song_url)
                    )
                ''')
                connection.execute('''
                    CREATE TABLE IF NOT EXISTS guild_settings (
                        guild_id TEXT PRIMARY KEY,
                        dj_role_id TEXT,
                        mode_247 INTEGER DEFAULT 0,
                        default_volume INTEGER DEFAULT 50,
                        eq_preset TEXT DEFAULT 'normal'
                    )
                ''')
                columns = {
                    row[1] for row in connection.execute('PRAGMA table_info(guild_settings)')
                }
                if 'music_channel_id' not in columns:
                    connection.execute('ALTER TABLE guild_settings ADD COLUMN music_channel_id TEXT')

    def log_play(self, guild_id, user_id, username, song_title, song_url, song_duration):
        now = datetime.now()
        with closing(self._connect()) as connection:
            with connection:
                connection.execute('''
                    INSERT INTO play_history
                    (guild_id, user_id, username, song_title, song_url, song_duration, year, month)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (guild_id, user_id, username, song_title, song_url, song_duration, now.year, now.month))

    def get_user_stats(self, guild_id, user_id, year=None):
        query = '''
            SELECT COUNT(*) AS total_plays, SUM(song_duration) AS total_duration,
                   song_title, song_url, COUNT(*) AS play_count
            FROM play_history
            WHERE guild_id = ? AND user_id = ?
        '''
        parameters = [guild_id, user_id]
        if year is not None:
            query += ' AND year = ?'
            parameters.append(year)
        query += ' GROUP BY song_title, song_url ORDER BY play_count DESC LIMIT 10'
        with closing(self._connect()) as connection:
            return connection.execute(query, parameters).fetchall()

    def get_guild_stats(self, guild_id, year=None):
        year_filter = ' AND year = ?' if year is not None else ''
        parameters = (guild_id, year) if year is not None else (guild_id,)
        with closing(self._connect()) as connection:
            cursor = connection.cursor()
            cursor.execute(f'''
                SELECT user_id, username, COUNT(*) AS play_count
                FROM play_history WHERE guild_id = ?{year_filter}
                GROUP BY user_id ORDER BY play_count DESC LIMIT 5
            ''', parameters)
            top_users = cursor.fetchall()
            cursor.execute(f'''
                SELECT song_title, song_url, COUNT(*) AS play_count
                FROM play_history WHERE guild_id = ?{year_filter}
                GROUP BY song_title, song_url ORDER BY play_count DESC LIMIT 5
            ''', parameters)
            top_songs = cursor.fetchall()
            cursor.execute(f'''
                SELECT COUNT(*), SUM(song_duration)
                FROM play_history WHERE guild_id = ?{year_filter}
            ''', parameters)
            total_plays, total_duration = cursor.fetchone()
        return {
            'top_users': top_users,
            'top_songs': top_songs,
            'total_plays': total_plays or 0,
            'total_duration': total_duration or 0,
        }

    def add_favorite(self, guild_id, user_id, song_title, song_url):
        with closing(self._connect()) as connection:
            try:
                with connection:
                    connection.execute('''
                        INSERT INTO favorites (guild_id, user_id, song_title, song_url)
                        VALUES (?, ?, ?, ?)
                    ''', (guild_id, user_id, song_title, song_url))
                return True
            except sqlite3.IntegrityError:
                return False

    def remove_favorite(self, guild_id, user_id, song_url):
        with closing(self._connect()) as connection:
            with connection:
                cursor = connection.execute('''
                    DELETE FROM favorites WHERE guild_id = ? AND user_id = ? AND song_url = ?
                ''', (guild_id, user_id, song_url))
                return cursor.rowcount > 0

    def get_favorites(self, guild_id, user_id):
        with closing(self._connect()) as connection:
            return connection.execute('''
                SELECT song_title, song_url, added_at
                FROM favorites WHERE guild_id = ? AND user_id = ?
                ORDER BY added_at DESC
            ''', (guild_id, user_id)).fetchall()

    def get_guild_settings(self, guild_id):
        with closing(self._connect()) as connection:
            return connection.execute(
                'SELECT * FROM guild_settings WHERE guild_id = ?', (guild_id,)
            ).fetchone()

    def get_music_channel_id(self, guild_id) -> Optional[int]:
        settings = self.get_guild_settings(guild_id)
        if not settings or len(settings) < 6 or not settings[5]:
            return None
        try:
            return int(settings[5])
        except (TypeError, ValueError):
            return None

    def update_guild_setting(self, guild_id, key, value):
        if key not in self.SETTING_COLUMNS:
            raise ValueError(f'Unsupported guild setting: {key}')
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(f'''
                    INSERT INTO guild_settings (guild_id, {key}) VALUES (?, ?)
                    ON CONFLICT(guild_id) DO UPDATE SET {key} = ?
                ''', (guild_id, value, value))