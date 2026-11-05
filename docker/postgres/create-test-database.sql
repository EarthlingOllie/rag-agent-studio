-- Runs once, when the Postgres volume is first initialised.
-- The backend test suite uses its own database so migration round trips never touch dev data.
CREATE DATABASE studio_test OWNER studio;
