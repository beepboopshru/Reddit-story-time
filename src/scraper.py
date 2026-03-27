"""
scraper.py — Reddit story acquisition module.
Uses PRAW to fetch trending stories from configurable subreddits.
"""

import praw
import prawcore
from dataclasses import dataclass
from utils import get_env, clean_text, truncate_text


@dataclass
class RedditStory:
    """Represents a single scraped Reddit story."""
    title: str
    body: str
    subreddit: str
    score: int
    url: str
    id: str


class RedditScraper:
    """
    Scrapes top/hot stories from Reddit using PRAW.

    Usage:
        scraper = RedditScraper()
        stories = scraper.fetch_stories(limit=5)
    """

    def __init__(self):
        self.reddit = praw.Reddit(
            client_id=get_env("PRAW_CLIENT_ID"),
            client_secret=get_env("PRAW_CLIENT_SECRET"),
            user_agent=get_env("PRAW_USER_AGENT", "ReelMaker/1.0"),
        )
        raw = get_env("SUBREDDITS", "AmItheAsshole,nosleep")
        self.subreddits = [s.strip() for s in raw.split(",")]

    def fetch_stories(
        self,
        limit: int = 5,
        sort: str = "hot",
        min_length: int = 200,
        max_length: int = 5000,
    ) -> list[RedditStory]:
        """
        Fetch stories from configured subreddits.

        Args:
            limit:      Max stories to return across all subreddits.
            sort:       Sorting method — 'hot', 'top', or 'new'.
            min_length: Minimum body character count (skip very short posts).
            max_length: Maximum body character count before truncation.

        Returns:
            A list of RedditStory objects, cleaned and ready for TTS.
        """
        stories: list[RedditStory] = []

        for sub_name in self.subreddits:
            subreddit = self.reddit.subreddit(sub_name)

            if sort == "top":
                posts = subreddit.top(time_filter="day", limit=limit)
            elif sort == "new":
                posts = subreddit.new(limit=limit)
            else:
                posts = subreddit.hot(limit=limit)

            for post in posts:
                # Skip stickied, media-only, or very short posts
                if post.stickied or not post.selftext:
                    continue
                if len(post.selftext) < min_length:
                    continue

                cleaned_body = clean_text(post.selftext)
                cleaned_body = truncate_text(cleaned_body, max_length)

                stories.append(RedditStory(
                    title=post.title,
                    body=cleaned_body,
                    subreddit=sub_name,
                    score=post.score,
                    url=post.url,
                    id=post.id,
                ))

                if len(stories) >= limit:
                    return stories

        return stories

    def fetch_post_by_url(self, url: str) -> tuple[RedditStory, str]:
        """
        Fetch a single Reddit post by its URL.

        Args:
            url: Full Reddit post URL.

        Returns:
            A RedditStory object with cleaned text.

        Raises:
            ValueError: If the post is deleted, removed, a link post, or the URL is invalid.
            ConnectionError: If PRAW auth or network fails.
        """
        try:
            submission = self.reddit.submission(url=url)
            # Force-load the submission attributes (triggers network call)
            _ = submission.title
        except prawcore.exceptions.NotFound:
            raise ValueError("Post not found. The URL may be invalid or the post may have been deleted.")
        except prawcore.exceptions.Forbidden:
            raise ValueError("Cannot access this post. The subreddit may be private or quarantined.")
        except prawcore.exceptions.ResponseException as e:
            raise ConnectionError(f"Reddit API error: {e}")
        except prawcore.exceptions.RequestException as e:
            raise ConnectionError(f"Network error connecting to Reddit: {e}")
        except Exception as e:
            raise ValueError(f"Invalid Reddit URL or unexpected error: {e}")

        # Check for deleted / removed posts
        body = submission.selftext or ""
        if not body or body.strip() in ("[deleted]", "[removed]", ""):
            if submission.is_self:
                raise ValueError("This post has been deleted or removed and has no body text.")
            else:
                raise ValueError("This is a link post with no body text. Only text posts (self posts) are supported.")

        cleaned_body = clean_text(body)
        if len(cleaned_body) < 20:
            raise ValueError("Post body is too short to generate a reel from.")

        return RedditStory(
            title=submission.title,
            body=cleaned_body,
            subreddit=submission.subreddit.display_name,
            score=submission.score,
            url=submission.url,
            id=submission.id,
        ), (f"u/{submission.author.name}" if submission.author else "u/[deleted]")


# ─── Quick test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    scraper = RedditScraper()
    for story in scraper.fetch_stories(limit=3):
        print(f"[r/{story.subreddit}] ({story.score}↑)  {story.title}")
        print(f"  {story.body[:120]}...\n")
