

-- Synthea core tables (PostgreSQL)
-- patients, encounters, conditions, medications, observations


DROP TABLE IF EXISTS observations CASCADE;
DROP TABLE IF EXISTS medications CASCADE;
DROP TABLE IF EXISTS conditions CASCADE;
DROP TABLE IF EXISTS encounters CASCADE;
DROP TABLE IF EXISTS patients CASCADE;

-- ===========
-- PATIENTS
-- ===========
CREATE TABLE patients (
  id                   TEXT PRIMARY KEY,
  birthdate            DATE,
  deathdate            DATE,
  ssn                  TEXT,
  drivers              TEXT,
  passport             TEXT,
  prefix               TEXT,
  first                TEXT,
  middle               TEXT,
  last                 TEXT,
  suffix               TEXT,
  maiden               TEXT,
  marital              TEXT,
  race                 TEXT,
  ethnicity            TEXT,
  gender               TEXT,
  birthplace           TEXT,
  address              TEXT,
  city                 TEXT,
  state                TEXT,
  county               TEXT,
  fips                 TEXT,
  zip                  TEXT,
  lat                  DOUBLE PRECISION,
  lon                  DOUBLE PRECISION,
  healthcare_expenses  NUMERIC(14,2),
  healthcare_coverage  NUMERIC(14,2),
  income               NUMERIC(14,2)
);

-- ===========
-- ENCOUNTERS
-- ===========
CREATE TABLE encounters (
  id                    TEXT PRIMARY KEY,
  start                 TIMESTAMP WITHOUT TIME ZONE,
  "stop"                TIMESTAMP WITHOUT TIME ZONE,
  patient               TEXT REFERENCES patients(id),           -- FK → patients.id
  organization          TEXT,
  provider              TEXT,
  payer                 TEXT,
  encounterclass        TEXT,
  code                  TEXT,
  description           TEXT,
  base_encounter_cost   NUMERIC(14,2),
  total_claim_cost      NUMERIC(14,2),
  payer_coverage        NUMERIC(14,2),
  reasoncode            TEXT,
  reasondescription     TEXT
);

-- ===========
-- CONDITIONS
-- ===========
-- Il CSV di Synthea non ha "Id" per conditions: creiamo PK surrogata
CREATE TABLE conditions (
  id            SERIAL PRIMARY KEY,
  start         TIMESTAMP WITHOUT TIME ZONE,
  "stop"        TIMESTAMP WITHOUT TIME ZONE,
  patient       TEXT REFERENCES patients(id),
  encounter     TEXT REFERENCES encounters(id),                     -- FK → encounters.id
  system        TEXT,
  code          TEXT,
  description   TEXT
);

-- ===========
-- MEDICATIONS
-- ===========
-- Anche qui normalmente non c'è "Id" nel CSV: PK surrogata
CREATE TABLE medications (
  id            SERIAL PRIMARY KEY,           -- surrogata
  start         TIMESTAMP WITHOUT TIME ZONE,
  "stop"        TIMESTAMP WITHOUT TIME ZONE,
  patient       TEXT REFERENCES patients(id),
  payer         TEXT,
  encounter     TEXT REFERENCES encounters(id),                          -- FK → encounters.id
  code          TEXT,
  description   TEXT,
  base_cost     NUMERIC(14,2),
  payer_coverage NUMERIC(14,2),
  dispenses INTEGER,
  totalcost NUMERIC(14,2),
  reasoncode TEXT,
  reasondescription TEXT
);

-- ===========
-- OBSERVATIONS
-- ===========
-- Anche qui creiamo PK surrogata
CREATE TABLE observations (
  id            BIGSERIAL PRIMARY KEY,           -- surrogata
  "date"        TIMESTAMP WITHOUT TIME ZONE,
  patient       TEXT REFERENCES patients(id),
  encounter     TEXT REFERENCES encounters(id),                    -- FK → encounters.id
  category      TEXT,
  code          TEXT,
  description   TEXT,
  value         TEXT,
  units         TEXT,
  "type"        TEXT
);


-- =========================
-- Indici utili alle query
-- =========================
CREATE INDEX IF NOT EXISTS idx_encounters_patient
  ON encounters (patient);

CREATE INDEX IF NOT EXISTS idx_conditions_patient
  ON conditions (patient);
CREATE INDEX IF NOT EXISTS idx_conditions_code
  ON conditions (code);

CREATE INDEX IF NOT EXISTS idx_medications_patient
  ON medications (patient);

CREATE INDEX IF NOT EXISTS idx_observations_patient
  ON observations (patient);
CREATE INDEX IF NOT EXISTS idx_observations_code_date
  ON observations (code, "date");

-- (Facoltativi)
CREATE INDEX IF NOT EXISTS idx_encounters_start
  ON encounters (start);
CREATE INDEX IF NOT EXISTS idx_observations_encounter
  ON observations (encounter);

