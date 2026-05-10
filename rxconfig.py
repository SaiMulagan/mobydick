import reflex as rx

config = rx.Config(
    app_name="moby",
    # SQLite locally (file lives at repo root); swap for a Cloud SQL URL
    # like "postgresql+psycopg://user:pass@host:5432/moby" when deploying.
    db_url="sqlite:///reflex.db",
    plugins=[
        rx.plugins.SitemapPlugin(),
        rx.plugins.TailwindV4Plugin(),
    ]
)