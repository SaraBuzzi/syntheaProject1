
CREATE SCHEMA IF NOT EXISTS owner;
CREATE SCHEMA IF NOT EXISTS server;

-- OWNER
CREATE TABLE IF NOT EXISTS owner.patients_owner (
  id                  TEXT PRIMARY KEY,
  deathdate           DATE,
  ssn                 TEXT,
  drivers             TEXT,
  passport            TEXT,
  prefix              TEXT,
  first               TEXT,
  middle              TEXT,
  last                TEXT,
  suffix              TEXT,
  maiden              TEXT,
  birthplace          TEXT,
  address             TEXT,
  city                TEXT,
  state               TEXT,
  county              TEXT,
  fips                TEXT,
  zip                 TEXT,
  lat                 DOUBLE PRECISION,
  lon                 DOUBLE PRECISION,
  healthcare_expenses NUMERIC(14,2),
  healthcare_coverage NUMERIC(14,2),
  income              NUMERIC(14,2)
);

INSERT INTO owner.patients_owner (
  id, deathdate, ssn, drivers, passport, prefix, first, middle, last, suffix, maiden,
  birthplace, address, city, state, county, fips, zip, lat, lon,
  healthcare_expenses, healthcare_coverage, income
)
SELECT
  id, deathdate, ssn, drivers, passport, prefix, first, middle, last, suffix, maiden,
  birthplace, address, city, state, county, fips, zip, lat, lon,
  healthcare_expenses, healthcare_coverage, income
FROM public.patients
ON CONFLICT (id) DO UPDATE SET
  deathdate=EXCLUDED.deathdate, ssn=EXCLUDED.ssn, drivers=EXCLUDED.drivers, passport=EXCLUDED.passport,
  prefix=EXCLUDED.prefix, first=EXCLUDED.first, middle=EXCLUDED.middle, last=EXCLUDED.last, suffix=EXCLUDED.suffix,
  maiden=EXCLUDED.maiden, birthplace=EXCLUDED.birthplace, address=EXCLUDED.address, city=EXCLUDED.city,
  state=EXCLUDED.state, county=EXCLUDED.county, fips=EXCLUDED.fips, zip=EXCLUDED.zip, lat=EXCLUDED.lat, lon=EXCLUDED.lon,
  healthcare_expenses=EXCLUDED.healthcare_expenses, healthcare_coverage=EXCLUDED.healthcare_coverage,
  income=EXCLUDED.income;


-- SERVER
CREATE TABLE IF NOT EXISTS server.patients_server (
  id        TEXT PRIMARY KEY,
  birthdate DATE,
  gender    TEXT,
  race      TEXT,
  ethnicity TEXT,
  marital   TEXT,
  CONSTRAINT fk_pat_owner
    FOREIGN KEY (id) REFERENCES owner.patients_owner(id)
    ON DELETE CASCADE
);

INSERT INTO server.patients_server (
  id, birthdate, gender, race, ethnicity, marital
)
SELECT
  id, birthdate, gender, race, ethnicity, marital
FROM public.patients
ON CONFLICT (id) DO UPDATE SET
    birthdate=EXCLUDED.birthdate, gender=EXCLUDED.gender, race=EXCLUDED.race,
    ethnicity=EXCLUDED.ethnicity, marital=EXCLUDED.marital;

CREATE OR REPLACE VIEW public.patients_v AS
SELECT
  o.id,
  -- OWNER
  o.deathdate, o.ssn, o.drivers, o.passport, o.prefix, o.first, o.middle, o.last,
  o.suffix, o.maiden, o.birthplace, o.address, o.city, o.state, o.county, o.fips,
  o.zip, o.lat, o.lon, o.healthcare_expenses, o.healthcare_coverage, o.income,
  -- SERVER
  s.birthdate, s.gender, s.race, s.ethnicity, s.marital
FROM owner.patients_owner o
JOIN server.patients_server s USING (id);

CREATE INDEX IF NOT EXISTS idx_owner_state  ON owner.patients_owner(state);
CREATE INDEX IF NOT EXISTS idx_server_gender ON server.patients_server(gender);


ANALYZE owner.patients_owner;
ANALYZE server.patients_server;
