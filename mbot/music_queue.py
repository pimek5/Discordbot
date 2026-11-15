"""Per-guild playback queue state."""

import random
from collections import deque
from datetime import datetime


class Song:
    """Track metadata and requester state stored in a music queue."""

    def __init__(self, source, requester, query=None, platform_source='YouTube'):
        self.source = source
        self.requester = requester
        self.query = query
        self.platform_source = getattr(source, 'platform_source', platform_source) if source else platform_source
        if source:
            self.title = source.title
            self.url = source.url
            self.thumbnail = source.thumbnail
            self.duration = source.duration
        else:
            self.title = query or "Loading..."
            self.url = None
            self.thumbnail = None
            self.duration = None
        self.added_at = datetime.now()


class MusicQueue:
    """Manage queued, current, and recently played tracks for one guild."""

    def __init__(self):
        self.queue = deque()
        self.current = None
        self.volume = 0.5
        self.loop_mode = 'off'
        self.history = deque(maxlen=20)
        self.skip_votes = set()
        self.autoplay = False
        self.last_message_id = None

    def add(self, song):
        self.queue.append(song)

    def next(self):
        if self.loop_mode == 'track' and self.current:
            return self.current

        if self.current:
            self.history.append(self.current)

        if self.queue:
            self.current = self.queue.popleft()
            return self.current

        if self.loop_mode == 'queue' and self.history:
            self.queue.extend(self.history)
            self.history.clear()
            return self.next()

        return None

    def previous(self):
        if not self.history:
            return None

        if self.current:
            self.queue.appendleft(self.current)
        self.current = self.history.pop()
        return self.current

    def clear(self):
        self.queue.clear()
        self.current = None
        self.skip_votes.clear()

    def shuffle(self):
        queue_items = list(self.queue)
        random.shuffle(queue_items)
        self.queue = deque(queue_items)

    def remove(self, index):
        if 0 <= index < len(self.queue):
            del self.queue[index]
            return True
        return False

    def is_empty(self):
        return not self.queue