-- Runs once, when the Docker Postgres volume is first created: the API tests
-- drop and rebuild the schema of slate_test, so they get their own database.
CREATE DATABASE slate_test OWNER slate;
