from setuptools import setup


setup(
    name="daily-briefing-bot",
    version="0.1.0",
    description="AI-powered daily briefing reports for social, news, and creator-community sources.",
    packages=["daily_briefing"],
    install_requires=["Pillow>=10.0"],
    entry_points={"console_scripts": ["daily-briefing=daily_briefing.cli:main"]},
    python_requires=">=3.9",
)
