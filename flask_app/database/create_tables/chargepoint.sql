
CREATE TABLE IF NOT EXISTS chargepoint (
    chargepoint_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    chargepoint_name           TEXT    NOT NULL,    
    description    TEXT    NOT NULL,   
    hyperlink      TEXT,                
    start_date     TEXT,            
    end_date       TEXT,                
    embedding TEXT DEFAULT NULL,
    FOREIGN KEY (owner_id) REFERENCES ownerpoint(owner_id)
);
