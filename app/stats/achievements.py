"""Achievement definitions for the stats system."""

from app.core.config import get_settings
from app.stats.models import Achievement


def get_achievements() -> dict[str, Achievement]:
    """Get all achievement definitions with thresholds from settings.

    Returns:
        Dictionary mapping achievement ID to Achievement object
    """
    settings = get_settings()

    achievements = {
        # Daily achievements (repeatable)
        "night_owl": Achievement(
            id="night_owl",
            name="Night Owl",
            emoji="🦉",
            description=f"Made {settings.achievement_night_owl_threshold}+ commits between 10pm-6am",
            frequency="daily",
            threshold=settings.achievement_night_owl_threshold,
            category="timing",
        ),
        "early_bird": Achievement(
            id="early_bird",
            name="Early Bird",
            emoji="🐦",
            description=f"Made {settings.achievement_early_bird_threshold}+ commits between 5am-9am",
            frequency="daily",
            threshold=settings.achievement_early_bird_threshold,
            category="timing",
        ),
        "daily_dozen": Achievement(
            id="daily_dozen",
            name="Daily Dozen",
            emoji="🔥",
            description=f"Made {settings.achievement_daily_dozen_threshold}+ commits in a single day",
            frequency="daily",
            threshold=settings.achievement_daily_dozen_threshold,
            category="productivity",
        ),
        "streak_keeper": Achievement(
            id="streak_keeper",
            name="Streak Keeper",
            emoji="⚡",
            description="Maintained an active daily commit streak",
            frequency="daily",
            threshold=1,
            category="consistency",
        ),
        "commit_poet": Achievement(
            id="commit_poet",
            name="Commit Poet",
            emoji="📝",
            description="Made a commit with a message longer than 100 characters",
            frequency="daily",
            threshold=1,
            category="quality",
        ),
        # Weekly achievements (repeatable)
        "weekend_warrior": Achievement(
            id="weekend_warrior",
            name="Weekend Warrior",
            emoji="⚔️",
            description=f"Made {settings.achievement_weekend_warrior_threshold}+ commits on a weekend",
            frequency="weekly",
            threshold=settings.achievement_weekend_warrior_threshold,
            category="timing",
        ),
        "weekday_grind": Achievement(
            id="weekday_grind",
            name="Weekday Grind",
            emoji="💼",
            description="Made commits every weekday (Mon-Fri)",
            frequency="weekly",
            threshold=5,
            category="consistency",
        ),
        "productive_week": Achievement(
            id="productive_week",
            name="Productive Week",
            emoji="📈",
            description="Made 25+ commits in a single week",
            frequency="weekly",
            threshold=25,
            category="productivity",
        ),
        # Monthly achievements (repeatable)
        "century_month": Achievement(
            id="century_month",
            name="Century Month",
            emoji="💯",
            description=f"Made {settings.achievement_century_month_threshold}+ commits in a month",
            frequency="monthly",
            threshold=settings.achievement_century_month_threshold,
            category="productivity",
        ),
        "pr_machine": Achievement(
            id="pr_machine",
            name="PR Machine",
            emoji="🔧",
            description="Opened 10+ pull requests in a month",
            frequency="monthly",
            threshold=10,
            category="productivity",
        ),
        "consistency_king": Achievement(
            id="consistency_king",
            name="Consistency King",
            emoji="👑",
            description="Made commits on 20+ different days in a month",
            frequency="monthly",
            threshold=20,
            category="consistency",
        ),
        # Milestone achievements (one-time per tier)
        "daily_fire_starter": Achievement(
            id="daily_fire_starter",
            name="Fire Starter",
            emoji="🔥",
            description="Reached a 7-day commit streak",
            frequency="milestone",
            threshold=7,
            category="streak",
        ),
        "daily_lightning": Achievement(
            id="daily_lightning",
            name="Lightning Bolt",
            emoji="⚡",
            description="Reached a 30-day commit streak",
            frequency="milestone",
            threshold=30,
            category="streak",
        ),
        "daily_diamond": Achievement(
            id="daily_diamond",
            name="Diamond Streak",
            emoji="💎",
            description="Reached a 100-day commit streak",
            frequency="milestone",
            threshold=100,
            category="streak",
        ),
        "daily_legend": Achievement(
            id="daily_legend",
            name="Legendary",
            emoji="🏆",
            description="Reached a 365-day commit streak",
            frequency="milestone",
            threshold=365,
            category="streak",
        ),
        "weekly_consistent": Achievement(
            id="weekly_consistent",
            name="Weekly Consistency",
            emoji="📅",
            description="Reached a 4-week commit streak",
            frequency="milestone",
            threshold=4,
            category="streak",
        ),
        "weekly_quarter": Achievement(
            id="weekly_quarter",
            name="Quarter Streak",
            emoji="📆",
            description="Reached a 13-week commit streak",
            frequency="milestone",
            threshold=13,
            category="streak",
        ),
        "monthly_tri": Achievement(
            id="monthly_tri",
            name="Tri-Monthly",
            emoji="🗓️",
            description="Reached a 3-month commit streak",
            frequency="milestone",
            threshold=3,
            category="streak",
        ),
        "monthly_half": Achievement(
            id="monthly_half",
            name="Half Year",
            emoji="📊",
            description="Reached a 6-month commit streak",
            frequency="milestone",
            threshold=6,
            category="streak",
        ),
        "monthly_annual": Achievement(
            id="monthly_annual",
            name="Annual Achiever",
            emoji="🎯",
            description="Reached a 12-month commit streak",
            frequency="milestone",
            threshold=12,
            category="streak",
        ),
        "century_club": Achievement(
            id="century_club",
            name="Century Club",
            emoji="💯",
            description="Reached 100 total commits",
            frequency="milestone",
            threshold=100,
            category="total",
        ),
        "sharpshooter": Achievement(
            id="sharpshooter",
            name="Sharpshooter",
            emoji="🎯",
            description="Reached 500 total commits",
            frequency="milestone",
            threshold=500,
            category="total",
        ),
        "rocket_ship": Achievement(
            id="rocket_ship",
            name="Rocket Ship",
            emoji="🚀",
            description="Reached 1000 total commits",
            frequency="milestone",
            threshold=1000,
            category="total",
        ),
    }

    return achievements
