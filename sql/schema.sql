-- PostgreSQL table structure for loading the supplied CSV files.
CREATE TABLE IF NOT EXISTS pokazaniya (
    anon_id text NOT NULL,
    data date NOT NULL,
    pokazanie numeric NOT NULL,
    paketov_za_sutki integer NOT NULL
);

CREATE TABLE IF NOT EXISTS pribory (
    anon_id text PRIMARY KEY,
    bs text,
    tip text,
    model text,
    mesyac_vypuska text
);

CREATE TABLE IF NOT EXISTS sobytiya (
    anon_id text NOT NULL,
    data date NOT NULL,
    sobytie text NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_pokazaniya_id_date ON pokazaniya (anon_id, data);
CREATE INDEX IF NOT EXISTS ix_sobytiya_id_date ON sobytiya (anon_id, data);
