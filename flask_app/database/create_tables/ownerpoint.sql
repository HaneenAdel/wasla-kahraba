
CREATE TABLE IF NOT EXISTS ownerpoint (
    owner_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,  
    owner_key   TEXT NOT NULL UNIQUE,
    contact     TEXT
);