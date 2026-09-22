
CREATE TABLE IF NOT EXISTS chargepoint (
    chargepoint_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL,
    chargepoint_name           TEXT    NOT NULL,  
    area TEXT NOT NULL,
    service_type TEXT NOT NULL,  
    description    TEXT    NOT NULL,   
    opening_hours TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'available',
    capacity INTEGER DEFAULT 1,
    waiting_count INTEGER DEFAULT 0,
    last_update TEXT,
    embedding TEXT DEFAULT NULL,
    FOREIGN KEY (owner_id) REFERENCES ownerpoint(owner_id)
);



