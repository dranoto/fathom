# app/database/migrations.py
import logging
from sqlalchemy import inspect
from sqlalchemy.sql import text

from .models import engine, Base

logger = logging.getLogger(__name__)


def create_db_and_tables():
    print("DATABASE: Attempting to create database tables...")
    try:
        Base.metadata.create_all(bind=engine)
        print("DATABASE: Database tables checked/created successfully.")

        inspector = inspect(engine)
        migration_user_id = None

        with engine.connect() as connection:
            with connection.begin():
                if inspector.has_table("users"):
                    result = connection.execute(text('SELECT id FROM users LIMIT 1'))
                    row = result.fetchone()
                    if row:
                        migration_user_id = row[0]
                        print(f"DATABASE: Found existing user with id={migration_user_id} for migration")
                
                if not migration_user_id:
                    if inspector.has_table("users"):
                        result = connection.execute(text('SELECT COUNT(*) FROM users'))
                        count = result.fetchone()[0]
                        if count > 0:
                            result = connection.execute(text('SELECT id FROM users LIMIT 1'))
                            migration_user_id = result.fetchone()[0]
                        else:
                            connection.execute(text("INSERT INTO users (email, password_hash) VALUES ('system@migration', 'placeholder')"))
                            result = connection.execute(text('SELECT last_insert_rowid()'))
                            migration_user_id = result.fetchone()[0]
                            print(f"DATABASE: Created migration user with id={migration_user_id}")
                    else:
                        connection.execute(text("INSERT INTO users (email, password_hash) VALUES ('system@migration', 'placeholder')"))
                        result = connection.execute(text('SELECT last_insert_rowid()'))
                        migration_user_id = result.fetchone()[0]
                        print(f"DATABASE: Created migration user with id={migration_user_id}")

                migration_checks = [
                    ('summaries', 'user_id', 'INTEGER'),
                    ('chat_history', 'user_id', 'INTEGER'),
                    ('article_tag_association', 'user_id', 'INTEGER'),
                    ('tags', 'user_id', 'INTEGER'),
                ]

                if inspector.has_table("tags"):
                    columns = inspector.get_columns("tags")
                    column_names = {c['name'] for c in columns}
                    if 'normalized_name' not in column_names:
                        try:
                            connection.execute(text('ALTER TABLE tags ADD COLUMN normalized_name VARCHAR'))
                            connection.execute(text("UPDATE tags SET normalized_name = LOWER(TRIM(name)) WHERE normalized_name IS NULL"))
                            print("DATABASE: Added column 'normalized_name' to 'tags' table.")
                        except Exception as e:
                            print(f"DATABASE: Could not add column 'normalized_name' to 'tags': {e}")

                for table_name, column_name, column_type in migration_checks:
                    if inspector.has_table(table_name):
                        columns = inspector.get_columns(table_name)
                        column_names = {c['name'] for c in columns}
                        if column_name not in column_names:
                            try:
                                connection.execute(text(f'ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}'))
                                print(f"DATABASE: Added column '{column_name}' to '{table_name}' table.")
                                if migration_user_id:
                                    connection.execute(text(f'UPDATE {table_name} SET {column_name} = {migration_user_id} WHERE {column_name} IS NULL'))
                                    print(f"DATABASE: Set default user_id={migration_user_id} for existing rows in '{table_name}'")
                            except Exception as e:
                                print(f"DATABASE: Could not add column '{column_name}' to '{table_name}': {e}")

                if inspector.has_table("article_tag_association"):
                    table_result = connection.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='article_tag_association'"))
                    table_row = table_result.fetchone()
                    if table_row and 'user_id,' not in table_row[0] and ', user_id' not in table_row[0]:
                        print("DATABASE: Fixing article_tag_association primary key to include user_id...")
                        try:
                            if migration_user_id:
                                connection.execute(text(f"UPDATE article_tag_association SET user_id = {migration_user_id} WHERE user_id IS NULL"))
                            else:
                                connection.execute(text("UPDATE article_tag_association SET user_id = 1 WHERE user_id IS NULL"))
                            connection.execute(text("DROP TABLE IF EXISTS article_tag_association_new"))
                            connection.execute(text("""
                                CREATE TABLE article_tag_association_new (
                                    user_id INTEGER NOT NULL,
                                    article_id INTEGER NOT NULL,
                                    tag_id INTEGER NOT NULL,
                                    PRIMARY KEY (user_id, article_id, tag_id),
                                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                                    FOREIGN KEY(article_id) REFERENCES articles(id) ON DELETE CASCADE,
                                    FOREIGN KEY(tag_id) REFERENCES tags(id) ON DELETE CASCADE
                                )
                            """))
                            connection.execute(text("""
                                INSERT INTO article_tag_association_new (user_id, article_id, tag_id)
                                SELECT user_id, article_id, tag_id FROM article_tag_association
                            """))
                            connection.execute(text("DROP TABLE article_tag_association"))
                            connection.execute(text("ALTER TABLE article_tag_association_new RENAME TO article_tag_association"))
                            print("DATABASE: article_tag_association primary key fixed.")
                        except Exception as e:
                            print(f"DATABASE: Error fixing article_tag_association PK: {e}")

                if inspector.has_table("user_rss_feeds") and inspector.has_table("rss_feed_sources"):
                    print("DATABASE: Migrating feed tables to new schema...")
                    try:
                        result = connection.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='rss_feed_sources'"))
                        old_rss_row = result.fetchone()
                        
                        if old_rss_row and 'feed_sources' not in old_rss_row[0]:
                            print("DATABASE: Renaming rss_feed_sources to feed_sources...")
                            connection.execute(text("DROP TABLE IF EXISTS feed_sources"))
                            connection.execute(text("ALTER TABLE rss_feed_sources RENAME TO feed_sources"))
                            print("DATABASE: rss_feed_sources renamed to feed_sources")

                        result = connection.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='user_rss_feeds'"))
                        old_user_row = result.fetchone()
                        
                        if old_user_row and 'feed_source_id' not in old_user_row[0]:
                            print("DATABASE: Migrating user_rss_feeds to user_feed_subscriptions...")
                            
                            connection.execute(text("DROP TABLE IF EXISTS user_feed_subscriptions"))
                            connection.execute(text("""
                                CREATE TABLE user_feed_subscriptions (
                                    id INTEGER NOT NULL,
                                    user_id INTEGER NOT NULL,
                                    feed_source_id INTEGER NOT NULL,
                                    custom_name VARCHAR,
                                    subscribed_at DATETIME,
                                    PRIMARY KEY (id),
                                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                                    FOREIGN KEY(feed_source_id) REFERENCES feed_sources(id) ON DELETE CASCADE,
                                    UNIQUE(user_id, feed_source_id)
                                )
                            """))
                            
                            connection.execute(text("""
                                INSERT INTO user_feed_subscriptions (id, user_id, feed_source_id, subscribed_at)
                                SELECT u.id, u.user_id, f.id, u.created_at
                                FROM user_rss_feeds u
                                JOIN feed_sources f ON u.url = f.url
                            """))
                            
                            connection.execute(text("DROP TABLE user_rss_feeds"))
                            print("DATABASE: user_rss_feeds migrated to user_feed_subscriptions")

                    except Exception as e:
                        print(f"DATABASE: Error migrating feed tables: {e}")

                if inspector.has_table("articles") and inspector.has_table("user_article_states"):
                    articles = connection.execute(text('SELECT id, is_favorite, is_read, is_deleted, deleted_at FROM articles WHERE is_favorite = 1 OR is_read = 1 OR is_deleted = 1')).fetchall()
                    if articles and migration_user_id:
                        for art_id, is_fav, is_read, is_del, del_at in articles:
                            try:
                                connection.execute(
                                    text("INSERT OR IGNORE INTO user_article_states (user_id, article_id, is_read, is_favorite, is_deleted, deleted_at) VALUES (:uid, :aid, :iread, :ifav, :idel, :delat)"),
                                    {"uid": migration_user_id, "aid": art_id, "iread": is_read, "ifav": is_fav, "idel": is_del, "delat": del_at}
                                )
                            except Exception as e:
                                print(f"DATABASE: Could not migrate article state for article {art_id}: {e}")
                        print(f"DATABASE: Migrated {len(articles)} article states to user_article_states for migration user")

                if inspector.has_table("articles") and inspector.has_table("feed_sources"):
                    result = connection.execute(text("""
                        SELECT COUNT(*) FROM articles 
                        WHERE feed_source_id NOT IN (SELECT id FROM feed_sources)
                    """)).fetchone()
                    orphaned_count = result[0] if result else 0
                    if orphaned_count > 0:
                        connection.execute(text("""
                            UPDATE articles 
                            SET feed_source_id = (SELECT id FROM feed_sources ORDER BY id LIMIT 1)
                            WHERE feed_source_id NOT IN (SELECT id FROM feed_sources)
                        """))
                        print(f"DATABASE: Fixed {orphaned_count} articles with orphaned feed_source_id references")

        print("DATABASE: Migration completed successfully.")

    except Exception as e:
        print(f"DATABASE: Error during database setup: {e}")
        raise


if __name__ == "__main__":
    print("DATABASE: Running database setup directly.")
    create_db_and_tables()